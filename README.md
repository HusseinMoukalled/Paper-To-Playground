# Paper to Playground

Team: Hussein Moukalled, Hadi Lahham, Yasmina Hanna

An autonomous generator that turns one research-paper source and a short learning brief into a single offline interactive lesson. It is a reusable compiler, not a page written for one paper.

## Architecture

`agent.py` only parses the command and runs the orchestrator. The pipeline is:

1. Acquire a local PDF, `file://` path, or HTTP(S) HTML/PDF paper and parse it into a `PaperDocument`.
2. Retrieve a compact evidence pack with explicit section, equation, figure, and table lookup, then lexical/BM25 ranking.
3. Ask the supplied OpenRouter model for a small lesson plan: explanations, scientific input declarations, executable calculation stages, visuals and two exploration presets. The model does not write the page.
4. Compile that plan into the scientific and teaching IR in Python, deriving IDs, dependencies, control types, executable teaching equations, coverage and exact claim-text records. Source prose keeps evidence citations; computed quantities and teaching equations keep computation provenance; toy settings are labeled pedagogical. Check schema, references, calculations, controls, presets and invariants, including independent array probes. Failures receive concrete feedback for up to three authoring attempts within the shared budget; predicate and boolean-type defects can receive smaller field revisions.
5. Calculate each exploration's observations directly from its preset and the default inputs; the model's predicted numerical observations are replaced with these computed comparisons. Review the complete lesson and its executable mathematics against the evidence, recording a concrete verdict for each calculation, source claim and exploration. The reviewer receives the actual computed default and preset values. Unsupported science receives correction feedback and must pass a fresh review. Execute the restricted math AST in Python, render it with the shared scientific UI, and check the page in installed Chrome, Edge, or Chromium.
6. Promote `out/index.html` only after those checks. `out/trace.jsonl` records stages, token use, failures, and repairs.

Every model call uses the `MODEL_ID` argument unchanged. The key is read from `OPENROUTER_API_KEY` and is never written into the page or the trace.

For DeepSeek V4.1 Flash, structured calls disable reasoning so the completion allowance remains available for the lesson and review JSON. Reported completion usage is charged to the shared budget. See [OpenRouter's reasoning-token documentation](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

## Setup and run

Python 3.11 or 3.12. No GPU, Node, server, or browser download. Chrome, Edge, or Chromium must already be installed so the generator can operate the page. Put `OPENROUTER_API_KEY` in the environment, then from this directory:

```bash
python -m pip install -r requirements.txt
python agent.py --input case.json --output out --model MODEL_ID
```

**MODEL_ID: `deepseek/deepseek-v4.1-flash`**

On Windows Command Prompt, a new window picks up a user-level key. For one window:

```bat
set OPENROUTER_API_KEY=your-key-here
```

Success exits 0 and writes `out/index.html` and `out/trace.jsonl`. The authored `candidate.plan.json` and decoded `candidate.ir.json` are retained for diagnostics. Open `index.html` directly. It embeds its own CSS, JavaScript, and math, and does not need a network connection.

## Input

`case.json` is UTF-8 JSON with exactly these three non-empty strings:

```json
{
  "source_url": "https://arxiv.org/html/1706.03762",
  "focus": "scaled dot-product attention in Section 3.2.1",
  "audience": "second-year engineering undergraduate"
}
```

`source_url` may be a local path, a `file://` URL, or an `http://` / `https://` URL. A local path is resolved relative to the case file. `focus` is the concept to teach. `audience` changes the wording, not the science.

## Example

Actual generated pages are included in Git, together with their exact input, authored plan and trace:

- [Attention HTML](examples/generated/attention/index.html), [input](examples/generated/attention/case.json), [trace](examples/generated/attention/trace.jsonl).
- [Shannon entropy HTML](examples/generated/entropy/index.html), [input](examples/generated/entropy/case.json), [trace](examples/generated/entropy/trace.jsonl).

Open the HTML directly in a browser; generation and an API key are unnecessary to use these examples. The pages are copied from successful fresh CLI runs. Generated working outputs stay ignored under `out/`; these submission examples are tracked under `examples/`.

## Verification

See [the measured verification report](VERIFICATION.md) and [the code walkthrough](WALKTHROUGH.md).

Run the deterministic tests, including offline Chromium checks:

```bash
python -m unittest discover -s tests -q
```

With `OPENROUTER_API_KEY` set, run fresh end-to-end tests using the supplied model:

```bash
python scripts/verify_live.py --model deepseek/deepseek-v4.1-flash --repeats 2
```

The runner tests attention, Shannon entropy, Adam, batch normalization, dropout, distillation and logical clocks with the public CLI, clean output directories, actual API calls and browser checks. It saves HTML, traces, per-run token/time measurements and a SHA-256 fingerprint of the production code under `out/verification/`. Use `--cases entropy attention --repeats 1` for a smaller check. Use `--prompt-key` to enter a key with terminal echo disabled if it is unavailable in the current environment. These are our practice briefs; they are not the instructor's hidden inputs or an official reassessment. Offline tests use controlled model responses and cannot establish live generation reliability.

## Reuse

Pinned libraries: PyMuPDF 1.26.7, httpx 0.28.1, Beautiful Soup 4.14.3, and Playwright 1.58.0. Playwright drives an already installed Chromium-family browser and does not download one. The page uses browser-native MathML for formulas, not a remote math font or a CDN. No LangChain, embeddings, or vector database.

## Limits

The run stops within 10 minutes, 10 model calls, and 30,000 completion tokens. Table cells in messy HTML papers can fail to extract; the trace records that and the lesson continues from the surrounding text. The model reply varies between runs. Unsupported science is rejected instead of inventing paper results.
