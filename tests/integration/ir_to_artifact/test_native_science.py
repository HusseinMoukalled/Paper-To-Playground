"""Verify the actual Dev2 canonical wire contract against installed Chromium."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from playground.computation.evaluator import compile_computations, evaluate, execute, execute_spec
from playground.computation.parser import parse
from playground.ir.models import ComputationSpec
from playground.render.manifest import build_manifest
from playground.render.pipeline import build_artifact
from playground.render.renderer import render_candidate
from playground.validation.browser import chromium_session, BrowserUnavailable, close_enough
from tests.fixtures.dev2_factory import explanation


class NativeScienceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.ir = compile_computations(explanation())
        cls.path = render_candidate(cls.ir, cls.directory.name)
        cls.session = chromium_session()
        try:
            cls.browser = cls.session.__enter__()
        except BrowserUnavailable as exc:
            cls.directory.cleanup()
            raise unittest.SkipTest(str(exc))
        cls.page = cls.browser.new_page()
        cls.page.goto(cls.path.as_uri())

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None, None, None)
        cls.directory.cleanup()

    def test_real_dev2_ir_promotes_with_python_parity(self):
        def reference(inputs):
            return {k:v for k,v in execute(self.ir, inputs)[0].items() if k.startswith('var-')}
        with tempfile.TemporaryDirectory() as out:
            result = build_artifact(self.ir, out, reference_evaluator=reference, browser=self.browser)
            self.assertTrue(result.promoted, result.report)
            self.assertEqual(result.report.status.value, 'PASS')

    def test_native_operations_and_representative_precision(self):
        expressions = [
            '2+3', '2-3', '2*3', '6/3', '2**3', '-2', 'abs(-2)', 'sqrt(4)', 'exp(0)', 'log(1)',
            'sin([0,1])', 'cos(0)', 'sum([[1,2],[3,4]])', 'mean([[1,2],[3,4]])',
            'sum([1e16,1,-1e16])', 'min([1,3])', 'max([1,3])', 'dot([1,2],[3,4])',
            'matmul([[1,2],[3,4]],[2,1])', 'matmul([[1,0],[0,1]],[[1,2],[3,4]])',
            'transpose([[1,2]])', 'norm([3,4])', 'normalize([3,4])', 'normalize([-3,4])',
            'softmax([10000,10001,9999])', 'entropy([1,0])', 'entropy([0.5,0.5])',
            'xlogx([0,0.25,0.75,1])', 'take([1,2,3,4],2)',
            'cross_entropy([0.5,0.5],[0.5,0.5])', 'cross_entropy([0,1],[0,1])',
            '-sum(xlogx([0.25,0.25,0.25,0.25]))/log(2)',
            'approx_equal([1,2],[1,2.000000001])', '1 if True else log(-1)',
            '[1,2][0]', 'True == 1', '1>0 and 2<3', 'not False',
        ]
        for expression in expressions:
            with self.subTest(expression=expression):
                node = parse(expression)
                observed = self.page.evaluate('(n)=>ScientificCanonical.evaluateNode(n,{})', node.to_dict())
                self.assertTrue(close_enough(observed, evaluate(node, {})), (expression, observed))

    def test_continuous_slider_preserves_off_grid_default_and_preset(self):
        ir = explanation()
        controls = (replace(ir.lesson_spec.controls[0], default=2**0.5), ir.lesson_spec.controls[1])
        explorations = (replace(ir.lesson_spec.guided_explorations[0],
                                setup={'control-a': 2**0.5, 'control-b': 0}),
                        replace(ir.lesson_spec.guided_explorations[1],
                                setup={'control-a': 1/3, 'control-b': 1}))
        ir = compile_computations(replace(ir, lesson_spec=replace(ir.lesson_spec, controls=controls,
                                                                 guided_explorations=explorations)))
        with tempfile.TemporaryDirectory() as out:
            result = build_artifact(ir, out, browser=self.browser,
                                    reference_evaluator=lambda inputs: execute(ir, inputs)[0])
            self.assertTrue(result.promoted, result.report)

    def test_array_probes_and_reset_with_duplicate_model_test_values(self):
        ir = explanation()
        identity = [[1, 0], [0, 1]]
        types = {'var-a': ('matrix', (2, 2)), 'var-b': ('vector', (2,)),
                 'var-x': ('vector', (2,)), 'var-y': ('vector', (2,))}
        variables = tuple(replace(v, type=types[v.id][0], shape=types[v.id][1])
                          for v in ir.scientific_model.variables)
        equation = replace(ir.scientific_model.equations[0], expression='matmul(a,x)+b')
        controls = (replace(ir.lesson_spec.controls[0], control_type='matrix', default=identity),
                    replace(ir.lesson_spec.controls[1], control_type='vector', default=[0, 0]))
        explorations = (replace(ir.lesson_spec.guided_explorations[0],
                               setup={'control-a': identity, 'control-b': [0, 0]}),
                        replace(ir.lesson_spec.guided_explorations[1],
                               setup={'control-a': [[2, 0], [0, 2]], 'control-b': [1, 1]}))
        ir = replace(ir, scientific_model=replace(ir.scientific_model, variables=variables, equations=(equation,),
                                                  invariants=('approx_equal(y,matmul(a,x)+b)',)),
                     lesson_spec=replace(ir.lesson_spec, controls=controls, guided_explorations=explorations),
                     computations=(replace(ir.computations[0], expression='matmul(a,x)+b', output_type='vector'),),
                     metadata={**ir.metadata, 'defaults': {'var-x': [1, 2]},
                               'control_test_values': {'control-a': [identity, identity], 'control-b': [[0, 0]]}})
        from playground.computation.validate import validate_computation
        ir = compile_computations(ir)
        self.assertEqual(validate_computation(ir).status.value, 'PASS')
        with tempfile.TemporaryDirectory() as out:
            result = build_artifact(ir, out, browser=self.browser,
                                    reference_evaluator=lambda inputs: execute(ir, inputs)[0])
            self.assertTrue(result.promoted, result.report)

    def test_invalid_domains_shapes_and_types_reject_in_both_runtimes(self):
        for expression in ('log(0)', 'sqrt(-1)', '1/0', 'normalize([0,0])', 'matmul([1,2],[1,2])',
                           '[[1,2],[3,4]]+[1,2]', 'softmax([[1]])', '2**129', 'entropy([0.2,0.2])',
                           'xlogx(-0.1)', 'take([1,2],0)', 'take([1,2],3)', 'take([1,2],1.5)',
                           'cross_entropy([0.5,0.5],[1,0])', 'cross_entropy([1],[0.5,0.5])'):
            with self.subTest(expression=expression):
                node = parse(expression)
                with self.assertRaises((ValueError, ZeroDivisionError, OverflowError)):
                    evaluate(node, {})
                accepted = self.page.evaluate('(n)=>{try{ScientificCanonical.evaluateNode(n,{});return true}catch(e){return false}}', node.to_dict())
                self.assertFalse(accepted)

    def test_iteration_and_state_history_parity(self):
        specs = [ComputationSpec('compute-iterate', 's', 'scalar', metadata={
            'kind':'iteration', 'bindings':{'factor':'var-a'}, 'initial':{'s':'1'},
            'updates':{'s':'s*factor'}, 'steps':4, 'state_invariants':['s>=0']}),
            ComputationSpec('compute-state', '', 'state', metadata={
                'kind':'state_transition', 'states':['off','on'], 'initial_state':'off', 'steps':2,
                'bindings':{'factor':'var-a'}, 'transitions':[{'from':'off','to':'on','when':'factor>0'}]})]
        for spec in specs:
            compiled = compile_computations(replace(explanation(), computations=(spec,))).computations[0]
            wrapper = {'type':'Canonical', 'metadata':compiled.metadata, 'output_type':compiled.output_type}
            observed = self.page.evaluate('(n)=>ScientificCanonical.execute(n,{"var-a":0.5})', wrapper)
            value, history = execute_spec(compiled, {'factor':0.5})
            self.assertTrue(close_enough(observed, {'value':value, 'history':history}))

    def test_failed_browser_gate_preserves_previous_artifact(self):
        from playground.validation.report import ValidationReport, ValidationStatus
        with tempfile.TemporaryDirectory() as out:
            path = Path(out)/'index.html'
            path.write_text('last valid artifact', encoding='utf-8')
            with patch('playground.render.pipeline.validate_browser', return_value=ValidationReport(ValidationStatus.FAIL)):
                result = build_artifact(self.ir, out)
            self.assertFalse(result.promoted)
            self.assertEqual(path.read_text(encoding='utf-8'), 'last valid artifact')

    def test_variable_and_computation_refs_adapt_without_rewriting_ir(self):
        manifest = build_manifest(self.ir)
        self.assertEqual(manifest['visuals'][0]['data_refs'], ['var-y'])
        self.assertEqual(self.ir.visuals[0].data_refs, ('compute-response',))
        self.assertEqual(manifest['initial_state']['var-x'], 2)
        self.assertTrue(manifest['invariant_programs'])
