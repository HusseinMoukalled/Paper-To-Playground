from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from playground.failures import PlaygroundError
from playground.render.ast_support import validate_ast
from playground.render.manifest import build_manifest, safe_json
from playground.render.renderer import render_candidate, render_html, source_link
from playground.render.visual_planner import FAMILIES
from playground.validation.artifact import validate_artifact
from playground.validation.report import ValidationStatus
from tests.fixtures.runtime_fixtures import fixture_ir, load_ir


class RenderTests(unittest.TestCase):
    def test_every_mechanism_family_has_offline_semantic_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            for family in FAMILIES:
                with self.subTest(family=family):
                    ir = fixture_ir(family)
                    path = render_candidate(ir, Path(directory) / family)
                    result = validate_artifact(path, ir)
                    self.assertEqual(result.status, ValidationStatus.PASS, result.findings)
                    html = path.read_text(encoding='utf-8')
                    self.assertIn('data-control-id', html)
                    self.assertIn('data-exploration-id', html)
                    self.assertNotIn('<script src=', html)

    def test_json_fixtures_follow_shared_schema(self):
        for family in ('scalar_relationship', 'distribution', 'matrix_transformation', 'signal_transformation', 'state_transition'):
            self.assertEqual(build_manifest(load_ir(family)), build_manifest(fixture_ir(family)))

    def test_byte_deterministic_html_and_lossless_manifest(self):
        ir = fixture_ir()
        self.assertEqual(render_html(ir), render_html(ir))
        manifest = build_manifest(ir)
        self.assertEqual(manifest['focus_coverage']['focus'], ir.focus_coverage.focus)
        self.assertEqual(manifest['computations'][0]['ast'], ir.computations[0].metadata['ast'])
        self.assertEqual(manifest['explorations'][1]['runtime_setup'], {'var-x': 3, 'var-y': 2})

    def test_source_strings_cannot_become_markup_or_script(self):
        ir = fixture_ir()
        malicious = '</script><img src="https://bad.invalid/a" onerror="alert(1)"> & <b>injection</b>'
        ir = replace(ir, scientific_model=replace(ir.scientific_model, concept=malicious, purpose=malicious),
                     lesson_spec=replace(ir.lesson_spec, intuition=malicious))
        html = render_html(ir)
        self.assertNotIn(malicious, html)
        self.assertIn('&lt;/script&gt;', html)
        self.assertIn('\\u003c/script\\u003e', html)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(validate_artifact(render_candidate(ir, directory), ir).status, ValidationStatus.PASS)

    def test_script_json_escaping_and_nonfinite_rejection(self):
        value = {'a': '</script>\u2028&'}
        serialized = safe_json(value)
        self.assertNotIn('<', serialized)
        self.assertEqual(json.loads(serialized), value)
        with self.assertRaises(ValueError):
            safe_json({'a': float('nan')})

    def test_citations_reject_local_and_executable_schemes(self):
        for value in ('javascript:alert(1)', 'file:///C:/secret', 'C:\\secret.pdf', '//example.org/a', 'data:text/html,bad'):
            self.assertNotIn('<a ', source_link(value))
        self.assertIn('<a ', source_link('https://example.org/paper?a=1&b=2'))
        self.assertIn('&amp;', source_link('https://example.org/paper?a=1&b=2'))

    def test_missing_canonical_ast_is_reported_without_dsl_reinterpretation(self):
        ir = fixture_ir()
        ir = replace(ir, computations=(replace(ir.computations[0], metadata={}), ir.computations[1]))
        with self.assertRaises(PlaygroundError) as caught:
            render_html(ir)
        self.assertEqual(caught.exception.failure.code.value, 'RENDER_FAILED')

    def test_ast_rejects_unknown_nodes_operations_and_cycles(self):
        for node in ({'type': 'Call', 'function': 'evil', 'args': []}, {'type': 'Variable', 'id': '__proto__'},
                     {'type': 'Constant', 'value': float('inf')}, {'type': 'Lambda'},
                     {'type': 'Matrix', 'rows': [[{'type': 'Constant', 'value': 1}], []]}):
            with self.subTest(node=node), self.assertRaises(ValueError):
                validate_ast(node)
        ir = fixture_ir()
        ir = replace(ir, computations=(replace(ir.computations[0], dependencies=('compute-result',)), ir.computations[1]))
        with self.assertRaises(PlaygroundError):
            render_html(ir)

    def test_explicit_asts_boundary_and_dependency_order(self):
        ir = fixture_ir()
        trees = {c.id: c.metadata['ast'] for c in ir.computations}
        ir = replace(ir, computations=tuple(replace(c, metadata={}) for c in reversed(ir.computations)))
        manifest = build_manifest(ir, asts=trees)
        self.assertEqual([c['id'] for c in manifest['computations']], ['compute-product', 'compute-result'])


if __name__ == '__main__':
    unittest.main()
