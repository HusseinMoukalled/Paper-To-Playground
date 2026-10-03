"""Exercise the public CLI's complete source/model/artifact wiring."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent import main
from playground.config import CaseInput
from playground.source.pipeline import build_evidence
from playground.ir.serialization import to_mapping, restore_structural_defaults, decode
from playground.ir.models import ExplanationIR
from tests.fixtures.dev2_factory import explanation, evidence_pack
from tests.unit.model.test_client import response, TEST_KEY


class IntegratedCliTests(unittest.TestCase):
    def fixture_case(self, root):
        paper = root/'paper.html'
        paper.write_text('<html><head><title>Original synthetic linear response</title></head><body><article>'
                         '<h1>Gain and offset</h1><p>The response is y = a*x + b. The gain a scales the input x and b offsets the response.</p>'
                         '<p>This idealized mechanism does not include saturation or measurement noise.</p></article></body></html>', encoding='utf-8')
        fixture = evidence_pack()
        case = CaseInput('./paper.html', fixture.focus, fixture.audience)
        case_path = root/'case.json'
        case_path.write_text(json.dumps({'source_url':case.source_url,'focus':case.focus,'audience':case.audience}), encoding='utf-8')
        source = build_evidence(case, base_dir=root)
        ids = source.evidence_pack.evidence_ids
        mapping = to_mapping(explanation())
        def adapt(value):
            if value == 'E1': return ids[0]
            if value == 'E2': return ids[min(1,len(ids)-1)]
            if isinstance(value,list): return [adapt(x) for x in value]
            if isinstance(value,dict): return {k:adapt(v) for k,v in value.items()}
            return value
        return case_path, adapt(mapping)

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':TEST_KEY})
    def test_full_cli_from_local_html_to_real_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case, ir = self.fixture_case(root)
            requests = []
            def transport(payload, headers, timeout):
                requests.append(payload)
                if payload['messages'][0]['content'].startswith('Verify only'):
                    unit = json.loads(payload['messages'][1]['content'])
                    return response(json.dumps({'target':unit['target'],'status':'SUPPORTED',
                        'evidence_refs':[b['id'] for b in unit['evidence_UNTRUSTED_DATA']], 'reason':'Synthetic oracle equation matches the source.'}))
                if payload['messages'][0]['content'].startswith('Select evidence'):
                    request = json.loads(payload['messages'][1]['content'])
                    return response(json.dumps({'selected_ids':[c['element_id'] for c in request['candidates_UNTRUSTED_DATA']], 'insufficient':False}))
                return response(json.dumps(ir))
            with patch('playground.model.client.http_transport', transport):
                code = main(['--input',str(case),'--output',str(root/'out'),'--model','caller-model'])
            self.assertEqual(code,0)
            self.assertEqual(sum(p['messages'][0]['content'].startswith('TASK:') for p in requests),1)
            self.assertEqual(requests[0]['model'],'caller-model')
            output = root/'out'
            self.assertEqual({p.name for p in output.iterdir()},{'index.html','trace.jsonl'})
            events = [json.loads(x) for x in (output/'trace.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual(events[-1]['action'],'run_completed')
            self.assertTrue(events[-1]['details']['promoted'])
            self.assertEqual(events[-1]['details']['calls'],len(requests))
            self.assertNotIn(TEST_KEY,(output/'index.html').read_text(encoding='utf-8'))
            self.assertNotIn(TEST_KEY,(output/'trace.jsonl').read_text(encoding='utf-8'))

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':TEST_KEY})
    def test_invalid_science_does_not_overwrite_previous_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case, ir = self.fixture_case(root)
            ir['computations'][0]['expression'] = 'a*x-b'
            output = root/'out'; output.mkdir()
            prior = output/'index.html'; prior.write_text('previous validated artifact', encoding='utf-8')
            with patch('playground.model.client.http_transport', lambda *_: response(json.dumps(ir))):
                code = main(['--input',str(case),'--output',str(output),'--model','caller-model'])
            self.assertEqual(code,2)
            self.assertEqual(prior.read_text(encoding='utf-8'),'previous validated artifact')

    def test_null_optional_containers_restore_without_inventing_required_data(self):
        mapping = to_mapping(explanation())
        mapping['lesson_spec']['controls'][0]['options'] = None
        mapping['lesson_spec']['controls'][0]['units'] = None
        repaired = restore_structural_defaults(ExplanationIR,mapping)
        self.assertEqual(decode(ExplanationIR,repaired).lesson_spec.controls[0].options,())
        self.assertIsNone(repaired['lesson_spec']['controls'][0]['units'])
        mapping['lesson_spec']['central_learning_question'] = None
        with self.assertRaises(ValueError):
            decode(ExplanationIR,restore_structural_defaults(ExplanationIR,mapping))
