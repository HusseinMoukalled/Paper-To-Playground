from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from playground.budget import RunBudget
from playground.config import CaseInput
from playground.failures import FailureCode, PlaygroundError
from playground.ir.models import (
    ExplanationIR,
    KnowledgeClass,
    LessonSpec,
    ScientificModel,
    ScientificVariable,
)
from playground.retrieval.evidence import (
    EvidenceChunk,
    EvidencePack,
    EvidenceType,
    RetrievalConfidence,
)
from playground.source.document import DocumentFormat, PaperDocument, SourceElement, SourceElementType
from playground.trace import TraceEvent, TraceWriter
from playground.validation.report import (
    ValidationFinding,
    ValidationReport,
    ValidationStatus,
)


class CaseInputTests(unittest.TestCase):
    def test_accepts_exact_schema_and_preserves_values(self) -> None:
        case = CaseInput.from_mapping(
            {"source_url": " paper.pdf ", "focus": " Equation 6 ", "audience": "Undergraduate"}
        )
        self.assertEqual(case.source_url, " paper.pdf ")
        self.assertEqual(case.focus, " Equation 6 ")

    def test_rejects_missing_extra_non_string_and_blank_fields(self) -> None:
        invalid_cases = [
            {"source_url": "paper.pdf", "focus": "mechanism"},
            {"source_url": "paper.pdf", "focus": "mechanism", "audience": "student", "extra": 1},
            {"source_url": "paper.pdf", "focus": 3, "audience": "student"},
            {"source_url": " ", "focus": "mechanism", "audience": "student"},
        ]
        for value in invalid_cases:
            with self.subTest(value=value), self.assertRaises(PlaygroundError) as caught:
                CaseInput.from_mapping(value)
            self.assertEqual(caught.exception.failure.code, FailureCode.INPUT_SCHEMA_INVALID)

    def test_rejects_non_object_json(self) -> None:
        with self.assertRaises(PlaygroundError):
            CaseInput.from_mapping(["not", "an", "object"])


class SharedContractTests(unittest.TestCase):
    def test_paper_and_evidence_pack_keep_provenance_and_unique_ids(self) -> None:
        element = SourceElement(
            element_id="P1-E1",
            element_type=SourceElementType.EQUATION,
            content="y = f(x)",
            page=1,
            section_id="sec-2",
            equation_number="2",
        )
        paper = PaperDocument(
            source_id="paper-1",
            source_type=DocumentFormat.PDF,
            elements=(element,),
        )
        pack = EvidencePack(
            source_id=paper.source_id,
            paper_metadata={"title": "Example"},
            focus="Equation 2",
            audience="Undergraduate",
            evidence_blocks=(
                EvidenceChunk(
                    evidence_id="E001",
                    evidence_type=EvidenceType.EQUATION,
                    content=element.content,
                    source_element_ids=(element.element_id,),
                    rank=0,
                    page=element.page,
                    section_id=element.section_id,
                ),
            ),
            retrieval_confidence=RetrievalConfidence.HIGH,
        )
        self.assertEqual(pack.evidence_ids, ("E001",))
        self.assertEqual(pack.evidence_blocks[0].source_element_ids, ("P1-E1",))

        with self.assertRaises(ValueError):
            EvidencePack(
                source_id="paper-1",
                paper_metadata={},
                focus="focus",
                audience="audience",
                evidence_blocks=(pack.evidence_blocks[0], pack.evidence_blocks[0]),
                retrieval_confidence=RetrievalConfidence.HIGH,
            )

    def test_scientific_model_lesson_and_ir_are_composable_contracts(self) -> None:
        scientific_model = ScientificModel(
            concept="Mechanism",
            purpose="Explain the mechanism",
            focus_alignment="Equation 2",
            variables=(
                ScientificVariable(
                    id="x",
                    source_symbol="x",
                    display_symbol="x",
                    meaning="input",
                    type="scalar",
                    evidence_refs=("E001",),
                    knowledge_class=KnowledgeClass.SOURCE_GROUNDED,
                ),
            ),
        )
        lesson_spec = LessonSpec(
            central_learning_question="How does x affect y?",
            learning_objectives=("Trace the relationship.",),
            audience_prerequisites=(),
            intuition="A simple mapping.",
            teaching_sequence=("intuition", "mechanism"),
            symbol_explanations={"x": "input"},
            controls=(),
            important_intermediates=(),
            visual_question="What changes?",
            visual_intent="Show the relationship.",
            guided_explorations=(),
            limitation_or_assumption="Toy inputs.",
            misconception="Input and output are not interchangeable.",
            source_grounding_plan=("E001",),
        )
        ir = ExplanationIR(scientific_model=scientific_model, lesson_spec=lesson_spec)
        self.assertEqual(ir.scientific_model.variables[0].evidence_refs, ("E001",))
        self.assertEqual(ir.lesson_spec.central_learning_question, "How does x affect y?")

    def test_validation_report_rejects_pass_with_failure(self) -> None:
        finding = ValidationFinding(
            status=ValidationStatus.FAIL,
            code="IR_INVALID",
            stage="ir",
            message="Invalid reference",
        )
        with self.assertRaises(ValueError):
            ValidationReport(status=ValidationStatus.PASS, findings=(finding,))


class BudgetAndTraceTests(unittest.TestCase):
    def test_run_budget_tracks_and_enforces_limits(self) -> None:
        budget = RunBudget(
            max_calls=1,
            max_completion_tokens=5,
            max_runtime_seconds=60,
            finalization_reserve_seconds=5,
        )
        budget.authorize_model_call(completion_token_reservation=5)
        budget.record_model_call(prompt_tokens=3, completion_tokens=5)
        self.assertEqual(budget.calls_used, 1)
        self.assertEqual(budget.total_tracked_tokens, 8)
        with self.assertRaises(PlaygroundError) as caught:
            budget.authorize_model_call()
        self.assertEqual(caught.exception.failure.code, FailureCode.BUDGET_EXCEEDED)

    def test_run_budget_reserves_finalization_and_keeps_actual_overage(self) -> None:
        budget = RunBudget(
            max_calls=2,
            max_completion_tokens=5,
            max_runtime_seconds=60,
            finalization_reserve_seconds=5,
            start_time=time.monotonic() - 56,
        )
        with self.assertRaises(PlaygroundError):
            budget.authorize_model_call()
        budget.authorize_model_call(optional=False)

        with self.assertRaises(PlaygroundError) as caught:
            budget.record_model_call(completion_tokens=6)
        self.assertEqual(caught.exception.failure.code, FailureCode.BUDGET_EXCEEDED)
        self.assertEqual(budget.calls_used, 1)
        self.assertEqual(budget.completion_tokens, 6)

    def test_trace_writer_streams_valid_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            with TraceWriter(path) as trace:
                first = trace.emit(stage="source", action="load", result="pass")
                second = trace.emit(
                    stage="model",
                    action="generate_ir",
                    result="pass",
                    prompt_tokens=12,
                    completion_tokens=7,
                )
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(events), 2)
            self.assertLessEqual(first.elapsed_seconds, second.elapsed_seconds)
            self.assertEqual(events[1]["completion_tokens"], 7)

    def test_trace_event_rejects_negative_usage(self) -> None:
        with self.assertRaises(ValueError):
            TraceEvent(
                elapsed_seconds=0,
                stage="model",
                action="call",
                result="pass",
                completion_tokens=-1,
            )


if __name__ == "__main__":
    unittest.main()
