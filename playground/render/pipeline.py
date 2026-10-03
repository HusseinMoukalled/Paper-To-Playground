"""Staged artifact verification/promotion, for the orchestrator to call."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from playground.failures import PlaygroundError
from playground.ir.models import ExplanationIR
from playground.render.renderer import render_candidate
from playground.trace import TraceWriter
from playground.validation.artifact import report, validate_artifact
from playground.validation.browser import ReferenceEvaluator, validate_browser
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus


@dataclass(frozen=True)
class ArtifactResult:
    path: Path | None
    report: ValidationReport
    promoted: bool


def build_artifact(ir: ExplanationIR, output_directory: str | Path, *, asts: Mapping[str, dict] | None = None,
                   reference_evaluator: ReferenceEvaluator | None = None,
                   trace: TraceWriter | None = None, browser: object | None = None) -> ArtifactResult:
    """Only a freshly verified candidate replaces index.html; WARN permits fallback.

    No model repair, scientific rewriting, or global recovery decisions occur
    here. The orchestrator owns those decisions and supplies its trace writer.
    """
    output = Path(output_directory)
    findings: list[ValidationFinding] = []
    destination = output / 'index.html'

    def emit(stage, action, validation):
        if trace:
            trace.emit(stage=stage, action=action, result=validation.status.value.lower(),
                       details={'codes': [f.code for f in validation.findings]})

    try:
        output.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.playground-candidate-', dir=output) as staging:
            candidate = render_candidate(ir, staging, asts=asts)
            static = validate_artifact(candidate, ir, asts=asts)
            findings.extend(static.findings)
            emit('STATIC_VALIDATION', 'validate_candidate', static)
            if static.status == ValidationStatus.FAIL:
                emit('FINAL_QUALITY_GATE', 'candidate_rejected', static)
                return ArtifactResult(destination if destination.is_file() else None, report(findings, 'render_pipeline'), False)
            browser_report = validate_browser(candidate, reference_evaluator=reference_evaluator, browser=browser)
            findings.extend(browser_report.findings)
            emit('BROWSER_VALIDATION', 'validate_candidate', browser_report)
            if browser_report.status == ValidationStatus.FAIL:
                emit('FINAL_QUALITY_GATE', 'candidate_rejected', browser_report)
                return ArtifactResult(destination if destination.is_file() else None, report(findings, 'render_pipeline'), False)
            # Candidate is on the same filesystem for atomic replacement. The
            # prior valid artifact remains intact if validation or replacement fails.
            os.replace(candidate, destination)
            result = report(findings, 'render_pipeline')
            emit('FINALIZE', 'promote_validated_candidate', result)
            return ArtifactResult(destination, result, True)
    except PlaygroundError as exc:
        findings.append(ValidationFinding(ValidationStatus.FAIL, exc.failure.code.value, 'render', exc.failure.message))
    except OSError:
        findings.append(ValidationFinding(ValidationStatus.FAIL, 'FINALIZE_FAILED', 'finalize', 'Artifact staging or atomic promotion failed.'))
    failed = report(findings, 'render_pipeline')
    emit('RENDER_CANDIDATE', 'candidate_rejected', failed)
    return ArtifactResult(destination if destination.is_file() else None, failed, False)
