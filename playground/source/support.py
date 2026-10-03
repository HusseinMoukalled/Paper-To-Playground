"""Sanitized diagnostics and shared deterministic stage helpers."""

from playground.budget import RunBudget
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError


def fail(code: FailureCode, stage: str, message: str, *, recoverable: bool = False) -> None:
    raise PlaygroundError(Failure(code, stage, FailureSeverity.MAJOR, recoverable, message))


def check_budget(budget: RunBudget | None) -> None:
    if budget is not None and not budget.optional_work_allowed:
        fail(FailureCode.BUDGET_EXCEEDED, "source", "Source work cannot consume the finalization reserve.")
