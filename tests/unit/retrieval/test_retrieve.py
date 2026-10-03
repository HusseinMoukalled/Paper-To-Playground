import unittest
from dataclasses import asdict, replace

from playground.budget import RunBudget
from playground.failures import PlaygroundError
from playground.retrieval.confidence import classify_confidence
from playground.retrieval.evidence import RetrievalConfidence
from playground.retrieval.index import BM25Index
from playground.retrieval.rerank import RerankResult
from playground.retrieval.retrieve import estimate_tokens, explanatory_context, retrieve_evidence
from playground.source.document import DocumentFormat, PaperDocument, SourceElement, SourceElementType
from playground.source.html import parse_html
from playground.source.settings import SourceSettings
from playground.source.validate import validate_source_evidence
from playground.validation.report import ValidationStatus
from tests.fixtures.source_factory import HTML_PAPER
from tests.unit.source.test_parsers import source


class RetrievalTests(unittest.TestCase):
    def setUp(self):
        self.document = parse_html(source(HTML_PAPER, DocumentFormat.HTML), focus="Figure 2")

    def retrieve(self, focus, **kwargs):
        return retrieve_evidence(self.document, focus, "Undergraduate", **kwargs)

    def test_all_explicit_reference_types(self):
        for focus, key, value in (("Section 1.1", "section_title", "1.1 Stability"),
                                   ("Equation 6", "equation_number", "6"),
                                   ("Figure 2", "figure_number", "2"),
                                   ("Table 3", "table_number", "3")):
            pack = self.retrieve(focus)
            block = pack.evidence_blocks[0]
            self.assertEqual(block.section_title if key == "section_title" else block.metadata[key], value)
            self.assertEqual(pack.retrieval_confidence, RetrievalConfidence.HIGH)

    def test_missing_explicit_reference_warns_without_inventing(self):
        pack = self.retrieve("Equation 99 feedback")
        self.assertEqual(pack.retrieval_confidence, RetrievalConfidence.LOW)
        self.assertEqual(pack.retrieval_metadata["unresolved_references"], ["equation 99"])

    def test_exact_lexical_match_and_noise_suppression(self):
        pack = self.retrieve("Higher gain alters the feedback rate.")
        self.assertEqual(pack.evidence_blocks[0].content, "Higher gain alters the feedback rate.")
        self.assertEqual(pack.retrieval_confidence, RetrievalConfidence.HIGH)
        pack = self.retrieve("feedback gain")
        self.assertTrue(all("References" not in (b.section_title or "") for b in pack.evidence_blocks))

    def test_bm25_ranks_relevant_terms(self):
        elements = (SourceElement("SRC-1", SourceElementType.PARAGRAPH, "signal filtering noise"),
                    SourceElement("SRC-2", SourceElementType.PARAGRAPH, "state feedback gain"))
        scores = BM25Index(elements).scores("feedback gain")
        self.assertGreater(scores[1], scores[0])
        self.assertEqual(scores[0], 0)

    def test_confidence_categories(self):
        common = dict(explicit_matches=0, unresolved_references=0, exact_matches=0,
                      positive_candidates=2, top_term_coverage=.5, tied_top=True)
        self.assertEqual(classify_confidence(**common), RetrievalConfidence.AMBIGUOUS)
        self.assertEqual(classify_confidence(**{**common, "explicit_matches": 1}), RetrievalConfidence.HIGH)
        self.assertEqual(classify_confidence(**{**common, "positive_candidates": 0}), RetrievalConfidence.LOW)

    def test_equation_and_figure_neighborhood(self):
        pack = self.retrieve("Equation 6", settings=SourceSettings(candidate_limit=1))
        self.assertEqual(pack.retrieval_metadata["neighbor_expansions"], 1)
        self.assertTrue(any("gain changes" in b.content for b in pack.evidence_blocks))
        self.assertTrue(any(b.metadata["figure_number"] == "2" for b in pack.evidence_blocks))

    def test_stable_ids_across_rankings_and_repeated_runs(self):
        first = self.retrieve("Equation 6")
        second = self.retrieve("Figure 2")
        mapping = {b.source_element_ids: b.evidence_id for b in first.evidence_blocks}
        for block in second.evidence_blocks:
            if block.source_element_ids in mapping:
                self.assertEqual(block.evidence_id, mapping[block.source_element_ids])
        self.assertEqual(first, self.retrieve("Equation 6"))

    def test_pack_size_and_deduplication(self):
        settings = SourceSettings(max_evidence_chunks=2, max_evidence_tokens=4000)
        pack = self.retrieve("feedback", settings=settings)
        self.assertLessEqual(len(pack.evidence_blocks), 2)
        self.assertLessEqual(estimate_tokens(asdict(pack)), 4000)
        duplicate = replace(self.document.elements[1], element_id="SRC-duplicate", source_order=999)
        doc = replace(self.document, elements=self.document.elements + (duplicate,))
        pack = retrieve_evidence(doc, "feedback", "student")
        contents = [b.content for b in pack.evidence_blocks]
        self.assertEqual(len(contents), len(set(contents)))
        with self.assertRaises(PlaygroundError):
            self.retrieve("feedback", settings=SourceSettings(max_evidence_tokens=100))

    def test_gate_provenance_and_empty_pack(self):
        pack = self.retrieve("Equation 6")
        self.assertNotEqual(validate_source_evidence(self.document, pack).status, ValidationStatus.FAIL)
        bad = replace(pack.evidence_blocks[0], page=100)
        altered = replace(pack, evidence_blocks=(bad,) + pack.evidence_blocks[1:])
        self.assertEqual(validate_source_evidence(self.document, altered).status, ValidationStatus.FAIL)
        self.assertEqual(validate_source_evidence(self.document, replace(pack, evidence_blocks=())).status, ValidationStatus.FAIL)

    def test_unmatched_focus_fails_instead_of_arbitrary_evidence(self):
        with self.assertRaises(PlaygroundError):
            self.retrieve("unfindablequasarxyz")

    def test_large_table_keeps_caption_without_fabricating_cells(self):
        table = next(e for e in self.document.elements if e.table_number == "3")
        table = replace(table, metadata={**table.metadata, "rows": [["long extracted cell " * 1000]]})
        doc = replace(self.document, elements=tuple(table if e.element_id == table.element_id else e for e in self.document.elements))
        pack = retrieve_evidence(doc, "Table 3", "student")
        block = pack.evidence_blocks[0]
        self.assertEqual(block.content, table.content)
        self.assertFalse(block.metadata["structured"])
        self.assertNotIn("rows", block.metadata)
        report = validate_source_evidence(doc, pack)
        self.assertEqual(report.status, ValidationStatus.WARN)
        self.assertTrue(any(f.code == "EVIDENCE_TABLE_DATA_OMITTED" for f in report.findings))

    def test_one_rerank_uses_supplied_model_budget_and_known_ids(self):
        requests = []
        class Stub:
            def rerank(self, request, *, budget, trace=None):
                requests.append(request)
                budget.record_model_call(prompt_tokens=20, completion_tokens=8)
                return RerankResult((request.candidates[0].element_id,), prompt_tokens=20, completion_tokens=8)
        budget = RunBudget()
        pack = self.retrieve("feedback unknownterm", budget=budget, reranker=Stub(), model_id="evaluator/model-id")
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].model_id, "evaluator/model-id")
        self.assertTrue(requests[0].source_is_untrusted)
        self.assertTrue(pack.retrieval_metadata["rerank_used"])
        self.assertEqual(budget.calls_used, 1)
        self.assertEqual(budget.completion_tokens, 8)

    def test_bad_rerank_id_and_exception_fall_back_and_count_attempt(self):
        class Bad:
            def rerank(self, request, *, budget, trace=None):
                budget.record_model_call()
                return RerankResult(("invented-id",))
        class Broken:
            def rerank(self, request, *, budget, trace=None):
                budget.record_model_call()
                raise RuntimeError("unsafe-secret")
        for stub in (Bad(), Broken()):
            budget = RunBudget()
            pack = self.retrieve("feedback unknownterm", budget=budget, reranker=stub, model_id="model")
            self.assertFalse(pack.retrieval_metadata["rerank_used"])
            self.assertEqual(budget.calls_used, 1)
            self.assertNotIn("unsafe-secret", str(pack))

    def test_rerank_call_budget_denial_keeps_deterministic_pack(self):
        class Never:
            def rerank(self, request):
                raise AssertionError("must not be called")
        pack = self.retrieve("feedback unknownterm", budget=RunBudget(max_calls=0), reranker=Never(), model_id="model")
        self.assertIn("budget_denied", pack.retrieval_metadata["rerank_status"])

    def test_high_confidence_never_uses_rerank(self):
        class Never:
            def rerank(self, request):
                raise AssertionError("must not be called")
        budget = RunBudget()
        self.retrieve("Equation 6", reranker=Never(), budget=budget, model_id="model")
        self.assertEqual(budget.calls_used, 0)

    def test_large_section_cannot_displace_requested_equation(self):
        data = ('<html><h1>1 Method</h1>' + ''.join(
            f'<p>Step {i} explains the process.</p>' for i in range(10))
            + '<h1>2 Analysis</h1><p>y = x + gain (6)</p></html>').encode()
        doc = parse_html(source(data, DocumentFormat.HTML))
        pack = retrieve_evidence(doc, 'Section 1 and Equation 6', 'student')
        self.assertTrue(any(b.metadata['equation_number'] == '6' for b in pack.evidence_blocks))
        self.assertTrue(any(b.section_title == '1 Method' for b in pack.evidence_blocks))
        self.assertEqual(pack.retrieval_metadata['omitted_references'], [])

    def test_reference_reservations_are_independent_of_rerank_preview_limit(self):
        pack = self.retrieve('Equation 6 Figure 2 Table 3', settings=SourceSettings(candidate_limit=1))
        for field, value in [('equation_number', '6'), ('figure_number', '2'), ('table_number', '3')]:
            self.assertTrue(any(b.metadata[field] == value for b in pack.evidence_blocks))

    def test_impossible_reference_cap_does_not_claim_high_confidence(self):
        pack = self.retrieve('Equation 6 Table 3', settings=SourceSettings(max_evidence_chunks=1))
        self.assertEqual(pack.retrieval_confidence, RetrievalConfidence.LOW)
        self.assertIn('table 3', pack.retrieval_metadata['omitted_references'])
        self.assertEqual(validate_source_evidence(self.document, pack).status, ValidationStatus.FAIL)

    def test_reranker_cannot_remove_requested_reference(self):
        class OtherCandidate:
            def rerank(self, request, *, budget, trace=None):
                budget.record_model_call()
                return RerankResult((request.candidates[-1].element_id,))
        pack = self.retrieve('Equation 6 Equation 99 feedback', budget=RunBudget(),
                             reranker=OtherCandidate(), model_id='supplied/model')
        self.assertTrue(any(b.metadata['equation_number'] == '6' for b in pack.evidence_blocks))

    def test_oversized_definition_is_reported_and_confidence_downgraded(self):
        data = ('<html><title>Feedback study</title><h1>1 Method</h1><p>'
                + 'The gain defines the feedback coupling. ' * 250
                + '</p><p>y = gain * x (6)</p><p>The output is a scalar.</p></html>').encode()
        doc = parse_html(source(data, DocumentFormat.HTML))
        pack = retrieve_evidence(doc, 'Equation 6', 'student')
        self.assertEqual(pack.retrieval_confidence, RetrievalConfidence.LOW)
        self.assertGreater(pack.retrieval_metadata['omitted_context_count'], 0)
        report = validate_source_evidence(doc, pack)
        self.assertEqual(report.status, ValidationStatus.WARN)
        self.assertIn('EVIDENCE_CONTEXT_OMITTED', [f.code for f in report.findings])
        self.assertLessEqual(estimate_tokens(asdict(pack)), SourceSettings().max_evidence_tokens)
        # Validation independently checks source context rather than trusting metadata.
        forged = replace(pack, retrieval_confidence=RetrievalConfidence.HIGH, retrieval_metadata={})
        self.assertIn('EVIDENCE_CONTEXT_OMITTED', [f.code for f in validate_source_evidence(doc, forged).findings])

    def test_final_reference_coverage_is_validated_independently(self):
        pack = self.retrieve('Equation 6 Table 3')
        blocks = tuple(replace(b, rank=i) for i, b in enumerate(
            b for b in pack.evidence_blocks if b.metadata['equation_number'] != '6'))
        forged = replace(pack, evidence_blocks=blocks, retrieval_metadata={})
        self.assertEqual(validate_source_evidence(self.document, forged).status, ValidationStatus.FAIL)

    def test_missing_reference_anchor_is_low_even_if_other_matches_survive(self):
        data = ('<html><title>Study</title><p>y = ' + 'x + ' * 2500
                + 'gain (6)</p><p>We perform 6 experiments.</p></html>').encode()
        doc = parse_html(source(data, DocumentFormat.HTML))
        pack = retrieve_evidence(doc, 'Equation 6', 'student')
        self.assertEqual(pack.retrieval_confidence, RetrievalConfidence.LOW)
        self.assertEqual(pack.retrieval_metadata['omitted_references'], ['equation 6'])
        self.assertEqual(validate_source_evidence(doc, pack).status, ValidationStatus.FAIL)

    def test_metadata_pruning_preserves_bounds_and_final_diagnostics(self):
        with self.assertRaises(PlaygroundError):
            self.retrieve('Equation 6 Table 3', settings=SourceSettings(max_evidence_tokens=1000))
        for cap in (1500, 2500, 4000):
            with self.subTest(cap=cap):
                pack = self.retrieve('Equation 6 Table 3', settings=SourceSettings(max_evidence_tokens=cap))
                self.assertLessEqual(estimate_tokens(asdict(pack)), cap)
                included = {i for b in pack.evidence_blocks for i in b.source_element_ids}
                if any(e.element_id not in included for e in self.document.elements if e.equation_number == '6'):
                    self.assertIn('equation 6', pack.retrieval_metadata['omitted_references'])

    def test_linked_evidence_retains_its_own_explanatory_prose(self):
        for focus in ('Figure 2', 'Table 3', 'Section 1.1'):
            with self.subTest(focus=focus):
                pack = self.retrieve(focus)
                included = {i for b in pack.evidence_blocks for i in b.source_element_ids}
                anchors = [e for e in self.document.elements if e.element_id in included]
                self.assertTrue(explanatory_context(self.document, anchors) <= included)
                self.assertEqual(pack.retrieval_metadata['neighbor_expansions'], 1)
