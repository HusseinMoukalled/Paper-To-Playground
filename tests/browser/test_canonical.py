"""Python 3.11 science -> real Chromium parity and canonical interaction tests."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from dataclasses import replace

from playground.computation.parser import parse
from playground.computation.evaluator import evaluate, compile_computations, execute
from playground.computation.operations import OPERATIONS
from playground.computation.validate import prepare_inputs
from playground.render.renderer import render_candidate
from playground.validation.browser import discover_chromium, alternative_values, close_enough
from tests.fixtures.dev2_factory import explanation


@unittest.skipUnless(os.environ.get('PLAYGROUND_NODE') and os.environ.get('NODE_PATH'), 'Optional existing Node browser verifier not configured')
class CanonicalBrowserTests(unittest.TestCase):
    def verify(self, ir, expressions=()):
        ir = compile_computations(ir)
        with tempfile.TemporaryDirectory() as folder:
            artifact = render_candidate(ir, folder)
            cases, expected = [], []
            for expression in expressions:
                node = parse(expression)
                cases.append({'ast': node.to_dict(), 'env': {}})
                try: expected.append({'value': evaluate(node, {})})
                except (ValueError, ArithmeticError): expected.append({'rejected': True})
            default = execute(ir, prepare_inputs(ir, strict=True))[0]
            probes = []
            from playground.ir.serialization import to_mapping
            for i, control in enumerate(ir.lesson_spec.controls):
                for value in alternative_values(to_mapping(control)):
                    if value == control.default: continue
                    values = execute(ir, prepare_inputs(ir, {control.id: value}))[0]
                    probes.append({'control_index': i, 'kind': control.control_type, 'value': value, 'expected': values})
            payload = {'artifact': str(artifact.resolve()), 'executable': str(discover_chromium()[0]),
                       'cases': cases, 'baseline': default, 'probes': probes,
                       'presets': [execute(ir, prepare_inputs(ir, e.setup))[0] for e in ir.lesson_spec.guided_explorations]}
            result = subprocess.run([os.environ['PLAYGROUND_NODE'], str(Path(__file__).with_name('node_verify.cjs'))],
                                    input=json.dumps(payload), capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(result.stdout)
            self.assertEqual(actual['status'], 'PASS')
            for a, e in zip(actual['parity'], expected): self.assertTrue(close_enough(a, e), (a, e))

    def test_all_canonical_operations_nodes_invalid_domains_and_ui(self):
        samples = ['add(2,3)','subtract(2,3)','multiply([1,2],2)','divide(3,2)','power(2,3)',
                   'negate([1,-2])','abs(-2)','sqrt(9)','exp(1)','log(2)','sin(1)','cos(1)',
                   'sum([[1,2],[3,4]])','mean([[1,2],[3,4]])','min([1,2])','max([1,2])',
                   'dot([1,2],[3,4])','matmul([[1,2],[3,4]],[2,3])','transpose([[1,2],[3,4]])',
                   'norm([3,4])','normalize([3,4])','softmax([1000,1001])','entropy([0,1])','approx_equal(1,1)',
                   '2 if 1 < 2 else 4','not False','True and False','True or False','[1,2][0]',
                   'sum([1e16,1,-1e16])','sqrt(-1)','log(0)','divide(1,0)','normalize([0,0])',
                   'matmul([1,2],[1,2])','power(2,129)','exp(10000)','add([[1],[2]],[1,2])',
                   'True == 1', 'True < 1', '\"1\" < 2', '1 == 1.0']
        self.assertEqual(set(OPERATIONS), {s.split('(')[0] for s in samples[:24]})
        self.verify(explanation(), samples)

    def test_declarative_iteration_in_browser(self):
        ir = explanation()
        computation = replace(ir.computations[0], expression='s', metadata={
            'kind': 'iteration', 'bindings': {'a':'var-a','b':'var-b','x':'var-x'},
            'initial': {'s':'x'}, 'updates': {'s':'s+a+b'}, 'steps':4,
            'state_specs': {'s': {'type':'scalar','shape':[],'domain':'nonnegative'}}, 'state_invariants':['s >= 0']})
        ir = replace(ir, computations=(computation,))
        ir = replace(ir, scientific_model=replace(ir.scientific_model, invariants=()))
        self.verify(ir)

    def test_matrix_and_distribution_controls_use_python_semantics(self):
        for distribution in (False, True):
            ir = explanation()
            variables = list(ir.scientific_model.variables)
            default = [1,2] if distribution else [[1,2],[3,4]]
            variables[0] = replace(variables[0], type='vector' if distribution else 'matrix', shape=(2,) if distribution else (2,2))
            variables[3] = replace(variables[3], type='distribution' if distribution else 'vector', shape=(2,))
            controls = list(ir.lesson_spec.controls)
            controls[0] = replace(controls[0], control_type='vector' if distribution else 'matrix', default=default, minimum=-4 if distribution else 0)
            controls[1] = replace(controls[1], default=1)
            if not distribution:
                variables[2] = replace(variables[2], type='vector', shape=(2,))
            expression = 'softmax(a*b)' if distribution else 'matmul(a,x)*b'
            bindings = {'a':'var-a','b':'var-b'} if distribution else {'a':'var-a','x':'var-x','b':'var-b'}
            computation = replace(ir.computations[0], expression=expression, output_type='distribution' if distribution else 'vector',
                                  input_refs=tuple(bindings.values()), metadata={'bindings':bindings,'equation_refs':[]})
            presets = tuple(replace(e, setup={'control-a':default,'control-b':i+1}) for i,e in enumerate(ir.lesson_spec.guided_explorations))
            ir = replace(ir, scientific_model=replace(ir.scientific_model, variables=tuple(variables), invariants=()),
                         lesson_spec=replace(ir.lesson_spec, controls=tuple(controls), guided_explorations=presets),
                         computations=(computation,), metadata={**ir.metadata,'defaults':{'var-x':2 if distribution else [2,3]},
                                                              'mechanism_family':'distribution' if distribution else 'matrix_transformation'})
            self.verify(ir)

    def test_declarative_state_transition_in_browser(self):
        ir = explanation()
        variables = tuple(replace(v,type='state') if v.id=='var-y' else v for v in ir.scientific_model.variables)
        computation = replace(ir.computations[0], expression='state', output_type='state', input_refs=('var-a','var-b'), metadata={
            'kind':'state_transition','bindings':{'a':'var-a','b':'var-b'},'states':['rest','active'],
            'initial_state':'rest','steps':2,'transitions':[{'from':'rest','to':'active','when':'a > b'},
                                                         {'from':'active','to':'rest','when':'a <= b'}]})
        presets = (ir.lesson_spec.guided_explorations[0], replace(ir.lesson_spec.guided_explorations[1],setup={'control-a':0,'control-b':2}))
        ir = replace(ir,scientific_model=replace(ir.scientific_model,variables=variables,invariants=()),
                     lesson_spec=replace(ir.lesson_spec,guided_explorations=presets),computations=(computation,),
                     metadata={**ir.metadata,'mechanism_family':'state_transition'})
        self.verify(ir)
