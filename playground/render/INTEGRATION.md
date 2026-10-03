# Developer 3 integration boundary

The renderer consumes the existing `ExplanationIR` dataclasses. It never reads
papers, calls a model, parses the scientific DSL, or repairs scientific meaning.
The master README, `docs/`, shared contracts and orchestrator are unchanged.

```python
from playground.render.pipeline import build_artifact

result = build_artifact(
    validated_ir,
    output_directory,
    asts=serialized_asts,              # Optional if computations already carry metadata['ast'].
    reference_evaluator=evaluate_ir,   # Python callable: initial/input state -> scientific state.
    trace=trace_writer,                # The orchestrator's existing TraceWriter.
)
if not result.promoted:
    # result.report describes the failure; a previous artifact remains intact.
    handle_failure(result.report)
```

`render_html` returns deterministic HTML. `render_candidate` writes `index.html`
to a caller-supplied staging directory. `validate_artifact` returns the shared
`ValidationReport`. `validate_browser` runs installed Chromium with network
blocked, directly through `file://`. `build_artifact` owns temporary candidates,
validation and atomic replacement, leaving global recovery decisions to the
orchestrator. A browser object can be supplied through `browser=` to reuse an
already-open `chromium_session()` across validations.

## AST adaptation

Milestone 0 supplies `ComputationSpec` and an empty computation package, but no
concrete canonical AST classes, serializer or Python evaluator. No shared schema
was changed. The consumer adapter in `ast_support.py` accepts the node vocabulary
described by the README, as JSON data. It is the single place to adapt Developer
2's final serialization. Missing trees fail explicitly; expressions are never
independently reparsed or reinterpreted here.

| Node | Exact data fields besides `type` |
| --- | --- |
| `Constant` | `value`: finite number, boolean or categorical string |
| `Variable` | `id`: scientific variable ID |
| `Unary` | `op`: `+`/`-`, `operand` |
| `Binary` | `op`, `left`, `right` |
| `Call` | `function`: whitelisted name, `args`: array of nodes |
| `Index` | `value`, `index`: zero-based, nonnegative integer expression |
| `Vector` | `items`: array of nodes |
| `Matrix` | `rows`: rectangular arrays of nodes |
| `Conditional` | `condition`: boolean expression, `then`, `else`: lazily evaluated |

Supported binary operators: `+ - * / ** < <= > >= == !=`. Arithmetic broadcasts
scalars across equal-shaped vectors/matrices; it rejects unequal array shapes.
Supported calls: `add subtract multiply divide power sqrt exp log abs min max sum
mean variance normalize softmax sigmoid dot matmul transpose norm distance clip
argmax`. Unary functions map elementwise. Reductions and normalization consume
nonempty vectors; variance is population variance; argmax returns the first
maximizing index. Matrix multiplication supports matrix/matrix, matrix/vector,
vector/matrix and vector/vector. Softmax and sigmoid use stable implementations.
These consumer semantics must be checked against the upstream operation registry
when it exists; fixture parity is not proof of integration with absent code.

Each computation currently produces one declared scientific variable (which may
itself be a matrix/vector/sequence). Actual AST reads must equal `input_refs`.
Declared dependencies reference computation IDs. A deterministic topological
order drives execution, equations and display. `metadata['initial_state']` supplies
uncontrolled input constants. Controls supply their own defaults. Variable shapes
use positive dimensions or exact variable IDs whose state resolves to positive
integers; no dimension expressions are executed.

The existing metadata extension carries `mechanism_family`, optional
`initial_state`, and optional `paper_metadata` (`title`, `source_url`). Presets may
address control IDs or scientific input variable IDs. They start from defaults
and never assign computed outputs. Focus learning-objective references resolve
to the objective text or its zero-based index string, since Milestone 0 has no
separate objective-ID field.

## Interaction and visuals

Controls support numbers, ranges, boolean toggles, categorical selects, vectors
and matrices. Clamp adjusts finite values to declared bounds. Reject and warn
retain the preceding valid state and explain invalid input. Normalize rescales
nonnegative vectors before checking bounds; zero mass, invalid dimensions and
nonfinite numbers are rejected. All updates are transactional.

The planner covers the twelve mechanism families in the master README. SVG
components implement bars/distributions, lines/trajectories, scatter, matrices,
vectors, flow, state graphs, waveforms, geometry, comparisons and process
steppers. State graphs only use explicitly supplied `VisualSpec.metadata.nodes`
and `edges`; they never infer transitions. Steppers display supplied computed
sequences; they never invent update rules. Comparison captures the actual
scientific state. Unusable advanced encodings fall back to an inspectable SVG
scene of actual values. No arbitrary generated computation/visual code escape
hatch is enabled.

Reset restores scientific values, equations, outputs, visuals, active exploration,
step index, comparison and status. Equations use the same AST, native MathML and
plain-text current substitution. All runtime code/CSS and the safely serialized
manifest are embedded; source/model strings reach HTML through escaping or DOM
`textContent` only.

## Browser capability and tests

Install the pinned pip requirements. No `playwright install`, system package,
browser download, Node installation or server is required. Discovery checks the
trusted `PLAYGROUND_CHROMIUM_PATH` override, PATH, common Windows/Linux/macOS
Chromium paths, and an already-existing Playwright browser. If the controller or
compatible browser cannot run, a `WARN / BROWSER_VALIDATION_UNAVAILABLE` report
includes the completed static gate. It permits promotion of a structurally valid
artifact while preserving the distinction between structural and behavioral
verification. Missing Python reference evaluation is separately reported as
`BROWSER_REFERENCE_UNAVAILABLE`; pass the real upstream evaluator for parity.

```text
python -m unittest discover -s tests -v
```

Set `PLAYGROUND_REQUIRE_BROWSER=1` in development/CI to fail when real browser
tests cannot run. Fixture JSON files are test-only schema-compatible IRs. Their
independent Python math oracles test all whitelisted operations and twelve
mechanism families without importing any fixture in production. JavaScript
syntax checks may use an optional development Node installation, but generated
pages and the Python generator do not require Node.

Actual Developer 2 AST serialization/operation parity and assessment-environment
browser compatibility remain integration checks because those implementations
and that environment are not present in this repository snapshot. The public
foundation CLI remains intentionally unchanged until the team integrates the
upstream pipeline.
