"""Centralized per-run limits and usage accounting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from playground.config import (
    FINALIZATION_RESERVE_SECONDS,
    MAX_COMPLETION_TOKENS,
    MAX_MODEL_CALLS,
    MAX_RUN_SECONDS,
)
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError


@dataclass(slots=True)
class RunBudget:
    """Tracks runtime, model calls, and completion-token usage for one case."""

    max_calls: int = MAX_MODEL_CALLS
    max_completion_tokens: int = MAX_COMPLETION_TOKENS
    max_runtime_seconds: float = MAX_RUN_SECONDS
    finalization_reserve_seconds: float = FINALIZATION_RESERVE_SECONDS
    start_time: float = field(default_factory=time.monotonic)
    calls_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def __post_init__(self) -> None:
        if self.max_calls < 0 or self.max_completion_tokens < 0:
            raise ValueError("Budget limits cannot be negative")
        if self.max_runtime_seconds <= 0:
            raise ValueError("max_runtime_seconds must be positive")
        if not 0 <= self.finalization_reserve_seconds < self.max_runtime_seconds:
            raise ValueError("finalization reserve must be within the run-time limit")

    @property
    def elapsed_seconds(self) -> float:
        return max(0.0, time.monotonic() - self.start_time)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.max_runtime_seconds - self.elapsed_seconds)

    @property
    def remaining_calls(self) -> int:
        return max(0, self.max_calls - self.calls_used)

    @property
    def total_tracked_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def optional_work_allowed(self) -> bool:
        return self.remaining_seconds > self.finalization_reserve_seconds

    def authorize_model_call(
        self,
        *,
        completion_token_reservation: int = 0,
        optional: bool = True,
    ) -> None:
        if completion_token_reservation < 0:
            raise ValueError("completion_token_reservation cannot be negative")
        if self.remaining_seconds <= 0:
            self._raise_budget_failure("The run-time budget is exhausted.")
        if optional and not self.optional_work_allowed:
            self._raise_budget_failure("Optional model work is denied in the finalization reserve.")
        if self.remaining_calls <= 0:
            self._raise_budget_failure("The model-call budget is exhausted.")
        if self.completion_tokens + completion_token_reservation > self.max_completion_tokens:
            self._raise_budget_failure("The completion-token budget would be exceeded.")

    def record_model_call(self, *, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("Token usage cannot be negative")
        self.calls_used += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        if self.calls_used > self.max_calls:
            self._raise_budget_failure("Recorded model calls exceed the call budget.")
        if self.completion_tokens > self.max_completion_tokens:
            self._raise_budget_failure("Recorded completion tokens exceed the token budget.")

    @staticmethod
    def _raise_budget_failure(message: str) -> None:
        raise PlaygroundError(
            Failure(
                code=FailureCode.BUDGET_EXCEEDED,
                stage="budget",
                severity=FailureSeverity.MAJOR,
                recoverable=False,
                message=message,
            )
        )
