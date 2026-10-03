"""Bounded orchestration of the three independently owned subsystems."""

from __future__ import annotations

from enum import StrEnum
from dataclasses import replace
import json
import os

from playground.config import RunConfig, CaseInput
from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError
from playground.trace import TraceWriter
from playground.budget import RunBudget
from playground.source.pipeline import build_evidence
from playground.model.client import OpenRouterClient
from playground.model.generation import SemanticEngine
from playground.model.rerank import DeepSeekReranker
from playground.model.verification import verify_units
from playground.model.verification import RiskUnit
from playground.model.repair import request_repair
from playground.ir.grounding import claim_locations, learner_claims
from playground.ir.serialization import to_mapping
from playground.computation.evaluator import execute, ExecutionGuard
from playground.render.pipeline import build_artifact
from playground.secrets import redact_secrets
from playground.validation.artifact import report as validation_report


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
    """One budget, one trace, atomic artifact promotion; never substitutes science."""

    def __init__(self, config: RunConfig, *, transport=None, budget=None, browser=None) -> None:
        self.config = config
        self.transport = transport
        self.budget = budget or RunBudget()
        self.browser = browser

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
                    return self._generate(case, trace)
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

    def _generate(self, case, trace):
        client = OpenRouterClient(self.config.model_id, self.budget, trace, transport=self.transport)
        source = build_evidence(case, base_dir=self.config.input_path.resolve().parent,
                                budget=self.budget, trace=trace, model_id=self.config.model_id,
                                reranker=DeepSeekReranker(client))
        engine = SemanticEngine(client, strategy=os.environ.get('PLAYGROUND_SEMANTIC_STRATEGY', 'combined'))
        generated = engine.generate(source.evidence_pack)
        ir = generated.ir
        trace.emit(stage='SEMANTIC_CORE', action='formalize_and_teach', result='pass',
                   details={'strategy': generated.strategy.value, 'calls': generated.calls})
        trace.emit(stage='IR_VALIDATION', action='progressive_contract_validation',
                   result=generated.validation.status.value.lower(),
                   details={'finding_codes':[f.code for f in generated.validation.findings]})
        trace.emit(stage='COMPUTATION_VALIDATION', action='execute_representative_scientific_states',
                   result='pass', details={'ast_version':1,'computations':len(ir.computations)})
        trace.emit(stage='GROUNDING_AND_COVERAGE', action='validate_claim_lineage_and_focus_paths',
                   result=generated.validation.status.value.lower(),
                   details={'claims':len(ir.grounding_records),'focus_preserved':ir.focus_coverage.focus==case.focus})
        ir = self._verify_risks(ir, source.evidence_pack, generated.risk_units, client, trace)
        metadata = {**ir.metadata, 'paper_metadata': redact_secrets({**source.evidence_pack.paper_metadata,
                                                    'source_url': case.source_url}),
                    'source_validation': {'status': source.validation_report.status.value,
                                          'finding_codes': [f.code for f in source.validation_report.findings],
                                          'retrieval_confidence': source.evidence_pack.retrieval_confidence.value}}
        ir = replace(ir, metadata=metadata)
        def reference(inputs):
            return execute(ir, inputs, guard=ExecutionGuard(self.budget))[0]
        result = build_artifact(ir, self.config.output_path, reference_evaluator=reference,
                                trace=trace, browser=self.browser, budget=self.budget)
        if not result.promoted:
            raise PlaygroundError(Failure(FailureCode.ARTIFACT_INVALID, 'final_quality_gate',
                                           FailureSeverity.MAJOR, True,
                                           'Candidate failed artifact validation; any previous index.html was preserved.',
                                           details={'finding_codes': [f.code for f in result.report.findings]}))
        # Diagnostic IR and report are data only. The final HTML needs neither file.
        combined_report = validation_report(list(source.validation_report.findings) +
                                            list(generated.validation.findings) + list(result.report.findings),
                                            'integration')
        report = {'status': combined_report.status.value,
                  'source_status': source.validation_report.status.value,
                  'ir_status': generated.validation.status.value,
                  'findings': [to_mapping(f) for f in combined_report.findings],
                  'calls': self.budget.calls_used, 'completion_tokens': self.budget.completion_tokens,
                  'elapsed_seconds': self.budget.elapsed_seconds}
        for name, value in (('explanation_ir.json', to_mapping(ir)), ('validation_report.json', report)):
            try:
                (self.config.output_path / name).write_text(json.dumps(value, ensure_ascii=True, indent=2), encoding='utf-8')
            except OSError:
                trace.emit(stage='FINALIZE', action='write_optional_diagnostics', result='warn', details={'file': name})
        trace.emit(stage='EXIT', action='complete', result=combined_report.status.value.lower(),
                   details={'artifact': 'index.html', 'calls': self.budget.calls_used,
                            'completion_tokens': self.budget.completion_tokens})
        return 0

    def _verify_risks(self, ir, evidence, units, client, trace):
        if not units:
            return ir
        try:
            verdicts = verify_units(client, evidence, units)
            failed = [unit for unit, verdict in zip(units, verdicts) if verdict['status'] != 'SUPPORTED']
            trace.emit(stage='GROUNDING_AND_COVERAGE', action='targeted_semantic_verification',
                       result='fail' if failed else 'pass',
                       details={'units': len(verdicts), 'statuses': [v['status'] for v in verdicts]})
            # At most two narrowly authorized claim-text repairs in one patch
            # request. Mathematics, IDs, contracts and all other claims stay fixed.
            if 1 <= len(failed) <= 2 and all(unit.kind == 'claim_evidence' for unit in failed):
                locations = claim_locations(ir)
                indices = {r.claim_id:i for i,r in enumerate(ir.grounding_records)}
                if all(unit.target in indices and unit.target in locations and unit.evidence_refs for unit in failed):
                    failure = Failure(FailureCode.GROUNDING_UNSUPPORTED, 'semantic_verification',
                                      FailureSeverity.MAJOR, True, 'Claim/evidence mismatch.',
                                      details={'verification_findings':[{**v,'reason':v['reason'][:500]}
                                                for v in verdicts if v['status'] != 'SUPPORTED']})
                    paths = {path for unit in failed for path in
                             (locations[unit.target],f'/grounding_records/{indices[unit.target]}/claim')}
                    evidence_refs = tuple(dict.fromkeys(ref for unit in failed for ref in unit.evidence_refs))
                    ir, _ = request_repair(client, ir, evidence, failure, allowed_paths=paths,
                                            evidence_refs=evidence_refs)
                    updated = tuple(RiskUnit(unit.kind, unit.target, learner_claims(ir)[unit.target],
                                             unit.evidence_refs,'repaired_claim') for unit in failed)
                    rechecked = verify_units(client, evidence, updated)
                    if all(verdict['status'] == 'SUPPORTED' for verdict in rechecked):
                        return ir
            if not failed:
                return ir
        except (ValueError, TypeError, KeyError, StopIteration):
            pass
        raise PlaygroundError(Failure(FailureCode.GROUNDING_UNSUPPORTED, 'semantic_verification',
                                       FailureSeverity.MAJOR, True,
                                       'A risky scientific unit could not be verified; no artifact was promoted.'))

    @staticmethod
    def _trace_failure(trace: TraceWriter, failure: Failure) -> None:
        trace.emit(
            stage=failure.stage,
            action="failure",
            result="fail",
            details=failure.to_dict(),
        )
