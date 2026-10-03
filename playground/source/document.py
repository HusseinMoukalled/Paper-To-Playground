"""Library-independent representation of extracted paper source material."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DocumentFormat(StrEnum):
    PDF = "pdf"
    HTML = "html"
    UNKNOWN = "unknown"


class SourceElementType(StrEnum):
    PARAGRAPH = "paragraph"
    EQUATION = "equation"
    ALGORITHM = "algorithm"
    PSEUDOCODE = "pseudocode"
    TABLE = "table"
    CAPTION = "caption"
    FIGURE = "figure"
    FIGURE_CONTEXT = "figure_context"
    FIGURE_LABELS = "figure_labels"


@dataclass(frozen=True, slots=True)
class SourceElement:
    element_id: str
    element_type: SourceElementType
    content: str
    page: int | None = None
    section_id: str | None = None
    section_title: str | None = None
    equation_number: str | None = None
    figure_number: str | None = None
    table_number: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    source_order: int = 0
    extraction_confidence: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.element_id.strip():
            raise ValueError("element_id must not be empty")
        if self.page is not None and self.page < 1:
            raise ValueError("page numbers are one-based and must be positive")
        if self.source_order < 0:
            raise ValueError("source_order cannot be negative")
        if self.bbox is not None and len(self.bbox) != 4:
            raise ValueError("bbox must contain four coordinates")


@dataclass(frozen=True, slots=True)
class PaperDocument:
    source_id: str
    source_type: DocumentFormat
    title: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    pages: tuple[int, ...] = ()
    sections: tuple[dict[str, Any], ...] = ()
    elements: tuple[SourceElement, ...] = ()
    extraction_warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        element_ids = [element.element_id for element in self.elements]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("PaperDocument element IDs must be unique")
        if any(page < 1 for page in self.pages):
            raise ValueError("PaperDocument page numbers are one-based and positive")
