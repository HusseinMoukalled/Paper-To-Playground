"""A human-authored linear oracle for the small authoring/compiler boundary."""
import copy
import json
import os
import unittest
from unittest.mock import patch

from playground.computation.evaluator import execute, compile_computations
from playground.computation.validate import prepare_inputs
from playground.ir.validate import validate_ir
from playground.model.lesson_plan import compile_plan
from playground.model.generation import SemanticEngine
from playground.model.client import OpenRouterClient
from playground.budget import RunBudget
from playground.failures import PlaygroundError
from tests.fixtures.dev2_factory import evidence_pack
from tests.unit.model.test_client import response, TEST_KEY, scientific_verdict


def plan():
    def input_value(name, value, editable):
        return {'name': name, 'label': name, 'meaning': 'Toy linear input ' + name,
                'type': 'scalar', 'domain': 'real', 'value': value, 'editable': editable,
                'minimum': 0 if editable else None, 'maximum': 4 if editable else None,
                'step': 0.1 if editable else None, 'units': None, 'evidence_refs': ['E1']}
    return {'title': 'Linear response', 'purpose': 'Explain gain and offset.',
            'scope': 'Illustrative inputs, no experiments.', 'intuition': 'Scale and then translate.',
            'learning_objectives': ['Explain how gain and offset affect output.'],
            'prerequisites': ['Algebra'], 'assumptions': ['Idealized linear response.'],
            'limitations': ['No saturation.'], 'misconception': 'Gain and offset are different.',
            'edge_cases': ['Zero gain removes input sensitivity.'], 'evidence_refs': ['E1', 'E2'],
            'inputs': [input_value('a', 1, True), input_value('b', 0, True), input_value('x', 2, False)],
            'steps': [{'name': 'y', 'label': 'y', 'expression': 'a*x+b', 'meaning': 'Scaled input plus offset.',
                       'type': 'scalar', 'domain': 'real', 'units': None, 'evidence_refs': ['E1']}],
            'invariants': ['approx_equal(y,a*x+b)'],
            'visuals': [{'type': 'scalar', 'question': 'How does y change?', 'refs': ['y']}],
            'explorations': [{'title': 'Baseline', 'setup': {'a': 1, 'b': 0}, 'observe': 'Output is two.',
                              'why': 'Unit gain preserves the input.'},
                             {'title': 'Contrast', 'setup': {'a': 2, 'b': 1}, 'observe': 'Output is five.',
                              'why': 'Scaling and offset both increase output.'}]}


class LessonPlanTests(unittest.TestCase):
    def test_compiled_lesson_executes_both_independent_oracle_setups(self):
        ir = compile_plan(plan(), evidence_pack())
        self.assertEqual(validate_ir(ir, evidence_pack()).status.value, 'PASS')
        ir = compile_computations(ir)
        self.assertEqual(execute(ir, prepare_inputs(ir))[0]['var-y'], 2)
        self.assertEqual(execute(ir, prepare_inputs(ir, ir.lesson_spec.guided_explorations[1].setup))[0]['var-y'], 5)
        self.assertEqual(ir.computations[0].metadata['bindings'], {'a': 'var-a', 'b': 'var-b', 'x': 'var-x'})

    def test_unknown_names_and_duplicate_names_are_actionable_errors(self):
        bad = plan()
        bad['steps'][0]['expression'] = 'unknown*x+b'
        with self.assertRaisesRegex(ValueError, 'unknown identifiers'):
            compile_plan(bad, evidence_pack())
        bad = plan()
        bad['steps'][0]['name'] = 'a'
        with self.assertRaisesRegex(ValueError, 'unique safe'):
            compile_plan(bad, evidence_pack())

    def test_exploration_observations_come_from_execution_not_model_predictions(self):
        from playground.model.observations import calculated_observations
        from playground.ir.grounding import validate_grounding
        draft = plan()
        draft['explorations'][1]['observe'] = 'Output is a fabricated 999.'
        ir = calculated_observations(compile_computations(compile_plan(draft, evidence_pack())))
        self.assertIn('y = 5', ir.lesson_spec.guided_explorations[1].observe)
        self.assertIn('starting value: 2', ir.lesson_spec.guided_explorations[1].observe)
        self.assertNotIn('999', ir.lesson_spec.guided_explorations[1].observe)
        self.assertFalse(validate_grounding(ir, evidence_pack()))

    def test_compiler_adds_a_computed_visual_for_a_missing_control_path(self):
        draft = plan()
        draft['steps'][0]['expression'] = 'a*x'
        draft['steps'][0]['meaning'] = 'Scaled input before the offset.'
        draft['steps'].append({**draft['steps'][0], 'name': 'z', 'label': 'z',
                              'expression': 'y+b', 'meaning': 'Scaled input plus offset.'})
        draft['invariants'] = ['approx_equal(z,a*x+b)']
        ir = compile_plan(draft, evidence_pack())
        self.assertEqual(len(ir.visuals), 2)
        self.assertEqual(ir.visuals[-1].data_refs, ('var-z',))
        self.assertEqual(validate_ir(ir, evidence_pack()).status.value, 'PASS')

    @patch.dict(os.environ, {'OPENROUTER_API_KEY': TEST_KEY})
    def test_evidence_review_is_mandatory_for_compiled_plans_and_rejects_bad_math(self):
        bad = plan()
        bad['steps'][0]['expression'] = 'a*x-b'
        bad['invariants'] = []
        candidates = iter([bad, plan()])
        requests = []
        def transport(payload, *_):
            requests.append(payload)
            if payload['messages'][0]['content'].startswith('TASK:'):
                return response(json.dumps(next(candidates)))
            if len(requests) == 2:
                return response(json.dumps(scientific_verdict(payload, {'status': 'UNSUPPORTED', 'issues': [
                    {'target': 'compute-y', 'reason': 'Offset must be added to the product.', 'evidence_refs': ['E1']}]})))
            return response(json.dumps(scientific_verdict(payload)))
        client = OpenRouterClient('caller-model', RunBudget(), transport=transport)
        result = SemanticEngine(client, enable_repairs=True).generate(evidence_pack())
        self.assertEqual(result.ir.computations[0].expression, 'a*x+b')
        self.assertEqual(len(requests), 4)
        feedback = json.loads(requests[2]['messages'][-1]['content'])
        self.assertEqual(feedback['previous_candidate_UNTRUSTED_DATA'], bad)

    def test_false_boolean_control_cannot_be_used_as_scalar_science(self):
        bad = plan()
        bad['inputs'][0]['value'] = True
        self.assertEqual(validate_ir(compile_plan(bad, evidence_pack()), evidence_pack()).status.value, 'FAIL')

    def test_explicit_editable_symbol_list_cannot_be_replaced_with_fixed_inputs(self):
        from dataclasses import replace
        evidence = replace(evidence_pack(), focus='Explain the response with editable a, b and x inputs.')
        bad = plan()
        report = validate_ir(compile_plan(bad, evidence), evidence)
        self.assertTrue(any('editable x' in f.message for f in report.findings))
        bad['inputs'][2].update(editable=True, minimum=0, maximum=4, step=0.1)
        self.assertEqual(validate_ir(compile_plan(bad, evidence), evidence).status.value, 'PASS')

    @patch.dict(os.environ, {'OPENROUTER_API_KEY': TEST_KEY})
    def test_reviewer_cannot_skip_checks_or_hide_an_unsupported_check(self):
        from playground.model.scientific_review import review_lesson
        def omitted(payload, *_):
            reply = scientific_verdict(payload)
            reply['checks'].pop('compute-y')
            return response(json.dumps(reply))
        with self.assertRaisesRegex(ValueError, 'omitted a required'):
            review_lesson(OpenRouterClient('caller-model', RunBudget(), transport=omitted),
                          compile_plan(plan(), evidence_pack()), evidence_pack())
        def hidden(payload, *_):
            reply = scientific_verdict(payload)
            reply['checks']['compute-y']['supported'] = False
            return response(json.dumps(reply))
        with self.assertRaisesRegex(ValueError, 'must have actionable issues'):
            review_lesson(OpenRouterClient('caller-model', RunBudget(), transport=hidden),
                          compile_plan(plan(), evidence_pack()), evidence_pack())

    @patch.dict(os.environ, {'OPENROUTER_API_KEY': TEST_KEY})
    def test_default_specific_invariant_receives_a_bounded_predicate_revision(self):
        bad = plan()
        bad['invariants'] = ['approx_equal(a,1)']
        replies = iter([bad, {'invariants': ['approx_equal(y,a*x+b)']}, {'status': 'SUPPORTED', 'issues': []}])
        requests = []
        def transport(payload, *_):
            requests.append(payload)
            reply = next(replies)
            if 'status' in reply:
                reply = scientific_verdict(payload, reply)
            return response(json.dumps(reply))
        client = OpenRouterClient('caller-model', RunBudget(), transport=transport)
        result = SemanticEngine(client, enable_repairs=True).generate(evidence_pack())
        self.assertEqual(result.ir.computations[0].expression, 'a*x+b')
        revision_schema = requests[1]['response_format']['json_schema']['schema']
        self.assertEqual(set(revision_schema['properties']), {'invariants'})
        self.assertEqual(result.ir.scientific_model.invariants, ('approx_equal(y,a*x+b)',))


if __name__ == '__main__':
    unittest.main()
