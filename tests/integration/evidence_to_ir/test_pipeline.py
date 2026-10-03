import json
import os
from dataclasses import replace
import unittest
from unittest.mock import patch

from playground.model.client import OpenRouterClient
from playground.model.generation import SemanticEngine, GenerationStrategy, benchmark_strategies
from playground.model.prompts import build_messages
from playground.model.verification import detect_risks, verify_units
from playground.model.repair import apply_patches, request_repair
from playground.ir.serialization import to_mapping
from playground.budget import RunBudget
from playground.failures import PlaygroundError, Failure, FailureCode, FailureSeverity
from tests.fixtures.dev2_factory import evidence_pack, explanation
from tests.unit.model.test_client import response, TEST_KEY


@patch.dict(os.environ, {"OPENROUTER_API_KEY": TEST_KEY})
class PipelineTests(unittest.TestCase):
    def client(self, outputs):
        values = iter(outputs)
        return OpenRouterClient("caller-model", RunBudget(), transport=lambda *_: response(next(values)))

    def test_success_one_call(self):
        client = self.client([json.dumps(to_mapping(explanation()))])
        result = SemanticEngine(client).generate(evidence_pack())
        self.assertEqual(result.calls, 1)
        self.assertEqual(result.validation.status.value, "PASS")
        self.assertIn("canonical_ast", result.ir.computations[0].metadata)

    def test_two_stage(self):
        ir = explanation()
        client = self.client([json.dumps(to_mapping(ir.scientific_model)), json.dumps(to_mapping(ir))])
        result = SemanticEngine(client, strategy=GenerationStrategy.TWO_STAGE).generate(evidence_pack())
        self.assertEqual(result.calls, 2)

    def test_model_json_failure_no_blind_retry(self):
        client = self.client(["not JSON"])
        with self.assertRaises(PlaygroundError):
            SemanticEngine(client).generate(evidence_pack())
        self.assertEqual(client.budget.calls_used, 1)

    def test_malformed_status_has_structured_schema_failure(self):
        for status in ([], {}, 1):
            client = self.client([json.dumps({"status": status})])
            with self.assertRaises(PlaygroundError) as captured:
                SemanticEngine(client).generate(evidence_pack())
            self.assertEqual(captured.exception.failure.code, FailureCode.IR_INVALID)
            self.assertEqual(client.budget.calls_used, 1)

    def test_deterministic_recovery_and_explicit_unsupported(self):
        raw = json.dumps(to_mapping(explanation()))
        result = SemanticEngine(self.client(["```json\n" + raw + "\n```"])).generate(evidence_pack())
        self.assertEqual(result.calls, 1)
        with self.assertRaises(PlaygroundError) as captured:
            SemanticEngine(self.client(['{"status":"insufficient_evidence", "scientific_model":null,"lesson_spec":null}'])).generate(evidence_pack())
        self.assertEqual(captured.exception.failure.code, FailureCode.RETRIEVAL_INSUFFICIENT_EVIDENCE)

    def test_empty_evidence_no_model_call(self):
        client = self.client([])
        with self.assertRaises(PlaygroundError):
            SemanticEngine(client).generate(replace(evidence_pack(), evidence_blocks=()))
        self.assertEqual(client.budget.calls_used, 0)

    def test_prompt_data_boundary_and_audience(self):
        evidence = evidence_pack()
        messages = build_messages(evidence)
        self.assertIn("untrusted DATA", messages[0]["content"])
        self.assertNotIn(evidence.evidence_blocks[0].content, messages[0]["content"])
        self.assertEqual(json.loads(messages[1]["content"])["case_context"]["audience"], evidence.audience)
        adapted = build_messages(replace(evidence, audience="advanced mathematics undergraduate"))
        self.assertNotEqual(messages[1]["content"], adapted[1]["content"])

    def test_no_mandatory_critic(self):
        evidence, ir = evidence_pack(), explanation()
        client = self.client([])
        self.assertEqual(detect_risks(ir, evidence), ())
        self.assertEqual(verify_units(client, evidence, ()), ())
        self.assertEqual(client.budget.calls_used, 0)

    def test_targeted_patch_transaction(self):
        evidence, ir = evidence_pack(), explanation()
        path = "/lesson_spec/controls/0/label"
        candidate, report = apply_patches(ir, evidence, [{"op": "replace", "path": path, "value": "Scaling gain"}], allowed_paths={path})
        self.assertNotEqual(candidate.lesson_spec.controls[0].label, ir.lesson_spec.controls[0].label)
        self.assertEqual(report.status.value, "PASS")
        before = to_mapping(ir)
        with self.assertRaises(ValueError):
            apply_patches(ir, evidence, [{"op": "replace", "path": path, "value": ""}], allowed_paths={path})
        self.assertEqual(to_mapping(ir), before)
        with self.assertRaises(ValueError):
            apply_patches(ir, evidence, [{"op": "replace", "path": "/lesson_spec", "value": {}}], allowed_paths={"/lesson_spec"})

    def test_targeted_model_repair(self):
        evidence, ir = evidence_pack(), explanation()
        path = "/lesson_spec/controls/0/label"
        client = self.client([json.dumps({"patches": [{"op": "replace", "path": path, "value": "Scaling gain"}]})])
        failure = Failure(FailureCode.IR_INVALID, "pedagogy", FailureSeverity.MINOR, True, "A targeted issue")
        result, report = request_repair(client, ir, evidence, failure, allowed_paths={path}, evidence_refs=("E1",))
        self.assertEqual(client.budget.calls_used, 1)
        self.assertEqual(report.status.value, "PASS")

    def test_opt_in_benchmark(self):
        ir = explanation()
        def factory(strategy):
            return self.client(([json.dumps(to_mapping(ir.scientific_model))] if strategy == GenerationStrategy.TWO_STAGE else []) + [json.dumps(to_mapping(ir))])
        metrics = benchmark_strategies(evidence_pack(), factory)
        self.assertEqual([x["calls"] for x in metrics], [1, 2])
