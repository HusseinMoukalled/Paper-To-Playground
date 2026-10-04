"""EvidencePack -> ScientificModel -> LessonSpec -> validated executable IR."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import time
import json

from playground.ir.models import ExplanationIR, ScientificModel
from playground.ir.serialization import parse_json, decode, to_mapping, restore_structural_defaults, json_schema
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
    if isinstance(value,dict) and value.get('status') in ('ok','success','supported') and value.get('scientific_model') is not None and value.get('lesson_spec') is not None:
        value = {key:item for key,item in value.items() if key != 'status'}
    return value


class SemanticEngine:
    def __init__(self, client, *, strategy=GenerationStrategy.COMBINED, enable_repairs=False):
        self.client = client
        self.strategy = GenerationStrategy(strategy)
        self.enable_repairs = enable_repairs

    def generate(self, evidence, *, previous=None, feedback=None, evidence_recovery=None) -> GenerationResult:
        """At most three error-guided attempts, all charged to the same run budget."""
        before_calls = self.client.budget.calls_used
        before_tokens = self.client.budget.completion_tokens
        started = time.monotonic()
        attempts = 3 if self.enable_repairs else 1
        for attempt in range(attempts):
            self._candidate = previous
            try:
                result = self._generate_once(evidence, previous=previous, feedback=feedback)
                from dataclasses import replace
                return replace(result, calls=self.client.budget.calls_used - before_calls,
                               completion_tokens=self.client.budget.completion_tokens - before_tokens,
                               elapsed_seconds=time.monotonic() - started)
            except PlaygroundError as exc:
                retryable = {FailureCode.IR_INVALID, FailureCode.GROUNDING_UNSUPPORTED}
                if evidence_recovery is not None:
                    retryable.add(FailureCode.RETRIEVAL_INSUFFICIENT_EVIDENCE)
                if exc.failure.code not in retryable:
                    raise
                self.client._event('candidate_rejected', 'fail', details={
                    'attempt': attempt + 1, 'failure': exc.failure.to_dict()})
                if attempt + 1 == attempts:
                    raise
                budget = self.client.budget
                if budget.remaining_calls <= 0 or budget.remaining_seconds <= budget.finalization_reserve_seconds:
                    raise
                previous = self._candidate
                feedback = {'message': exc.failure.message, **exc.failure.details}
                if evidence_recovery is not None and exc.failure.code in {
                        FailureCode.GROUNDING_UNSUPPORTED, FailureCode.RETRIEVAL_INSUFFICIENT_EVIDENCE}:
                    evidence = evidence_recovery(evidence)
                self.client._event('revise_candidate', 'started', details={'attempt': attempt + 2})
        raise AssertionError('Unreachable generation state')

    def _generate_once(self, evidence, *, previous=None, feedback=None) -> GenerationResult:
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
        schema = json_schema(ExplanationIR)
        from playground.computation.operations import TYPES, DOMAINS
        variable_schema = schema['properties']['scientific_model']['properties']['variables']['items']['properties']
        variable_schema['type']['enum'] = sorted(TYPES)
        variable_schema['domain'] = {'anyOf':[{'type':'null'},{'type':'string','enum':sorted(d for d in DOMAINS if d is not None)}]}
        control_schema = schema['properties']['lesson_spec']['properties']['controls']['items']['properties']
        control_schema['control_type']['enum'] = ['slider','number','select','toggle','vector','matrix']
        control_schema['validation_rule']['enum'] = ['clamp','reject','normalize','warn']
        schema['properties']['computations']['items']['properties']['output_type']['enum'] = sorted(TYPES)
        schema['properties']['metadata'] = {'type':'object','properties':{
            'audience':{'type':'string','const':evidence.audience},
            'audience_adaptation':{'type':'string'},
            'defaults':{'type':'object','additionalProperties':{}},
            'invariant_bindings':{'type':'object','additionalProperties':{'type':'string'}},
            'control_test_values':{'type':'object','additionalProperties':{'type':'array','items':{}}},
            'equation_scope':{'type':'object','additionalProperties':{'type':'string','enum':['context_only']}},
        },'required':['audience','audience_adaptation','defaults','invariant_bindings','control_test_values','equation_scope'],
            'additionalProperties':True}
        compact = self.enable_repairs and scientific is None
        if compact:
            from playground.model.lesson_plan import plan_schema
            schema = plan_schema()
        messages = build_messages(evidence, stage=stage, scientific_model=scientific, compact=compact)
        if compact:
            from playground.model.lesson_plan import plan_messages
            messages = plan_messages(evidence)
        partial_fields = None
        if compact and isinstance(previous, dict) and 'inputs' in previous and feedback:
            findings = feedback.get('findings', [])
            substantive = [f for f in findings if f.get('code') not in {'CONTROL_UNTESTED', 'DEAD_CONTROL'}]
            if substantive and all('invariant' in f.get('message', '').lower() for f in substantive):
                partial_fields = ['invariants']
            elif substantive and all('expected boolean' in f.get('message', '').lower() for f in substantive):
                partial_fields = ['steps']
            elif 'Invalid invariant' in feedback.get('schema_error', ''):
                partial_fields = ['invariants']
            elif 'Invalid step' in feedback.get('schema_error', ''):
                partial_fields = ['steps']
            if partial_fields:
                schema = {'type': 'object', 'properties': {k: schema['properties'][k] for k in partial_fields},
                          'required': partial_fields, 'additionalProperties': False}
                messages[0]['content'] += ('\nREVISION CONTRACT: Return ONLY ' + ', '.join(partial_fields) +
                    '. Other plan fields are preserved by Python. Correct the exact defects in these fields. '
                    'Invariants describe universal scientific properties, not default input values. '
                    'Replace invalid example-specific assertions with valid scientific predicates; preserve genuine universal checks.')
        if feedback is not None:
            messages.append({'role': 'user', 'content': json.dumps({
                'revision': ('Correct ALL concrete errors below using the evidence. Return ' +
                             ('ONLY the requested revision fields. ' if partial_fields else 'the complete lesson plan. ')) +
                            'Preserve valid science and teaching choices. Do not remove checks, misclassify source claims, '
                            'or demote a mismatched computation to context-only to hide a defect.',
                'previous_candidate_UNTRUSTED_DATA': previous, 'validation_feedback': feedback}, ensure_ascii=True)})
        raw = self.client.complete(messages, max_tokens=8500 if compact else 16000,
                                   purpose="semantic" if scientific is None else "lesson", response_schema=schema)
        self._candidate = raw
        try:
            value = _normalize(raw)
            if partial_fields:
                if not isinstance(value, dict) or set(value) != set(partial_fields):
                    raise ValueError('Revision must return only the requested fields: ' + ', '.join(partial_fields))
                value = {**previous, **value}
            self._candidate = value
            from playground.model.draft import decode_authoring
            is_plan = isinstance(value, dict) and 'inputs' in value and 'steps' in value
            if is_plan:
                if self.client.trace is not None:
                    try:
                        (self.client.trace.path.parent / 'candidate.plan.json').write_text(
                            json.dumps(value, indent=2, ensure_ascii=True), encoding='utf-8')
                    except OSError:
                        self.client._event('save_plan_diagnostic', 'warn')
                from playground.model.lesson_plan import compile_plan
                ir, is_draft = compile_plan(value, evidence), True
            else:
                ir, is_draft = decode_authoring(value, evidence)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            _error(FailureCode.IR_INVALID, "ExplanationIR schema validation failed.", {'schema_error': str(exc)})
        if scientific is not None and to_mapping(ir.scientific_model) != to_mapping(scientific):
            _error(FailureCode.IR_INVALID, "Lesson stage changed the fixed ScientificModel.")
        from playground.model.structural_repair import (
            declare_used_knowledge_classes, normalize_declared_inputs, normalize_wire_conventions)
        try:
            ir, wire_changes = normalize_wire_conventions(ir)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            _error(FailureCode.IR_INVALID, 'Invalid computation metadata.', {'schema_error': str(exc)})
        if wire_changes:
            self.client._event('deterministic_wire_repair','pass',details={'changed_paths':wire_changes})
        ir, changes = normalize_declared_inputs(ir)
        if changes:
            self.client._event('deterministic_input_repair', 'pass', details={'changed_setups':changes})
        ir, class_changes = declare_used_knowledge_classes(ir)
        if class_changes:
            self.client._event('deterministic_knowledge_class_repair', 'pass', details={'added_classes': class_changes})
        if self.client.trace is not None:
            # Retain the latest decoded candidate for diagnosing rejected runs.
            # It contains structured lesson data, never hidden model reasoning.
            try:
                (self.client.trace.path.parent / 'candidate.ir.json').write_text(
                    json.dumps(to_mapping(ir), indent=2, ensure_ascii=True), encoding='utf-8')
            except OSError:
                self.client._event('save_candidate_diagnostic', 'warn')
        # Never discard a mismatched equation link to make incorrect science pass.
        from playground.model.draft import as_authoring
        self._candidate = value if is_plan else as_authoring(ir) if compact else to_mapping(ir)
        if is_draft:
            preliminary = validate_ir(ir, evidence, budget=self.client.budget, require_grounding=False)
            if preliminary.status == ValidationStatus.FAIL:
                _error(FailureCode.IR_INVALID, 'Lesson draft failed executable validation.', {
                    'findings': [{'code': f.code, 'target': f.target, 'message': f.message}
                                 for f in preliminary.findings if f.status == ValidationStatus.FAIL]})
        report = validate_ir(ir, evidence, budget=self.client.budget)
        self.client._event('initial_ir_validation', report.status.value,
                           details={'findings':[{'code':f.code,'target':f.target,'message':f.message}
                                                for f in report.findings]})
        failed = [f for f in report.findings if f.status == ValidationStatus.FAIL]
        if self.enable_repairs and failed and any(f.code in {'CLAIM_UNCLASSIFIED','EVIDENCE_LINEAGE_MISMATCH'} for f in failed):
            from playground.model.grounding_repair import complete_missing_grounding
            try:
                ir = complete_missing_grounding(self.client,ir,evidence,targets={f.target for f in failed})
                ir, class_changes = declare_used_knowledge_classes(ir)
                if class_changes:
                    self.client._event('deterministic_knowledge_class_repair', 'pass', details={'added_classes': class_changes})
                report = validate_ir(ir,evidence,budget=self.client.budget)
                self.client._event('grounding_revalidation',report.status.value,
                                   details={'findings':[{'code':f.code,'target':f.target,'message':f.message}
                                                        for f in report.findings]})
            except (ValueError,TypeError,KeyError) as exc:
                _error(FailureCode.IR_INVALID, 'Targeted provenance repair failed; scientific prose preserved.',
                       {'repair_error': str(exc)})
        if self.enable_repairs and report.status == ValidationStatus.FAIL:
            from playground.model.repair import request_repair, repair_paths
            paths = repair_paths(ir,report)
            if paths:
                failure = Failure(FailureCode.IR_INVALID, 'IR_VALIDATION', FailureSeverity.MAJOR, True,
                                  'Small executable fragment failed validation.', details={'findings':[
                                      {'code':f.code,'target':f.target,'message':f.message} for f in report.findings]})
                try:
                    ir, report = request_repair(self.client,ir,evidence,failure,allowed_paths=paths,
                                               evidence_refs=ir.scientific_model.provenance)
                except (ValueError,TypeError,KeyError):
                    report = validate_ir(ir, evidence, budget=self.client.budget)
                    if report.status == ValidationStatus.FAIL:
                        _error(FailureCode.IR_INVALID,'Targeted executable repair failed; original IR preserved.',
                               {'findings': [{'code': f.code, 'target': f.target, 'message': f.message}
                                             for f in report.findings if f.status == ValidationStatus.FAIL]})
        self.client._event("validate_ir", report.status.value,
                           details={"findings": [{"code": f.code, "stage": f.stage, "status": f.status.value, "target": f.target, "message": f.message} for f in report.findings]})
        if report.status == ValidationStatus.FAIL:
            _error(FailureCode.IR_INVALID, "Generated IR failed deterministic validation.",
                   {"findings": [{"code": f.code, "stage": f.stage, 'target': f.target, 'message': f.message}
                                 for f in report.findings]})
        ir = compile_computations(ir)
        if is_draft:
            if is_plan:
                from playground.model.observations import calculated_observations
                ir = calculated_observations(ir)
                self.client._event('calculated_exploration_observations', 'pass',
                                   details={'count': len(ir.lesson_spec.guided_explorations)})
                if self.client.trace is not None:
                    try:
                        (self.client.trace.path.parent / 'candidate.ir.json').write_text(
                            json.dumps(to_mapping(ir), indent=2, ensure_ascii=True), encoding='utf-8')
                    except OSError:
                        self.client._event('save_candidate_diagnostic', 'warn')
            from playground.model.scientific_review import review_lesson
            try:
                issues = review_lesson(self.client, ir, evidence)
            except (ValueError, TypeError, KeyError) as exc:
                _error(FailureCode.IR_INVALID, 'Scientific review returned an invalid response.', {'review_error': str(exc)})
            if issues:
                _error(FailureCode.GROUNDING_UNSUPPORTED, 'Scientific review rejected the candidate.', {'issues': issues})
            return GenerationResult(ir, report, self.strategy, self.client.budget.calls_used - before_calls,
                                    self.client.budget.completion_tokens - before_tokens, time.monotonic() - started)
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
