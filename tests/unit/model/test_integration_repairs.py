import json
import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from playground.budget import RunBudget
from playground.ir.serialization import to_mapping, restore_structural_defaults, decode
from playground.ir.models import ExplanationIR
from playground.ir.validate import validate_ir
from playground.model.client import OpenRouterClient
from playground.model.generation import SemanticEngine
from playground.model.structural_repair import normalize_wire_conventions, normalize_declared_inputs
from tests.fixtures.dev2_factory import explanation, evidence_pack
from tests.unit.model.test_client import response, TEST_KEY


class IntegrationRepairTests(unittest.TestCase):
    def test_unambiguous_symbol_and_claim_paths_preserve_text_and_lineage(self):
        ir = explanation()
        symbols = {v.display_symbol:ir.lesson_spec.symbol_explanations[v.id] for v in ir.scientific_model.variables}
        records = tuple(replace(r,claim_id=r.claim_id.replace('science.assumptions.0','science.assumptions.i0').replace('symbol.var-a','symbol.a')) for r in ir.grounding_records)
        control_vars = {c.id:c.scientific_variable for c in ir.lesson_spec.controls}
        explorations = tuple(replace(e,setup={control_vars[key]:value for key,value in e.setup.items()}) for e in ir.lesson_spec.guided_explorations)
        candidate = replace(ir,lesson_spec=replace(ir.lesson_spec,symbol_explanations=symbols,guided_explorations=explorations),grounding_records=records)
        restored,changes = normalize_wire_conventions(candidate)
        self.assertGreater(changes,0)
        self.assertEqual(restored,ir)

    def test_enum_formatting_and_null_container_defaults_remain_strict(self):
        data = to_mapping(explanation())
        data['scientific_model']['variables'][0]['knowledge_class'] = 'source_grounded'
        data['lesson_spec']['controls'][0]['options'] = None
        with self.assertRaises(ValueError): decode(ExplanationIR,data)
        self.assertEqual(decode(ExplanationIR,restore_structural_defaults(ExplanationIR,data)),explanation())

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':TEST_KEY})
    def test_missing_provenance_batches_preserve_science_and_valid_records(self):
        ir,evidence = explanation(),evidence_pack()
        removed = ir.grounding_records[:30]
        retained = ir.grounding_records[30:]
        candidate = replace(ir,grounding_records=retained)
        oracle = {r.claim_id:to_mapping(r) for r in removed}
        def transport(payload,*_):
            if payload['messages'][0]['content'].startswith('TASK:'):
                return response(json.dumps(to_mapping(candidate)))
            request = json.loads(payload['messages'][1]['content'])
            return response(json.dumps({'grounding_records':[oracle[k] for k in request['missing_claims']]}))
        client = OpenRouterClient('caller-model',RunBudget(),transport=transport)
        generated = SemanticEngine(client,enable_repairs=True).generate(evidence)
        self.assertEqual(client.budget.calls_used,3)
        self.assertEqual(generated.ir.scientific_model,ir.scientific_model)
        self.assertTrue(all(record in generated.ir.grounding_records for record in retained))
        self.assertEqual(generated.validation.status.value,'PASS')

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':TEST_KEY})
    def test_provenance_repair_cannot_rewrite_scientific_claim(self):
        ir = explanation()
        candidate = replace(ir,grounding_records=ir.grounding_records[1:])
        wrong = replace(ir.grounding_records[0],claim='An unrelated invented claim.')
        replies = iter([json.dumps(to_mapping(candidate)),json.dumps({'grounding_records':[to_mapping(wrong)]})])
        client = OpenRouterClient('caller-model',RunBudget(),transport=lambda *_: response(next(replies)))
        from playground.failures import PlaygroundError
        with self.assertRaises(PlaygroundError): SemanticEngine(client,enable_repairs=True).generate(evidence_pack())
        self.assertEqual(candidate.scientific_model,ir.scientific_model)

    def test_equation_aliases_still_reject_mathematical_changes(self):
        ir = explanation()
        variables = tuple(replace(v,source_symbol='source_'+v.source_symbol) for v in ir.scientific_model.variables)
        renamed = replace(ir,scientific_model=replace(ir.scientific_model,variables=variables))
        self.assertEqual(validate_ir(renamed,evidence_pack()).status.value,'PASS')
        bad = replace(renamed,computations=(replace(renamed.computations[0],expression='a*x-b'),))
        self.assertEqual(validate_ir(bad,evidence_pack()).status.value,'FAIL')

    def test_degenerate_control_fallback_retains_fixed_value_and_two_controls(self):
        ir = explanation()
        fixed = replace(ir.lesson_spec.controls[0],id='control-x',scientific_variable='var-x',minimum=2,maximum=2,default=2)
        candidate = replace(ir,lesson_spec=replace(ir.lesson_spec,controls=ir.lesson_spec.controls+(fixed,)))
        restored,changes = normalize_declared_inputs(candidate)
        self.assertEqual(len(restored.lesson_spec.controls),2)
        self.assertEqual(restored.metadata['defaults']['var-x'],2)
        self.assertEqual(changes,1)
