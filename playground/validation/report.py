"""Shared structured validation findings and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ValidationStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    status: ValidationStatus
    code: str
    stage: str
    message: str
    target: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    status: ValidationStatus
    findings: tuple[ValidationFinding, ...] = ()
    stage: str = "validation"

    def __post_init__(self) -> None:
        if self.status is ValidationStatus.PASS and any(
            finding.status is ValidationStatus.FAIL for finding in self.findings
        ):
            raise ValueError("A passing report cannot contain failing findings")
