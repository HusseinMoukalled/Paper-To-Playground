# Paper to Playground

Team: Hussein Moukalled, Hadi Lahham, Yasmina Mansour

An autonomous generator that turns one research-paper source and a short learning brief into a single offline interactive lesson. It is a reusable compiler, not a page written for one paper.

## Architecture

`agent.py` only parses the command and runs the orchestrator. The pipeline is:

1. Acquire a local PDF, `file://` path, or HTTP(S) HTML/PDF paper and parse it into a `PaperDocument`.
2. Retrieve a compact evidence pack with explicit section, equation, figure, and table lookup, then lexical/BM25 ranking.
3. Ask the supplied OpenRouter model for a structured scientific model and lesson. The model does not write the page.
4. Check the lesson, repair missing provenance and knowledge-class declarations deterministically, and keep only equation links whose math matches the code that runs.
5. Execute the restricted math AST in Python, render it with the shared scientific UI, and check the page in installed Chrome, Edge, or Chromium.
6. Promote `out/index.html` only after those checks. `out/trace.jsonl` records stages, token use, failures, and repairs.

Every model call uses the `MODEL_ID` argument unchanged. The key is read from `OPENROUTER_API_KEY` and is never written into the page or the trace.

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

Success exits 0 and writes `out/index.html` and `out/trace.jsonl`. Open `index.html` directly. It embeds its own CSS, JavaScript, and math, and does not need a network connection.

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

`case.json` in this repository asks for scaled dot-product attention from *Attention Is All You Need*, Section 3.2.1, for a second-year engineering undergraduate. A successful run writes `out/index.html`: a self-contained lesson with the question, symbols set as math, live scores, softmax weights, the output vector, at least two controls, two guided setups, a limitation, and source grounding. `out/trace.jsonl` is the matching execution record. Assessed pages are generated again from the case; this example is only a sample.

## Reuse

Pinned libraries: PyMuPDF 1.26.7, httpx 0.28.1, Beautiful Soup 4.14.3, and Playwright 1.58.0. Playwright drives an already installed Chromium-family browser and does not download one. The page uses browser-native MathML for formulas, not a remote math font or a CDN. No LangChain, embeddings, or vector database.

## Limits

The run stops within 10 minutes, 10 model calls, and 30,000 completion tokens. Table cells in messy HTML papers can fail to extract; the trace records that and the lesson continues from the surrounding text. The model reply varies between runs. Unsupported science is rejected instead of inventing paper results.
