"""Locked explicit → lexical → heading/symbol → BM25 → rerank → expansion order."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, replace

from playground.budget import RunBudget
from playground.failures import FailureCode, PlaygroundError
from playground.retrieval.confidence import classify_confidence
from playground.retrieval.evidence import EvidenceChunk, EvidencePack, EvidenceType, RetrievalConfidence
from playground.retrieval.index import BM25Index, searchable_text, tokenize
from playground.retrieval.rerank import RerankCandidate, RerankRequest, RerankResult, RetrievalReranker
from playground.source.settings import SourceSettings
from playground.source.structure import reference_keys
from playground.source.support import check_budget, fail


def explicit_lookup(document, references):
    matched, unresolved = set(), []
    for kind, number in references:
        ids = set()
        if kind == "section":
            sections = {section["section_id"] for section in document.sections
                        if str(section.get("number", "")).casefold() == number}
            # Hierarchy is source-derived; children belong to a requested parent section.
            changed = True
            while changed:
                children = {s["section_id"] for s in document.sections if s.get("parent_id") in sections}
                changed = bool(children - sections)
                sections |= children
            ids = {e.element_id for e in document.elements if e.section_id in sections}
        else:
            attr = {"equation": "equation_number", "figure": "figure_number", "table": "table_number"}[kind]
            ids = {e.element_id for e in document.elements if str(getattr(e, attr) or "").casefold() == number}
        matched |= ids
        if not ids:
            unresolved.append(f"{kind} {number}")
    return matched, unresolved


def estimate_tokens(value) -> int:
    """Conservative UTF-8 byte upper bound, including serialized contract overhead.

    This is a size discipline, not an assertion of the model's tokenizer count.
    With a byte tokenizer, at most one token is needed per UTF-8 byte.
    """
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return len(value.encode("utf-8"))


def explanatory_context(document, anchors):
    """Source-derived immediate prose required by typed mechanism evidence."""
    positions = {e.element_id: i for i, e in enumerate(document.elements)}
    result = set()
    for anchor in anchors:
        if anchor.element_type.value not in ("equation", "figure", "figure_context", "table", "algorithm", "pseudocode"):
            continue
        position = positions[anchor.element_id]
        for other in document.elements[max(0, position - 1):position + 2]:
            if (other.element_type.value == "paragraph" and other.section_id == anchor.section_id
                    and not other.metadata.get("noise") and other.content != other.section_title
                    and (anchor.page is None or other.page == anchor.page)):
                result.add(other.element_id)
    return result


def retrieve_evidence(document, focus: str, audience: str, *, settings: SourceSettings | None = None,
                      budget: RunBudget | None = None, trace=None,
                      reranker: RetrievalReranker | None = None, model_id: str | None = None) -> EvidencePack:
    settings = settings or SourceSettings()
    check_budget(budget)
    if not document.elements:
        fail(FailureCode.RETRIEVAL_FAILED, "retrieval", "Cannot retrieve from an empty document.")
    references = tuple(dict.fromkeys(reference_keys(focus)))
    explicit, unresolved = explicit_lookup(document, references)
    large_section = any(kind == 'section' and len(explicit_lookup(document, ((kind, number),))[0]) > settings.max_evidence_chunks
                        for kind, number in references)
    # Section title matches are handled separately in the rank key. Including
    # the title in every BM25 document rewards tiny PDF fragments repeatedly.
    index = BM25Index(tuple(replace(e, section_title=None) for e in document.elements) if large_section else document.elements)
    lexical_focus = re.sub(r'\b(?:section|sec\.?|equation|eq\.?|figure|fig\.?|table)\s*\(?\s*\d+(?:\.\d+)*\)?', '', focus, flags=re.I) if large_section else focus
    scores = index.scores(lexical_focus)
    query = set(tokenize(focus))
    focus_phrase = " ".join(focus.casefold().split())
    records = []
    for element, score in zip(document.elements, scores):
        text = searchable_text(element)
        terms = set(tokenize(text))
        exact = bool(focus_phrase and focus_phrase in " ".join(text.casefold().split()))
        heading_overlap = len(query & set(tokenize(element.section_title or "")))
        # Repeating a section title in a one-character PDF fragment makes BM25
        # prefer that fragment over the actual definition. Rank substantive
        # content ahead of glyph debris and the heading itself.
        if large_section and (len(''.join(c for c in element.content if c.isalpha())) < 20 or element.content == element.section_title):
            heading_overlap = 0
        coverage = len(query & terms) / len(query) if query else 0
        is_explicit = element.element_id in explicit
        # On a large requested section, a short sentence with one keyword must
        # not displace the paragraphs that define and qualify the mechanism.
        if is_explicit and len(explicit) > settings.max_evidence_chunks and element.element_type.value == 'paragraph':
            score *= 1 + min(len(element.content), 1200) / 200
        # Noise can only be promoted by an explicitly requested source reference.
        noise = element.metadata.get("noise", False) and not is_explicit
        key = (is_explicit, exact and not noise, heading_overlap if not noise else 0, score)
        records.append((key, element, coverage, exact))
    records.sort(key=lambda r: (tuple(-float(value) for value in r[0]), r[1].source_order))
    eligible = [r for r in records if r[0][0] or (r[0][3] > 0 and not r[1].metadata.get("noise"))]
    if not eligible:
        fail(FailureCode.RETRIEVAL_INSUFFICIENT_EVIDENCE, "retrieval", "No source evidence matches the requested focus.", recoverable=True)
    top = eligible[0]
    confidence = classify_confidence(explicit_matches=len(explicit), unresolved_references=len(unresolved),
        exact_matches=sum(r[3] for r in eligible), positive_candidates=len(eligible),
        top_term_coverage=top[2], tied_top=len(eligible) > 1 and eligible[1][0] == top[0])
    # Each requested reference gets an anchor before a large section consumes
    # the ordinary candidate slots. This may exceed the rerank preview cap;
    # the final evidence cap remains authoritative.
    protected = []
    protected_ids = set()
    for reference in references:
        matched, _ = explicit_lookup(document, (reference,))
        candidates = [r[1] for r in eligible if r[1].element_id in matched]
        anchor = next((e for e in candidates if not large_section or reference[0] != 'section' or
                       (e.content != e.section_title and len(e.content) >= 40)),
                      candidates[0] if candidates else None)
        if anchor is not None and anchor.element_id not in protected_ids:
            protected.append(anchor)
            protected_ids.add(anchor.element_id)
    selected = protected + [r[1] for r in eligible if r[1].element_id not in protected_ids][
        :max(0, settings.candidate_limit - len(protected))]
    metadata = {"strategy": "explicit_lexical_heading_bm25", "explicit_matches": len(explicit),
                "unresolved_references": unresolved, "top_term_coverage": top[2],
                "top_bm25_score": top[0][3], "rerank_used": False, "neighbor_expansions": 0,
                "confidence_basis": "observable_structural_signals; not a probability",
                "source_is_untrusted": True}
    if trace:
        trace.emit(stage="retrieval", action="rank", result="pass",
                   details={"confidence": confidence.value, "candidates": len(eligible), "explicit_matches": len(explicit)})
    if confidence != RetrievalConfidence.HIGH:
        if reranker is None:
            metadata["rerank_status"] = "unavailable; deterministic evidence retained"
            if trace:
                trace.emit(stage="retrieval", action="fallback", result="warn",
                    details={"reason": "model_rerank_interface_unavailable", "confidence": confidence.value,
                             "fallback": "bounded_deterministic_evidence"})
        elif budget is None or not model_id or not model_id.strip():
            fail(FailureCode.RETRIEVAL_FAILED, "retrieval", "Reranking requires the global budget and supplied model identifier.")
        else:
            request = RerankRequest(model_id, focus, tuple(RerankCandidate(e.element_id, e.section_title,
                e.content[:settings.preview_characters]) for e in selected[:settings.candidate_limit]))
            result = None
            before_calls = budget.calls_used
            try:
                budget.authorize_model_call(completion_token_reservation=request.max_completion_tokens)
                result = reranker.rerank(request, budget=budget, trace=trace)
                if budget.calls_used != before_calls + 1:
                    raise ValueError("model client must account for exactly one rerank attempt")
                if not isinstance(result, RerankResult) or result.prompt_tokens < 0 or result.completion_tokens < 0:
                    raise ValueError("invalid rerank result")
                known = {e.element_id: e for e in selected[:settings.candidate_limit]}
                if len(result.selected_ids) != len(set(result.selected_ids)) or any(i not in known for i in result.selected_ids):
                    raise ValueError("unknown or duplicated rerank IDs")
                if result.completion_tokens > request.max_completion_tokens:
                    raise ValueError("rerank exceeded reservation")
                if result.selected_ids:
                    selected = protected + [known[i] for i in result.selected_ids if i not in protected_ids]
                metadata["rerank_used"] = True
                metadata["rerank_insufficient"] = result.insufficient
                metadata["rerank_selected_ids"] = list(result.selected_ids)
                metadata["rerank_status"] = "pass"
            except Exception as exc:
                metadata["rerank_status"] = "failed; deterministic evidence retained"
                if isinstance(exc, PlaygroundError) and exc.failure.code == FailureCode.BUDGET_EXCEEDED:
                    metadata["rerank_status"] = "budget_denied; deterministic evidence retained"
            finally:
                if trace:
                    trace.emit(stage="retrieval", action="rerank", result="pass" if metadata["rerank_used"] else "warn",
                        details={"status": metadata["rerank_status"], "model_id": model_id,
                                 "attempts": budget.calls_used - before_calls})
    check_budget(budget)
    primary = protected or selected[:1]
    primary_ids = {e.element_id for e in primary}
    required_context = explanatory_context(document, primary)
    # One expansion, including linked captions/equations and immediate same-section context.
    if settings.neighbor_radius:
        neighbors = []
        selected_ids = {e.element_id for e in selected}
        by_id = {e.element_id: position for position, e in enumerate(document.elements)}
        for element in selected:
            pos = by_id[element.element_id]
            candidates = list(document.elements[max(0, pos - 1):pos + 2])
            context_text = " ".join(e.content for e in candidates if e.section_id == element.section_id)
            targets, _ = explicit_lookup(document, reference_keys(context_text))
            candidates += [e for e in document.elements if e.element_id in targets]
            for candidate in candidates:
                if (candidate.element_id not in selected_ids and not candidate.metadata.get("noise")
                        and (candidate.section_id == element.section_id or candidate.element_id in targets)):
                    neighbors.append(candidate)
                    selected_ids.add(candidate.element_id)
        # Linked equations/captions are evidence anchors too. Assemble their
        # immediate prose in this same bounded expansion, without recursively
        # following references from the newly added prose.
        required_context |= explanatory_context(document, selected + neighbors)
        neighbors.extend(e for e in document.elements
                         if e.element_id in required_context and e.element_id not in selected_ids)
        if neighbors:
            metadata["neighbor_expansions"] = 1
            # Required reference anchors precede all context and optional hits.
            # Definition prose then precedes optional candidates, so lexical
            # matches cannot displace the explanatory neighborhood.
            context = [e for e in selected + neighbors if e.element_id in required_context
                       and e.element_id not in primary_ids]
            context_ids = {e.element_id for e in context}
            ordered = primary + context + [e for e in selected + neighbors
                if e.element_id not in primary_ids | context_ids]
            selected = list({e.element_id: e for e in ordered}.values())
    if trace:
        trace.emit(stage="retrieval", action="neighbor_expansion", result="pass",
                   details={"expansions": metadata["neighbor_expansions"]})
    blocks, seen = [], set()
    for element in selected:
        content = element.content
        kind = EvidenceType.FIGURE_CONTEXT if element.element_type.value == "figure" else EvidenceType(element.element_type.value)
        identity = (kind.value, element.section_id, element.equation_number, element.figure_number,
                    element.table_number, " ".join(content.split()), json.dumps(element.metadata.get("rows", [])))
        if identity in seen:
            continue
        evidence_id = "E" + hashlib.sha256((document.source_id + ":" + element.element_id).encode()).hexdigest()[:20]
        block = EvidenceChunk(evidence_id, kind, content, (element.element_id,), len(blocks), element.page,
                              element.section_id, element.section_title, {**element.metadata,
                              "equation_number": element.equation_number, "figure_number": element.figure_number,
                              "table_number": element.table_number, "bbox": element.bbox,
                              "extraction_confidence": element.extraction_confidence})
        proposed = EvidencePack(document.source_id, {**document.metadata, "title": document.title}, focus,
                                audience, tuple(blocks + [block]), confidence, metadata)
        if estimate_tokens(asdict(proposed)) > settings.max_evidence_tokens:
            # Rich details are optional; preserve a complete caption before
            # discarding focused visual evidence merely for its metadata size.
            compact = dict(block.metadata)
            removed = [name for name in ("rows", "columns", "labels", "vector_shapes", "image_bounds", "image_alt", "raw_table_text") if name in compact]
            if removed:
                for name in removed:
                    compact.pop(name)
                compact["evidence_details_omitted"] = removed
                if "rows" in removed:
                    compact["structured"] = False
                block = replace(block, metadata=compact)
                proposed = EvidencePack(document.source_id, proposed.paper_metadata, focus, audience,
                                        tuple(blocks + [block]), confidence, metadata)
        if len(blocks) >= settings.max_evidence_chunks or estimate_tokens(asdict(proposed)) > settings.max_evidence_tokens:
            metadata["size_limited"] = True
            continue
        blocks.append(block)
        seen.add(identity)
    if not blocks:
        fail(FailureCode.EVIDENCE_PACK_INVALID, "evidence_pack", "No complete evidence block fits the evidence size budget.")
    # Assess the final retained evidence, not just the pre-budget candidate list.
    # Diagnostics also count toward the bound; recompute after every removal.
    while blocks:
        included = {element_id for block in blocks for element_id in block.source_element_ids}
        missing_explicit = sorted(explicit - included)
        retained = [e for e in document.elements if e.element_id in included]
        missing_context = sorted((required_context | explanatory_context(document, retained)) - included)
        missing_references = [f"{kind} {number}" for kind, number in references
            if (matches := explicit_lookup(document, ((kind, number),))[0]) and not matches & included]
        metadata.update(omitted_explicit_count=len(missing_explicit),
            omitted_explicit_element_ids=missing_explicit[:settings.candidate_limit],
            omitted_context_count=len(missing_context),
            omitted_context_element_ids=missing_context[:settings.candidate_limit],
            omitted_references=missing_references)
        final_confidence = confidence
        if missing_references or missing_context or metadata.get("rerank_insufficient"):
            final_confidence = RetrievalConfidence.LOW
        elif metadata.get("size_limited") and confidence == RetrievalConfidence.HIGH:
            final_confidence = RetrievalConfidence.AMBIGUOUS
        pack = EvidencePack(document.source_id, {**document.metadata, "title": document.title}, focus,
                            audience, tuple(blocks), final_confidence, metadata)
        if estimate_tokens(asdict(pack)) <= settings.max_evidence_tokens:
            if trace:
                trace.emit(stage="retrieval", action="final_evidence", result="pass" if final_confidence == RetrievalConfidence.HIGH else "warn",
                    details={"confidence": final_confidence.value, "blocks": len(blocks),
                             "omitted_references": len(missing_references), "omitted_context": len(missing_context)})
            return pack
        metadata["size_limited"] = True
        blocks.pop()
    fail(FailureCode.EVIDENCE_PACK_INVALID, "evidence_pack", "Evidence and omission diagnostics exceed the size budget.")
