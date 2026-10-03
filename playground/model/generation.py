"""EvidencePack -> ScientificModel -> LessonSpec -> validated executable IR."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import time

from playground.ir.models import ExplanationIR, ScientificModel
from playground.ir.serialization import parse_json, decode, to_mapping
from playground.ir.validate import validate_ir
from playground.ir.grounding import learner_claims, claim_aliases
from playground.computation.evaluator import compile_computations
from playground.model.prompts import build_messages
from playground.model.verification import detect_risks
from playground.model.grounding_plan import expand_grounding_plan
from playground.model.wire import lower_wire
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


def _science_wire(value):
    if not isinstance(value, dict):
        return value
    value = dict(value)
    if isinstance(value.get('status'), str) and value['status'] in {'ok','success','supported'}:
        value.pop('status')
    if set(value) == {'scientific_model'}:
        return value['scientific_model']
    return value


def expand_compact_grounding(value):
    """Copy claim text only; never invent a class, citation, or support verdict."""
    if not isinstance(value, dict) or not isinstance(value.get('grounding_records'), list):
        return value
    if not any(isinstance(r, dict) and ('claim' not in r or 'claim_ids' in r) for r in value['grounding_records']):
        return value
    partial = dict(value, grounding_records=[])
    partial_ir = decode(ExplanationIR, partial)
    claims = learner_claims(partial_ir)
    aliases = claim_aliases(partial_ir)
    records = []
    for record in value['grounding_records']:
        if not isinstance(record, dict):
            raise ValueError('Invalid compact grounding')
        if 'claim_ids' in record:
            if set(record) != {'claim_ids', 'knowledge_class', 'status', 'evidence_refs', 'computation_refs'} or not isinstance(record['claim_ids'], list):
                raise ValueError('Invalid grouped grounding fields')
            for claim_id in record['claim_ids']:
                if isinstance(claim_id, str):
                    claim_id = aliases.get(claim_id, claim_id)
                if not isinstance(claim_id, str) or claim_id not in claims:
                    raise ValueError('Unknown grouped claim path: ' + str(claim_id)[:120])
                records.append({**{k:v for k,v in record.items() if k != 'claim_ids'},
                                'claim_id': claim_id, 'claim': claims[claim_id]})
            continue
        if 'claim' not in record:
            if not isinstance(record.get('claim_id'), str):
                raise ValueError('Invalid compact claim ID')
            record = dict(record, claim_id=aliases.get(record.get('claim_id'), record.get('claim_id')))
            if record.get('claim_id') not in claims:
                raise ValueError('Unknown compact claim path')
            record = dict(record, claim=claims[record['claim_id']])
        records.append(record)
    return dict(value, grounding_records=records)


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
                scientific = decode(ScientificModel, _science_wire(_normalize(raw)))
            except ValueError:
                _error(FailureCode.IR_INVALID, "ScientificModel schema validation failed.")
        stage = "combined" if scientific is None else "lesson"
        raw = self.client.complete(build_messages(evidence, stage=stage, scientific_model=scientific),
                                   max_tokens=7500, purpose="semantic" if scientific is None else "lesson")
        try:
            ir = decode(ExplanationIR, expand_compact_grounding(expand_grounding_plan(lower_wire(_normalize(raw), evidence))))
        except ValueError as exc:
            _error(FailureCode.IR_INVALID, "ExplanationIR schema validation failed.", {'schema_error': str(exc)})
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
