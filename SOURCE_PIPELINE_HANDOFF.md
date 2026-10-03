# Developer 1 handoff

The source/evidence subsystem is implemented independently of generation,
computation, rendering and browser validation. README.md and docs/ are unchanged.
The root CLI still truthfully stops at the foundation's generation boundary.

Call `playground.source.pipeline.build_evidence(case, base_dir=case_path.parent,
budget=run_budget, trace=trace_writer)` from the integrating orchestrator.
It returns `SourceStageResult(document, evidence_pack, validation_report)` using
the existing canonical contracts. Expected fatal errors raise `PlaygroundError`.
Warnings, unresolved references and size-limited evidence are visible in the
report and retrieval metadata; global recovery decisions belong to the orchestrator.

## Shared contracts

No existing shared schemas, IDs module, budget, trace, failures, config or
orchestrator were changed. Source IDs hash the original bytes. Element IDs use
the established `SRC-` prefix and deterministic source order. Evidence IDs use
the established `E` prefix followed by a hash of source ID and element ID;
reranking does not reassign them. A parser-version change may change element
ordering; these are stable for the same bytes and extraction implementation.

Tables' structured rows/columns, caption fallbacks, reference numbers, bounding
boxes and figure metadata travel in the existing metadata dictionaries. Source
text is always untrusted data. `tests/fixtures/evidence_pack.json` is a real
extraction/retrieval result from the original generic HTML fixture, for Developer 2.

## Reranking boundary

`playground.retrieval.rerank.RetrievalReranker` is an injectable Protocol for
Developer 2's model client, not a second client. It receives the supplied model
identifier unchanged, focus, short candidate previews and known source IDs,
plus the shared budget and trace writer. The model client must delimit source
data as untrusted, reserve completion tokens, count exactly one transport attempt
(including failures), record usage and trace, and enforce the remaining deadline.
The optional request is capped at 256 completion tokens and five candidates by
default. Invalid IDs/results, transport errors or denied call budgets retain
deterministic evidence and record the fallback. No live model client was added;
this boundary is tested with mocks. HIGH confidence never invokes reranking.

## Bounds and fallbacks

`SourceSettings` centralizes source-stage limits. Defaults: 30-second acquisition
deadline, 32 MiB source, three redirects, at most one transient source retry,
500 PDF pages, 30,000 source elements and four million extracted characters.
Local paths and file URIs read only the explicitly requested paper. `allowed_root`
can restrict local reads; symlink-resolved paths outside it are rejected. UNC
shares, URL credentials and unsupported schemes fail. HTML never loads links,
scripts or images. No source paths/contents or unsafe exception strings are traced.

Evidence is capped at 12 chunks and 8,000 conservatively estimated tokens.
The estimate is the serialized UTF-8 byte count (an upper bound rather than the
model tokenizer's exact count). Complete source blocks are retained without
rewriting equations or truncating claims. Oversized blocks are skipped; a pack
with oversized optional table/figure metadata first falls back to its full
caption with explicitly marked omitted details, never fabricated cells. A pack
that cannot hold any block fails explicitly. Omitted explicit evidence is reported.
One immediate same-section neighborhood/linked-reference expansion is allowed.
Exact focus and audience strings survive unchanged.

PDF tables are processed richly only when relevant, require nonempty data rows,
and must be spatially associated with their caption without crossing another
caption/section boundary. Failure retains the caption and surrounding evidence,
with `PARSE_TABLE_FAILED`. Figure regions are explicitly labeled as heuristic;
labels, image bounds and drawing bounds are source metadata, not inferred graph
datasets. No exact graph values are guessed from pixels. HTML cells are used
only when structurally reliable; merged cells fall back to caption/raw text.

## Requirement review and limitations

Covered: local/file/HTTP acquisition, format sniffing, PDF/static HTML extraction,
canonical normalization, source order and stable IDs, numbered/font/HTML headings
and hierarchy, paragraphs/equations/algorithms, tables/fallbacks, figures/labels/
vector metadata with relevance gating, multi-column ordering, provenance,
explicit references, lexical/heading matching, internal BM25, categorical
confidence, bounded rerank interface, one expansion, deduplication, pack limits,
typed failures, sanitized trace and Gate 1 validation.

No embeddings, vector service, OCR, image-semantic model or additional model is
used. Scanned-only PDFs fail explicitly. Heading/caption/column heuristics are
conservative and cannot recover all unusual layouts or equations; unresolved
references are reported rather than invented. Captions without recognizable
number/punctuation may remain paragraphs. PDF figure geometry is a bounded
caption neighborhood, not a claim of exact figure segmentation. Uncaptioned PDF
visuals remain in nearby extracted text rather than receiving invented numbers.
HTML with required dynamic JavaScript is outside the static parser's scope.

Confidence uses explicit matches, exact matches, complete term coverage and ties,
not a numeric probability threshold. Generic regression fixtures exercise these
decisions; broader real-paper benchmark tuning/ablation remains an integration
task. Live DeepSeek reranking remains dependent on Developer 2's permitted model
client. No upstream semantic sufficiency or scientific claims are asserted by
Gate 1 when retrieval remains LOW/AMBIGUOUS.

## Validation

Run on Python 3.11:

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python agent.py --help
python -m compileall -q playground agent.py
```

Tests use original PDFs generated with PyMuPDF, static HTML and mocked HTTP/model
responses. They cover source failures, bounds, table fallback, multi-column
layout, source references, graph anti-hallucination, injection-looking text,
provenance tampering, evidence stability/size, rerank budgets/failure, JSON contract
roundtrips and trace integration. Existing foundation and CLI tests are included.
No commit, push or merge is performed.

Verified in this workspace using a local CPython 3.11.14 environment: all 72
tests passed, including the existing foundation and CLI tests; compile/import
checks passed; CLI help exited 0; an invalid case exited 2 with
`INPUT_SCHEMA_INVALID` and no traceback. Dependencies were installed from the
pinned requirements into the local environment. HTTP and reranking tests use
mocks, so this does not claim a live OpenRouter or public-paper network test.

## Pre-merge review corrections (2026-10-03)

The four independently reproduced review findings are covered by regression
tests and corrected locally:

- Each explicit focus reference receives a reserved evidence anchor before
  ordinary candidate selection. A reranker cannot remove those anchors; its
  preview remains bounded by `candidate_limit`. Gate 1 independently verifies
  final reference coverage. A reference found in the source but omitted from
  the pack fails the gate instead of reporting successful retrieval.
- Uniquely aligned PDF formula/number blocks are associated before column
  ordering. The exact extracted expression and number are joined; the union
  bounding box and both original component boxes are preserved. Ambiguous or
  unassociated isolated numbers remain source text with a structured warning;
  no expression is guessed or repaired. Multiline associations are deliberately
  conservative and may remain unresolved.
- Repeated edge noise cannot create a numbered or font-based heading, so
  continuing body paragraphs retain their actual section provenance.
- Required reference anchors precede optional material. Immediate explanatory
  prose is assembled for selected and linked typed evidence in the single
  expansion, without recursively following additional prose references.
  Final confidence is recomputed after size limits and diagnostic overhead.
  Context omissions produce `EVIDENCE_CONTEXT_OMITTED` and LOW confidence;
  `size_limited` produces `EVIDENCE_SIZE_LIMITED`. Gate 1 recomputes source
  neighborhoods even if omission metadata is absent or incorrect.

The byte bound and complete-block policy remain conservative: an explanatory
block too large for the configured pack is not rewritten or silently truncated.
Its omission is visible to the orchestrator. Very small bounds that cannot fit
evidence plus diagnostics fail explicitly. Source-text deduplication preserves
distinct sections and numbered evidence references.

Verification: created a fresh CPython 3.11.14 virtual environment outside the
repository, installed through `python -m pip install -r requirements.txt`, and
ran all 72 tests successfully (57 original tests plus 15 regression tests).
The Developer 2 evidence fixture was refreshed for the additional retrieval
diagnostics. Live model reranking, empirical confidence calibration on diverse
real papers, and integration into the team orchestrator remain pending; these
checks do not claim that the full evaluator pipeline is implemented.

## File inventory

Modified:

```text
requirements.txt
```

Created:

```text
SOURCE_PIPELINE_HANDOFF.md
playground/source/acquire.py
playground/source/html.py
playground/source/pdf.py
playground/source/pipeline.py
playground/source/settings.py
playground/source/structure.py
playground/source/support.py
playground/source/validate.py
playground/source/visual_evidence.py
playground/retrieval/confidence.py
playground/retrieval/index.py
playground/retrieval/rerank.py
playground/retrieval/retrieve.py
tests/fixtures/__init__.py
tests/fixtures/evidence_pack.json
tests/fixtures/source_factory.py
tests/integration/source_to_evidence/__init__.py
tests/integration/source_to_evidence/test_pipeline.py
tests/unit/retrieval/__init__.py
tests/unit/retrieval/test_retrieve.py
tests/unit/source/__init__.py
tests/unit/source/test_acquire.py
tests/unit/source/test_parsers.py
```

Ignored local verification files are under `.venv/`, `tmp/` (interpreter,
test environment, download cache and invalid-case trace), and `__pycache__/`.
They are not runtime requirements or submission files.
