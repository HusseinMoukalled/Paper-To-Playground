"""Human-authored scientific oracle, used ONLY in tests, never in production."""
import json
from pathlib import Path
from dataclasses import replace

from playground.ir.models import *
from playground.ir.serialization import decode
from playground.ir.grounding import learner_claims
from playground.retrieval.evidence import EvidencePack


def evidence_pack():
    return decode(EvidencePack, json.loads(Path(__file__).with_name("dev2_evidence.json").read_text(encoding="utf-8")))


def explanation():
    evidence = evidence_pack()
    variables = tuple(ScientificVariable("var-" + name, name, name, meaning, "scalar",
                                        evidence_refs=("E1",)) for name, meaning in (
        ("a", "Gain scales the input."), ("b", "Offset translates the response."),
        ("x", "Input to the response."), ("y", "Output response.")))
    science = ScientificModel(
        concept="Linear response", purpose="Explain gain and offset.", focus_alignment=evidence.focus,
        variables=variables,
        equations=(ScientificEquation("eq-response", "a*x+b", "The linear response is scaled input plus offset.",
                                      tuple(v.id for v in variables), ("E1",)),),
        relationships=(ScientificRelationship("rel-response", "Gain and offset determine the output.",
                                               ("var-a", "var-b", "var-x"), ("var-y",), ("eq-response",), ("E1",)),),
        mechanism_steps=(MechanismStep("step-response", 0, "Scale the input, then add the offset.",
                                       ("eq-response",), ("var-a", "var-b", "var-x"), ("var-y",)),),
        assumptions=("The response is idealized.",), limitations=("No saturation or measurement noise is represented.",),
        misconceptions=("Changing gain is not the same as changing offset.",),
        invariants=("approx_equal(y, a*x+b)",), edge_cases=("Zero gain removes input sensitivity.",),
        provenance=("E1", "E2"), knowledge_classes=tuple(KnowledgeClass),
        demonstration_scope="Toy inputs demonstrate the mechanism, not paper experiments or benchmark results.")
    controls = tuple(ControlSpec("control-" + name, label, "var-" + name, "slider", default, None,
                                 "clamp", ("compute-response", "var-y"), purpose,
                                 "Bounded toy teaching values, not experimental ranges.", 0, 4, 0.1)
                     for name, label, default, purpose in (
                         ("a", "Gain", 1, "Observe scaling sensitivity."),
                         ("b", "Offset", 0, "Observe translation.")))
    explorations = (ExplorationSpec("explore-baseline", "Baseline", "Set gain to one and offset to zero.",
                                    "The output equals the input.", "Unit gain preserves the input.",
                                    {"control-a": 1, "control-b": 0}),
                    ExplorationSpec("explore-contrast", "Contrast", "Increase gain and offset.",
                                    "The output increases.", "Scaling and translation both contribute.",
                                    {"control-a": 2, "control-b": 1}))
    objective = "Explain how gain and offset affect the response."
    lesson = LessonSpec("How do gain and offset affect a response?", (objective,), ("Basic algebra",),
                        "Think of scaling followed by translation.", ("Inspect the equation.", "Vary each control."),
                        {v.id: v.meaning for v in variables}, controls, ("compute-response",),
                        "How does the response change?", "Show the live output response.", explorations,
                        "The model is idealized.", "Gain and offset are different operations.",
                        ("E1 supports the equation; toy inputs are pedagogical.",))
    ir = ExplanationIR(science, lesson,
                       (ComputationSpec("compute-response", "a*x+b", "scalar", ("var-a", "var-b", "var-x"), ("var-y",),
                                        metadata={"bindings": {"a": "var-a", "b": "var-b", "x": "var-x"}, "equation_refs": ["eq-response"]}),),
                       (VisualSpec("visual-response", "scalar", lesson.visual_question, ("compute-response",)),),
                       focus_coverage=FocusCoverageMap(evidence.focus, (objective,), ("eq-response", "step-response"),
                                                      tuple(c.id for c in controls), ("compute-response",),
                                                      ("visual-response",), tuple(e.id for e in explorations)),
                       metadata={"defaults": {"var-x": 2}, "audience": evidence.audience,
                                 "audience_adaptation": "Use introductory algebra and separate gain from offset.",
                                 "invariant_bindings": {"y": "var-y", "a": "var-a", "b": "var-b", "x": "var-x"}})
    source_ids = {v.id for v in variables} | {"eq-response", "rel-response", "step-response", "science.concept", "science.purpose"}
    records = tuple(GroundingRecord(key, text,
                                   KnowledgeClass.SOURCE_GROUNDED if key in source_ids else KnowledgeClass.PEDAGOGICAL,
                                   GroundingStatus.SUPPORTED, ("E1",) if key in source_ids else ())
                    for key, text in learner_claims(ir).items())
    return replace(ir, grounding_records=records)
