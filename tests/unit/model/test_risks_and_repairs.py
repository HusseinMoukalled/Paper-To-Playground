import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from playground.budget import RunBudget
from playground.model.client import OpenRouterClient
from playground.model.verification import detect_risks, verify_units, RiskUnit
from playground.model.generation import SemanticEngine, GenerationStrategy
from playground.model.repair import apply_patches, request_repair
from playground.ir.models import GroundingStatus
from playground.ir.serialization import to_mapping
from playground.retrieval.evidence import RetrievalConfidence
from playground.failures import PlaygroundError, Failure, FailureCode, FailureSeverity
from tests.fixtures.dev2_factory import explanation, evidence_pack
from tests.unit.model.test_client import TEST_KEY, response


@patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
class RiskRepairTests(unittest.TestCase):
    def client(self, replies):
        stream = iter(replies)
        return OpenRouterClient("caller-model", RunBudget(), transport=lambda *_: response(next(stream)))

    def test_partial_and_ambiguous_risks(self):
        ir, evidence = explanation(), evidence_pack()
        records = (replace(ir.grounding_records[0], status=GroundingStatus.PARTIAL),) + ir.grounding_records[1:]
        partial = replace(ir, grounding_records=records)
        unit = detect_risks(partial, evidence)[0]
        reply = {"target": unit.target, "status": "SUPPORTED", "evidence_refs": ["E1"], "reason": "The equation supports this unit."}
        client = self.client([json.dumps(reply)])
        self.assertEqual(verify_units(client, evidence, (unit,))[0]["status"], "SUPPORTED")
        self.assertEqual(client.budget.calls_used, 1)
        # A verdict does not silently rewrite the original partially supported claim.
        self.assertEqual(partial.grounding_records[0].status, GroundingStatus.PARTIAL)
        risks = detect_risks(ir, replace(evidence, retrieval_confidence=RetrievalConfidence.AMBIGUOUS))
        self.assertEqual(risks[0].kind, "equation_evidence")

    def test_performance_claim_risk(self):
        ir = explanation()
        claim = replace(ir.grounding_records[0], claim="The method improves benchmark accuracy by 25%.")
        risks = detect_risks(replace(ir, grounding_records=(claim,) + ir.grounding_records[1:]), evidence_pack())
        self.assertEqual(risks[0].reason, "high_risk_paper_claim")

    def test_verifier_cannot_invent_citations(self):
        unit = RiskUnit("claim_evidence", "science.concept", "A linear response.", ("E1",), "partial_support")
        for refs in (["E404"], []):
            client = self.client([json.dumps({"target": unit.target, "status": "SUPPORTED", "evidence_refs": refs, "reason": "supported"})])
            with self.assertRaises(ValueError):
                verify_units(client, evidence_pack(), (unit,))

    def test_two_stage_does_not_change_science(self):
        ir = explanation()
        changed = replace(ir, scientific_model=replace(ir.scientific_model, concept="Unrelated mechanism"))
        client = self.client([json.dumps(to_mapping(ir.scientific_model)), json.dumps(to_mapping(changed))])
        with self.assertRaises(PlaygroundError):
            SemanticEngine(client, strategy=GenerationStrategy.TWO_STAGE).generate(evidence_pack())

    def test_unauthorized_and_protected_patches(self):
        ir = explanation()
        for path, value in (("/lesson_spec/controls/0/id", "control-changed"),
                            ("/computations/0/metadata/canonical_ast", {}),
                            ("/metadata/audience", "other"), ("/lesson_spec", {})):
            with self.subTest(path=path), self.assertRaises(ValueError):
                apply_patches(ir, evidence_pack(), [{"op": "replace", "path": path, "value": value}], allowed_paths={path})

    def test_failed_model_repair_does_not_mutate_original(self):
        ir = explanation()
        before = to_mapping(ir)
        path = "/lesson_spec/controls/0/label"
        client = self.client([json.dumps({"patches": [{"op": "replace", "path": path, "value": ""}]})])
        failure = Failure(FailureCode.IR_INVALID, "pedagogy", FailureSeverity.MINOR, True, "small defect")
        with self.assertRaises(ValueError):
            request_repair(client, ir, evidence_pack(), failure, allowed_paths={path}, evidence_refs=("E1",))
        self.assertEqual(to_mapping(ir), before)

    def test_provider_model_mismatch_no_fallback(self):
        client = OpenRouterClient("caller-model", RunBudget(), transport=lambda *_: {**response(), "model": "different-model"})
        with self.assertRaises(PlaygroundError):
            client.complete([])
        self.assertEqual(client.budget.calls_used, 1)
