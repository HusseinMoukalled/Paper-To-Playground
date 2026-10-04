# Verification of the corrected generator

These results measure fresh local generation, not an official practical score. The instructor’s original assessment remains unchanged.

Profile: Windows, Python 3.11.9, installed Chromium-family browser, supplied model `deepseek/deepseek-v4.1-flash`. Seven public practice briefs were run twice each through `agent.py`, with clean output directories and no production-code changes during the suite. The runner retains the assignment’s 10-minute, 10-call and 30,000-completion-token limits per run.

Command: `python scripts/verify_live.py --model deepseek/deepseek-v4.1-flash --repeats 2`. Inputs are in `examples/verification/`; each archived run also has its exact `case.json`.

Result: **14/14 produced HTML and passed static, browser and final promotion checks.** The Python 3.11 regression suite passed **210 tests**, including offline browser checks.

| Practice paper | Run | Seconds | Calls | Completion tokens | HTML / static / browser |
|---|---:|---:|---:|---:|---|
| [adam](verification/runs/adam-1/index.html) | 1 | 18.062 | 2 | 4051 | pass / pass / pass |
| [adam](verification/runs/adam-2/index.html) | 2 | 31.375 | 3 | 7813 | pass / pass / pass |
| [attention](verification/runs/attention-1/index.html) | 1 | 17.547 | 2 | 3828 | pass / pass / pass |
| [attention](verification/runs/attention-2/index.html) | 2 | 21.468 | 2 | 3412 | pass / pass / pass |
| [batch-normalization](verification/runs/batch-normalization-1/index.html) | 1 | 19.438 | 3 | 3630 | pass / pass / pass |
| [batch-normalization](verification/runs/batch-normalization-2/index.html) | 2 | 21.266 | 3 | 3853 | pass / pass / pass |
| [distillation](verification/runs/distillation-1/index.html) | 1 | 28.407 | 2 | 5480 | pass / pass / pass |
| [distillation](verification/runs/distillation-2/index.html) | 2 | 31.015 | 3 | 7320 | pass / pass / pass |
| [dropout](verification/runs/dropout-1/index.html) | 1 | 24.469 | 4 | 5146 | pass / pass / pass |
| [dropout](verification/runs/dropout-2/index.html) | 2 | 25.437 | 4 | 5710 | pass / pass / pass |
| [entropy](verification/runs/entropy-1/index.html) | 1 | 17.344 | 2 | 3636 | pass / pass / pass |
| [entropy](verification/runs/entropy-2/index.html) | 2 | 19.578 | 2 | 3961 | pass / pass / pass |
| [logical-clocks](verification/runs/logical-clocks-1/index.html) | 1 | 17.703 | 4 | 3510 | pass / pass / pass |
| [logical-clocks](verification/runs/logical-clocks-2/index.html) | 2 | 16.500 | 3 | 3333 | pass / pass / pass |

Full measurements, prompt-token counts, inputs and recorded failures are in [results.json](verification/results.json). Each run directory contains its HTML, authored plan, compiled candidate and trace. Rejected drafts and correction attempts remain in the traces; they are included in the reported time and token totals.

The production working-tree SHA-256 was `7e63ae291c8d5462f8e4aecf73bfafe87640de1bea71b3bcdb4c3721de3419d7`. The fingerprint includes `agent.py`, `requirements.txt` and production Python/JavaScript/CSS files, using local file bytes; Git line-ending conversion can change it after checkout. The original submitted baseline was `c637151edb24cb0528123af5276f67b0ac6a3b3e`.

Committed announcement examples: [attention](examples/generated/attention/index.html) and [Shannon entropy](examples/generated/entropy/index.html). Both include the matching input, authored plan and trace, and work offline. Exploration observations in the final pages come from program execution; authored draft observations may differ because they are replaced before review.

Limits: the exact hidden inputs and original ten assessment traces were unavailable. This was not the instructor’s VPS or an independent reassessment. Model-authored prose and scientific review remain fallible: passing these gates is not a full scientific-accuracy score or a guarantee on future papers. For example, explanations of Adam’s gradient scaling and bias correction can still overgeneralize even when the executed update is correct. The recorded model findings should be read as check results, not authoritative scientific proof. Source parsing can issue equation/table warnings, which remain visible in the traces.

Read [WALKTHROUGH.md](WALKTHROUGH.md) to follow the executed code and [RESUBMISSION.md](RESUBMISSION.md) for an editable request to review the corrected work.
