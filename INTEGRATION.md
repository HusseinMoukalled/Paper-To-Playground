# Hussein integration

`Hussein/Integration` combines `dev/source-pipeline`, `dev/science-engine`, and
`dev/playground-runtime`. The original role handoffs describe each subsystem
before integration; this document describes the running public CLI.

## Run

Use Python 3.11 and an installed Chrome, Edge, or Chromium. No browser download,
Node installation, server, or GPU is required.

```powershell
python -m pip install -r requirements.txt
$env:OPENROUTER_API_KEY = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY', 'User')
python agent.py --input examples/case.json --output out --model deepseek/deepseek-v4.1-flash
```

The key must be in the CLI process environment; the program does not load `.env`
or read credentials from case files. Never commit credentials. Local source
paths resolve relative to the case JSON file, not the working directory.

Success writes `out/index.html` and `out/trace.jsonl`. Open `index.html` directly
in a browser, including offline. The example uses the actual Transformer paper
and requests a clearly scoped attention demonstration.

## Integrated behavior

- One shared budget covers source retrieval, optional tie-breaking, semantic
  generation, narrow repairs, risky-unit verification, science and browser tests.
- The supplied model ID is unchanged. Provider selection favors throughput.
  DeepSeek V4.1 Flash's default high thinking mode is explicitly disabled for
  bounded JSON generation; deterministic science validation remains required.
- Strict IR checks run before rendering. Known null-container/enum formatting
  differences and explicitly declared input policies are repaired deterministically.
  Fixed numeric parameters are omitted from controls only when at least two
  genuinely adjustable controls remain. Missing provenance and small executable
  failures have bounded fragment repairs, followed by full revalidation.
- The renderer consumes Dev2's canonical AST directly, including DAG aliases,
  distributions, matrices, bounded iteration, state transitions and invariants.
  The browser evaluates data-only ASTs, never generated code or parsed DSL.
- Real browser trajectories check scientific outputs against Python, controls,
  equation substitutions, visuals, presets, Reset, accessibility and mobile widths.
- Candidates are staged and promoted atomically only after validation. Failed
  runs return nonzero, record structured failures, and preserve an existing HTML.
- If Chromium cannot be controlled, a validated static artifact may be promoted
  with an explicit warning. The trace never presents that fallback as a browser pass.

## Verify

```powershell
$env:PLAYGROUND_REQUIRE_BROWSER = '1'
python -m unittest discover -s tests -v
git diff --check
```

Tests use synthetic evidence and transport mocks for reproducible science and
failure checks, plus installed Chromium for runtime parity. Live model quality
and source extraction can vary; unsupported evidence or invalid science is rejected.
