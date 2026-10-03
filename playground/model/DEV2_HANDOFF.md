# Developer 2 subsystem handoff

The shared Milestone 0 dataclasses, CLI, RunBudget, trace format, README and
developer specifications are unchanged. Production implementation uses only
the Python standard library and supports Python 3.11.

## Integration boundary

Developer 1 passes a canonical `EvidencePack`. Developer 2 returns validated
`ExplanationIR`, its validation report, usage metrics and concrete semantic risk
units. Developer 3 consumes that IR, including the canonical AST, and owns
rendering, browser execution, equation rendering and browser validation.

```python
from playground.budget import RunBudget
from playground.model import OpenRouterClient, SemanticEngine, GenerationStrategy

# Use the SAME run budget/trace as retrieval, orchestration and finalization.
client = OpenRouterClient(config.model_id, shared_run_budget, shared_trace)
result = SemanticEngine(client).generate(evidence_pack)
explanation_ir = result.ir
validation_report = result.validation

# Explicit experimental alternative; not an automatic fallback:
# SemanticEngine(client, strategy=GenerationStrategy.TWO_STAGE)
```

The supplied model ID is forwarded unchanged. The client has no default model,
model router, embeddings, alternative LLM or model-based frontend generator.
The team must supply the intended DeepSeek V4.1 Flash ID via `--model`.
The CLI remains the original foundation stub, intentionally: wiring the complete
source-to-renderer pipeline belongs to team integration, not this subsystem.

## API key

Set `OPENROUTER_API_KEY` in the environment of the process running the CLI.
For a PowerShell terminal, use the following with your own key locally:

```powershell
$env:OPENROUTER_API_KEY = "your-key"
python agent.py --input case.json --output out --model MODEL_ID
```

Do not save the key in the repository, case JSON, README, prompts, trace or
generated lesson. The client reads it only from the environment when a call is
needed. Missing/blank keys produce `MODEL_REQUEST_FAILED` before transport.
This implementation does not load `.env` files. A separate terminal's environment
does not change an already-running application's environment.

## Shared contracts: unchanged; metadata conventions: new

There are no changes to existing dataclass fields or constructors. These additive
metadata conventions are the executable wire interface. Dev 3 should implement
them exactly, not parse the source paper or reinterpret the equations.

### Expression computations

`ComputationSpec.expression` is a restricted math expression. Its metadata:

- `kind`: `expression`, default when omitted.
- `bindings`: maps DSL identifiers to stable scientific-variable or predecessor
  computation IDs. Every referenced identifier must have exactly one binding.
- `equation_refs`: source scientific equation IDs directly executed by this
  expression. Their AST must match modulo explicit source-symbol renaming.
- `canonical_ast`: generated deterministically from the expression; never trust
  a model-supplied AST without recompiling it.
- `ast_version`: `1`.

`dependencies` lists predecessor computation IDs, including producers of bound
output variables. `input_refs` lists variable inputs. `output_refs` assigns the
single result to scientific variables, checked against type/shape/domain.
Computations cannot overwrite controls or multiply-own output variables.
Unknown computation metadata/custom-code fields are rejected.

Source equation expressions may be DSL right-hand sides or simple `y = RHS`.
Directly linked equations preserve the math and output symbol. Algebraically
different rewrites are conservatively rejected rather than asserted equivalent.
An unexecuted contextual equation needs
`ExplanationIR.metadata.equation_scope[EQUATION_ID] = "context_only"`.

### Canonical AST version 1

Every node has exactly `kind`, `value`, `args`. `args` is an array of child nodes.
The supported forms are:

- `literal`: finite number, boolean or short categorical string; no children.
- `variable`: a safe DSL identifier; no children.
- `array`: vector/matrix literals; `value=null`.
- `call`: whitelisted operation name in `value`; arguments follow registry arity.
- `compare`: `lt`, `le`, `gt`, `ge`, `eq`, `ne`; two scalar arguments.
- `index`: nonnegative constant index in `value`; one array child.
- `and`, `or`: boolean children; `value=null`.
- `not`: one boolean child; `value=null`.
- `if`: condition/true/false children; evaluate only the selected branch.

Python syntax is parsed only to translate into these nodes. Attributes,
comprehensions, lambdas, assignments, imports, arbitrary calls, dunder names,
slice expressions, keyword calls and arbitrary executable code are rejected.

Limits: 4,096 expression characters, 256 nodes, depth 32, at most 4,096 array
entries, rank at most 2. Only scalar broadcasting is allowed; arrays must have
exact matching shapes. Shared symbolic dimensions must resolve consistently.

### Operation registry and numeric conventions

`playground.computation.operations.OPERATIONS` is authoritative. Arity, purpose
and function are explicit. Current operations:

`add subtract multiply divide power negate abs sqrt exp log sin cos sum mean
min max dot matmul transpose norm normalize softmax entropy approx_equal`.

Important browser-parity requirements:

- `sum`/`mean` reduce all entries; `min`/`max` reduce a vector.
- `matmul` supports matrix-vector and matrix-matrix products, not arbitrary ranks.
- `normalize` means unit Euclidean norm; zero vectors reject.
- A distribution control's `normalize` validation rule instead normalizes
  nonnegative probability mass to sum one. This is not Euclidean normalization.
- `softmax` subtracts the maximum before exponentiation.
- `entropy` uses natural logarithms/nats, with `0 log 0 = 0`.
- `approx_equal` uses absolute and relative tolerance `1e-8`, shape-aware.
- Distribution values must be nonnegative and sum to one within tolerance.
- Real powers have bounded exponents; nonfinite/complex results reject.
- Supported domains: null, `real`, `positive`, `nonnegative`, `unit_interval`,
  `probability`, `integer`. Unknown domains must be narrowed or reported unsupported.

### Bounded iterative computations

Metadata `kind=iteration` adds:

- `initial`: local state name -> restricted DSL initialization expression.
- `updates`: identical local state keys -> DSL next-state expressions.
- `steps`: integer 1..100.
- `state_specs`: optional local-name -> `{type, shape, domain}` declarations.
- `state_invariants`: optional list of boolean DSL predicates checked at the
  initial state and after EVERY update, maximum 16.
- Generated `initial_ast`, `update_ast`, `state_invariant_ast`.

Initializers use only externally bound inputs. Updates are simultaneous from the
previous snapshot, not sequential mutations. `expression` selects the final
result using external bindings and local state. Without declarations, local
types/shapes are inferred from the initial state and preserved through updates.
`execute` also returns per-computation histories for steppers/trajectories.

### Finite-state transition computations

Metadata `kind=state_transition` adds `states`, `initial_state`, `steps` (1..100,
default 1), and `transitions=[{from,to,when}]`. `when` is boolean DSL and may use
the current categorical `state` plus external inputs. Generated `transition_ast`
entries add `condition_ast`. More than one enabled transition is an error, not
an arbitrary choice. No enabled transition preserves the state. Output type is
`state`; histories contain the initial and subsequent categorical states.

### IR-level metadata and presets

- `defaults`: fixed inputs keyed by scientific-variable ID.
- `audience`: exact EvidencePack audience.
- `audience_adaptation`: explicit teaching-depth/prerequisite rationale.
- `invariant_bindings`: invariant DSL symbol -> variable/computation ID.
- `control_test_values`: representative arrays for controls without scalar
  ranges/options. Maximum 16 samples per control.
- `equation_scope`: explicit context-only equations as described above.

Exploration `setup` is keyed by CONTROL ID, not variable ID. Reset means invoking
the same default inputs as `prepare_inputs(ir)`. Numeric controls are bounded;
invalid behavior is `clamp`, `reject`, `normalize` or `warn`. `warn` does not
permit scientifically invalid or nonfinite values to reach computation.

### Grounding and focus coverage

`learner_claims(ir)` defines exact claim paths for prose without object IDs.
Every such claim needs an exact matching GroundingRecord and knowledge class.
Variable/equation/relationship/step prose uses its object ID as `claim_id`.
Symbol explanations, control purposes/range rationales, exploration content,
lesson scientific prose, objectives and visual intent are individually covered.
Numeric toy inputs/ranges/presets are pedagogical configuration, not paper data.

Source objects and records preserve canonical evidence IDs. Derived records
require executable computation references. `UNSUPPORTED` blocks validated IR;
`PARTIAL` returns WARN and a semantic risk unit. Citation existence alone is not
proof of entailment. Never display a partial result as unqualified paper truth.

FocusCoverageMap objective references are exact objective strings, because the
foundation LessonSpec has no objective-ID objects. All other refs are stable
object IDs with shared prefixes. The validator checks the focus string, reference
integrity and dependency paths connecting mechanisms, controls, computations,
observable visuals and executable explorations. It cannot prove unrestricted
natural-language semantic alignment without evidence review.

## Validation and failures

`validate_ir(ir, evidence, budget=shared_budget)` returns the unchanged shared
ValidationReport contract. Validation proceeds through schema, metadata, IDs,
references, scientific declarations, grounding, pedagogy, coverage and
computation. Bad early layers never reach executable scientific validation.

Scientific execution tests default state, each numeric boundary/interior,
categorical options, toggles, guided presets and declared array test values.
It checks finite outputs, types/shapes/domains, invariants, observed control
effects, visible dependency paths and distinct exploration outputs.

Execution uses the shared deadline/finalization reserve, plus a local 30-second
and 250,000-node validation cap. Optional unsafe work is denied by RunBudget.

## Risk-triggered verification and repair

`GenerationResult.risk_units` contains narrow detected risks. Partial support,
ambiguous retrieval and experimental/performance/causal language trigger units.
The orchestrator can call `verify_units(client, evidence, units)` only when
needed and budget-safe. No unit means zero critic calls. Verdicts are advisory;
they never silently mutate grounding or certify the whole lesson.

`request_repair` accepts a typed failure, explicit authorized JSON-pointer leaf
paths and relevant evidence IDs. It submits only those fragments and evidence.
Only bounded `replace` patches are permitted. Stable IDs, audience/focus,
canonical AST and broad subtree replacements are protected. Scientific prose
changes require corresponding exact grounding-record patches; otherwise they
fail. Every candidate is decoded, compiled and fully revalidated before return.
Original candidates are immutable/preserved. File staging/promotion is owned by
the orchestrator, not this module.

## Call strategy, transport and budgets

Normal success: one combined semantic call producing distinct ScientificModel
and LessonSpec within ExplanationIR. Two-stage mode: science first, then lesson
with an unchanged ScientificModel. `benchmark_strategies` is an explicit opt-in
measurement helper; it never runs automatically or silently resets shared budgets.

Only `model/client.py` performs requests. It uses the OpenRouter chat-completions
endpoint, JSON mode, supplied model ID, environment-only bearer key, a capped
total wall-time transport and at most one conservative retry for timeout/network,
429 or 5xx. It counts EVERY attempted request before transport and clips completion
allocation to the remaining global cap. Missing/failed usage is explicitly
marked unknown and conservatively reserved at the requested completion cap.
Late timed-out transport results cannot alter budgets or trace events.

Malformed completions do not cause blind API retries. Recovery is limited to one
JSON fence and trailing commas outside strings. Duplicate keys and nonfinite
JSON reject. Prompts/responses/credentials/reasoning are not written to trace.
Trace contains bounded action/status/usage/finding-code summaries only.

## Tests and requirement review

Run normal installations with:

```powershell
python -m unittest discover -s tests -v
```

The Dev 2 tests cover:

- Caller model propagation, environment-only credentials, redaction, clean missing
  key errors, no alternate model, timeout including total wall time, 429, 5xx,
  retries, token pressure, unknown usage and finalization budget denial.
- JSON recovery, strict shared schemas, IDs, references, grounding classes,
  unsupported/partial claims, evidence lineage, focus paths and audience context.
- Whitelisted DSL, malicious/oversized syntax, serialized AST integrity, every
  operation's normal/boundary/invalid cases, scalar/vector/matrix/distribution
  evaluation, symbolic shapes, domains and stable numerics.
- Defaults/boundaries/interiors/presets, finite output, global and iterative
  invariants, meaningful control effects, finite-state ambiguity and reset inputs.
- One-call and two-stage fixture pipelines, stage science preservation, opt-in
  benchmark metrics, targeted verification, patch authorization, and failed
  repair preserving the original validated candidate.
- Static absence of dynamic execution, embeddings, forbidden model libraries,
  scattered transport and actual environment credentials in owned source artifacts.
- All existing foundation and CLI-stub tests remain unchanged and pass.

Fixtures are independent of Dev 1, canonical and test-only:
`tests/fixtures/dev2_evidence.json` and `tests/fixtures/dev2_explanation_ir.json`.
The latter is a ready-to-consume Dev 3 fixture with generated canonical AST.

Tested locally on Python 3.11.9 and Python 3.12.14. The temporary portable 3.11
runtime is ignored under `tmp/` and is NOT a project/runtime dependency.

Final verification: **74 tests passed** on both versions: 61 Dev 2 tests and
13 existing foundation/CLI tests. Separate subsystem runs also passed.
Repository credential scan checked 65 versioned/unignored files with zero
credential findings. `git diff --check` passed. README, docs, shared dataclasses,
budget, trace, config, requirements and orchestrator have no changes.

## Created/modified files

Modified package entry points only:

- `playground/model/__init__.py`
- `playground/computation/__init__.py`

Created production/hand-off files:

- `playground/model/client.py`
- `playground/model/prompts.py`
- `playground/model/generation.py`
- `playground/model/verification.py`
- `playground/model/repair.py`
- `playground/model/DEV2_HANDOFF.md`
- `playground/ir/serialization.py`
- `playground/ir/grounding.py`
- `playground/ir/coverage.py`
- `playground/ir/validate.py`
- `playground/computation/ast.py`
- `playground/computation/parser.py`
- `playground/computation/operations.py`
- `playground/computation/evaluator.py`
- `playground/computation/invariants.py`
- `playground/computation/science.py`
- `playground/computation/validate.py`

Created test/fixture files:

- `tests/fixtures/__init__.py`
- `tests/fixtures/dev2_evidence.json`
- `tests/fixtures/dev2_explanation_ir.json`
- `tests/fixtures/dev2_factory.py`
- `tests/unit/model/__init__.py`
- `tests/unit/model/test_client.py`
- `tests/unit/model/test_security.py`
- `tests/unit/model/test_risks_and_repairs.py`
- `tests/unit/ir/__init__.py`
- `tests/unit/ir/test_validation.py`
- `tests/unit/computation/__init__.py`
- `tests/unit/computation/test_engine.py`
- `tests/unit/computation/test_adversarial.py`
- `tests/integration/evidence_to_ir/__init__.py`
- `tests/integration/evidence_to_ir/test_pipeline.py`

## Explicit remaining validation/team work

No live API call or empirical DeepSeek accuracy/strategy comparison was performed.
Mock-transport tests prove interface/accounting behavior, not model scientific
quality. Run the opt-in comparison on a diverse team evidence corpus before
freezing prompts. The system reports unsupported mechanisms rather than claiming
the small DSL covers every possible paper.

No general dimensional-analysis engine or automatic proof of natural-language
entailment is claimed. Units are preserved/checked at control boundaries;
scientific invariants and exact equation linkage provide deterministic checks.
Citation validity is structural; high-risk semantics need narrow verification or
human benchmark oracles. Browser parity/rendering/browser tests belong to Dev 3.
Source retrieval and evidence-expansion fallback belong to Dev 1. Orchestrator
integration and file-level last-known-good promotion belong to team integration.

Publication is performed only when explicitly requested by the user. No merges,
README edits, developer-doc edits or dependencies were introduced by this
subsystem work.
