# Team integration verification

Branch: **hadi-integration**. Main has not been merged into or modified.
This records an integration checkpoint, not a guarantee of correctness for every paper.
The authoritative specification remains README.md and the developer documents.

## Included developer work

- Developer 1: `origin/dev/source-pipeline`, commit `cc4c8c6`.
- Developer 2: `origin/dev/science-engine`, commit `aa817e9`.
- Developer 3: `origin/dev/playground-runtime`, commit `d8672c4`.

All three tips were fetched and verified as ancestors of this branch. They were merged
without squashing. Conflicts in requirements.txt and tests/fixtures/__init__.py were
resolved by retaining the combined dependencies and both fixture families.

## Connected production path

```text
agent.py --input CASE --output OUT --model MODEL_ID
  -> shared CaseInput / RunBudget / TraceWriter
  -> Dev1 acquisition, PDF/HTML parsing, bounded retrieval, EvidencePack
  -> one centralized OpenRouter client using MODEL_ID unchanged
  -> Dev2 ScientificModel + LessonSpec, claim-level grounding, focus coverage
  -> restricted DSL, canonical AST v1, Python computation and invariant checks
  -> concrete-risk-only semantic verification / narrowly authorized claim repair
  -> Dev3 manifest, pre-engineered UI, the same AST evaluated in the browser
  -> static/browser validation, atomic index.html promotion, diagnostic reports
```

The CLI is no longer a successful-looking stub. A missing source fails cleanly.
Missing credentials, invalid science and unsupported risky claims also fail without
overwriting a previous valid HTML artifact.

## Integration fixes

- Connected the source, semantic, computation, renderer and validation entry points.
- Added a consumer adapter for Dev2's real `{kind,value,args}` AST and declarative mechanisms.
  The browser no longer relies on the different legacy renderer-fixture AST format.
- Matched Python/browser behavior for all 24 operations, scalar broadcasting, arrays,
  symbolic shapes, domains, normalization, mixed-type comparison rejection and invariants.
- Preserved computation-ID references, dependency ordering, fixed inputs and control-ID presets.
- Reduced semantic output duplication with an explicitly model-declared compact grounding
  policy; deterministic expansion still creates every required strict claim-level record.
  It does not invent evidence IDs or silently promote unsupported scientific claims.
- Added conservative JSON/wire formatting recovery, without rewriting scientific equations.
- Wired optional retrieval reranking through the same model client and budget.
- Disabled/excluded requested model reasoning output; no chain-of-thought is requested or logged.
- Preserved PDF-marked superscripts using native span flags. PDF visual inspection revealed
  lost exponent layout and fragment-only evidence; bounded, same-expansion section anchors
  now retain relevant unnumbered formulas and their immediate definition prose.
- Equation consistency follows only declared expression dependencies under strict work bounds.
  It does not assert arbitrary algebraic rewrites equivalent.
- Narrow equation verification includes dependency definitions and existing adjacent evidence.
  Derived intermediates are checked through executable lineage, not treated as paper quotations.
- Added concrete rate/reciprocal terminology risk detection after manual inspection caught a
  mislabeled frequency denominator in a mechanically valid generated lesson. Narrow repairs
  can address up to two failed claim-text units in one leaf-only patch, followed by revalidation.
- Added source warnings, collapsed claim audit, mobile equation overflow handling, and a safe
  labeled-state visual fallback when a requested curve has no computed series/coordinates.
- Kept secret redaction, bounded model requests, finalization reserve and atomic promotion.
- Final diagnostic status combines source, IR and artifact findings instead of hiding upstream warnings.

## Verification results

Python 3.11 regression suite: **171 tests run, successful, 1 skipped**. The skipped item is
the Python Playwright browser class; Windows Application Control blocks its greenlet extension.
Four canonical browser tests ran successfully using an existing Node Playwright installation
and real Chrome. Application Control was not changed or bypassed.

Coverage includes the existing foundation and all developer suites, genuine source parsing
with mocked model transport, strict grounding/coverage/schema failures, malicious DSL rejection,
AST serialization, all operations, numerical stability, scalar/vector/matrix execution,
iteration/state transitions, defaults/boundaries/presets, controls, reset, offline operation,
targeted repair constraints, key handling, rate limits/timeouts/retries and global budgets.

Dependency check: `pip --python <local Python 3.11> check` reported no broken requirements.
The ignored embedded runtime does not contain pip; the bundled pip controller performed this
read-only dependency check. Normal Python 3.11 installations use the standard pip command.

Git whitespace/conflict checks passed. No eval/exec calls, embedding/local/fallback-model
dependencies or new model SDK dependency were introduced. The actual configured key had
zero matches in non-ignored repository files and in the two successful runs' HTML/JSON/traces.
Temporary downloads, diagnostics and generated artifacts remain ignored and uncommitted.

### Actual live model runs

Model supplied unchanged: `deepseek/deepseek-v4.1-flash`.

- Synthetic affine-response article: fresh CLI success, **1 request**, **3,291 completion tokens**,
  **16.656 seconds**. Source/IR/static artifact validation passed. This is not a published-paper result.
- Published-paper positional-encoding focus: fresh CLI success, **3 requests**, **3,817 completion
  tokens**, **18.094 seconds**. One semantic request plus two narrow equation checks. IR and
  static artifact validation passed; source extraction/retrieval warnings remain visible.
- The actual generated artifacts both passed independent offline Chrome verification:
  seven non-default control probes, two presets, deterministic reset, shared-state
  numbers/equations/visuals, Python parity, zero page errors, zero HTTP requests, and mobile widths.
- The real-paper artifact was deterministically rerendered after the safe visual-fallback
  change and again passed the same Chrome verification. Desktop/mobile screenshots were inspected.
- Manual review found an incorrect quantity label in that earlier mechanically passing lesson.
  A later stricter run rejected two unsupported claims and promoted no artifact. Therefore the
  earlier real-paper result proves pipeline/browser connectivity, not full scientific quality.
- Final stricter paper run: **success**, **4 requests**, **4,344 completion tokens**,
  **68.422 seconds**, with one semantic request and three narrow supported verdicts.
  Manual inspection confirmed the frequency denominator is labeled as a denominator,
  not as angular frequency. The bounded lesson demonstrates the even sine branch and
  explicitly excludes the full embedding vector, cosine branch and downstream performance.
  Its actual artifact passed **8 control probes**, two presets, reset, offline Chrome,
  Python/browser numerical parity and mobile widths. Source/browser WARN findings remain.
- Two-stage live comparison on the synthetic source: **failed ScientificModel schema validation**
  on its first request, **2,261 completion tokens**, approximately **11.047 seconds**. The option
  remains experimental; the combined strategy is the working default.

Both successful CLI reports are WARN on this machine because the application's Python
browser controller is unavailable. Independent Chrome verification supplements that result;
it does not retroactively change the CLI report to PASS. Earlier model attempts also exposed
and correctly rejected schema, grounding, equation-linkage and invariant failures.
These small tests do not establish a statistical quality benchmark across arbitrary papers.

## Shared contracts and call strategy

No canonical shared dataclasses were replaced or changed. ScientificModel, LessonSpec,
ExplanationIR, EvidencePack, ValidationReport, Failure, RunBudget and trace shapes remain compatible.
The render manifest now explicitly carries `canonical_ast_version=1` and canonical computation
envelopes. The legacy fixture path is retained for existing tests, not used as generated science.

Default semantic strategy: one combined request with separate science/lesson structures.
Optional reranking and concrete-risk verification are bounded. Up to two failed claim/evidence
units can receive one leaf-only repair request and revalidation; equations are not silently rewritten.
Retries and optional calls count against the same 10-request, 30,000-completion-token,
600-second case budget. No agent swarm, separate critic, fallback model, embeddings or VLM.

## Remaining limitations

- The two-stage strategy is configurable and unit-tested, but failed its live comparison.
- Native Python browser validation cannot run on this particular Windows security policy;
  the specified static-validation WARN fallback is used. Other environments must verify their controller.
- No OCR for scanned papers. PDF layout/extraction can still be imperfect and is explicitly warned.
- The restricted DSL and generic visuals do not cover every conceivable paper mechanism.
  No arbitrary custom-code execution has been introduced to force unsupported mechanisms through.
- Weak-model scientific/contract quality is variable. Deterministic recovery does not fix semantic
  mistakes, and unsupported math or multiple risky failures can stop a run. Broad unseen-paper,
  repeated-run and human scientific/pedagogical quality evaluation remains future work.
- A series plot requires genuine series data; a current-state fallback is less expressive than
  a full sampled curve but does not fabricate observations or axes.
- Normal runs log concise diagnostics, not visible/raw model responses. Live-debug files are local
  ignored work only. A failed rerun leaves previous artifact/diagnostics; inspect the latest trace.

## Integration files created/modified after the merges

```text
INTEGRATION_REPORT.md
INTEGRATION_RUNBOOK.md
agent.py
examples/attention_case.json
examples/linear_case.json
examples/linear_response.html
playground/computation/evaluator.py
playground/computation/science.py
playground/computation/validate.py
playground/ir/grounding.py
playground/model/client.py
playground/model/generation.py
playground/model/grounding_plan.py
playground/model/prompts.py
playground/model/repair.py
playground/model/rerank.py
playground/model/verification.py
playground/model/wire.py
playground/orchestrator.py
playground/render/ast_support.py
playground/render/canonical.py
playground/render/manifest.py
playground/render/pipeline.py
playground/render/renderer.py
playground/render/runtime/canonical.js
playground/render/runtime/evaluator.js
playground/render/runtime/runtime.js
playground/render/runtime/styles.css
playground/render/visual_planner.py
playground/retrieval/retrieve.py
playground/secrets.py
playground/source/pdf.py
playground/source/structure.py
playground/trace.py
playground/validation/artifact.py
playground/validation/browser.py
tests/browser/node_verify.cjs
tests/browser/test_canonical.py
tests/browser/verify_artifact.py
tests/integration/test_cli.py
tests/integration/test_team_pipeline.py
tests/unit/computation/test_adversarial.py
tests/unit/model/test_risks_and_repairs.py
tests/unit/model/test_wire.py
tests/unit/retrieval/test_retrieve.py
tests/unit/source/test_parsers.py
```

README.md and docs/ were preserved. See INTEGRATION_RUNBOOK.md for exact setup, API-key,
generation, browser-opening and regression-test commands.
