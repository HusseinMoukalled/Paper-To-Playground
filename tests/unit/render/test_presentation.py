import copy
import tempfile
import unittest
from dataclasses import replace
from html.parser import HTMLParser

from playground.computation.evaluator import compile_computations, execute
from playground.computation.validate import prepare_inputs
from playground.render.manifest import build_manifest
from playground.render.renderer import render_candidate, lesson_title
from playground.validation.artifact import validate_manifest, validate_artifact
from playground.validation.report import ValidationStatus
from tests.fixtures.dev2_factory import explanation


class LearnerText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = False
        self.text = []
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}: self.hidden = True
    def handle_endtag(self,tag):
        if tag in {'script','style'}: self.hidden = False
    def handle_data(self,data):
        if not self.hidden: self.text.append(data)


class PresentationTests(unittest.TestCase):
    def curve_ir(self):
        ir = explanation()
        return compile_computations(replace(ir,visuals=(replace(ir.visuals[0],visual_type='waveform',data_refs=('var-y','compute-response')),)))

    def test_aliases_deduplicate_visible_outputs_not_scientific_contract(self):
        ir = self.curve_ir()
        m = build_manifest(ir)
        self.assertEqual(m['presentation']['output_refs'],['var-y'])
        self.assertEqual(set(m['outputs']),{'var-y','compute-response'})
        with tempfile.TemporaryDirectory() as folder:
            path = render_candidate(ir,folder)
            self.assertEqual(validate_artifact(path,ir).status,ValidationStatus.PASS)
            text = path.read_text(encoding='utf-8')
            self.assertEqual(text.count('data-output-id="'),1)
            parsed = LearnerText()
            parsed.feed(text)
            visible = ' '.join(parsed.text)
            for internal in ('SOURCE_GROUNDED','compute-response','Claim-level grounding','Executable intermediate:','No sampled series'):
                self.assertNotIn(internal,visible)
            self.assertIn('SOURCE_GROUNDED',text)  # Kept in machine-readable provenance.

    def test_parameter_sweep_uses_only_existing_bounded_science(self):
        ir = self.curve_ir()
        sweep = build_manifest(ir)['visuals'][0]['sweep']
        self.assertLessEqual(len(sweep['sample_values']),81)
        for x in sweep['sample_values']:
            result,_ = execute(ir,prepare_inputs(ir,{sweep['control_id']:x},strict=True))
            self.assertAlmostEqual(result[sweep['output_ref']],2*x)

    def test_tampered_sweep_cannot_pass_static_gate(self):
        m = build_manifest(self.curve_ir())
        validate_manifest(m)
        for patch in ({'sample_values':[0,5]},{'sample_values':[2,1]},{'sample_values':[0,.15,4]},
                      {'output_ref':'var-x'},{'input_ref':'var-b'},{'x_label':'Unrelated quantity'},
                      {'sample_values':[float('nan'),4]}):
            with self.subTest(patch=patch):
                altered = copy.deepcopy(m)
                altered['visuals'][0]['sweep'].update(patch)
                with self.assertRaises(ValueError): validate_manifest(altered)

    def test_unsafe_sweep_retains_honest_scalar_visual(self):
        ir = self.curve_ir()
        # Default/presets are valid, but the full teaching range crosses a pole.
        computation = replace(ir.computations[0],expression='1/(a-0.5)+b',metadata={'bindings':{'a':'var-a','b':'var-b'},'equation_refs':[]})
        ir = compile_computations(replace(ir,computations=(computation,),scientific_model=replace(ir.scientific_model,invariants=())))
        m = build_manifest(ir)
        # a is unsafe; b remains a valid independent sweep.
        self.assertEqual(m['visuals'][0]['sweep']['input_ref'],'var-b')

    def test_long_concept_uses_explicit_focus_as_title(self):
        m = build_manifest(self.curve_ir())
        m['scientific_model']['concept']='A detailed mechanism explanation. '*8
        m['focus_coverage']['focus']='linear response'
        self.assertEqual(lesson_title(m),'Linear response')


if __name__ == '__main__':
    unittest.main()
