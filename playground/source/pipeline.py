"""Developer 1's source-stage entry point, ready for orchestration integration.

This module performs no global retries or recovery transitions. It returns
warnings to the orchestrator and raises typed fatal failures. Later semantic
generation and artifact production are deliberately outside this subsystem.
"""

from dataclasses import dataclass
from pathlib import Path

from playground.config import CaseInput
from playground.failures import FailureCode, PlaygroundError
from playground.retrieval.evidence import EvidencePack
from playground.retrieval.retrieve import retrieve_evidence
from playground.source.acquire import acquire_source
from playground.source.document import DocumentFormat, PaperDocument
from playground.source.html import parse_html
from playground.source.pdf import parse_pdf
from playground.source.settings import SourceSettings
from playground.source.support import check_budget, fail
from playground.source.validate import validate_source_evidence
from playground.validation.report import ValidationReport, ValidationStatus


@dataclass(frozen=True, slots=True)
class SourceStageResult:
    document: PaperDocument
    evidence_pack: EvidencePack
    validation_report: ValidationReport


def build_evidence(case: CaseInput, *, base_dir: Path | None = None, allowed_root: Path | None = None,
                   settings: SourceSettings | None = None, budget=None, trace=None,
                   transport=None, reranker=None, model_id: str | None = None) -> SourceStageResult:
    """Resolve relative sources against base_dir (normally the case file's parent).

    Only the explicit source is read; no HTML links/images or source-supplied
    local paths are opened. A host may additionally restrict local reads using
    allowed_root. Trace receives summaries and sanitized failures, never content.
    """
    settings = settings or SourceSettings()
    stage = "source_acquisition"
    try:
        source = acquire_source(case.source_url, base_dir=base_dir, allowed_root=allowed_root,
                                settings=settings, budget=budget, transport=transport)
        if trace:
            trace.emit(stage=stage, action="acquire", result="pass",
                       details={"format": source.format.value, "bytes": len(source.data), "source_id": source.source_id})
        stage = "paper_parsing"
        parser = parse_pdf if source.format == DocumentFormat.PDF else parse_html
        document = parser(source, focus=case.focus, settings=settings, budget=budget)
        if trace:
            trace.emit(stage=stage, action="extract", result="pass",
                       details={"elements": len(document.elements), "sections": len(document.sections),
                                "pages": len(document.pages), "warnings": len(document.extraction_warnings)})
        stage = "retrieval"
        pack = retrieve_evidence(document, case.focus, case.audience, settings=settings,
                                 budget=budget, trace=trace, reranker=reranker, model_id=model_id)
        check_budget(budget)
        stage = "evidence_pack"
        report = validate_source_evidence(document, pack, settings=settings)
        if trace:
            trace.emit(stage=stage, action="validate", result=report.status.value.lower(),
                       details={"blocks": len(pack.evidence_blocks), "finding_codes": [f.code for f in report.findings]})
        if report.status == ValidationStatus.FAIL:
            fail(FailureCode.EVIDENCE_PACK_INVALID, stage, "Source/evidence validation failed.")
        return SourceStageResult(document, pack, report)
    except PlaygroundError as exc:
        if trace:
            trace.emit(stage=exc.failure.stage, action="failure", result="fail", details=exc.failure.to_dict())
        raise
    except Exception:
        if trace:
            trace.emit(stage=stage, action="failure", result="fail", details={"code": FailureCode.UNEXPECTED_ERROR.value})
        fail(FailureCode.UNEXPECTED_ERROR, stage, "Unexpected source-stage error; unsafe details were omitted.")
