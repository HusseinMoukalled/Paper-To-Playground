import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import threading
import time

from playground.model.client import OpenRouterClient
from playground.budget import RunBudget
from playground.failures import PlaygroundError
from playground.trace import TraceWriter

TEST_KEY = "synthetic-test-credential-not-real"


def response(content='{"ok":true}', usage=True):
    result = {"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}
    if usage:
        result["usage"] = {"prompt_tokens": 20, "completion_tokens": 10}
    return result


class ClientTests(unittest.TestCase):
    def client(self, transport, budget=None, trace=None):
        return OpenRouterClient("supplied/model-id-UNCHANGED", budget or RunBudget(), trace, transport=transport)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_model_key_and_usage(self):
        seen = []
        client = self.client(lambda payload, headers, timeout: seen.append((payload, headers, timeout)) or response())
        client.complete([{"role": "user", "content": "test"}])
        self.assertEqual(seen[0][0]["model"], "supplied/model-id-UNCHANGED")
        self.assertEqual(seen[0][1]["Authorization"], "Bearer " + TEST_KEY)
        self.assertEqual(client.budget.calls_used, 1)
        self.assertEqual(client.budget.completion_tokens, 10)
        self.assertEqual(client.budget.prompt_tokens, 20)
        self.assertLessEqual(seen[0][2], 90)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_key_clean_failure(self):
        client = self.client(lambda *_: self.fail("No call without key"))
        with self.assertRaises(PlaygroundError) as captured:
            client.complete([])
        self.assertEqual(captured.exception.failure.code.value, "MODEL_REQUEST_FAILED")
        self.assertEqual(client.budget.calls_used, 0)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_key_never_logged_or_echoed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            with TraceWriter(path) as trace:
                client = self.client(lambda *_: response(TEST_KEY), trace=trace)
                self.assertNotIn(TEST_KEY, client.complete([]))
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertNotIn(TEST_KEY, path.read_text())
            self.assertTrue(all(events[i]["elapsed_seconds"] <= events[i + 1]["elapsed_seconds"] for i in range(len(events) - 1)))

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_timeout_429_and_5xx_retry_counted(self):
        for problem in (TimeoutError(TEST_KEY), urllib.error.HTTPError("https://example.invalid", 429, TEST_KEY, {}, None),
                        urllib.error.HTTPError("https://example.invalid", 503, TEST_KEY, {}, None)):
            calls = []
            def transport(*_):
                calls.append(1)
                if len(calls) == 1:
                    raise problem
                return response()
            client = self.client(transport)
            client.complete([], max_tokens=100)
            self.assertEqual(client.budget.calls_used, 2)
            self.assertEqual(client.budget.completion_tokens, 110)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_retry_limit_and_sanitized_errors(self):
        def transport(*_):
            raise TimeoutError(TEST_KEY)
        client = self.client(transport)
        with self.assertRaises(PlaygroundError) as captured:
            client.complete([], max_tokens=100)
        self.assertNotIn(TEST_KEY, str(captured.exception))
        self.assertEqual(client.budget.calls_used, 2)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_budget_prevents_11th_call_and_optional_window(self):
        budget = RunBudget(calls_used=9)
        client = self.client(lambda *_: response(), budget)
        client.complete([])
        with self.assertRaises(PlaygroundError):
            client.complete([])
        self.assertEqual(budget.calls_used, 10)
        budget = RunBudget(max_runtime_seconds=1, finalization_reserve_seconds=0.9)
        budget.start_time -= 0.2
        with self.assertRaises(PlaygroundError):
            self.client(lambda *_: self.fail("No time"), budget).complete([], optional=True)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_missing_usage_conservative_and_malformed_response(self):
        client = self.client(lambda *_: response(usage=False))
        client.complete([], max_tokens=100)
        self.assertEqual(client.budget.completion_tokens, 100)
        for content in ({}, {"choices": []}, response(content=""), {"choices": [{"message": {"content": None}}]}):
            with self.assertRaises(PlaygroundError):
                self.client(lambda *_: content).complete([])

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_token_pressure(self):
        seen = []
        budget = RunBudget(completion_tokens=29995)
        client = self.client(lambda payload, *_: seen.append(payload) or response(), budget)
        with self.assertRaises(PlaygroundError):
            client.complete([], max_tokens=100)
        self.assertEqual(seen[0]["max_tokens"], 5)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_nontransient_failure_no_retry(self):
        def transport(*_):
            raise urllib.error.HTTPError("https://example.invalid", 401, TEST_KEY, {}, None)
        client = self.client(transport)
        with self.assertRaises(PlaygroundError):
            client.complete([])
        self.assertEqual(client.budget.calls_used, 1)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_all_transport_failures_reserve_unknown_completion_usage(self):
        for problem in (ValueError(TEST_KEY), RuntimeError(TEST_KEY)):
            def transport(*_):
                raise problem
            client = self.client(transport)
            with self.assertRaises(PlaygroundError) as captured:
                client.complete([], max_tokens=100)
            self.assertNotIn(TEST_KEY, str(captured.exception))
            self.assertEqual(client.budget.calls_used, 1)
            self.assertEqual(client.budget.completion_tokens, 100)

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
    def test_transport_total_wall_timeout_is_enforced(self):
        def delayed(*_):
            threading.Event().wait(0.15)
            return response()
        client = self.client(delayed)
        with patch("playground.model.client.MODEL_TIMEOUT_SECONDS", 0.01):
            started = time.monotonic()
            with self.assertRaises(PlaygroundError):
                client.complete([], max_tokens=100)
            self.assertLess(time.monotonic() - started, 0.1)
        self.assertEqual(client.budget.calls_used, 2)
        self.assertEqual(client.budget.completion_tokens, 200)
