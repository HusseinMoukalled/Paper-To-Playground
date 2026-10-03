"""Evidence Pack contracts passed from source intelligence to science generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class EvidenceType(StrEnum):
    PARAGRAPH = "paragraph"
    EQUATION = "equation"
    ALGORITHM = "algorithm"
    PSEUDOCODE = "pseudocode"
    TABLE = "table"
    CAPTION = "caption"
    FIGURE_CONTEXT = "figure_context"
    FIGURE_LABELS = "figure_labels"


class RetrievalConfidence(StrEnum):
    HIGH = "HIGH"
    AMBIGUOUS = "AMBIGUOUS"
    LOW = "LOW"


@dataclass(frozen=True, slots=True)
class EvidenceChunk:
    evidence_id: str
    evidence_type: EvidenceType
    content: str
    source_element_ids: tuple[str, ...]
    rank: int
    page: int | None = None
    section_id: str | None = None
    section_title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.evidence_id.strip():
            raise ValueError("evidence_id must not be empty")
        if self.rank < 0:
            raise ValueError("rank cannot be negative")
        if self.page is not None and self.page < 1:
            raise ValueError("page numbers are one-based and must be positive")
        if len(self.source_element_ids) != len(set(self.source_element_ids)):
            raise ValueError("source_element_ids must not contain duplicates")


@dataclass(frozen=True, slots=True)
class EvidencePack:
    source_id: str
    paper_metadata: dict[str, Any]
    focus: str
    audience: str
    evidence_blocks: tuple[EvidenceChunk, ...]
    retrieval_confidence: RetrievalConfidence
    retrieval_metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if not self.focus.strip() or not self.audience.strip():
            raise ValueError("focus and audience must not be empty")
        ids = [block.evidence_id for block in self.evidence_blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("EvidencePack IDs must be unique")

    @property
    def evidence_ids(self) -> tuple[str, ...]:
        return tuple(block.evidence_id for block in self.evidence_blocks)
