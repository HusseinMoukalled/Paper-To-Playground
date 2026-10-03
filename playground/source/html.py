"""Static HTML extraction without scripts, browsing, or linked resource access."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from playground.failures import FailureCode
from playground.source.document import DocumentFormat, PaperDocument, SourceElementType
from playground.source.settings import SourceSettings
from playground.source.structure import CAPTION, HEADING, StructureBuilder
from playground.source.support import check_budget, fail
from playground.source.visual_evidence import relevant_caption


def parse_html(source, *, focus: str = "", settings: SourceSettings | None = None, budget=None) -> PaperDocument:
    settings = settings or SourceSettings()
    check_budget(budget)
    soup = BeautifulSoup(source.data, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    for tag in soup.find_all(["script", "style", "nav", "noscript", "iframe", "object", "form"]):
        tag.decompose()
    builder, warnings = StructureBuilder(), []
    extracted_characters = 0
    root = soup.find("article") or soup.find("main") or soup.body or soup
    names = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "figure", "pre", "math", "li"}
    for tag in root.find_all(list(names)):
        check_budget(budget)
        if any(parent.name in names and parent.name not in {"h1", "h2", "h3"} for parent in tag.parents if parent is not root):
            continue
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        extracted_characters += len(text)
        if extracted_characters > settings.max_extracted_characters:
            fail(FailureCode.PARSE_FAILED, "paper_parsing", "HTML exceeds the extraction size limit.")
        metadata = {"html_tag": tag.name}
        kind = None
        if re.fullmatch(r"h[1-6]", tag.name):
            numbered = HEADING.fullmatch(text)
            builder.heading(text, None, int(tag.name[1]), numbered.group(1) if numbered else None)
        elif tag.name == "table":
            kind = SourceElementType.TABLE
            caption = tag.find("caption")
            caption_text = caption.get_text(" ", strip=True) if caption else ""
            metadata["caption"] = caption_text
            # HTML cells are explicit source data, not inferred from layout/pixels.
            rows = [[cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"], recursive=False)]
                    for row in tag.find_all("tr")]
            reliable = bool(rows and len({len(row) for row in rows}) == 1 and all(rows))
            if any(cell.has_attr("rowspan") or cell.has_attr("colspan") for cell in tag.find_all(["th", "td"])):
                reliable = False
            metadata.update(structured=reliable, rows=rows if reliable else [],
                            columns=rows[0] if reliable and tag.find("th") else [])
            if not reliable:
                warnings.append("PARSE_TABLE_FAILED: complex HTML table; caption and raw text retained")
                metadata["raw_table_text"] = text
            text = caption_text or text
            if reliable:
                metadata["richly_processed"] = relevant_caption(text, focus)
        elif tag.name == "figure":
            kind = SourceElementType.FIGURE_CONTEXT
            caption = tag.find("figcaption")
            text = caption.get_text(" ", strip=True) if caption else text
            metadata.update(caption=text, numeric_values_from_pixels=False)
            if relevant_caption(text, focus):
                metadata["labels"] = [t.get_text(" ", strip=True) for t in tag.find_all("text")][:settings.max_visual_items]
                metadata["image_alt"] = [img.get("alt", "") for img in tag.find_all("img")][:settings.max_visual_items]
                metadata["richly_processed"] = True
        elif tag.name == "pre":
            kind = SourceElementType.PSEUDOCODE
        elif tag.name == "math":
            kind = SourceElementType.EQUATION
        builder.add(text, kind=kind, metadata=metadata, recognize_heading=False)
        if len(builder.elements) > settings.max_elements:
            fail(FailureCode.PARSE_FAILED, "paper_parsing", "HTML exceeds the source element limit.")
    if not builder.elements:
        fail(FailureCode.PARSE_FAILED, "paper_parsing", "Static HTML contains no extractable paper evidence.")
    return PaperDocument(source.source_id, DocumentFormat.HTML, title, {"title": title} if title else {},
                         (), tuple(builder.sections), tuple(builder.elements), tuple(warnings))
