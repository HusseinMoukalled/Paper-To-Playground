import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from playground.model.wire import lower_wire
from playground.model.grounding_plan import expand_grounding_plan
from playground.model.generation import expand_compact_grounding
from playground.model.rerank import DeepSeekReranker
from playground.model.client import OpenRouterClient
from playground.budget import RunBudget
from playground.retrieval.rerank import RerankRequest, RerankCandidate
from playground.failures import PlaygroundError
from playground.ir.serialization import to_mapping, decode
from playground.ir.models import ExplanationIR
from playground.ir.validate import validate_ir
from playground.trace import TraceWriter
from playground.validation.report import ValidationStatus
from tests.fixtures.dev2_factory import explanation, evidence_pack


class WireTests(unittest.TestCase):
    def test_symbol_keys_success_envelope_and_unused_bindings_are_lossless(self):
        original = to_mapping(explanation())
        wire = json.loads(json.dumps(original))
        wire['status'] = 'ok'
        wire['metadata']['defaults'] = {'x':2}
        wire['lesson_spec']['symbol_explanations'] = {k[4:]:v for k,v in wire['lesson_spec']['symbol_explanations'].items()}
        wire['computations'][0]['metadata']['bindings']['unused'] = 'var-y'
        self.assertEqual(lower_wire(wire,evidence_pack()),original)

    def test_explicit_grounding_policy_builds_complete_records_without_inventing_support(self):
        wire = to_mapping(explanation())
        sources = [r['claim_id'] for r in wire['grounding_records'] if r['knowledge_class']=='SOURCE_GROUNDED']
        wire['grounding_records'] = []
        wire['metadata']['grounding_plan'] = {'teaching_default':{'knowledge_class':'PEDAGOGICAL','status':'SUPPORTED'},
                                             'overrides':[{'claim_ids':sources,'knowledge_class':'SOURCE_GROUNDED',
                                                           'status':'SUPPORTED','evidence_refs':['E1'],'computation_refs':[]}]}
        ir = decode(ExplanationIR,expand_grounding_plan(wire))
        self.assertEqual(validate_ir(ir,evidence_pack()).status,ValidationStatus.PASS)
        self.assertEqual(len(ir.grounding_records),len(explanation().grounding_records))
        wire['metadata']['grounding_plan']['overrides'][0]['evidence_refs'] = ['E-unknown']
        self.assertEqual(validate_ir(decode(ExplanationIR,expand_grounding_plan(wire)),evidence_pack()).status,ValidationStatus.FAIL)

    def test_grouped_grounding_accepts_only_unambiguous_field_aliases(self):
        wire = to_mapping(explanation())
        wire['grounding_records'] = [{'claim_ids':['var-a.meaning','scientific_model.variables.1.meaning'],
                                     'knowledge_class':'SOURCE_GROUNDED','status':'SUPPORTED','evidence_refs':['E1'],'computation_refs':[]}]
        result = expand_compact_grounding(wire)
        self.assertEqual([r['claim_id'] for r in result['grounding_records']],['var-a','var-b'])
        wire['grounding_records'][0]['claim_ids'].append('VISUAL_ID.question')
        with self.assertRaises(ValueError): expand_compact_grounding(wire)

    def test_optional_rerank_uses_exactly_one_attempt_shared_budget_and_supplied_model(self):
        budget = RunBudget()
        calls=[]
        def transport(payload,headers,timeout):
            calls.append(payload)
            raise urllib.error.HTTPError('https://openrouter.ai',429,'limited',{},None)
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'}):
            client=OpenRouterClient('supplied-model',budget,transport=transport)
            request=RerankRequest('supplied-model','focus',(RerankCandidate('SRC-1',None,'DATA'),))
            with self.assertRaises(PlaygroundError): DeepSeekReranker(client).rerank(request,budget=budget)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]['model'],'supplied-model')
        self.assertEqual(budget.calls_used,1)

    def test_hostile_trace_metadata_cannot_echo_environment_key(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-sensitive-value'}):
            path=Path(folder,'trace.jsonl')
            with TraceWriter(path) as trace:
                trace.emit(stage='test',action='data',result='warn',details={'model':'test-sensitive-value','test-sensitive-value':['test-sensitive-value']})
            self.assertNotIn('test-sensitive-value',path.read_text())


if __name__ == '__main__': unittest.main()
