"""PyMuPDF extraction normalized immediately to canonical source contracts."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
import re
from statistics import median

import pymupdf

from playground.failures import FailureCode, PlaygroundError
from playground.source.document import DocumentFormat, PaperDocument, SourceElementType
from playground.source.settings import SourceSettings
from playground.source.structure import CAPTION, EQUATION, HEADING, NUMBER, StructureBuilder, reading_order
from playground.source.support import check_budget, fail
from playground.source.visual_evidence import enrich_figure, relevant_caption


def associate_equation_numbers(blocks, warnings):
    """Join uniquely aligned source blocks before column ordering separates them.

    No equation is repaired or inferred: only extracted text and coordinates
    are joined. Ambiguous associations remain separate and are reported.
    """
    consumed = set()
    replacements = {}
    for number_index, number in enumerate(blocks):
        if not re.fullmatch(r"\(" + NUMBER + r"\)", number["text"].strip()):
            continue
        nx0, ny0, nx1, ny1 = number["bbox"]
        candidates = []
        for index, block in enumerate(blocks):
            if index == number_index or index in consumed or index in replacements:
                continue
            x0, y0, x1, y1 = block["bbox"]
            if (any(symbol in block["text"] for symbol in ("=", "∝", "→", "∑", "≤", "≥"))
                    and "\n" not in block["text"] and not EQUATION.search(block["text"]) and x1 <= nx0
                    and abs(y1 - ny1) <= max(3, (ny1 - ny0) * .4)
                    and y1 - y0 <= (ny1 - ny0) * 2):
                candidates.append(index)
        if len(candidates) != 1:
            warnings.append("PARSE_EQUATION_NUMBER_UNRESOLVED: isolated number has no unique aligned expression")
            continue
        index = candidates[0]
        expression = blocks[index]
        x0, y0, x1, y1 = expression["bbox"]
        replacements[index] = {**expression, "text": expression["text"] + " " + number["text"],
            "bbox": (min(x0, nx0), min(y0, ny0), max(x1, nx1), max(y1, ny1)),
            "component_bboxes": [list(expression["bbox"]), list(number["bbox"])]}
        consumed.add(number_index)
    return [replacements.get(i, block) for i, block in enumerate(blocks) if i not in consumed]


def parse_pdf(source, *, focus: str = "", settings: SourceSettings | None = None, budget=None) -> PaperDocument:
    settings = settings or SourceSettings()
    builder, warnings = StructureBuilder(), []
    try:
        with pymupdf.open(stream=source.data, filetype="pdf") as document:
            if document.needs_pass:
                fail(FailureCode.PARSE_FAILED, "paper_parsing", "Encrypted PDF requires an unsupported password.")
            if len(document) > settings.max_pages:
                fail(FailureCode.PARSE_FAILED, "paper_parsing", "PDF exceeds the page limit.")
            metadata = {key: value for key, value in document.metadata.items() if value}
            page_blocks = []
            edge_texts = Counter()
            extracted_characters = block_count = 0
            for page in document:
                check_budget(budget)
                blocks = []
                # TEXTFLAGS_TEXT avoids materializing embedded image bytes.
                raw_blocks = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]
                # Math fragments on a single-column page are not prose columns.
                # Require actual prose lines on both sides before splitting blocks.
                middle = page.rect.width / 2
                prose_sides = Counter()
                for raw_block in raw_blocks:
                    for line in raw_block.get('lines', []):
                        text = ''.join(s['text'] for s in line['spans'])
                        if len(re.findall(r'[A-Za-z]{2,}', text)) < 3:
                            continue
                        x0, _y0, x1, _y1 = line['bbox']
                        side = 'left' if x1 <= middle + page.rect.width * .04 else 'right' if x0 >= middle - page.rect.width * .04 else 'span'
                        prose_sides[side] += 1
                two_columns = bool(prose_sides['left'] and prose_sides['right'] and
                                   prose_sides['left'] + prose_sides['right'] > prose_sides['span'])
                for block in raw_blocks:
                    if block.get("type") != 0:
                        continue
                    # PDF text blocks can themselves merge lines from separate columns.
                    groups = {}
                    middle = page.rect.width / 2
                    lines_in_block = block.get('lines', [])
                    has_equation_number = any(re.fullmatch(r'\(' + NUMBER + r'\)',
                        ''.join(s['text'] for s in line['spans']).strip()) for line in lines_in_block)
                    for line_index, line in enumerate(lines_in_block):
                        x0, y0, x1, y1 = line["bbox"]
                        side = ("left" if x1 <= middle + page.rect.width * .04 else "right" if x0 >= middle - page.rect.width * .04 else "span") if two_columns else 'span'
                        if has_equation_number:
                            side = f'equation-line-{line_index}'
                        groups.setdefault(side, []).append(line)
                    for lines in groups.values():
                        text = "\n".join("".join(s["text"] for s in line["spans"]) for line in lines).strip()
                        if not text:
                            continue
                        extracted_characters += len(text)
                        block_count += 1
                        if extracted_characters > settings.max_extracted_characters or block_count > settings.max_elements:
                            fail(FailureCode.PARSE_FAILED, "paper_parsing", "PDF exceeds the extraction size limit.")
                        sizes = [s["size"] for line in lines for s in line["spans"]]
                        bbox = (min(line["bbox"][0] for line in lines), min(line["bbox"][1] for line in lines),
                                max(line["bbox"][2] for line in lines), max(line["bbox"][3] for line in lines))
                        bold = any(s.get('flags', 0) & 16 for line in lines for s in line['spans'])
                        blocks.append({"text": text, "bbox": bbox, "font_size": max(sizes, default=0),
                                       'bold': bold})
                        if bbox[1] < page.rect.height * .08 or bbox[3] > page.rect.height * .92:
                            edge_texts[text] += 1
                ordered = associate_equation_numbers(blocks, warnings)
                page_blocks.append(reading_order(ordered, page.rect.width) if two_columns else
                                   sorted(ordered, key=lambda b: (b['bbox'][1], b['bbox'][0])))
            body_size = median([b["font_size"] for blocks in page_blocks for b in blocks] or [10])
            for page_index, blocks in enumerate(page_blocks):
                check_budget(budget)
                for block in blocks:
                    text, bbox = block["text"], block["bbox"]
                    meta = {"font_size": block["font_size"]}
                    if "component_bboxes" in block:
                        meta["component_bboxes"] = block["component_bboxes"]
                    if len(document) > 1 and edge_texts[text] >= max(2, len(document) // 2):
                        meta["noise"] = True
                    if (not meta.get("noise") and not HEADING.match(text) and not CAPTION.match(text) and len(text) < 100
                            and "\n" not in text and block["font_size"] > body_size * 1.2):
                        builder.heading(text, page_index + 1)
                    match = HEADING.fullmatch(text)
                    # Numbered sentences, lists and formula fragments must not
                    # reset the section. Use typography or a short title shape.
                    title = match.group(2) if match else ''
                    title_words = re.findall(r'[A-Za-z]+', title)
                    short_title = (0 < len(title_words) <= 8 and title[:1].isupper() and
                                   not re.search(r'[.;:=!?]|\d', title) and
                                   all(word[:1].isupper() or word.lower() in
                                       {'a', 'an', 'the', 'of', 'and', 'or', 'in', 'on', 'for', 'to', 'with'}
                                       for word in title_words))
                    numbered_heading = bool(match and (title.isupper() or block.get('bold') or
                                             block['font_size'] > body_size * 1.05 or short_title))
                    builder.add(text, page=page_index + 1, bbox=bbox, metadata=meta,
                                recognize_heading=not meta.get("noise", False) and
                                (numbered_heading or bool(re.match(r'^(References|Bibliography|Acknowledg)', text, re.I))))
                    if len(builder.elements) > settings.max_elements:
                        fail(FailureCode.PARSE_FAILED, "paper_parsing", "PDF exceeds the source element limit.")
            # Visual enrichment occurs after section assignment, allowing focus relevance gating.
            for index, element in enumerate(builder.elements):
                check_budget(budget)
                if element.element_type not in (SourceElementType.TABLE, SourceElementType.FIGURE_CONTEXT):
                    continue
                section_text = " ".join(e.content for e in builder.elements if e.section_id == element.section_id)
                if not relevant_caption(element.content, focus, section_text):
                    continue
                page = document[element.page - 1]
                if element.element_type == SourceElementType.FIGURE_CONTEXT:
                    try:
                        builder.elements[index] = enrich_figure(element, page, settings)
                    except Exception:
                        warnings.append("PARSE_FIGURE_METADATA_FAILED: caption and context retained")
                    continue
                try:
                    tables = page.find_tables().tables
                    # Only attach a table spatially near this caption, in the same column.
                    eligible = [t for t in tables if min(t.bbox[2], element.bbox[2]) > max(t.bbox[0], element.bbox[0])]
                    eligible = [t for t in eligible if min(abs(t.bbox[1] - element.bbox[3]), abs(element.bbox[1] - t.bbox[3])) < page.rect.height * .2]
                    # A caption cannot jump across another visual's caption or a
                    # section boundary to claim an unrelated detected grid.
                    def unobstructed(table):
                        gap_start, gap_end = ((table.bbox[3], element.bbox[1])
                            if table.bbox[3] < element.bbox[1] else (element.bbox[3], table.bbox[1]))
                        return not any(other.element_id != element.element_id and other.page == element.page
                            and other.bbox is not None and gap_start < other.bbox[1] < gap_end
                            and (CAPTION.match(other.content) or HEADING.fullmatch(other.content))
                            for other in builder.elements)
                    eligible = [t for t in eligible if unobstructed(t)]
                    if not eligible:
                        raise ValueError("no reliable caption-associated table")
                    table = min(eligible, key=lambda t: min(abs(t.bbox[1] - element.bbox[3]), abs(element.bbox[1] - t.bbox[3])))
                    rows = [row for row in table.extract() if any(cell for cell in row)]
                    if len(rows) < 2 or not any(any(cell for cell in row) for row in rows):
                        raise ValueError("empty table")
                    if sum(len(row) for row in rows) > settings.max_visual_items * 16:
                        raise ValueError("table exceeds structured cell limit")
                    builder.elements[index] = replace(element, metadata={**element.metadata,
                        "structured": True, "columns": list(table.header.names), "rows": rows,
                        "table_bbox": list(table.bbox), "richly_processed": True})
                except Exception:
                    warnings.append(f"PARSE_TABLE_FAILED: {element.element_id}; caption and context retained")
            if not builder.elements:
                fail(FailureCode.PARSE_FAILED, "paper_parsing", "PDF extraction is empty; scanned PDFs require OCR which is not enabled.")
            return PaperDocument(source.source_id, DocumentFormat.PDF, metadata.get("title"), metadata,
                                 tuple(range(1, len(document) + 1)), tuple(builder.sections),
                                 tuple(builder.elements), tuple(warnings))
    except PlaygroundError:
        raise
    except Exception as exc:
        fail(FailureCode.PARSE_FAILED, "paper_parsing", "PDF is corrupt or could not be extracted.")
