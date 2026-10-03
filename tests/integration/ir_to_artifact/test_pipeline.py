from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from playground.render.pipeline import build_artifact
from playground.trace import TraceWriter
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus
from tests.fixtures.runtime_fixtures import fixture_ir


def browser_report(status, code='BROWSER_TEST_RESULT'):
    return ValidationReport(status, (ValidationFinding(status, code, 'browser', 'Injected browser result'),), 'browser')


class PipelineTests(unittest.TestCase):
    def test_failed_repair_preserves_last_known_good_and_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            with TraceWriter(out / 'trace.jsonl') as trace:
                with patch('playground.render.pipeline.validate_browser', return_value=browser_report(ValidationStatus.PASS)):
                    a = build_artifact(fixture_ir(), out, trace=trace)
                self.assertTrue(a.promoted)
                good = a.path.read_bytes()
                with patch('playground.render.pipeline.validate_browser', return_value=browser_report(ValidationStatus.FAIL)):
                    b = build_artifact(fixture_ir('distribution'), out, trace=trace)
                self.assertFalse(b.promoted)
                self.assertEqual((out / 'index.html').read_bytes(), good)
                invalid = replace(fixture_ir(), computations=())
                c = build_artifact(invalid, out, trace=trace)
                self.assertFalse(c.promoted)
                self.assertEqual((out / 'index.html').read_bytes(), good)
            self.assertEqual({p.name for p in out.iterdir()}, {'index.html', 'trace.jsonl'})
            events = [json.loads(line) for line in (out / 'trace.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertTrue(any(e['action'] == 'promote_validated_candidate' for e in events))
            self.assertEqual(events[-1]['action'], 'candidate_rejected')
            self.assertEqual([e['elapsed_seconds'] for e in events], sorted(e['elapsed_seconds'] for e in events))

    def test_browser_unavailable_fallback_can_promote_valid_static_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('playground.render.pipeline.validate_browser', return_value=browser_report(ValidationStatus.WARN, 'BROWSER_VALIDATION_UNAVAILABLE')):
                result = build_artifact(fixture_ir(), directory)
            self.assertTrue(result.promoted)
            self.assertEqual(result.report.status, ValidationStatus.WARN)

    def test_atomic_promotion_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'index.html'
            path.write_text('previous validated artifact', encoding='utf-8')
            with patch('playground.render.pipeline.validate_browser', return_value=browser_report(ValidationStatus.PASS)), patch('playground.render.pipeline.os.replace', side_effect=OSError):
                result = build_artifact(fixture_ir(), directory)
            self.assertFalse(result.promoted)
            self.assertEqual(path.read_text(encoding='utf-8'), 'previous validated artifact')


if __name__ == '__main__':
    unittest.main()
