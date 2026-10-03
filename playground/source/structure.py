"""Conservative section/reference recognition and coordinate reading order."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from playground.source.document import SourceElement, SourceElementType

NUMBER = r"\d+(?:\.\d+)*[a-zA-Z]?"
CAPTION = re.compile(r"^\s*(Figure|Fig\.?|Table)\s+(" + NUMBER + r")\s*[.:\-]\s*(.*)", re.I | re.S)
HEADING = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:[.)]|\s)+\s*([A-Za-z][^\n]{1,100})$")
EQUATION = re.compile(r"\((" + NUMBER + r")\)\s*$")
ALGORITHM = re.compile(r"^\s*(?:Algorithm|Pseudocode)\s*(\d+)?[.:\s]", re.I)
NOISE = re.compile(r"^(references|bibliography|acknowledg(?:e)?ments|contents|table of contents|author affiliations)\b", re.I)


def noise_heading(text: str) -> bool:
    heading = HEADING.fullmatch(text)
    return bool(NOISE.match(heading.group(2) if heading else text))


def reference_keys(text: str) -> tuple[tuple[str, str], ...]:
    pattern = r"\b(section|sec\.?|equation|eq\.?|figure|fig\.?|table)\s*\(?\s*(" + NUMBER + r")\)?"
    aliases = {"sec": "section", "eq": "equation", "fig": "figure"}
    return tuple((aliases.get(kind.lower().rstrip("."), kind.lower()), number.lower())
                 for kind, number in re.findall(pattern, text, re.I))


def reading_order(blocks: list[dict[str, Any]], width: float) -> list[dict[str, Any]]:
    """Read columns within bands separated by full-width blocks."""
    middle = width / 2
    left = [b for b in blocks if b["bbox"][2] <= middle + width * .04]
    right = [b for b in blocks if b["bbox"][0] >= middle - width * .04]
    if not left or not right:
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
    spans = sorted([b for b in blocks if b not in left and b not in right], key=lambda b: b["bbox"][1])
    pending = [b for b in blocks if b in left or b in right]
    output = []
    for span in spans:
        band = [b for b in pending if b["bbox"][1] < span["bbox"][1]]
        output.extend(sorted(band, key=lambda b: (b["bbox"][0] >= middle - width * .04, b["bbox"][1], b["bbox"][0])))
        pending = [b for b in pending if b not in band]
        output.append(span)
    output.extend(sorted(pending, key=lambda b: (b["bbox"][0] >= middle - width * .04, b["bbox"][1], b["bbox"][0])))
    return output


@dataclass
class StructureBuilder:
    sections: list[dict[str, Any]] = field(default_factory=list)
    elements: list[SourceElement] = field(default_factory=list)
    current: dict[str, Any] | None = None

    def heading(self, text: str, page: int | None, level: int = 1, number: str | None = None) -> None:
        parents = [s for s in self.sections if s["level"] < level]
        self.current = {"section_id": f"sec-{len(self.sections) + 1:04d}", "title": text,
                        "number": number, "level": level, "page": page,
                        "parent_id": parents[-1]["section_id"] if parents else None}
        self.sections.append(self.current)

    def add(self, text: str, *, page: int | None = None, bbox: tuple | None = None,
            kind: SourceElementType | None = None, metadata: dict | None = None,
            recognize_heading: bool = True) -> SourceElement:
        text = text.strip()
        metadata = dict(metadata or {})
        heading = HEADING.fullmatch(text)
        if recognize_heading and not metadata.get("noise") and (heading or NOISE.match(text)) and len(text) < 120:
            self.heading(text, page, heading.group(1).count(".") + 1 if heading else 1,
                         heading.group(1) if heading else None)
        caption = CAPTION.match(text)
        equation = EQUATION.search(text) if any(symbol in text for symbol in ("=", "∝", "→", "∑", "≤", "≥")) else None
        equation_number = figure_number = table_number = None
        if kind is None:
            kind = SourceElementType.PARAGRAPH
            if caption:
                kind = SourceElementType.TABLE if caption.group(1).lower() == "table" else SourceElementType.FIGURE_CONTEXT
            elif equation or (len(text) <= 240 and "\n" not in text
                              and re.fullmatch(r"[\w(),\[\].^+*/\-]+\s*=\s*[^=]+", text)
                              and not re.search(r"[A-Za-z]{3,}\s+[A-Za-z]{3,}", text)):
                kind = SourceElementType.EQUATION
            elif ALGORITHM.match(text):
                kind = SourceElementType.ALGORITHM
        if caption:
            if caption.group(1).lower() == "table":
                table_number = caption.group(2)
                metadata.setdefault("structured", False)
                metadata.setdefault("caption", text)
            else:
                figure_number = caption.group(2)
                metadata.setdefault("caption", text)
                metadata["numeric_values_from_pixels"] = False
        if equation:
            equation_number = equation.group(1)
        if self.current and noise_heading(self.current["title"]):
            metadata["noise"] = True
        metadata["body_references"] = reference_keys(text)
        element = SourceElement(f"SRC-{len(self.elements) + 1:06d}", kind, text, page,
                                self.current["section_id"] if self.current else None,
                                self.current["title"] if self.current else None,
                                equation_number, figure_number, table_number, bbox,
                                len(self.elements), "deterministic", metadata)
        self.elements.append(element)
        return element
