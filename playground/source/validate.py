"""Gate 1: real source and EvidencePack provenance/sufficiency checks."""

from dataclasses import asdict

from playground.retrieval.evidence import RetrievalConfidence
from playground.retrieval.retrieve import estimate_tokens, explanatory_context, explicit_lookup
from playground.source.structure import reference_keys
from playground.source.settings import SourceSettings
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus


def validate_source_evidence(document, pack, *, settings: SourceSettings | None = None) -> ValidationReport:
    settings = settings or SourceSettings()
    findings = []

    def finding(status, code, message, target=None):
        findings.append(ValidationFinding(status, code, "source_evidence", message, target))

    if not document.elements or not any(e.content.strip() for e in document.elements):
        finding(ValidationStatus.FAIL, "PARSE_FAILED", "Source extraction is empty.")
    if pack.source_id != document.source_id:
        finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence source ID does not match the document.")
    if not pack.evidence_blocks:
        finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence Pack is empty.")
    elements = {e.element_id: e for e in document.elements}
    ids = [b.evidence_id for b in pack.evidence_blocks]
    if len(ids) != len(set(ids)):
        finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence IDs are duplicated.")
    for rank, block in enumerate(pack.evidence_blocks):
        if not block.content.strip() or not block.source_element_ids:
            finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence lacks content or provenance.", block.evidence_id)
        if block.rank != rank:
            finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence ranks must be contiguous.", block.evidence_id)
        for element_id in block.source_element_ids:
            source = elements.get(element_id)
            if source is None:
                finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence references an absent source element.", block.evidence_id)
            elif (block.page != source.page or block.section_id != source.section_id or block.section_title != source.section_title
                  or block.content != source.content):
                finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence provenance/content differs from the source.", block.evidence_id)
            elif block.metadata.get("rows", []) != source.metadata.get("rows", []):
                if "rows" in block.metadata.get("evidence_details_omitted", []) and "rows" not in block.metadata and block.metadata.get("structured") is False:
                    finding(ValidationStatus.WARN, "EVIDENCE_TABLE_DATA_OMITTED", "Table caption retained; cells omitted to meet evidence size limit.", block.evidence_id)
                else:
                    finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Table cells differ from extracted source cells.", block.evidence_id)
            if source is not None and any(block.metadata.get(name) != getattr(source, name)
                     for name in ("equation_number", "figure_number", "table_number")):
                finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence reference numbers differ from the source.", block.evidence_id)
            if source is not None:
                expected_type = "figure_context" if source.element_type.value == "figure" else source.element_type.value
                if block.evidence_type.value != expected_type:
                    finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence type differs from the extracted source.", block.evidence_id)
                source_bbox = tuple(source.bbox) if source.bbox is not None else None
                evidence_bbox = block.metadata.get("bbox")
                if (tuple(evidence_bbox) if evidence_bbox is not None else None) != source_bbox:
                    finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence bounding box differs from the source.", block.evidence_id)
        if block.metadata.get("numeric_values_from_pixels"):
            finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Pixel-inferred graph values are forbidden.", block.evidence_id)
    if len(pack.evidence_blocks) > settings.max_evidence_chunks or estimate_tokens(asdict(pack)) > settings.max_evidence_tokens:
        finding(ValidationStatus.FAIL, "EVIDENCE_PACK_INVALID", "Evidence Pack exceeds its configured size limit.")
    included = {i for b in pack.evidence_blocks for i in b.source_element_ids}
    for reference in dict.fromkeys(reference_keys(pack.focus)):
        matched, _ = explicit_lookup(document, (reference,))
        if matched and not matched & included:
            finding(ValidationStatus.FAIL, "RETRIEVAL_INSUFFICIENT_EVIDENCE",
                    "A recoverable explicit focus reference was omitted from the final pack.", " ".join(reference))
    anchors = [elements[i] for i in included if i in elements]
    if explanatory_context(document, anchors) - included or pack.retrieval_metadata.get("omitted_context_count"):
        finding(ValidationStatus.WARN, "EVIDENCE_CONTEXT_OMITTED", "Required explanatory source context is missing.")
    if pack.retrieval_metadata.get("size_limited"):
        finding(ValidationStatus.WARN, "EVIDENCE_SIZE_LIMITED", "The evidence size limit omitted source material.")
    if pack.retrieval_metadata.get("rerank_insufficient"):
        finding(ValidationStatus.WARN, "RETRIEVAL_INSUFFICIENT_EVIDENCE", "The reranker reported insufficient evidence.")
    if pack.retrieval_metadata.get("unresolved_references"):
        finding(ValidationStatus.WARN, "RETRIEVAL_INSUFFICIENT_EVIDENCE", "Explicit focus references could not all be resolved.")
    if pack.retrieval_metadata.get("omitted_explicit_element_ids"):
        finding(ValidationStatus.WARN, "RETRIEVAL_INSUFFICIENT_EVIDENCE", "Evidence limits omitted some explicitly referenced section elements.")
    if pack.retrieval_confidence != RetrievalConfidence.HIGH:
        finding(ValidationStatus.WARN, "RETRIEVAL_INSUFFICIENT_EVIDENCE", "Retrieval remains low or ambiguous; downstream claims require caution.")
    for warning in document.extraction_warnings:
        finding(ValidationStatus.WARN, warning.split(":")[0], warning)
    if not document.title:
        finding(ValidationStatus.WARN, "SOURCE_METADATA_UNAVAILABLE", "No reliable paper title was recovered.")
    statuses = {f.status for f in findings}
    status = ValidationStatus.FAIL if ValidationStatus.FAIL in statuses else ValidationStatus.WARN if ValidationStatus.WARN in statuses else ValidationStatus.PASS
    return ValidationReport(status, tuple(findings), "source_evidence")
