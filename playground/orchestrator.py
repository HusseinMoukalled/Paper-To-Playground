"""Bounded top-level pipeline state machine for the foundation milestone."""

from __future__ import annotations

from enum import StrEnum

from playground.config import RunConfig, CaseInput
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError
from playground.trace import TraceWriter


class PipelineStage(StrEnum):
    START = "START"
    STARTUP_VALIDATION = "STARTUP_VALIDATION"
    SOURCE_ACQUISITION = "SOURCE_ACQUISITION"
    PAPER_PARSING = "PAPER_PARSING"
    RETRIEVAL = "RETRIEVAL"
    EVIDENCE_PACK = "EVIDENCE_PACK"
    SEMANTIC_CORE = "SEMANTIC_CORE"
    IR_VALIDATION = "IR_VALIDATION"
    COMPUTATION_VALIDATION = "COMPUTATION_VALIDATION"
    RENDER_CANDIDATE = "RENDER_CANDIDATE"
    STATIC_VALIDATION = "STATIC_VALIDATION"
    BROWSER_VALIDATION = "BROWSER_VALIDATION"
    GROUNDING_AND_COVERAGE = "GROUNDING_AND_COVERAGE"
    FINAL_QUALITY_GATE = "FINAL_QUALITY_GATE"
    FINALIZE = "FINALIZE"
    EXIT = "EXIT"


class Orchestrator:
    """Owns global stage transitions; subsystem work is intentionally absent."""

    def __init__(self, config: RunConfig) -> None:
        self.config = config

    def run(self) -> int:
        try:
            self.config.output_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise PlaygroundError(
                Failure(
                    code=FailureCode.OUTPUT_DIRECTORY_UNAVAILABLE,
                    stage=PipelineStage.STARTUP_VALIDATION.value,
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message=f"Cannot create output directory: {self.config.output_path}.",
                )
            ) from exc

        trace_path = self.config.output_path / "trace.jsonl"
        try:
            with TraceWriter(trace_path) as trace:
                try:
                    trace.emit(
                        stage=PipelineStage.START.value,
                        action="initialize",
                        result="pass",
                        details={"model_id": self.config.model_id},
                    )
                    case: CaseInput = CaseInput.from_json_file(self.config.input_path)
                    trace.emit(
                        stage=PipelineStage.STARTUP_VALIDATION.value,
                        action="validate_case",
                        result="pass",
                        details={"case_fields": ["source_url", "focus", "audience"]},
                    )
                    failure = Failure(
                        code=FailureCode.PIPELINE_NOT_IMPLEMENTED,
                        stage=PipelineStage.START.value,
                        severity=FailureSeverity.CRITICAL,
                        recoverable=False,
                        message=(
                            "The repository foundation is ready, but the generation pipeline "
                            "is intentionally not implemented in Milestone 0."
                        ),
                        details={"source_url_present": bool(case.source_url)},
                    )
                    raise PlaygroundError(failure)
                except PlaygroundError as exc:
                    self._trace_failure(trace, exc.failure)
                    raise
                except Exception as exc:
                    failure = Failure(
                        code=FailureCode.UNEXPECTED_ERROR,
                        stage=PipelineStage.START.value,
                        severity=FailureSeverity.CRITICAL,
                        recoverable=False,
                        message="An unexpected foundation error occurred; details were omitted.",
                    )
                    self._trace_failure(trace, failure)
                    raise PlaygroundError(failure) from exc
        except OSError as exc:
            raise PlaygroundError(
                Failure(
                    code=FailureCode.OUTPUT_DIRECTORY_UNAVAILABLE,
                    stage=PipelineStage.STARTUP_VALIDATION.value,
                    severity=FailureSeverity.CRITICAL,
                    recoverable=False,
                    message=f"Cannot write execution trace: {trace_path}.",
                )
            ) from exc

    @staticmethod
    def _trace_failure(trace: TraceWriter, failure: Failure) -> None:
        trace.emit(
            stage=failure.stage,
            action="failure",
            result="fail",
            details=failure.to_dict(),
        )
