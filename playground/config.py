"""Run configuration and the exact external case-input contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError

SOURCE_TIMEOUT_SECONDS = 30
MODEL_TIMEOUT_SECONDS = 90
MAX_TRANSIENT_RETRIES = 1
MAX_EVIDENCE_CHUNKS = 12
MAX_EVIDENCE_TOKENS = 8_000
MAX_NEIGHBOR_EXPANSIONS = 1
BROWSER_TIMEOUT_SECONDS = 30
FINALIZATION_RESERVE_SECONDS = 30
NUMERIC_TOLERANCE = 1e-8
MAX_MODEL_CALLS = 10
MAX_COMPLETION_TOKENS = 30_000
MAX_RUN_SECONDS = 600

CASE_FIELDS = frozenset({"source_url", "focus", "audience"})


@dataclass(frozen=True, slots=True)
class CaseInput:
    """The only three case fields accepted by the public interface."""

    source_url: str
    focus: str
    audience: str

    def __post_init__(self) -> None:
        for field_name in ("source_url", "focus", "audience"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must be a string")
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

    @classmethod
    def from_mapping(cls, data: Any) -> CaseInput:
        if not isinstance(data, dict):
            raise PlaygroundError(
                Failure(
                    code=FailureCode.INPUT_SCHEMA_INVALID,
                    stage="startup_validation",
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message="Case input must be a JSON object with exactly source_url, focus, and audience.",
                )
            )

        missing = sorted(CASE_FIELDS - data.keys())
        extra = sorted(data.keys() - CASE_FIELDS)
        if missing or extra:
            details: dict[str, Any] = {}
            if missing:
                details["missing_fields"] = missing
            if extra:
                details["unexpected_fields"] = extra
            raise PlaygroundError(
                Failure(
                    code=FailureCode.INPUT_SCHEMA_INVALID,
                    stage="startup_validation",
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message="Case input must contain exactly source_url, focus, and audience.",
                    details=details,
                )
            )

        try:
            return cls(
                source_url=data["source_url"],
                focus=data["focus"],
                audience=data["audience"],
            )
        except ValueError as exc:
            raise PlaygroundError(
                Failure(
                    code=FailureCode.INPUT_SCHEMA_INVALID,
                    stage="startup_validation",
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message=str(exc),
                )
            ) from exc

    @classmethod
    def from_json_file(cls, path: str | Path) -> CaseInput:
        try:
            with Path(path).open("r", encoding="utf-8") as case_file:
                data = json.load(case_file)
        except json.JSONDecodeError as exc:
            raise PlaygroundError(
                Failure(
                    code=FailureCode.INPUT_INVALID_JSON,
                    stage="startup_validation",
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message=f"Case input is not valid JSON (line {exc.lineno}, column {exc.colno}).",
                )
            ) from exc
        except OSError as exc:
            raise PlaygroundError(
                Failure(
                    code=FailureCode.INPUT_FILE_UNAVAILABLE,
                    stage="startup_validation",
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message=f"Cannot read case input file: {Path(path)}.",
                )
            ) from exc
        return cls.from_mapping(data)


@dataclass(frozen=True, slots=True)
class RunConfig:
    """Validated public run arguments; model IDs are passed through unchanged."""

    input_path: Path
    output_path: Path
    model_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("--model must be a non-empty model identifier")
        object.__setattr__(self, "input_path", Path(self.input_path))
        object.__setattr__(self, "output_path", Path(self.output_path))
