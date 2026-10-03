"""Shared typed contracts for the scientific and pedagogical IR boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class KnowledgeClass(StrEnum):
    SOURCE_GROUNDED = "SOURCE_GROUNDED"
    DERIVED = "DERIVED"
    PEDAGOGICAL = "PEDAGOGICAL"


class GroundingStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class ScientificVariable:
    id: str
    source_symbol: str | None
    display_symbol: str
    meaning: str
    type: str
    shape: tuple[int | str, ...] = ()
    domain: str | None = None
    units: str | None = None
    evidence_refs: tuple[str, ...] = ()
    knowledge_class: KnowledgeClass = KnowledgeClass.SOURCE_GROUNDED


@dataclass(frozen=True, slots=True)
class ScientificEquation:
    id: str
    expression: str
    meaning: str
    variable_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    knowledge_class: KnowledgeClass = KnowledgeClass.SOURCE_GROUNDED


@dataclass(frozen=True, slots=True)
class ScientificRelationship:
    id: str
    description: str
    input_refs: tuple[str, ...]
    output_refs: tuple[str, ...]
    equation_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    knowledge_class: KnowledgeClass = KnowledgeClass.SOURCE_GROUNDED


@dataclass(frozen=True, slots=True)
class MechanismStep:
    id: str
    order: int
    description: str
    equation_refs: tuple[str, ...] = ()
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ScientificModel:
    concept: str
    purpose: str
    focus_alignment: str
    variables: tuple[ScientificVariable, ...] = ()
    equations: tuple[ScientificEquation, ...] = ()
    relationships: tuple[ScientificRelationship, ...] = ()
    mechanism_steps: tuple[MechanismStep, ...] = ()
    assumptions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    misconceptions: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    edge_cases: tuple[str, ...] = ()
    provenance: tuple[str, ...] = ()
    knowledge_classes: tuple[KnowledgeClass, ...] = ()
    demonstration_scope: str = ""


@dataclass(frozen=True, slots=True)
class ControlSpec:
    id: str
    label: str
    scientific_variable: str
    control_type: str
    default: Any
    units: str | None
    validation_rule: str
    effect_targets: tuple[str, ...]
    learning_purpose: str
    safe_range_reason: str
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    options: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExplorationSpec:
    id: str
    title: str
    change: str
    observe: str
    why: str
    setup: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LessonSpec:
    central_learning_question: str
    learning_objectives: tuple[str, ...]
    audience_prerequisites: tuple[str, ...]
    intuition: str
    teaching_sequence: tuple[str, ...]
    symbol_explanations: dict[str, str]
    controls: tuple[ControlSpec, ...]
    important_intermediates: tuple[str, ...]
    visual_question: str
    visual_intent: str
    guided_explorations: tuple[ExplorationSpec, ...]
    limitation_or_assumption: str
    misconception: str
    source_grounding_plan: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComputationSpec:
    id: str
    expression: str
    output_type: str
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VisualSpec:
    id: str
    visual_type: str
    question: str
    data_refs: tuple[str, ...]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GroundingRecord:
    claim_id: str
    claim: str
    knowledge_class: KnowledgeClass
    status: GroundingStatus
    evidence_refs: tuple[str, ...] = ()
    computation_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FocusCoverageMap:
    focus: str
    learning_objective_refs: tuple[str, ...]
    mechanism_refs: tuple[str, ...]
    control_refs: tuple[str, ...]
    computation_refs: tuple[str, ...]
    visual_refs: tuple[str, ...]
    exploration_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExplanationIR:
    scientific_model: ScientificModel
    lesson_spec: LessonSpec
    computations: tuple[ComputationSpec, ...] = ()
    visuals: tuple[VisualSpec, ...] = ()
    grounding_records: tuple[GroundingRecord, ...] = ()
    focus_coverage: FocusCoverageMap | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
