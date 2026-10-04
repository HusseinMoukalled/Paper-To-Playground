from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from playground.render.renderer import render_candidate
from playground.validation.artifact import ArtifactParser, validate_artifact, validate_manifest
from playground.validation.browser import BrowserUnavailable, validate_browser
from playground.validation.report import ValidationStatus
from tests.fixtures.runtime_fixtures import fixture_ir


class ArtifactValidationTests(unittest.TestCase):
    def test_browser_probes_respect_integer_scientific_domains(self):
        from playground.validation.browser import alternative_values
        control = {'default': 4, 'control_type': 'number', 'minimum': 1,
                   'maximum': 4, 'step': 1}
        probes = alternative_values(control, integer=True)
        self.assertTrue(probes)
        self.assertTrue(all(isinstance(v, int) and 1 <= v <= 4 for v in probes))
        self.assertIn(1, probes)
        self.assertIn(2.5, alternative_values(control))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ir = fixture_ir()
        self.path = render_candidate(self.ir, self.temp.name)
        self.html = self.path.read_text(encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def mutate(self, source):
        self.path.write_text(source, encoding='utf-8')
        return validate_artifact(self.path)

    def test_missing_file(self):
        self.assertEqual(validate_artifact(Path(self.temp.name) / 'missing.html').status, ValidationStatus.FAIL)

    def test_external_runtime_and_unsafe_links_are_detected(self):
        snippets = ['<script src="https://example.org/a.js"></script>', '<link rel="stylesheet" href="a.css">',
                    '<img src="a.png">', '<iframe srcdoc="bad"></iframe>', '<style>@import "a.css";</style>',
                    '<style>body{background:url(https://example.org/a)}</style>', '<script>fetch("x")</script>',
                    '<script>new WebSocket("x")</script>', '<script>new Function("bad")</script>',
                    '<script>import("x")</script>', '<script>navigator.sendBeacon("x")</script>',
                    '<a href="file:///C:/secret">Bad</a>', '<a href="javascript:alert(1)">Bad</a>',
                    '<img onerror="alert(1)">', '<svg><use href="https://example.org/a.svg"></use></svg>']
        for snippet in snippets:
            with self.subTest(snippet=snippet):
                result = self.mutate(self.html.replace('</body>', snippet + '</body>'))
                self.assertEqual(result.status, ValidationStatus.FAIL, snippet)

    def test_missing_sections_controls_labels_or_metadata_fail(self):
        for old, new in [('data-role="reset"', 'data-role="absent"'), ('data-visual-id="visual-result"', 'data-x="visual-result"'),
                         ('data-control-id="control-x"', 'data-x="control-x"'), ('for="input-0"', 'for="missing"'),
                         ('data-output-id="var-product"', 'data-output-id="missing"'), ('data-setup-id="explore-baseline"', 'data-setup-id="bad"')]:
            with self.subTest(old=old):
                self.assertEqual(self.mutate(self.html.replace(old, new)).status, ValidationStatus.FAIL)

    def test_ir_manifest_and_dom_mismatch_fail(self):
        self.path.write_text(self.html.replace('data-output-id="var-result"', 'data-output-id="other"'), encoding='utf-8')
        self.assertEqual(validate_artifact(self.path, self.ir).status, ValidationStatus.FAIL)
        from dataclasses import replace
        other = replace(self.ir, scientific_model=replace(self.ir.scientific_model, concept='Other'))
        self.path.write_text(self.html, encoding='utf-8')
        self.assertEqual(validate_artifact(self.path, other).status, ValidationStatus.FAIL)

    def test_dead_dependencies_invalid_presets_and_unsupported_claims_fail(self):
        parser = ArtifactParser(); parser.feed(self.html)
        raw = next(s for attrs, s in parser.scripts if attrs.get('id') == 'playground-manifest')
        for change in ('dead', 'preset', 'unsupported', 'coverage', 'dependency', 'default'):
            m = json.loads(raw)
            if change == 'dead':
                m['computations'][0]['ast'] = {'type': 'Constant', 'value': 2}
                m['computations'][0]['reads'] = m['computations'][0]['input_refs'] = []
                m['dependencies']['compute-product'] = []
                m['computations'][1]['ast'] = {'type': 'Constant', 'value': 4}
                m['computations'][1]['reads'] = m['computations'][1]['input_refs'] = []
                m['dependencies']['compute-result'] = []
            elif change == 'preset':
                m['explorations'][0]['runtime_setup']['var-x'] = 100
            elif change == 'unsupported':
                m['grounding_records'][0]['status'] = 'UNSUPPORTED'
            elif change == 'coverage':
                m['focus_coverage']['visual_refs'] = ['absent']
            elif change == 'dependency':
                m['dependencies']['compute-product'] = []
            else:
                m['initial_state']['var-x'] = 3
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_manifest(m)

    def test_browser_unavailable_is_warn_after_strong_static_gate(self):
        with patch('playground.validation.browser.chromium_session', side_effect=BrowserUnavailable('No controller')):
            result = validate_browser(self.path)
        self.assertEqual(result.status, ValidationStatus.WARN)
        self.assertEqual(result.findings[0].code, 'BROWSER_VALIDATION_UNAVAILABLE')
        self.assertEqual(result.findings[0].details['static_status'], 'PASS')
        self.assertTrue(self.path.is_file())

    def test_invalid_static_artifact_does_not_launch_browser(self):
        self.path.write_text('<html>broken</html>', encoding='utf-8')
        with patch('playground.validation.browser.chromium_session') as launch:
            self.assertEqual(validate_browser(self.path).status, ValidationStatus.FAIL)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
