"""Compile validated IR to deterministic, dependency-free, self-contained HTML."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from playground.failures import Failure, FailureCode, FailureSeverity, PlaygroundError
from playground.ir.models import ExplanationIR
from playground.render.manifest import build_manifest, safe_json

RUNTIME = Path(__file__).with_name('runtime')


def escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def source_link(value: str) -> str:
    """Citations may link to HTTP(S); local paths and all other schemes stay text."""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return escape(value)
    if parsed.scheme.lower() in {'http', 'https'} and parsed.hostname and not any(ord(c) < 32 for c in value):
        return f'<a href="{escape(value.strip())}" rel="noreferrer noopener">{escape(value)}</a>'
    return escape(value)


def _control(control: dict, index: int) -> str:
    key = f'input-{index}'
    value_id, hint_id = f'value-{index}', f'hint-{index}'
    kind = control['control_type']
    attrs = (f'id="{key}" data-control-id="{escape(control["id"])}" '
             f'data-variable-id="{escape(control["scientific_variable"])}" '
             f'data-depends-on="{escape(control["scientific_variable"])}" '
             f'aria-describedby="{value_id} {hint_id}"')
    grid = ''
    if kind == 'select':
        input_html = f'<select {attrs}>' + ''.join(f'<option value="{escape(x)}">{escape(x)}</option>' for x in control['options']) + '</select>'
    elif kind in {'vector', 'matrix'}:
        # The textarea stays the validated source of truth; the runtime layers an editable number grid on it.
        input_html = f'<textarea {attrs} rows="2" spellcheck="false" class="array-source">{escape(safe_json(control["default"]))}</textarea>'
        grid = f'<div class="array-grid" data-grid-for="{key}" aria-hidden="true"></div>'
    elif kind == 'toggle':
        input_html = f'<input {attrs} type="checkbox"' + (' checked' if control['default'] else '') + '>'
    else:
        input_type = 'range' if kind in {'slider', 'range'} else 'number'
        domain = ''.join(f' {a}="{escape(control[b])}"' for a, b in [('min', 'minimum'), ('max', 'maximum'), ('step', 'step')] if control[b] is not None)
        if control['step'] is None:
            domain += ' step="any"'
        input_html = f'<input {attrs} type="{input_type}" value="{escape(control["default"])}"{domain}>'
        if input_type == 'range':
            lo, hi = control['minimum'], control['maximum']
            input_html += f'<div class="range-ends"><span>{escape(lo)}</span><span>{escape(hi)}</span></div>'
    units = (' (' + escape(control['units']) + ')') if control['units'] else ''
    return (f'<div class="control" data-kind="{escape(kind)}"><div class="control-head"><label for="{key}">{escape(control["label"])}{units}</label>'
            f'<output id="{value_id}" class="current-value">{escape(control["default"])}</output></div>{grid}{input_html}'
            f'<p id="{hint_id}" class="hint">{escape(control["learning_purpose"])} '
            f'{escape(control["safe_range_reason"])}</p></div>')


def render_html(ir: ExplanationIR, *, asts: Mapping[str, dict] | None = None) -> str:
    try:
        m = build_manifest(ir, asts=asts)
        lesson, science = m['lesson_spec'], m['scientific_model']
        controls = ''.join(_control(c, i) for i, c in enumerate(m['controls']))
        symbols = ''.join(f'<dt data-variable-id="{escape(v["id"])}" data-symbol="{escape(v["display_symbol"])}">{escape(v["display_symbol"])}</dt><dd>{escape(v["meaning"])}'
                          + (f' · {escape(v["units"])}' if v['units'] else '')
                          + f' <span class="badge">{escape(v["knowledge_class"])}</span></dd>' for v in m['variables'])
        objectives = ''.join(f'<li data-objective-id="{i}">{escape(value)}</li>' for i, value in enumerate(lesson['learning_objectives']))
        steps = ''.join(f'<li data-mechanism-id="{escape(s["id"])}">{escape(s["description"])}</li>' for s in sorted(science['mechanism_steps'], key=lambda s: s['order']))
        equations = ''.join(f'<div class="equation-panel" id="equation-{escape(c["id"])}" data-computation-id="{escape(c["id"])}" '
                            f'data-depends-on="{escape(" ".join(c["reads"]))}"><p class="equation-label">Step {i + 1}</p>'
                            f'<p class="equation" data-role="equation"></p>'
                            f'<p class="equation substituted" data-role="substituted"></p>'
                            f'<p class="substitution" data-role="substitution"></p></div>' for i, c in enumerate(m['computations']))
        visuals = ''.join(f'<article class="panel figure"><p class="eyebrow">Live figure</p><h3>{escape(v["question"])}</h3>'
                         f'<div class="visual" data-visual-id="{escape(v["id"])}" data-depends-on="{escape(" ".join(v["data_refs"]))}"></div>'
                         f'<p class="caption">{escape(lesson["visual_intent"])}</p></article>' for v in m['visuals'])
        output_ids = list(dict.fromkeys(m['outputs'] + lesson['important_intermediates']))
        variable_by_id = {v['id']: v for v in m['variables']}
        values = ''.join(f'<div class="output"><span class="symbol" data-symbol="{escape(variable_by_id[ref]["display_symbol"])}">{escape(variable_by_id[ref]["display_symbol"])}</span>'
                        f'<output data-output-id="{escape(ref)}" data-variable-id="{escape(ref)}" data-depends-on="{escape(ref)}" aria-live="polite"></output>'
                        f'<div class="math-view" data-math-for="{escape(ref)}" aria-hidden="true"></div>'
                        f'<p class="hint">{escape(variable_by_id[ref]["meaning"])}</p></div>' for ref in output_ids)
        explorations = ''.join(f'<article class="panel exploration" data-exploration-id="{escape(e["id"])}"><span class="eyebrow">Exploration {i + 1}</span>'
                              f'<h3>{escape(e["title"])}</h3><p><strong>Change:</strong> {escape(e["change"])}</p>'
                              f'<p><strong>Observe:</strong> {escape(e["observe"])}</p><p><strong>Why:</strong> {escape(e["why"])}</p>'
                              f'<button data-role="apply-setup" data-setup-id="{escape(e["id"])}">Apply Setup</button></article>'
                              for i, e in enumerate(m['explorations']))
        grounding = ''.join(f'<p data-claim-id="{escape(r["claim_id"])}"><span class="badge">{escape(r["knowledge_class"])}</span>'
                           f'{escape(r["claim"])} <span class="hint">[{escape(r["status"])}; '
                           f'{escape(", ".join(r["evidence_refs"] + r["computation_refs"]))}]</span></p>' for r in m['grounding_records'])
        sources = ''.join(f'<li>{source_link(ref)}</li>' for ref in m['source_references'])
        paper_metadata = m['metadata'].get('paper_metadata', {})
        paper_details = ''
        if isinstance(paper_metadata, dict):
            if paper_metadata.get('title'):
                paper_details += f'<p><strong>Paper:</strong> {escape(paper_metadata["title"])}</p>'
            if isinstance(paper_metadata.get('source_url'), str):
                paper_details += '<p>' + source_link(paper_metadata['source_url']) + '</p>'
        ground_plan = ''.join(f'<li>{escape(x)}</li>' for x in lesson['source_grounding_plan'])
        toolbar = '<button class="secondary" data-role="reset">Reset</button>'
        if any(v['component'] == 'comparison' for v in m['visuals']):
            toolbar += '<button class="secondary" data-role="save-comparison">Save comparison</button><span data-role="comparison-status"></span>'
        if any(v['component'] == 'process' for v in m['visuals']):
            toolbar += '<button class="secondary" data-role="step-next">Next step</button><span data-role="step-value"></span>'
        css = (RUNTIME / 'styles.css').read_text(encoding='utf-8')
        js = '\n'.join((RUNTIME / name).read_text(encoding='utf-8') for name in ('evaluator.js', 'canonical.js', 'visuals.js', 'runtime.js'))
        return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(m['concept'])} · Paper to Playground</title><style>{css}</style></head>
<body><main><header data-role="central-question"><div class="eyebrow">Paper to Playground · Interactive scientific lesson</div>
<h1>{escape(lesson['central_learning_question'])}</h1><p class="lede">{escape(science['purpose'])}</p><ul class="objectives">{objectives}</ul></header>
<section class="block" data-role="intuition"><h2>Build an intuition</h2><p class="lede">{escape(lesson['intuition'])}</p></section>
<section class="block" data-role="symbols"><h2>The parts and symbols</h2><dl class="symbols">{symbols}</dl></section>
<section class="block" data-role="mechanism"><h2>Follow the mechanism</h2><ol class="steps">{steps}</ol>{equations}</section>
<section class="block" data-role="playground"><h2>Predict, change, observe</h2><div class="playground-grid"><div class="panel controls">{controls}</div><div class="stage">{visuals}</div></div>
<div class="toolbar">{toolbar}</div><p class="status" role="status" aria-live="polite" data-role="status"></p></section>
<section class="block" data-role="intermediates"><h2>Follow the numbers</h2><div class="outputs">{values}</div></section>
<section class="block" data-role="explorations"><h2>Two ways to explore</h2><div class="explorations">{explorations}</div></section>
<section data-role="limitation" class="callout"><h2>Where this demonstration stops</h2><p>{escape(lesson['limitation_or_assumption'])}</p>
<p>{escape(lesson['misconception'])}</p><p>{escape(science['demonstration_scope'])}</p>
<ul>{''.join('<li>' + escape(x) + '</li>' for x in science['limitations'] + science['assumptions'])}</ul></section>
<section data-role="source-grounding" class="grounding"><h2>What supports this lesson</h2>{paper_details}{grounding}<ul>{sources}</ul><ul>{ground_plan}</ul>
<p>Paper-supported claims cite evidence IDs. Derived values use the executable mechanism. Teaching choices and ranges are pedagogical simplifications.</p></section>
<footer>Explore the mechanism with small inputs. Generated diagrams are teaching representations; they are not original paper figures.</footer>
</main><script type="application/json" id="playground-manifest">{safe_json(m)}</script><script>{js}</script></body></html>'''
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise PlaygroundError(Failure(code=FailureCode.RENDER_FAILED, stage='render', severity=FailureSeverity.MAJOR,
                                      recoverable=True, message='Cannot render the supplied executable IR.',
                                      details={'reason': str(exc) if isinstance(exc, ValueError) else type(exc).__name__})) from exc


def render_candidate(ir: ExplanationIR, directory: str | Path, *, asts: Mapping[str, dict] | None = None) -> Path:
    """Write only to the caller's staging directory; promotion is a separate gate."""
    result = render_html(ir, asts=asts)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'index.html'
    path.write_text(result, encoding='utf-8', newline='\n')
    return path
