"""Structured failures shared by all pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FailureCode(StrEnum):
    INPUT_INVALID_JSON = "INPUT_INVALID_JSON"
    INPUT_FILE_UNAVAILABLE = "INPUT_FILE_UNAVAILABLE"
    INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
    OUTPUT_DIRECTORY_UNAVAILABLE = "OUTPUT_DIRECTORY_UNAVAILABLE"
    SOURCE_ACQUISITION_FAILED = "SOURCE_ACQUISITION_FAILED"
    PARSE_FAILED = "PARSE_FAILED"
    PARSE_TABLE_FAILED = "PARSE_TABLE_FAILED"
    RETRIEVAL_FAILED = "RETRIEVAL_FAILED"
    RETRIEVAL_INSUFFICIENT_EVIDENCE = "RETRIEVAL_INSUFFICIENT_EVIDENCE"
    EVIDENCE_PACK_INVALID = "EVIDENCE_PACK_INVALID"
    MODEL_REQUEST_FAILED = "MODEL_REQUEST_FAILED"
    IR_INVALID = "IR_INVALID"
    GROUNDING_UNSUPPORTED = "GROUNDING_UNSUPPORTED"
    COMPUTATION_INVALID = "COMPUTATION_INVALID"
    RENDER_FAILED = "RENDER_FAILED"
    ARTIFACT_INVALID = "ARTIFACT_INVALID"
    BROWSER_VALIDATION_FAILED = "BROWSER_VALIDATION_FAILED"
    BROWSER_VALIDATION_UNAVAILABLE = "BROWSER_VALIDATION_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    FINALIZE_FAILED = "FINALIZE_FAILED"
    PIPELINE_NOT_IMPLEMENTED = "PIPELINE_NOT_IMPLEMENTED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


class FailureSeverity(StrEnum):
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class Failure:
    code: FailureCode
    stage: str
    severity: FailureSeverity
    recoverable: bool
    message: str
    target: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code.value,
            "stage": self.stage,
            "severity": self.severity.value,
            "recoverable": self.recoverable,
            "message": self.message,
        }
        if self.target is not None:
            result["target"] = self.target
        if self.details:
            result["details"] = self.details
        return result


class PlaygroundError(Exception):
    """Expected application error carrying its structured failure."""

    def __init__(self, failure: Failure) -> None:
        super().__init__(failure.message)
        self.failure = failure
