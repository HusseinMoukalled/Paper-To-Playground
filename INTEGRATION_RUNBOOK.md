# Running the integrated project

The three developer branches are combined on **hadi-integration**. Main is unchanged.
The authoritative design remains README.md and docs/; this file is a practical run guide.

## 1. Open the project

In PowerShell:

```powershell
Set-Location 'C:\Users\User\Documents\ChatGPT\503P Hackathon'
git switch hadi-integration
```

If using another clone, first run `git fetch origin`, then switch to the remote integration branch.
Do not discard local edits just to switch branches.

## 2. Python

This machine already has a working, ignored Python 3.11 runtime with the dependencies installed:

```powershell
& '.\tmp\dev2-python311\runtime\python.exe' --version
```

That local runtime is NOT committed. On a different machine, use Python 3.11 and install the dependencies:

```powershell
py -3.11 -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
```

Use the chosen Python executable in every command below. No Docker, server, GPU,
npm build, browser download, or extra system package is required to generate HTML.

## 3. Load the API key safely

You already saved the key in your Windows **User environment**. Load it into this PowerShell process:

```powershell
$env:OPENROUTER_API_KEY = [Environment]::GetEnvironmentVariable('OPENROUTER_API_KEY', 'User')
if ([string]::IsNullOrWhiteSpace($env:OPENROUTER_API_KEY)) { throw 'API key is not configured' }
```

Do NOT print the variable. Do not put the key in case JSON, source code, a committed file,
or a command containing a literal key. The application reads only the process environment;
it does not automatically read Windows User settings or load `.env` files.

If you need to enter a new key for this terminal only:

```powershell
$taskSecureKey = Read-Host 'OpenRouter API key' -AsSecureString
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new('', $taskSecureKey).Password
Remove-Variable taskSecureKey
```

All model requests use the `--model` value unchanged. The model tested here was
`deepseek/deepseek-v4.1-flash`; there are no fallback or embedding models.

## 4. First run: small verification example

```powershell
& '.\tmp\dev2-python311\runtime\python.exe' agent.py --input examples/linear_case.json --output out/linear --model deepseek/deepseek-v4.1-flash
if ($LASTEXITCODE -eq 0) { Invoke-Item '.\out\linear\index.html' }
```

This is an original synthetic article for checking the pipeline, NOT a published-paper benchmark.
Move both controls, apply both exploration setups, and press Reset.

## 5. Published-paper example

```powershell
& '.\tmp\dev2-python311\runtime\python.exe' agent.py --input examples/attention_case.json --output out/attention --model deepseek/deepseek-v4.1-flash
if ($LASTEXITCODE -eq 0) { Invoke-Item '.\out\attention\index.html' }
```

This downloads a public paper and requests a bounded lesson about sinusoidal positional encoding.
Downloading the paper and generating the lesson require internet access. The resulting HTML works offline.

Each execution is a new model run and may fail validation even after a previous success.
The system does not substitute canned science or silently accept unsupported claims.

## 6. Your own paper

Create a JSON case containing exactly these three fields:

```json
{
  "source_url": "C:/Users/User/Downloads/my-paper.pdf",
  "focus": "the mechanism in Equation 6",
  "audience": "second-year engineering undergraduate"
}
```

Use a genuine equation/section reference or a precise mechanism name. The focus is preserved exactly.
Forward slashes are convenient in Windows JSON paths. Relative paper paths resolve against the
**case file's folder**, not the terminal folder. `examples/case.json` is the original placeholder;
it does not include a real `paper.pdf`. Use the supplied working examples or your own case.

```powershell
& '.\tmp\dev2-python311\runtime\python.exe' agent.py --input case.json --output out/custom --model deepseek/deepseek-v4.1-flash
if ($LASTEXITCODE -eq 0) { Invoke-Item '.\out\custom\index.html' }
```

## 7. Outputs and failures

On success, the output folder contains:

- `index.html`: standalone lesson, inline scripts/styles/manifest, no server required.
- `trace.jsonl`: flushed stage/call/usage/failure summaries; no credentials or reasoning transcripts.
- `explanation_ir.json`: diagnostic science, lesson, grounding and canonical computation data.
- `validation_report.json`: status, warnings, request/token counts and elapsed time.

Exit code 0 means a candidate passed the available gates and was promoted. WARN is not PASS:
check the report. In particular, a browser-controller restriction can permit a static-validated
artifact with `BROWSER_VALIDATION_UNAVAILABLE`. Windows Application Control currently blocks
the Python controller on this machine. We did not weaken that policy; an independently installed
Node controller verified the generated artifacts in real Chrome.

Exit code 2 means failure. Inspect the final trace lines:

```powershell
Get-Content '.\out\custom\trace.jsonl' -Tail 10
```

Common causes are missing API key, missing PDF, unsupported/scanned source, insufficient evidence,
model timeout/rate limit, malformed contracts, invalid scientific computation, or unsupported claims.
An unsuccessful candidate does not replace an existing `index.html`. Existing diagnostic files
may describe the earlier successful run; use the latest trace to identify a failed rerun.

## 8. Tests

```powershell
& '.\tmp\dev2-python311\runtime\python.exe' -m unittest discover -s tests
```

Tests use fixtures/mocked model transport and do not spend API credits. Browser tests can skip
when a controller is unavailable. The optional development Node verifier is not an application
dependency and is not needed by the evaluator. On this Codex-equipped machine:

```powershell
$env:PLAYGROUND_NODE = 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
$env:NODE_PATH = 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules'
& '.\tmp\dev2-python311\runtime\python.exe' -m unittest discover -s tests
& '.\tmp\dev2-python311\runtime\python.exe' -m tests.browser.verify_artifact out/attention
```

## Limits and experimental settings

The normal path uses one combined semantic request. Ambiguous retrieval can add one narrow
rerank; concrete science risks can add targeted verification and a bounded claim repair.
All requests, including retries, share the 10-request/30,000-completion-token/600-second budget.
There is no mandatory critic and no generated JavaScript execution.

The two-stage option remains experimental. It is unit-tested for preserving ScientificModel,
but the live two-stage comparison failed schema validation. Use the default combined strategy.
To restore the default after experimenting:

```powershell
Remove-Item Env:PLAYGROUND_SEMANTIC_STRATEGY -ErrorAction SilentlyContinue
```

This is not a guarantee of correct output for every paper. There is no OCR, arbitrary custom
code is disabled, and mechanisms outside the restricted DSL are rejected. A waveform requires
actual series data: scalar-only inputs receive a labeled current-state view instead of a fabricated curve.

See INTEGRATION_REPORT.md for the verification evidence, integration fixes and remaining limitations.
