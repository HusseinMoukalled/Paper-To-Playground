"""Installed-Chromium validation. Never installs/downloads a browser at runtime."""

from __future__ import annotations

import json
import math
import os
import shutil
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Callable, Iterator

from playground.config import BROWSER_TIMEOUT_SECONDS, NUMERIC_TOLERANCE
from playground.validation.artifact import report, validate_artifact
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus

ReferenceEvaluator = Callable[[dict], dict]


def discover_chromium() -> list[Path]:
    candidates = [os.environ.get('PLAYGROUND_CHROMIUM_PATH', '')]
    candidates.extend(shutil.which(name) or '' for name in ('chromium', 'chromium-browser', 'google-chrome', 'chrome', 'msedge'))
    for base in (os.environ.get('PROGRAMFILES', ''), os.environ.get('PROGRAMFILES(X86)', ''), os.environ.get('LOCALAPPDATA', '')):
        if base:
            candidates.extend(str(Path(base) / suffix) for suffix in ('Google/Chrome/Application/chrome.exe', 'Microsoft/Edge/Application/msedge.exe'))
    candidates.extend(['/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome',
                       '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])
    result = []
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and Path(candidate) not in result:
            result.append(Path(candidate))
    return result


@contextmanager
def chromium_session(*, timeout_seconds: float = BROWSER_TIMEOUT_SECONDS) -> Iterator[object]:
    """Use existing executables only, with isolated headless profiles."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BrowserUnavailable('Pip-installable browser controller is unavailable.') from exc
    manager = sync_playwright()
    try:
        controller = manager.start()
    except Exception as exc:
        raise BrowserUnavailable('Browser controller could not start in this environment.') from exc
    try:
        candidates = discover_chromium()
        bundled = Path(controller.chromium.executable_path)
        if bundled.is_file() and bundled not in candidates:
            candidates.append(bundled)
        browser = None
        deadline = time.monotonic() + timeout_seconds
        for executable in candidates:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                browser = controller.chromium.launch(executable_path=str(executable), headless=True,
                                                     timeout=min(5000, remaining * 1000),
                                                     args=['--disable-background-networking', '--disable-component-update'])
                break
            except Exception:
                continue
        if browser is None:
            raise BrowserUnavailable('No compatible installed Chromium could be controlled; no browser was downloaded.')
        try:
            yield browser
        finally:
            browser.close()
    finally:
        controller.stop()


class BrowserUnavailable(RuntimeError):
    pass


def close_enough(a, b, tolerance=NUMERIC_TOLERANCE) -> bool:
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(close_enough(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(close_enough(a[k], b[k], tolerance) for k in a)
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=tolerance, abs_tol=tolerance)
    return type(a) is type(b) and a == b


def alternative_values(control: dict, *, integer=False) -> list:
    """Deterministic interior/boundary probes; avoid assuming one endpoint matters."""
    default = control['default']
    kind = control['control_type']
    if kind == 'toggle':
        return [not default]
    if kind == 'select':
        return [x for x in control['options'] if x != default]
    lo, hi = control['minimum'], control['maximum']
    if kind in {'vector', 'matrix'}:
        candidate = json.loads(json.dumps(default))
        if kind == 'matrix':
            old = candidate[0][0]
            candidate[0][0] = hi if hi is not None and hi != old else lo if lo is not None and lo != old else old + 1
        else:
            old = candidate[0]
            candidate[0] = hi if hi is not None and hi != old else lo if lo is not None and lo != old else old + 1
        if control['validation_rule'] == 'normalize':
            total = sum(candidate)
            if total > 0:
                candidate = [x / total for x in candidate]
        return [candidate]
    values = []
    for value in (lo, hi, (lo + hi) / 2 if lo is not None and hi is not None else None, default + (control['step'] or 1)):
        if integer and value is not None:
            value = round(value)
        if value is not None and value != default and value not in values and (lo is None or value >= lo) and (hi is None or value <= hi):
            values.append(value)
    return values


def set_native_control(page, control: dict, value) -> None:
    # IDs are data: do not interpolate them into CSS or JavaScript source.
    locator = page.locator('[data-control-id]').nth(next(i for i, c in enumerate(page.evaluate('JSON.parse(document.getElementById("playground-manifest").textContent).controls')) if c['id'] == control['id']))
    kind = control['control_type']
    if kind == 'toggle':
        locator.set_checked(value)
    elif kind == 'select':
        locator.select_option(value)
    elif kind in {'slider', 'range'}:
        locator.evaluate('(el,value)=>{el.value=String(value)}', value)
        locator.dispatch_event('input')
    else:
        locator.fill(json.dumps(value) if isinstance(value, list) else str(value))
        locator.dispatch_event('change')


def validate_browser(path: str | Path, *, reference_evaluator: ReferenceEvaluator | None = None,
                     timeout_seconds: float = BROWSER_TIMEOUT_SECONDS, browser: object | None = None) -> ValidationReport:
    static = validate_artifact(path)
    if static.status == ValidationStatus.FAIL:
        return ValidationReport(ValidationStatus.FAIL, static.findings, 'browser')
    findings: list[ValidationFinding] = []

    def finding(code, message, target=None, status=ValidationStatus.FAIL, details=None):
        findings.append(ValidationFinding(status, code, 'browser', message, target, details or {}))

    def require(condition, code, message, target=None, details=None):
        if not condition:
            finding(code, message, target, details=details)

    def reset_diff(snapshot, baseline, visuals, baseline_visuals, tolerance):
        """Name what Reset failed to restore so the trace is actionable."""
        changed_state = [k for k in snapshot['state'] if k not in baseline['state'] or not close_enough(snapshot['state'][k], baseline['state'][k], tolerance)]
        changed_visuals = [k for k in visuals if visuals[k] != baseline_visuals.get(k)]
        excerpt = {}
        for key in changed_visuals[:2]:
            a, b = baseline_visuals.get(key, ''), visuals[key]
            index = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))
            excerpt[key] = {'baseline': a[max(0, index - 60):index + 120], 'after_reset': b[max(0, index - 60):index + 120]}
        return {'state_keys': changed_state, 'ui': snapshot['ui'] if snapshot['ui'] != baseline['ui'] else None,
                'state_values': {k: {'baseline': baseline['state'].get(k), 'after_reset': snapshot['state'][k]}
                                 for k in changed_state[:5]},
                'error': snapshot['error'], 'visuals': changed_visuals, 'excerpt': excerpt}

    errors: list[str] = []
    attempted_network: list[str] = []
    deadline = time.monotonic() + timeout_seconds
    try:
        session = nullcontext(browser) if browser is not None else chromium_session(timeout_seconds=timeout_seconds)
        with session as controlled_browser:
            context = controlled_browser.new_context(viewport={'width': 1280, 'height': 900}, offline=True)
            context.route('**/*', lambda route: route.abort() if url_is_network(route.request.url) else route.continue_())
            page = context.new_page()
            page.set_default_timeout(min(5000, timeout_seconds * 1000))
            page.on('pageerror', lambda err: errors.append(type(err).__name__))
            page.on('request', lambda request: attempted_network.append('network request') if url_is_network(request.url) else None)
            page.goto(Path(path).resolve().as_uri(), wait_until='load')
            if not page.evaluate('document.documentElement.dataset.runtimeReady === "true"'):
                finding('BROWSER_JS_ERROR', 'Scientific runtime failed to initialize.')
                return report(findings, 'browser')
            m = page.evaluate('JSON.parse(document.getElementById("playground-manifest").textContent)')
            tolerance = m['numeric_tolerance']

            def inspect():
                if time.monotonic() > deadline:
                    raise TimeoutError('Browser trajectory budget exceeded')
                snapshot = page.evaluate('PlaygroundRuntime.snapshot()')
                require(snapshot['error'] is None, 'BROWSER_INVALID_STATE', 'Runtime rejected a validated scientific setup.')
                state = snapshot['state']
                output_data = page.locator('[data-output-id]').evaluate_all('(els) => els.map(el => ({id:el.dataset.outputId, value:JSON.parse(el.dataset.value), text:el.textContent}))')
                for output in output_data:
                    require(close_enough(output['value'], state[output['id']], tolerance), 'BROWSER_STALE_NUMBER', 'Displayed number differs from scientific state.', output['id'])
                    expected_text = page.evaluate('([id]) => ScientificAST.format(PlaygroundRuntime.snapshot().state[id])', [output['id']])
                    require(output['text'] == expected_text, 'BROWSER_STALE_NUMBER', 'Visible number differs from scientific state.', output['id'])
                controls = page.locator('[data-control-id]').evaluate_all('(els)=>els.map(el=>({id:el.dataset.variableId, value:el.type==="checkbox"?el.checked:el.value}))')
                for control, spec in zip(controls, m['controls']):
                    value = control['value']
                    if spec['control_type'] in {'vector', 'matrix'}:
                        value = json.loads(value)
                    elif spec['control_type'] not in {'select', 'toggle'}:
                        value = float(value)
                    require(close_enough(value, state[control['id']], tolerance), 'BROWSER_REPRESENTATION_MISMATCH',
                            'Control and scientific state disagree.', spec['id'],
                            {'displayed': value, 'scientific_state': state[control['id']]})
                rendered = page.locator('[data-visual-id]').evaluate_all('(els)=>els.map(el=>({id:el.dataset.visualId, values:JSON.parse(el.dataset.values), html:el.innerHTML}))')
                for item, visual in zip(rendered, m['visuals']):
                    require(close_enough(item['values'], [state[r] for r in visual['data_refs']], tolerance), 'BROWSER_REPRESENTATION_MISMATCH', 'Visual encodes values that differ from scientific state.', visual['id'])
                    require('<svg' in item['html'] and ('<rect' in item['html'] or '<circle' in item['html'] or '<text' in item['html']), 'BROWSER_DEAD_VISUAL', 'Visual has no scientific marks.', visual['id'])
                equation_values = page.locator('[data-computation-id]').evaluate_all('(els)=>els.map(el=>({id:el.dataset.computationId,value:JSON.parse(el.dataset.value),text:el.querySelector("[data-role=substitution]").textContent}))')
                for item, comp in zip(equation_values, m['computations']):
                    expected_substitution = page.evaluate('(c)=>ScientificAST.equation(c.ast,{},PlaygroundRuntime.snapshot().state)+" = "+ScientificAST.format(PlaygroundRuntime.snapshot().state[c.output_refs[0]])', comp)
                    require(close_enough(item['value'], state[comp['output_refs'][0]], tolerance) and item['text'] == expected_substitution, 'BROWSER_REPRESENTATION_MISMATCH', 'Equation substitution differs from scientific state.', comp['id'])
                if reference_evaluator:
                    expected = reference_evaluator({k: state[k] for k in m['initial_state']})
                    for key in m['outputs']:
                        require(key in expected and close_enough(state[key], expected[key], tolerance), 'BROWSER_COMPUTATION_PARITY', 'Browser computation differs from the Python reference.', key)
                return snapshot, {v['id']: v['html'] for v in rendered}

            baseline, baseline_visuals = inspect()
            for control in m['controls']:
                changed_output = changed_visual = False
                declared = m.get('metadata', {}).get('control_test_values', {}).get(control['id'], [])
                from playground.computation.probes import array_probes
                variable = next(v for v in m['variables'] if v['id'] == control['scientific_variable'])
                independent = array_probes(control, variable)
                candidates = (declared + independent if control['control_type'] in {'vector', 'matrix'}
                              else alternative_values(control, integer=any(
                                  v['id'] == control['scientific_variable'] and v.get('domain') == 'integer'
                                  for v in m['variables'])))
                for value in candidates:
                    page.locator('[data-role="reset"]').click()
                    set_native_control(page, control, value)
                    observed, visuals = inspect()
                    changed_output |= any(not close_enough(baseline['state'][key], observed['state'][key], tolerance) for key in m['outputs'])
                    relevant = [v for v in m['visuals'] if any(not close_enough(baseline['state'][ref], observed['state'][ref], tolerance) for ref in v['data_refs'])]
                    changed_visual |= any(visuals[v['id']] != baseline_visuals[v['id']] for v in relevant)
                require(changed_output, 'BROWSER_DEAD_CONTROL', 'No scientific output changed across deterministic control probes.', control['id'])
                require(changed_visual, 'BROWSER_DEAD_VISUAL', 'No scientific visual changed across control probes.', control['id'])
                page.locator('[data-role="reset"]').click()
                reset, reset_visuals = inspect()
                require(close_enough(reset, baseline, tolerance) and reset_visuals == baseline_visuals, 'BROWSER_RESET_FAILED', 'Reset did not restore baseline representations.',
                        control['id'], reset_diff(reset, baseline, reset_visuals, baseline_visuals, tolerance))
            for exploration in m['explorations']:
                # Buttons are selected by ordinal; source IDs remain data.
                index = next(i for i, e in enumerate(m['explorations']) if e['id'] == exploration['id'])
                page.locator('[data-role="apply-setup"]').nth(index).click()
                snapshot, _ = inspect()
                require(all(close_enough(snapshot['state'][key], value, tolerance) for key, value in exploration['runtime_setup'].items()) and snapshot['ui']['exploration'] == exploration['id'],
                        'BROWSER_PRESET_FAILED', 'Apply Setup did not restore the validated preset.', exploration['id'])
            if page.locator('[data-role="save-comparison"]').count():
                page.locator('[data-role="save-comparison"]').click()
                snapshot, _ = inspect()
                require(snapshot['ui']['comparison'] == snapshot['state'], 'BROWSER_COMPARISON_FAILED', 'Comparison failed to capture scientific state.')
            if page.locator('[data-role="step-next"]').count():
                page.locator('[data-role="step-next"]').click()
                snapshot, _ = inspect()
                lengths = [len(snapshot['state'][v['data_refs'][0]]) for v in m['visuals'] if v['component'] == 'process' and isinstance(snapshot['state'][v['data_refs'][0]], list)]
                require(not lengths or max(lengths) <= 1 or snapshot['ui']['step'] == 1, 'BROWSER_STEPPER_FAILED', 'Stepper did not advance scientific process view.')
            page.locator('[data-role="reset"]').click()
            snapshot, visuals = inspect()
            require(close_enough(snapshot, baseline, tolerance) and visuals == baseline_visuals, 'BROWSER_RESET_FAILED', 'Final Reset did not restore all scientific and explanatory state.',
                    None, reset_diff(snapshot, baseline, visuals, baseline_visuals, tolerance))
            for width in (375, 768):
                page.set_viewport_size({'width': width, 'height': 900})
                require(page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), 'BROWSER_RESPONSIVE_FAILED', 'Lesson overflows the viewport.')
            require(page.locator('[data-control-id]').evaluate_all('(els)=>els.every(el=>el.labels && el.labels.length && el.getAttribute("aria-describedby"))'),
                    'BROWSER_ACCESSIBILITY_FAILED', 'Scientific controls lack native labels or descriptions.')
            require(not errors, 'BROWSER_JS_ERROR', 'JavaScript exception during the interaction trajectory.')
            require(not attempted_network, 'BROWSER_NETWORK_DEPENDENCY', 'Offline page attempted a network request.')
            context.close()
    except BrowserUnavailable as exc:
        finding('BROWSER_VALIDATION_UNAVAILABLE', str(exc), status=ValidationStatus.WARN,
                details={'fallback': 'Static artifact validation completed', 'static_status': static.status.value})
    except Exception as exc:
        finding('BROWSER_VALIDATION_FAILED', 'Chromium interaction validation could not complete.', details={'exception_type': type(exc).__name__})
    if errors and not any(f.code == 'BROWSER_JS_ERROR' for f in findings):
        finding('BROWSER_JS_ERROR', 'JavaScript exception during the interaction trajectory.')
    if not findings:
        finding('BROWSER_TRAJECTORY_PASS', 'Offline file:// controls, scientific values, visuals, presets, Reset and responsive behavior verified.', status=ValidationStatus.PASS)
        if reference_evaluator is None:
            finding('BROWSER_REFERENCE_UNAVAILABLE', 'Python computation parity requires the upstream reference evaluator.', status=ValidationStatus.WARN)
    return report(findings, 'browser')


def url_is_network(url: str) -> bool:
    return url.lower().startswith(('http:', 'https:', 'ws:', 'wss:'))
