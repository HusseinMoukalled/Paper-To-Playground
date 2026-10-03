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


def learner_symbol(variable):
    symbol = variable['display_symbol']
    if len(symbol) > 24 or '^' in symbol or '/' in symbol:
        return variable.get('source_symbol') or symbol
    return symbol


def lesson_title(manifest):
    """Use the explicit focus when a concept field is a full scientific claim."""
    concept = manifest['scientific_model']['concept'].strip()
    focus = manifest['focus_coverage']['focus'].strip()
    if len(concept) > 100 and focus and len(focus) <= 100:
        return focus[0].upper() + focus[1:]
    return concept


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
    if kind == 'select':
        input_html = f'<select {attrs}>' + ''.join(f'<option value="{escape(x)}">{escape(x)}</option>' for x in control['options']) + '</select>'
    elif kind in {'vector', 'matrix'}:
        input_html = f'<textarea {attrs} rows="2" spellcheck="false">{escape(safe_json(control["default"]))}</textarea>'
    elif kind == 'toggle':
        input_html = f'<input {attrs} type="checkbox"' + (' checked' if control['default'] else '') + '>'
    else:
        input_type = 'range' if kind in {'slider', 'range'} else 'number'
        domain = ''.join(f' {a}="{escape(control[b])}"' for a, b in [('min', 'minimum'), ('max', 'maximum'), ('step', 'step')] if control[b] is not None)
        if control['step'] is None:
            domain += ' step="any"'
        input_html = f'<input {attrs} type="{input_type}" value="{escape(control["default"])}"{domain}>'
    units = (' (' + escape(control['units']) + ')') if control['units'] else ''
    return (f'<div class="control"><label for="{key}">{escape(control["label"])}{units}</label>'
            f'<output id="{value_id}" class="current-value">{escape(control["default"])}</output>{input_html}'
            + (f'<div class="range-labels"><span>{escape(control["minimum"])}</span><span>{escape(control["maximum"])}</span></div>' if kind=='slider' else '')
            + f'<p id="{hint_id}" class="hint">{escape(control["learning_purpose"])}</p></div>')


def render_html(ir: ExplanationIR, *, asts: Mapping[str, dict] | None = None) -> str:
    try:
        m = build_manifest(ir, asts=asts)
        lesson, science = m['lesson_spec'], m['scientific_model']
        controls = ''.join(_control(c, i) for i, c in enumerate(m['controls']))
        symbols = ''.join(f'<div class="symbol-card"><dt data-variable-id="{escape(v["id"])}">{escape(learner_symbol(v))}</dt><dd>{escape(v["meaning"])}'
                          + (f' · {escape(v["units"])}' if v['units'] else '')
                          + '</dd></div>' for v in science['variables'])
        objectives = ''.join(f'<li data-objective-id="{i}">{escape(value)}</li>' for i, value in enumerate(lesson['learning_objectives']))
        steps = ''.join(f'<li data-mechanism-id="{escape(s["id"])}">{escape(s["description"])}</li>' for s in sorted(science['mechanism_steps'], key=lambda s: s['order']))
        equations = ''.join(f'<div class="equation-panel" id="equation-{escape(c["id"])}" data-computation-id="{escape(c["id"])}" '
                            f'data-depends-on="{escape(" ".join(c["reads"]))}"><p class="equation" data-role="equation"></p>'
                            f'<p class="substitution" data-role="substitution"></p></div>' for c in m['computations'])
        visuals = ''.join(f'<article class="panel chart-panel"><div class="eyebrow">Live model</div><h3>{escape(v["question"])}</h3>'
                         f'<div class="visual" data-visual-id="{escape(v["id"])}" data-depends-on="{escape(" ".join(v["data_refs"]))}"></div>'
                         + ('<p class="hint">Move the controls to explore the model. The highlighted point is your current setup.</p>' if v.get('sweep') else '<p class="hint">Values computed for your current setup.</p>')
                         + '</article>' for v in m['visuals'])
        output_ids = m.get('presentation',{}).get('output_refs',list(dict.fromkeys(m['outputs'] + lesson['important_intermediates'])))
        variable_by_id = {v['id']: v for v in m['variables']}
        values = ''.join(f'<div class="output"><span class="value-symbol">{escape(learner_symbol(variable_by_id[ref]))}</span>'
                        f'<output data-output-id="{escape(ref)}" data-variable-id="{escape(ref)}" data-depends-on="{escape(ref)}" aria-live="polite"></output>'
                        f'<p class="hint">{escape(variable_by_id[ref]["meaning"])}</p></div>' for ref in output_ids)
        explorations = ''.join(f'<article class="panel exploration" data-exploration-id="{escape(e["id"])}"><span class="eyebrow">Exploration {i + 1}</span>'
                              f'<h3>{escape(e["title"])}</h3><p><strong>Change:</strong> {escape(e["change"])}</p>'
                              f'<p><strong>Observe:</strong> {escape(e["observe"])}</p><p><strong>Why:</strong> {escape(e["why"])}</p>'
                              f'<button data-role="apply-setup" data-setup-id="{escape(e["id"])}">Apply Setup</button></article>'
                              for i, e in enumerate(m['explorations']))
        paper_metadata = m['metadata'].get('paper_metadata', {})
        paper_details = ''
        if isinstance(paper_metadata, dict):
            if paper_metadata.get('title'):
                paper_details += f'<p><strong>Paper:</strong> {escape(paper_metadata["title"])}</p>'
            if isinstance(paper_metadata.get('source_url'), str):
                paper_details += '<p>' + source_link(paper_metadata['source_url']) + '</p>'
        toolbar = '<button class="secondary" data-role="reset">Reset</button>'
        if any(v['component'] == 'comparison' for v in m['visuals']):
            toolbar += '<button class="secondary" data-role="save-comparison">Save comparison</button><span data-role="comparison-status"></span>'
        if any(v['component'] == 'process' for v in m['visuals']):
            toolbar += '<button class="secondary" data-role="step-next">Next step</button><span data-role="step-value"></span>'
        css = (RUNTIME / 'styles.css').read_text(encoding='utf-8')
        js = '\n'.join((RUNTIME / name).read_text(encoding='utf-8') for name in ('canonical.js', 'evaluator.js', 'visuals.js', 'runtime.js'))
        return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(lesson_title(m))} · Paper to Playground</title><style>{css}</style></head>
<body><main><nav class="topbar"><a class="brand" href="#top"><span class="brand-mark">P</span>Paper to Playground</a><div><a href="#playground">Play</a><a href="#mechanism">Understand</a><a href="#explorations">Explore</a></div></nav>
<header id="top" data-role="central-question"><div class="hero-copy"><div class="eyebrow">An interactive lesson</div>
<h1>{escape(lesson_title(m))}</h1><p class="lede">{escape(lesson['central_learning_question'])}</p><a class="start-link" href="#playground">Try it yourself <span aria-hidden="true">↗</span></a></div>
<aside class="learning-card"><span class="eyebrow">What you’ll discover</span><ul>{objectives}</ul></aside></header>
<section data-role="intuition" class="intuition"><span class="section-number">01</span><div><h2>The idea</h2><p>{escape(lesson['intuition'])}</p></div></section>
<section id="playground" data-role="playground"><div class="section-heading"><div><span class="eyebrow">Learn by changing</span><h2>Your playground</h2></div><span class="section-tag">Computed live · works offline</span></div><div class="playground-grid"><div class="panel controls"><h3>Set your inputs</h3>{controls}<div class="toolbar">{toolbar}</div><p class="status" role="status" aria-live="polite" data-role="status"></p></div><div>{visuals}</div></div></section>
<section data-role="intermediates"><div class="section-heading"><h2>Your current values</h2><p class="hint">One setup. Every step connected.</p></div><div class="outputs">{values}</div></section>
<section id="mechanism" data-role="mechanism"><div class="section-heading"><div><span class="eyebrow">From inputs to result</span><h2>How it works</h2></div></div><ol class="mechanism-steps">{steps}</ol><div class="equations">{equations}</div></section>
<section id="explorations" data-role="explorations"><div class="section-heading"><div><span class="eyebrow">Two guided experiments</span><h2>Try these next</h2></div></div><div class="explorations">{explorations}</div></section>
<section data-role="symbols"><details class="glossary"><summary>Know your symbols <span>Definitions & units</span></summary><dl class="symbols">{symbols}</dl></details></section>
<section data-role="limitation" class="callout"><div class="eyebrow">Keep in mind</div><h2>What this lesson does—and doesn’t—show</h2><p>{escape(lesson['limitation_or_assumption'])}</p>
<p>{escape(lesson['misconception'])}</p><p>{escape(science['demonstration_scope'])}</p>
<ul>{''.join('<li>' + escape(x) + '</li>' for x in science['limitations'] + science['assumptions'])}</ul></section>
<section data-role="source-grounding" class="grounding"><h2>Based on the paper</h2>{paper_details}<p>This lesson explores the paper mechanism. Values and curves are computed from the model; input ranges and guided examples are teaching choices, not experimental results.</p></section>
<footer><span class="brand">Paper to Playground</span><span>Understand it. Change it. See what happens.</span></footer>
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
