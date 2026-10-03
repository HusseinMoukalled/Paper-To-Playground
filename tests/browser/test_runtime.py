from __future__ import annotations

import json
import math
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from playground.render.renderer import render_candidate
from playground.render.pipeline import build_artifact
from playground.trace import TraceWriter
from playground.render.visual_planner import FAMILIES
from playground.validation.browser import BrowserUnavailable, chromium_session, close_enough, validate_browser
from playground.validation.report import ValidationStatus
from playground.ir.models import ScientificVariable
from tests.fixtures.runtime_fixtures import binary, call, constant, control_fixture, fixture_ir, matrix, reference, variable, vector


class BrowserRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = chromium_session()
        try:
            cls.browser = cls.session.__enter__()
        except BrowserUnavailable as exc:
            if os.environ.get('PLAYGROUND_REQUIRE_BROWSER') == '1':
                raise RuntimeError('Browser tests were required but Chromium is unavailable') from exc
            raise unittest.SkipTest(str(exc)) from exc

    @classmethod
    def tearDownClass(cls):
        cls.session.__exit__(None, None, None)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.context = self.browser.new_context(offline=True)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        self.context.close()
        self.temp.cleanup()

    def load(self, ir=None):
        path = render_candidate(ir or fixture_ir(), self.temp.name)
        self.page.goto(path.resolve().as_uri())
        self.assertTrue(self.page.evaluate('document.documentElement.dataset.runtimeReady === "true"'), self.errors)
        return path

    def test_ast_operations_and_nodes_match_independent_python_fixtures(self):
        self.load()
        fixtures = json.loads((Path(__file__).parents[1] / 'fixtures/ast_parity.json').read_text(encoding='utf-8'))
        for case in fixtures:
            with self.subTest(case=case['name']):
                actual = self.page.evaluate('(arg)=>ScientificAST.evaluate(arg.ast,arg.state)', case)
                self.assertTrue(close_enough(actual, case['expected']), (actual, case['expected']))
        self.assertEqual(set(self.page.evaluate('ScientificAST.operations')), {case['name'] for case in fixtures if case['operation']})

    def test_ast_invalid_numeric_shape_arity_index_and_unknown_operation(self):
        self.load()
        cases = [binary('/', constant(1), constant(0)), call('sqrt', constant(-1)),
                 call('log', constant(0)), call('exp', constant(10000)),
                 call('normalize', vector(constant(0), constant(0))),
                 call('dot', vector(constant(1)), vector(constant(1), constant(2))),
                 call('unknown', constant(1)), call('sum', constant(1)), call('sqrt', constant(1), constant(2)),
                 {'type': 'Index', 'value': vector(constant(2)), 'index': constant(-1)},
                 {'type': 'Conditional', 'condition': constant(2), 'then': constant(1), 'else': constant(2)}]
        for ast in cases:
            result = self.page.evaluate('(ast)=>{try{ScientificAST.evaluate(ast,{});return false}catch(e){return true}}', ast)
            self.assertTrue(result, ast)

    def test_equation_display_is_derived_from_ast_and_current_substitution(self):
        self.load()
        tests = [call('sqrt', constant(9)), binary('/', constant(3), constant(2)), binary('**', constant(2), constant(3)),
                 call('sum', vector(constant(1), constant(2))), matrix([[constant(1), constant(2)]]),
                 {'type': 'Index', 'value': variable('var-x'), 'index': constant(0)}]
        for tree in tests:
            self.assertTrue(self.page.evaluate('(ast)=>ScientificAST.equation(ast)', tree))
        for tree, tag in zip(tests, ['msqrt', 'mfrac', 'msup', 'mo', 'mtable', 'msub']):
            self.assertIn('<' + tag, self.page.evaluate('(ast)=>ScientificAST.math(ast,{}).outerHTML', tree))
        self.page.locator('[data-control-id]').nth(0).fill('3')
        self.page.locator('[data-control-id]').nth(0).dispatch_event('change')
        self.assertIn('3 × 2', self.page.locator('[data-role="substitution"]').nth(0).text_content())
        self.assertEqual(self.page.locator('[data-output-id="var-product"]').text_content(), '6')
        self.assertEqual(self.page.locator('[data-output-id="var-result"]').text_content(), '9')

    def test_global_state_preset_and_reset_transaction(self):
        self.load()
        baseline = self.page.evaluate('PlaygroundRuntime.snapshot()')
        self.page.locator('[data-role="apply-setup"]').nth(1).click()
        state = self.page.evaluate('PlaygroundRuntime.snapshot()')
        self.assertEqual(state['state']['var-x'], 3)
        self.assertEqual(state['state']['var-result'], 9)
        self.assertEqual(state['ui']['exploration'], 'explore-contrast')
        self.page.locator('[data-role="reset"]').click()
        self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot()'), baseline)
        # Undefined arithmetic is rejected atomically even with finite inputs.
        result = self.page.evaluate('()=>{const before=PlaygroundRuntime.snapshot();try{PlaygroundRuntime.apply({"var-x":0})}catch(e){}return {before,after:PlaygroundRuntime.snapshot()}}')
        self.assertEqual(result['before'], result['after'])

    def test_invalid_input_policies_and_native_domains(self):
        for policy in ('reject', 'warn', 'clamp'):
            ir = fixture_ir()
            c = replace(ir.lesson_spec.controls[0], validation_rule=policy)
            ir = replace(ir, lesson_spec=replace(ir.lesson_spec, controls=(c, ir.lesson_spec.controls[1])))
            self.load(ir)
            input_el = self.page.locator('[data-control-id]').nth(0)
            self.assertEqual(input_el.get_attribute('min'), '0.5')
            self.assertEqual(input_el.get_attribute('max'), '4')
            input_el.fill('99'); input_el.dispatch_event('change')
            state = self.page.evaluate('PlaygroundRuntime.snapshot()')
            self.assertEqual(state['state']['var-x'], 4 if policy == 'clamp' else 1)
            self.assertIn('clamped' if policy == 'clamp' else 'invalid', self.page.locator('[data-role="status"]').text_content())
            input_el.fill(''); input_el.dispatch_event('change')
            self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().state["var-x"]'), state['state']['var-x'])

    def test_all_generic_visual_families_change_scientifically(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                path = render_candidate(fixture_ir(family), Path(self.temp.name) / family)
                validation = validate_browser(path, reference_evaluator=reference(family), browser=self.browser)
                self.assertEqual(validation.status, ValidationStatus.PASS, validation.findings)

    def test_stepper_and_comparison_are_reset(self):
        for family in ('iterative_process', 'comparison'):
            self.load(fixture_ir(family))
            baseline = self.page.evaluate('PlaygroundRuntime.snapshot()')
            if family == 'iterative_process':
                self.page.locator('[data-role="step-next"]').click()
                self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().ui.step'), 1)
            else:
                self.page.locator('[data-role="save-comparison"]').click()
                self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().ui.comparison'), baseline['state'])
                self.page.evaluate('PlaygroundRuntime.apply({"var-x":3})')
                self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().ui.comparison'), baseline['state'])
            self.page.locator('[data-role="reset"]').click()
            self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot()'), baseline)

    def test_accessible_keyboard_and_responsive_offline_file_protocol(self):
        self.load()
        self.assertTrue(self.page.url.startswith('file:///'))
        self.page.locator('[data-control-id]').nth(0).focus()
        self.page.keyboard.press('ArrowUp')
        self.page.keyboard.press('Tab')
        self.assertTrue(self.page.evaluate('document.activeElement !== document.body'))
        self.assertEqual(self.page.evaluate('getComputedStyle(document.activeElement).outlineStyle'), 'solid')
        for width in (320, 375, 768, 1280):
            self.page.set_viewport_size({'width': width, 'height': 900})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
        self.assertEqual(self.errors, [])

    def test_browser_validator_detects_injected_runtime_failures(self):
        injected = {
            'BROWSER_DEAD_CONTROL': "const el=document.querySelector('[data-control-id]');el.replaceWith(el.cloneNode(true));",
            'BROWSER_DEAD_VISUAL': "const previous=ScientificVisuals;globalThis.ScientificVisuals={render:(el,s,state,ui)=>{const old=el.innerHTML;previous.render(el,s,state,ui);el.innerHTML=old;}};",
            'BROWSER_STALE_NUMBER': "document.querySelector('[data-output-id]').textContent='stale';",
            'BROWSER_JS_ERROR': "throw new Error('Injected runtime error');",
            'BROWSER_RESET_FAILED': "const el=document.querySelector('[data-role=reset]');el.replaceWith(el.cloneNode(true));",
            'BROWSER_PRESET_FAILED': "const el=document.querySelector('[data-role=apply-setup]');el.replaceWith(el.cloneNode(true));",
        }
        for expected, code in injected.items():
            with self.subTest(expected=expected):
                path = render_candidate(fixture_ir(), Path(self.temp.name) / expected)
                source = path.read_text(encoding='utf-8')
                path.write_text(source.replace('</body>', '<script>' + code + '</script></body>'), encoding='utf-8')
                validation = validate_browser(path, reference_evaluator=reference('scalar_relationship'), browser=self.browser)
                self.assertEqual(validation.status, ValidationStatus.FAIL)
                self.assertIn(expected, [f.code for f in validation.findings], validation.findings)

    def test_mismatching_python_reference_fails_parity_gate(self):
        path = self.load()
        validation = validate_browser(path, reference_evaluator=lambda inputs: {'var-product': -1, 'var-result': -1}, browser=self.browser)
        self.assertEqual(validation.status, ValidationStatus.FAIL)
        self.assertIn('BROWSER_COMPUTATION_PARITY', [f.code for f in validation.findings])

    def test_vector_normalization_matrix_edit_and_categorical_controls(self):
        for kind in ('vector', 'matrix', 'categorical'):
            with self.subTest(kind=kind):
                self.load(control_fixture(kind))
                control = self.page.locator('[data-control-id]').nth(0)
                if kind == 'categorical':
                    control.check()
                    self.page.locator('[data-control-id]').nth(1).select_option('high')
                    self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().state["var-result"]'), 2)
                else:
                    value = '[2,3,5]' if kind == 'vector' else '[[3,2],[1,3]]'
                    control.fill(value); control.dispatch_event('change')
                    state = self.page.evaluate('PlaygroundRuntime.snapshot()')
                    self.assertIsNone(state['error'])
                    self.assertEqual(state['state']['var-x'], [.2, .3, .5] if kind == 'vector' else [[3, 2], [1, 3]])
                    before = state['state']
                    control.fill('[0,0,0]' if kind == 'vector' else '[[1],[2,3]]')
                    control.dispatch_event('change')
                    self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().state'), before)
                    self.assertIn('invalid', self.page.locator('[data-role="status"]').text_content())

    def test_range_control_uses_native_input_events(self):
        ir = fixture_ir()
        controls = tuple(replace(c, control_type='slider') for c in ir.lesson_spec.controls)
        self.load(replace(ir, lesson_spec=replace(ir.lesson_spec, controls=controls)))
        input_el = self.page.locator('[data-control-id]').nth(0)
        input_el.fill('4'); input_el.dispatch_event('input')
        self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().state["var-result"]'), 12)

    def test_real_staging_promotion_and_failed_repair_preserve_last_good(self):
        out = Path(self.temp.name)
        ir = fixture_ir()
        with TraceWriter(out / 'trace.jsonl') as trace:
            first = build_artifact(ir, out, reference_evaluator=reference('scalar_relationship'), trace=trace, browser=self.browser)
            self.assertTrue(first.promoted, first.report.findings)
            self.assertEqual(first.report.status, ValidationStatus.PASS)
            good = first.path.read_bytes()
            second_computation = replace(ir.computations[1], input_refs=('var-product',), metadata={'ast': binary('*', variable('var-product'), constant(0))})
            invalid = replace(ir, computations=(ir.computations[0], second_computation))
            second = build_artifact(invalid, out, reference_evaluator=reference('scalar_relationship'), trace=trace, browser=self.browser)
            self.assertFalse(second.promoted)
            self.assertIn('BROWSER_DEAD_VISUAL', [f.code for f in second.report.findings])
            self.assertEqual(first.path.read_bytes(), good)
        self.assertEqual({p.name for p in out.iterdir()}, {'index.html', 'trace.jsonl'})

    def test_symbolic_shape_dimensions_use_declared_scientific_state(self):
        ir = control_fixture('vector')
        variables = tuple(replace(v, shape=('var-n',)) if v.shape else v for v in ir.scientific_model.variables)
        variables += (ScientificVariable('var-n', None, 'n', 'Vector length', 'scalar'),)
        ir = replace(ir, scientific_model=replace(ir.scientific_model, variables=variables), metadata={**ir.metadata, 'initial_state': {'var-n': 3}})
        self.load(ir)
        self.assertEqual(self.page.evaluate('PlaygroundRuntime.snapshot().state["var-n"]'), 3)
        control = self.page.locator('[data-control-id]').nth(0)
        control.fill('[1,2]'); control.dispatch_event('change')
        self.assertEqual(len(self.page.evaluate('PlaygroundRuntime.snapshot().state["var-x"]')), 3)
        self.assertIn('invalid', self.page.locator('[data-role="status"]').text_content())

    def test_additional_primitives_and_scientifically_valid_visual_fallback(self):
        for component, family in [('scatter', 'geometry'), ('vector', 'geometry'), ('line', 'signal_transformation'), ('scene', 'scalar_relationship')]:
            with self.subTest(component=component):
                ir = fixture_ir(family)
                ir = replace(ir, visuals=(replace(ir.visuals[0], visual_type=component),))
                self.load(ir)
                baseline = self.page.locator('[data-visual-id]').inner_html()
                self.page.locator('[data-control-id]').nth(0).fill('3')
                self.page.locator('[data-control-id]').nth(0).dispatch_event('change')
                self.assertNotEqual(self.page.locator('[data-visual-id]').inner_html(), baseline)
                self.assertEqual(self.page.locator('[data-visual-id]').get_attribute('data-component'), component)
        ir = fixture_ir()
        self.load(replace(ir, visuals=(replace(ir.visuals[0], visual_type='matrix'),)))
        self.assertEqual(self.page.locator('[data-visual-id]').get_attribute('data-component'), 'scene')
        self.assertIn('r = 3', self.page.locator('[data-visual-id]').text_content())


if __name__ == '__main__':
    unittest.main()
