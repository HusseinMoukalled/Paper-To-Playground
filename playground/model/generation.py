"""EvidencePack -> ScientificModel -> LessonSpec -> validated executable IR."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import time

from playground.ir.models import ExplanationIR, ScientificModel
from playground.ir.serialization import parse_json, decode, to_mapping
from playground.ir.validate import validate_ir
from playground.computation.evaluator import compile_computations
from playground.model.prompts import build_messages
from playground.model.verification import detect_risks
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError
from playground.validation.report import ValidationStatus


class GenerationStrategy(StrEnum):
    COMBINED = "combined"
    TWO_STAGE = "two_stage"


@dataclass(frozen=True)
class GenerationResult:
    ir: ExplanationIR
    validation: object
    strategy: GenerationStrategy
    calls: int
    completion_tokens: int
    elapsed_seconds: float
    risk_units: tuple = ()


def _error(code, message, details=None):
    raise PlaygroundError(Failure(code, "semantic", FailureSeverity.MAJOR, True, message,
                                  details=details or {})) from None


def _normalize(content):
    try:
        value = parse_json(content)
    except (ValueError, RecursionError):
        _error(FailureCode.IR_INVALID, "Model JSON is invalid after deterministic recovery.")
    if isinstance(value, dict) and isinstance(value.get("status"), str) and value["status"] in {"unsupported", "insufficient_evidence"}:
        _error(FailureCode.RETRIEVAL_INSUFFICIENT_EVIDENCE, "Model explicitly reported unsupported or insufficient evidence.",
               {"status": value["status"]})
    return value


class SemanticEngine:
    def __init__(self, client, *, strategy=GenerationStrategy.COMBINED):
        self.client = client
        self.strategy = GenerationStrategy(strategy)

    def generate(self, evidence) -> GenerationResult:
        if not evidence.evidence_blocks:
            _error(FailureCode.RETRIEVAL_INSUFFICIENT_EVIDENCE, "EvidencePack is empty; model call was not attempted.")
        before_calls = self.client.budget.calls_used
        before_tokens = self.client.budget.completion_tokens
        started = time.monotonic()
        scientific = None
        if self.strategy == GenerationStrategy.TWO_STAGE:
            raw = self.client.complete(build_messages(evidence, stage="science"), max_tokens=3500, purpose="science")
            try:
                scientific = decode(ScientificModel, _normalize(raw))
            except ValueError:
                _error(FailureCode.IR_INVALID, "ScientificModel schema validation failed.")
        stage = "combined" if scientific is None else "lesson"
        raw = self.client.complete(build_messages(evidence, stage=stage, scientific_model=scientific),
                                   max_tokens=7500, purpose="semantic" if scientific is None else "lesson")
        try:
            ir = decode(ExplanationIR, _normalize(raw))
        except ValueError:
            _error(FailureCode.IR_INVALID, "ExplanationIR schema validation failed.")
        if scientific is not None and to_mapping(ir.scientific_model) != to_mapping(scientific):
            _error(FailureCode.IR_INVALID, "Lesson stage changed the fixed ScientificModel.")
        report = validate_ir(ir, evidence, budget=self.client.budget)
        self.client._event("validate_ir", report.status.value,
                           details={"findings": [{"code": f.code, "stage": f.stage, "status": f.status.value} for f in report.findings]})
        if report.status == ValidationStatus.FAIL:
            _error(FailureCode.IR_INVALID, "Generated IR failed deterministic validation.",
                   {"findings": [{"code": f.code, "stage": f.stage} for f in report.findings]})
        ir = compile_computations(ir)
        risks = detect_risks(ir, evidence)
        self.client._event("semantic_risk_detection", "warn" if risks else "pass", details={"risk_units": len(risks)})
        return GenerationResult(ir, report, self.strategy, self.client.budget.calls_used - before_calls,
                                self.client.budget.completion_tokens - before_tokens, time.monotonic() - started, risks)


def benchmark_strategies(evidence, client_factory, *, repeats=1):
    """Opt-in benchmark. client_factory receives strategy; caller controls shared budgets.

    Never runs as part of normal generation. Returns metrics, not invented quality scores.
    """
    if not 1 <= repeats <= 10:
        raise ValueError("Benchmark repeats must be bounded")
    results = []
    for strategy in GenerationStrategy:
        for repetition in range(repeats):
            client = client_factory(strategy)
            start_calls, start_tokens = client.budget.calls_used, client.budget.completion_tokens
            started = time.monotonic()
            try:
                result = SemanticEngine(client, strategy=strategy).generate(evidence)
                entry = {"status": result.validation.status.value,
                         "mechanism": result.ir.scientific_model.concept,
                         "control_variables": [c.scientific_variable for c in result.ir.lesson_spec.controls],
                         "visual_families": [v.visual_type for v in result.ir.visuals]}
            except PlaygroundError as error:
                entry = {"status": "FAIL", "failure_code": error.failure.code.value}
            results.append({"strategy": strategy.value, "repetition": repetition, **entry,
                            "calls": client.budget.calls_used - start_calls,
                            "completion_tokens": client.budget.completion_tokens - start_tokens,
                            "elapsed_seconds": time.monotonic() - started})
    return results
