"""Cross-owner tests: genuine parsing, semantic transport, science, and rendering."""
import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from playground.config import RunConfig
from playground.failures import PlaygroundError
from playground.orchestrator import Orchestrator
from playground.ir.serialization import to_mapping
from playground.computation.evaluator import compile_computations, execute
from playground.computation.validate import prepare_inputs
from playground.render.renderer import render_candidate
from playground.render.manifest import build_manifest
from playground.validation.artifact import validate_artifact
from playground.validation.report import ValidationStatus
from tests.fixtures.dev2_factory import explanation


class TeamPipelineTests(unittest.TestCase):
    def test_real_html_to_one_model_call_to_offline_artifact(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'OPENROUTER_API_KEY': 'test-integration-secret'}):
            root = Path(folder)
            (root / 'paper.html').write_text('<article><h1>How gain and offset affect the response</h1><p>The ideal linear response is y = a*x+b (1). Gain a scales input x; offset b translates output y. No saturation or noise is represented.</p></article>', encoding='utf-8')
            oracle = to_mapping(explanation())
            case = {'source_url': 'paper.html', 'focus': oracle['focus_coverage']['focus'], 'audience': oracle['metadata']['audience']}
            (root / 'case.json').write_text(json.dumps(case), encoding='utf-8')
            def transport(payload, headers, timeout):
                self.assertEqual(payload['model'], 'supplied-model-id')
                self.assertFalse(payload['reasoning']['enabled'])
                context = json.loads(payload['messages'][1]['content'])
                evidence_id = context['EvidencePack_UNTRUSTED_DATA']['evidence_blocks'][0]['id']
                def bind(x):
                    if isinstance(x, str): return evidence_id if x in {'E1', 'E2'} else x
                    if isinstance(x, list): return [bind(v) for v in x]
                    if isinstance(x, dict): return {k: bind(v) for k, v in x.items()}
                    return x
                response = bind(oracle)
                response['scientific_model']['provenance'] = [evidence_id]
                for record in response['grounding_records']:
                    record.pop('claim')  # Production compact format, exact text copied deterministically.
                return {'choices': [{'message': {'content': json.dumps(response)}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 100, 'completion_tokens': 1000}}
            output = root / 'out'
            runner = Orchestrator(RunConfig(root / 'case.json', output, 'supplied-model-id'), transport=transport)
            self.assertEqual(runner.run(), 0)
            self.assertEqual(runner.budget.calls_used, 1)
            self.assertEqual(validate_artifact(output / 'index.html').status, ValidationStatus.PASS)
            events = [json.loads(line) for line in (output / 'trace.jsonl').read_text().splitlines()]
            self.assertEqual(events[-1]['stage'], 'EXIT')
            self.assertNotIn('test-integration-secret', (output / 'index.html').read_text(encoding='utf-8'))
            self.assertNotIn('test-integration-secret', (output / 'trace.jsonl').read_text())
            previous = (output / 'index.html').read_bytes()
            # Failed subsequent run preserves the last-known-good artifact.
            with patch.dict(os.environ, {'OPENROUTER_API_KEY': ''}):
                with self.assertRaises(PlaygroundError):
                    Orchestrator(runner.config).run()
            self.assertEqual((output / 'index.html').read_bytes(), previous)

    def test_dev2_ast_and_computation_refs_render_without_reinterpretation(self):
        ir = compile_computations(explanation())
        manifest = build_manifest(ir)
        self.assertEqual(manifest['canonical_ast_version'], 1)
        self.assertEqual(manifest['initial_state'], prepare_inputs(ir, strict=True))
        self.assertEqual(manifest['computations'][0]['ast']['spec']['metadata'], ir.computations[0].metadata)
        self.assertIn('compute-response', manifest['outputs'])
        with tempfile.TemporaryDirectory() as folder:
            path = render_candidate(ir, folder)
            result = validate_artifact(path, ir)
            self.assertEqual(result.status, ValidationStatus.PASS, result.findings)

    def test_scalar_outputs_cannot_be_misrepresented_as_sampled_waveform(self):
        ir = compile_computations(explanation())
        visual = replace(ir.visuals[0], visual_type='waveform', data_refs=('var-y','compute-response'))
        manifest = build_manifest(replace(ir,visuals=(visual,)))
        self.assertEqual(manifest['visuals'][0]['component'],'scene')
        self.assertIn('No sampled series',manifest['visuals'][0]['fallback_reason'])


if __name__ == '__main__':
    unittest.main()
