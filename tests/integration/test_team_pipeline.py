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
from tests.fixtures.dev2_factory import evidence_pack


class TeamPipelineTests(unittest.TestCase):
    def test_two_failed_claims_receive_one_leaf_only_patch_then_reverification(self):
        from playground.model.verification import RiskUnit
        from playground.model.client import OpenRouterClient
        from playground.budget import RunBudget
        ir = explanation()
        targets = ('science.concept','science.purpose')
        texts = ('Affine response','Explore the gain and offset mechanism.')
        indices = {r.claim_id:i for i,r in enumerate(ir.grounding_records)}
        verdict = lambda target,status: json.dumps({'target':target,'status':status,'evidence_refs':['E1'],'reason':'Small claim mismatch' if status!='SUPPORTED' else 'Evidence supports corrected claim'})
        patches = [{'op':'replace','path':path,'value':text} for target,text in zip(targets,texts)
                   for path in ('/scientific_model/'+target.split('.')[1],f'/grounding_records/{indices[target]}/claim')]
        replies = iter([verdict(target,'UNSUPPORTED') for target in targets] +
                       [json.dumps({'patches':patches})] + [verdict(target,'SUPPORTED') for target in targets])
        purposes = []
        def transport(payload,headers,timeout):
            purposes.append(payload)
            return {'choices':[{'message':{'content':next(replies)}}],'usage':{'prompt_tokens':10,'completion_tokens':30}}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-repair-key'}):
            config = RunConfig(Path(folder,'case.json'),Path(folder,'out'),'supplied-model-id')
            runner = Orchestrator(config)
            client = OpenRouterClient(config.model_id,RunBudget(),transport=transport)
            units = tuple(RiskUnit('claim_evidence',target,'Original claim',('E1',),'partial_support') for target in targets)
            class Trace:
                def emit(self,**kwargs): pass
            updated = runner._verify_risks(ir,evidence_pack(),units,client,Trace())
            self.assertEqual(updated.scientific_model.concept,texts[0])
            self.assertEqual(updated.scientific_model.purpose,texts[1])
            self.assertEqual(client.budget.calls_used,5)
            repair = json.loads(purposes[2]['messages'][1]['content'])
            self.assertEqual(set(repair['affected_fragments']),{p['path'] for p in patches})
            self.assertEqual(len(repair['failure']['verification_findings']),2)

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
        self.assertEqual(manifest['visuals'][0]['component'],'curve')
        sweep = manifest['visuals'][0]['sweep']
        self.assertEqual(sweep['output_ref'],'var-y')
        self.assertEqual(sweep['input_ref'],'var-a')
        self.assertEqual(sweep['sample_values'][0],0)
        self.assertEqual(sweep['sample_values'][-1],4)
        self.assertNotIn('fallback_reason',manifest['visuals'][0])
        self.assertEqual(manifest['presentation']['output_refs'],['var-y'])


if __name__ == '__main__':
    unittest.main()
