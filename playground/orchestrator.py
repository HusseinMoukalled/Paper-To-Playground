"""One budgeted source-to-science-to-browser pipeline with atomic promotion."""

from __future__ import annotations

from enum import StrEnum
from dataclasses import replace
import json

from playground.config import RunConfig, CaseInput
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError
from playground.trace import TraceWriter
from playground.budget import RunBudget
from playground.source.pipeline import build_evidence
from playground.model.client import OpenRouterClient
from playground.model.rerank import OpenRouterReranker
from playground.model.generation import SemanticEngine
from playground.model.verification import verify_units
from playground.computation.evaluator import execute
from playground.computation.validate import prepare_inputs
from playground.computation.invariants import check_invariants
from playground.render.pipeline import build_artifact
from playground.validation.report import ValidationStatus


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
    """Owns global budgets, recovery decisions and the final quality gate."""

    def __init__(self, config: RunConfig) -> None:
        self.config = config

    def run(self) -> int:
        budget = RunBudget()
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
                    client = OpenRouterClient(self.config.model_id, budget, trace)
                    source = build_evidence(case, base_dir=self.config.input_path.parent, budget=budget,
                                            trace=trace, reranker=OpenRouterReranker(client), model_id=self.config.model_id)
                    generated = SemanticEngine(client, enable_repairs=True).generate(source.evidence_pack)
                    ir = generated.ir
                    if generated.risk_units:
                        verdicts = verify_units(client, source.evidence_pack, generated.risk_units)
                        trace.emit(stage='GROUNDING_AND_COVERAGE', action='verify_risky_units',
                                   result='fail' if any(v['status'] == 'UNSUPPORTED' for v in verdicts) else 'pass',
                                   details={'verdicts': verdicts})
                        if any(v['status'] == 'UNSUPPORTED' for v in verdicts):
                            raise PlaygroundError(Failure(FailureCode.GROUNDING_UNSUPPORTED, 'GROUNDING_AND_COVERAGE',
                                FailureSeverity.MAJOR, True, 'Targeted verification rejected a scientific claim or equation.'))
                    ir = replace(ir, metadata={**ir.metadata, 'paper_metadata': source.evidence_pack.paper_metadata,
                                               'source_url': case.source_url, 'model_id': self.config.model_id})
                    variable_ids = {v.id for v in ir.scientific_model.variables}
                    def reference(inputs):
                        setup = {c.id: inputs[c.scientific_variable] for c in ir.lesson_spec.controls}
                        prepared = prepare_inputs(ir, setup)
                        for key in prepared:
                            if key in inputs:
                                prepared[key] = inputs[key]
                        values, _ = execute(ir, prepared)
                        if not all(passed for _, passed in check_invariants(ir, values)):
                            raise ValueError('Reference scientific invariant failed')
                        return {key: values[key] for key in variable_ids}
                    artifact = build_artifact(ir, self.config.output_path, reference_evaluator=reference,
                                              trace=trace, budget=budget)
                    if not artifact.promoted or artifact.report.status == ValidationStatus.FAIL:
                        raise PlaygroundError(Failure(FailureCode.ARTIFACT_INVALID, 'FINAL_QUALITY_GATE',
                            FailureSeverity.MAJOR, False, 'Candidate failed artifact or browser validation; previous artifact preserved.',
                            details={'findings': [{'code': f.code, 'message': f.message} for f in artifact.report.findings]}))
                    warnings = [f.code for report in (source.validation_report, generated.validation, artifact.report)
                                for f in report.findings if f.status == ValidationStatus.WARN]
                    trace.emit(stage='EXIT', action='run_completed', result='warn' if warnings else 'pass',
                               details={'model_id': self.config.model_id, 'calls': budget.calls_used,
                                        'completion_tokens': budget.completion_tokens, 'prompt_tokens': budget.prompt_tokens,
                                        'run_seconds': round(budget.elapsed_seconds, 3), 'warning_codes': warnings,
                                        'artifact': 'index.html', 'promoted': True})
                    print(f'Generated {artifact.path}' + (' (warnings recorded in trace.jsonl)' if warnings else ''))
                    return 0
                except PlaygroundError as exc:
                    self._trace_failure(trace, exc.failure)
                    raise
                except Exception as exc:
                    failure = Failure(
                        code=FailureCode.UNEXPECTED_ERROR,
                        stage=PipelineStage.START.value,
                        severity=FailureSeverity.CRITICAL,
                        recoverable=False,
                        message="An unexpected pipeline error occurred; unsafe details were omitted.",
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
