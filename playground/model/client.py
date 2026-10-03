"""The sole model transport: unchanged supplied model, env-only key, bounded retries."""
from __future__ import annotations

import json
import os
import socket
import queue
import threading
import urllib.request
import urllib.error

from playground.budget import RunBudget
from playground.config import MODEL_TIMEOUT_SECONDS, MAX_TRANSIENT_RETRIES
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MAX_RESPONSE_BYTES = 1_000_000


def http_transport(payload, headers, timeout):
    request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    # No redirects: Authorization must never be forwarded to another host.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, hdrs, newurl):
            return None
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Oversized model response")
        return json.loads(raw)


def _bounded_transport(transport, payload, headers, timeout):
    """Bound TOTAL wall time, not just the socket's idle timeout.

    A daemon worker cannot delay finalization/process exit if a provider trickles
    bytes indefinitely. Late results never change budgets or emit traces. A timed
    out request remains counted and conservatively token-reserved by the caller.
    """
    channel = queue.Queue(maxsize=1)
    def work():
        try:
            channel.put((True, transport(payload, headers, timeout)))
        except Exception as error:
            channel.put((False, error))
    threading.Thread(target=work, name="bounded-model-transport", daemon=True).start()
    try:
        success, result = channel.get(timeout=timeout)
    except queue.Empty:
        raise TimeoutError("Model transport wall-time limit reached") from None
    if not success:
        raise result
    return result


class OpenRouterClient:
    def __init__(self, model_id: str, budget: RunBudget, trace=None, *, transport=None):
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("Supplied MODEL_ID is required")
        self.model_id, self.budget, self.trace = model_id, budget, trace
        self._transport = transport or http_transport

    def _event(self, action, result, **kwargs):
        if self.trace:
            self.trace.emit(stage="model", action=action, result=result, **kwargs)

    def _fail(self, reason, *, recoverable=False):
        self._event("request", "fail", details={"reason": reason})
        raise PlaygroundError(Failure(FailureCode.MODEL_REQUEST_FAILED, "model", FailureSeverity.MAJOR,
                                      recoverable, "Model request failed: " + reason)) from None

    def _reserve_unknown_usage(self, allocation, purpose):
        self.budget.completion_tokens += allocation
        self._event("usage", "warn", details={"purpose": purpose, "usage_known": False,
                                               "completion_budget_estimated": True})

    def complete(self, messages, *, max_tokens=6000, purpose="semantic", optional=False):
        if type(max_tokens) is not int or max_tokens <= 0:
            raise ValueError("Completion cap must be a positive integer")
        if purpose not in {"semantic", "science", "lesson", "semantic_verification", "semantic_repair", "retrieval_rerank"}:
            raise ValueError("Unknown model request purpose")
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key or not key.strip():
            self._fail("OPENROUTER_API_KEY is unavailable in the environment")
        # Do not transmit credentials echoed by hostile evidence or upstream metadata.
        if key in self.model_id:
            self._fail("MODEL_ID must not contain credentials")
        def redact(value):
            if isinstance(value, str):
                return value.replace(key, "[REDACTED]")
            if isinstance(value, list):
                return [redact(x) for x in value]
            if isinstance(value, dict):
                return {redact(k): redact(v) for k, v in value.items()}
            return value
        clean_messages = redact(messages)
        for attempt in range(MAX_TRANSIENT_RETRIES + 1):
            remaining_tokens = self.budget.max_completion_tokens - self.budget.completion_tokens
            allocation = min(max_tokens, remaining_tokens)
            if allocation <= 0:
                self.budget._raise_budget_failure("No completion tokens remain.")
            self.budget.authorize_model_call(completion_token_reservation=allocation, optional=optional)
            # Always reserve time for finalization, including required semantic calls.
            usable_seconds = self.budget.remaining_seconds - self.budget.finalization_reserve_seconds
            if usable_seconds <= 0:
                self.budget._raise_budget_failure("No model time remains before finalization.")
            timeout = min(MODEL_TIMEOUT_SECONDS, usable_seconds)
            payload = {"model": self.model_id, "messages": clean_messages, "max_tokens": allocation,
                       "temperature": 0, "response_format": {"type": "json_object"}}
            # Count attempts BEFORE transport, including timeout/HTTP failures.
            self.budget.record_model_call()
            self._event("request", "started", details={"purpose": purpose, "attempt": attempt + 1})
            try:
                response = _bounded_transport(self._transport, payload, {"Authorization": "Bearer " + key,
                                                                         "Content-Type": "application/json"}, timeout)
            except urllib.error.HTTPError as error:
                retry = error.code == 429 or 500 <= error.code <= 599
                reason = "HTTP " + str(error.code)
            except (TimeoutError, socket.timeout):
                retry, reason = True, "timeout"
            except urllib.error.URLError as error:
                retry, reason = True, "network error"
            except (ValueError, TypeError, OSError, RecursionError):
                self._reserve_unknown_usage(allocation, purpose)
                self._fail("invalid transport response")
            except Exception:
                self._reserve_unknown_usage(allocation, purpose)
                self._fail("unexpected transport failure")
            else:
                # Budget missing usage conservatively at the requested completion cap.
                usage = response.get("usage") if isinstance(response, dict) else None
                usage_known = isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0
                                                            for k in ("prompt_tokens", "completion_tokens"))
                prompt = usage["prompt_tokens"] if usage_known else 0
                completion = usage["completion_tokens"] if usage_known else allocation
                self.budget.prompt_tokens += prompt
                self.budget.completion_tokens += completion
                self._event("usage", "pass", details={"purpose": purpose, "usage_known": usage_known,
                                                       "completion_budget_estimated": not usage_known},
                            prompt_tokens=prompt if usage_known else None,
                            completion_tokens=completion if usage_known else None)
                if self.budget.completion_tokens > self.budget.max_completion_tokens:
                    self.budget._raise_budget_failure("Reported completion-token usage exceeds the budget.")
                if self.budget.remaining_seconds <= self.budget.finalization_reserve_seconds:
                    self.budget._raise_budget_failure("Model response reached the finalization window.")
                if isinstance(response, dict) and isinstance(response.get("model"), str) and response["model"] != self.model_id:
                    self._fail("provider returned a different model identity")
                try:
                    choice = response["choices"][0]
                    content = choice["message"]["content"]
                    if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > MAX_RESPONSE_BYTES:
                        raise ValueError
                    if choice.get("finish_reason") == "length":
                        self._fail("completion was truncated")
                    content = content.replace(key, "[REDACTED]")
                except (KeyError, IndexError, TypeError, ValueError):
                    self._fail("empty or malformed completion")
                self._event("request", "pass", details={"purpose": purpose})
                return content
            # Failed responses may have consumed tokens without usable usage information.
            self._reserve_unknown_usage(allocation, purpose)
            self._event("request", "retry" if retry and attempt < MAX_TRANSIENT_RETRIES else "fail",
                        details={"purpose": purpose, "reason": reason, "completion_budget_estimated": True})
            if not retry or attempt == MAX_TRANSIENT_RETRIES:
                self._fail(reason, recoverable=retry)
        raise AssertionError("Unreachable retry state")
