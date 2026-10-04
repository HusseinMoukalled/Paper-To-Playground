"""Regression tests for schema, executable, and semantic failures on fresh candidates."""
import copy
import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from playground.budget import RunBudget
from playground.failures import PlaygroundError, FailureCode
from playground.ir.grounding import learner_claims
from playground.model.client import OpenRouterClient
from playground.model.draft import as_authoring, decode_authoring, authoring_schema
from playground.model.generation import SemanticEngine
from tests.fixtures.dev2_factory import explanation, evidence_pack
from tests.unit.model.test_client import response, TEST_KEY, scientific_verdict


@patch.dict(os.environ, {'OPENROUTER_API_KEY': TEST_KEY})
class GenerationRecoveryTests(unittest.TestCase):
    def engine(self, candidates, reviews=(), budget=None):
        originals = iter(candidates)
        verdicts = iter(reviews)
        requests = []
        oracle = {r.claim_id: r for r in explanation().grounding_records}

        def transport(payload, *_):
            requests.append(payload)
            system = payload['messages'][0]['content']
            if system.startswith('TASK:'):
                return response(json.dumps(next(originals)))
            if system.startswith('Classify ONLY'):
                claims = json.loads(payload['messages'][1]['content'])['missing_claims']
                records = []
                for key in claims:
                    record = oracle[key]
                    records.append({'claim_id': key, 'knowledge_class': record.knowledge_class.value,
                                    'status': record.status.value, 'evidence_refs': record.evidence_refs,
                                    'computation_refs': record.computation_refs})
                return response(json.dumps({'grounding_records': records}))
            if system.startswith('Review the scientific'):
                return response(json.dumps(scientific_verdict(payload, next(verdicts, None))))
            raise AssertionError('Unexpected model purpose')

        client = OpenRouterClient('caller-model', budget or RunBudget(), transport=transport)
        return SemanticEngine(client, enable_repairs=True), requests

    def test_draft_compiles_bookkeeping_without_repeating_prose(self):
        draft = as_authoring(explanation())
        schema = authoring_schema()
        self.assertNotIn('grounding_records', schema['properties'])
        self.assertNotIn('focus_coverage', schema['properties'])
        ir, compact = decode_authoring(draft, evidence_pack())
        self.assertTrue(compact)
        self.assertEqual(ir.focus_coverage.focus, evidence_pack().focus)
        engine, requests = self.engine([draft])
        generated = engine.generate(evidence_pack())
        self.assertEqual(generated.validation.status.value, 'PASS')
        claims = learner_claims(generated.ir)
        self.assertEqual({r.claim_id: r.claim for r in generated.ir.grounding_records}, claims)
        self.assertTrue(any(p['messages'][0]['content'].startswith('Review the scientific') for p in requests))

    def test_schema_failure_is_revised_with_exact_field_diagnostic(self):
        good = as_authoring(explanation())
        bad = copy.deepcopy(good)
        bad['lesson_spec']['controls'][0].pop('learning_purpose')
        engine, requests = self.engine([bad, good])
        generated = engine.generate(evidence_pack())
        attempts = [p for p in requests if p['messages'][0]['content'].startswith('TASK:')]
        self.assertEqual(len(attempts), 2)
        feedback = json.loads(attempts[1]['messages'][-1]['content'])
        self.assertIn('learning_purpose', feedback['validation_feedback']['schema_error'])
        self.assertEqual(feedback['previous_candidate_UNTRUSTED_DATA'], bad)
        self.assertEqual(generated.calls, len(requests))

    def test_mathematical_mismatch_remains_a_failure_until_corrected(self):
        good = as_authoring(explanation())
        bad = copy.deepcopy(good)
        bad['computations'][0]['expression'] = 'a*x-b'
        engine, requests = self.engine([bad, good])
        generated = engine.generate(evidence_pack())
        self.assertEqual(generated.ir.computations[0].expression, 'a*x+b')
        self.assertEqual(generated.ir.computations[0].metadata['equation_refs'], ['eq-response'])
        self.assertNotEqual(generated.ir.metadata.get('equation_scope', {}).get('eq-response'), 'context_only')
        attempts = [p for p in requests if p['messages'][0]['content'].startswith('TASK:')]
        self.assertIn('EQUATION_COMPUTATION_MISMATCH', attempts[1]['messages'][-1]['content'])

    def test_semantic_rejection_triggers_revision_and_a_second_review(self):
        draft = as_authoring(explanation())
        rejection = {'status': 'UNSUPPORTED', 'issues': [
            {'target': 'science.concept', 'reason': 'Use the exact mechanism supported by the source.', 'evidence_refs': ['E1']}]}
        engine, requests = self.engine([draft, draft], [rejection, {'status': 'SUPPORTED', 'issues': []}])
        self.assertEqual(engine.generate(evidence_pack()).validation.status.value, 'PASS')
        reviews = [p for p in requests if p['messages'][0]['content'].startswith('Review the scientific')]
        self.assertEqual(len(reviews), 2)

    def test_repeated_bad_math_stops_after_three_attempts(self):
        draft = as_authoring(explanation())
        draft['computations'][0]['expression'] = '__import__("os")'
        engine, requests = self.engine([draft, draft, draft])
        with self.assertRaises(PlaygroundError) as caught:
            engine.generate(evidence_pack())
        self.assertEqual(caught.exception.failure.code, FailureCode.IR_INVALID)
        self.assertEqual(len(requests), 3)
        self.assertIn('DSL whitelist', caught.exception.failure.details['findings'][0]['message'])

    def test_revisions_never_make_an_eleventh_request(self):
        draft = as_authoring(explanation())
        draft['scientific_model']['concept'] = None
        engine, requests = self.engine([draft], budget=RunBudget(calls_used=9))
        with self.assertRaises(PlaygroundError):
            engine.generate(evidence_pack())
        self.assertEqual(engine.client.budget.calls_used, 10)
        self.assertEqual(len(requests), 1)

    def test_insufficient_evidence_can_expand_before_a_guided_revision(self):
        evidence = evidence_pack()
        initial = replace(evidence, evidence_blocks=evidence.evidence_blocks[:1])
        engine, requests = self.engine([{'status': 'insufficient_evidence'}, as_authoring(explanation())])
        recovered = []
        def recovery(current):
            recovered.append(current)
            return evidence
        generated = engine.generate(initial, evidence_recovery=recovery)
        self.assertEqual(generated.validation.status.value, 'PASS')
        self.assertEqual(recovered, [initial])
        attempts = [p for p in requests if p['messages'][0]['content'].startswith('TASK:')]
        revised_payload = json.loads(attempts[1]['messages'][1]['content'])
        self.assertEqual(len(revised_payload['evidence_UNTRUSTED_DATA']),
                         len(evidence.evidence_blocks))
