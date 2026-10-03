"""Cheap deterministic artifact, manifest, security and semantic coverage gate."""

from __future__ import annotations

import json
import math
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

from playground.ir.models import ExplanationIR
from playground.render.ast_support import computation_order, validate_ast
from playground.render.manifest import build_manifest
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus

REQUIRED_ROLES = {'central-question', 'intuition', 'symbols', 'mechanism', 'playground',
                  'intermediates', 'explorations', 'limitation', 'source-grounding', 'reset', 'status'}


def report(findings: list[ValidationFinding], stage: str) -> ValidationReport:
    status = ValidationStatus.FAIL if any(f.status == ValidationStatus.FAIL for f in findings) else (
        ValidationStatus.WARN if any(f.status == ValidationStatus.WARN for f in findings) else ValidationStatus.PASS)
    return ValidationReport(status=status, findings=tuple(findings), stage=stage)


class ArtifactParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[tuple[str, dict[str, str | None]]] = []
        self.scripts: list[tuple[dict, str]] = []
        self.styles: list[str] = []
        self.active: str | None = None
        self.attributes: dict = {}
        self.content: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.elements.append((tag, attributes))
        if tag in {'script', 'style'}:
            self.active, self.attributes, self.content = tag, attributes, []

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        if self.active:
            self.content.append(data)

    def handle_endtag(self, tag):
        if tag == self.active:
            content = ''.join(self.content)
            if tag == 'script':
                self.scripts.append((self.attributes, content))
            else:
                self.styles.append(content)
            self.active = None


def _finite(value):
    if isinstance(value, list):
        return bool(value) and all(_finite(x) for x in value)
    return isinstance(value, (str, bool)) or isinstance(value, (int, float)) and math.isfinite(value)


def _shape(value):
    if not isinstance(value, list):
        return []
    if not value:
        raise ValueError('Empty array')
    sub = _shape(value[0])
    if any(_shape(x) != sub for x in value):
        raise ValueError('Ragged array')
    return [len(value), *sub]


def validate_setup(m: dict, setup: dict, *, defaults: bool = False) -> None:
    by_var = {c['scientific_variable']: c for c in m['controls']}
    variables = {v['id']: v for v in m['variables']}
    proposed = {**m['initial_state'], **setup}
    for key, value in setup.items():
        if key not in by_var:
            raise ValueError('Preset references uncontrolled input')
        c = by_var[key]
        actual = _shape(value)
        shape = [actual[i] if m.get('canonical_ast_version') and isinstance(dimension, str) and i < len(actual)
                 else proposed.get(dimension) if isinstance(dimension, str) else dimension
                 for i, dimension in enumerate(variables[key]['shape'])]
        if not all(isinstance(d, (int, float)) and not isinstance(d, bool) and math.isfinite(d) and d > 0 and d == int(d) for d in shape):
            raise ValueError('Shape dimensions must resolve to positive integers')
        if not _finite(value) or _shape(value) != shape:
            raise ValueError('Invalid input value or shape')
        if c['control_type'] == 'select':
            if value not in c['options']:
                raise ValueError('Unlisted control option')
        elif c['control_type'] == 'toggle':
            if not isinstance(value, bool):
                raise ValueError('Toggle requires boolean')
        else:
            def check(x):
                if isinstance(x, list):
                    for item in x:
                        check(item)
                elif isinstance(x, bool) or not isinstance(x, (int, float)):
                    raise ValueError('Numeric control requires numbers')
                elif c['minimum'] is not None and x < c['minimum'] or c['maximum'] is not None and x > c['maximum']:
                    raise ValueError('Default or preset outside domain')
            check(value)
            distribution = variables[key]['type'] == 'distribution' or not m.get('canonical_ast_version')
            norm = sum(value) if isinstance(value, list) and distribution else math.hypot(*value) if isinstance(value, list) else 0
            if c['validation_rule'] == 'normalize' and (not isinstance(value, list) or distribution and any(x < 0 for x in value) or abs(norm - 1) > m['numeric_tolerance']):
                raise ValueError('Validated setups must already be normalized')


def validate_manifest(m: dict) -> None:
    """Structural verification even when browser execution is unavailable."""
    required = {'generator_version', 'config_version', 'concept', 'mechanism_family', 'variables', 'controls',
                'computations', 'dependencies', 'outputs', 'visuals', 'explorations', 'source_references',
                'knowledge_classes', 'grounding_records', 'simplifications', 'limitations', 'focus_coverage',
                'initial_state', 'scientific_model', 'lesson_spec', 'numeric_tolerance'}
    if required - set(m) or not m['concept'] or not m['focus_coverage']:
        raise ValueError('Incomplete manifest')
    lesson = m['lesson_spec']
    if not all(isinstance(lesson[k], str) and lesson[k].strip() for k in ('central_learning_question', 'intuition', 'visual_question', 'visual_intent', 'limitation_or_assumption', 'misconception')):
        raise ValueError('Required lesson content is empty')
    if not lesson['learning_objectives'] or not lesson['source_grounding_plan'] or not m['grounding_records']:
        raise ValueError('Objectives and source grounding are required')
    if not isinstance(m['numeric_tolerance'], (int, float)) or not math.isfinite(m['numeric_tolerance']) or m['numeric_tolerance'] <= 0:
        raise ValueError('Invalid numeric tolerance')
    ids = {v['id'] for v in m['variables']}
    by_id = {v['id']: v for v in m['variables']}
    if len(ids) != len(m['variables']):
        raise ValueError('Duplicate variable IDs')
    if m.get('canonical_ast_version'):
        from playground.render.presentation import display_projection
        if m.get('presentation') != display_projection(m):
            raise ValueError('Learner projection does not preserve scientific outputs')
        from playground.computation.parser import parse
        expected_invariants = {'bindings':m['metadata'].get('invariant_bindings',{}),
                               'asts':[parse(text).to_dict() for text in m['scientific_model']['invariants']]}
        if m.get('invariants') != expected_invariants:
            raise ValueError('Runtime invariants differ from the scientific model')
    if len(m['controls']) < 2 or len(m['explorations']) != 2 or not m['visuals'] or not m['computations']:
        raise ValueError('Missing interactive lesson components')
    computations = m['computations']
    runtime_ids = [x['id'] for field in ('controls', 'computations', 'visuals', 'explorations') for x in m[field]]
    if len(runtime_ids) != len(set(runtime_ids)) or len({c['scientific_variable'] for c in m['controls']}) != len(m['controls']):
        raise ValueError('Duplicate runtime IDs or control variables')
    for c in computations:
        reads = validate_ast(c['ast'])
        canonical = c['ast'].get('type') == 'Canonical'
        declared = set(c['input_refs']) | set(c['dependencies']) if canonical else set(c['input_refs'])
        if reads != set(c['reads']) or not reads <= declared or not canonical and reads != declared or not canonical and len(c['output_refs']) != 1:
            raise ValueError('Computation dependencies disagree with AST')
        if any(c['output_type'] != by_id[r]['type'] for r in c['output_refs']):
            raise ValueError('Computation and scientific output types disagree')
    if computation_order(computations, set(m['initial_state'])) != computations:
        raise ValueError('Manifest computations are not dependency ordered')
    if m['dependencies'] != {c['id']: c['reads'] for c in computations}:
        raise ValueError('Manifest dependency map differs from AST')
    produced = {r for c in computations for r in c['output_refs']}
    if m.get('canonical_ast_version'):
        produced.update(c['id'] for c in computations)
    if (not m.get('canonical_ast_version') and len(produced) != len(computations)) or produced != set(m['outputs']) or produced & set(m['initial_state']) or produced | set(m['initial_state']) != ids:
        raise ValueError('Scientific state coverage mismatch')
    validate_setup(m, {c['scientific_variable']: c['default'] for c in m['controls']}, defaults=True)
    if any(m['initial_state'][c['scientific_variable']] != c['default'] for c in m['controls']):
        raise ValueError('Initial state differs from control defaults')
    for exploration in m['explorations']:
        if not all(exploration[k] for k in ('change', 'observe', 'why', 'runtime_setup')):
            raise ValueError('Incomplete guided exploration')
        validate_setup(m, exploration['runtime_setup'])
    visual_refs = {r for v in m['visuals'] for r in v['data_refs']}
    if visual_refs - ids:
        raise ValueError('Unresolved visual data')
    for visual in m['visuals']:
        if 'sweep' not in visual:
            if visual['component'] == 'curve':
                raise ValueError('Curve requires a validated parameter sweep')
            continue
        sweep = visual['sweep']
        if not m.get('canonical_ast_version') or visual['component'] != 'curve' or set(sweep) != {'input_ref','control_id','output_ref','sample_values','x_label','y_label'}:
            raise ValueError('Invalid parameter sweep contract')
        control = next((c for c in m['controls'] if c['id'] == sweep['control_id']),None)
        output = by_id.get(sweep['output_ref'])
        if not control or control['scientific_variable'] != sweep['input_ref'] or control['control_type'] not in {'slider','number'} or control['minimum'] is None or control['maximum'] is None:
            raise ValueError('Sweep requires a bounded numeric control')
        if not output or output['type'] != 'scalar' or sweep['output_ref'] not in produced or sweep['x_label'] != control['label'] or sweep['y_label'] != output['display_symbol']:
            raise ValueError('Sweep output or axes disagree with the scientific model')
        points = sweep['sample_values']
        if not isinstance(points,list) or not 2 <= len(points) <= 81 or any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or x < control['minimum'] or x > control['maximum'] for x in points) or any(a >= b for a,b in zip(points,points[1:])):
            raise ValueError('Sweep samples must be ordered and inside the input domain')
        if by_id[sweep['input_ref']]['domain'] == 'integer' and any(x != int(x) for x in points):
            raise ValueError('Sweep violates integer domain')
        if control['step'] and any(abs((x-control['minimum'])/control['step']-round((x-control['minimum'])/control['step'])) > 1e-7 for x in points):
            raise ValueError('Sweep violates the control step')
        reached = {sweep['input_ref']}
        for c in computations:
            if c['ast']['spec']['metadata'].get('kind','expression') != 'expression':
                raise ValueError('Parameter sweeps require pure computations')
            if reached.intersection(c['reads']):
                reached.update(c['output_refs'])
                reached.add(c['id'])
        aliases = m['presentation']['output_aliases']
        if sweep['output_ref'] not in reached or sweep['output_ref'] not in {aliases.get(r,r) for r in visual['data_refs']}:
            raise ValueError('Sweep lacks a scientific dependency path')
    target_ids = ids | {c['id'] for c in computations} | {v['id'] for v in m['visuals']}
    for control in m['controls']:
        if set(control['effect_targets']) - target_ids:
            raise ValueError('Unknown control effect target')
        reached = {control['scientific_variable']}
        for c in computations:
            if reached & set(c['reads']):
                reached.update(c['output_refs'])
                if m.get('canonical_ast_version'):
                    reached.add(c['id'])
        if not reached & produced or not reached & visual_refs:
            raise ValueError('Dead control: no computation and visualization path')
        for target in control['effect_targets']:
            if target in ids and target not in reached:
                raise ValueError('Declared control effect has no dependency path')
            if target in {c['id'] for c in computations} and not any(c['id'] == target and reached & set(c['output_refs']) for c in computations):
                raise ValueError('Declared computation effect has no dependency path')
            if target in {v['id'] for v in m['visuals']} and not any(v['id'] == target and reached & set(v['data_refs']) for v in m['visuals']):
                raise ValueError('Declared visual effect has no dependency path')
    focus = m['focus_coverage']
    science = m['scientific_model']
    mechanism_ids = {s['id'] for s in science['mechanism_steps']} | {e['id'] for e in science['equations']} | {r['id'] for r in science['relationships']}
    objective_ids = set(m['lesson_spec']['learning_objectives']) | {str(i) for i in range(len(m['lesson_spec']['learning_objectives']))}
    for field, known in [('learning_objective_refs', objective_ids), ('mechanism_refs', mechanism_ids),
                         ('control_refs', {c['id'] for c in m['controls']}), ('computation_refs', {c['id'] for c in computations}),
                         ('visual_refs', {v['id'] for v in m['visuals']}), ('exploration_refs', {e['id'] for e in m['explorations']})]:
        if not focus[field] or set(focus[field]) - known:
            raise ValueError('Unresolved or empty FocusCoverageMap ' + field)
    for record in m['grounding_records']:
        if record['knowledge_class'] not in {'SOURCE_GROUNDED', 'DERIVED', 'PEDAGOGICAL'} or record['status'] not in {'SUPPORTED', 'PARTIAL', 'UNSUPPORTED'}:
            raise ValueError('Invalid scientific grounding classification')
        if record['status'] == 'UNSUPPORTED':
            raise ValueError('Unsupported scientific claim cannot be promoted')
        if record['knowledge_class'] == 'SOURCE_GROUNDED' and not record['evidence_refs']:
            raise ValueError('Paper-supported claim requires evidence IDs')
        if record['knowledge_class'] == 'DERIVED' and (not record['computation_refs'] or set(record['computation_refs']) - {c['id'] for c in computations}):
            raise ValueError('Derived claim requires valid computation lineage')


def validate_artifact(path: str | Path, ir: ExplanationIR | None = None, *, asts: Mapping[str, dict] | None = None) -> ValidationReport:
    findings: list[ValidationFinding] = []

    def fail(code, message, target=None):
        findings.append(ValidationFinding(ValidationStatus.FAIL, code, 'artifact', message, target))

    try:
        content = Path(path).read_text(encoding='utf-8')
    except (OSError, UnicodeError):
        fail('ARTIFACT_MISSING', 'Candidate index.html is absent or unreadable.')
        return report(findings, 'artifact')
    parser = ArtifactParser()
    parser.feed(content)
    elements = parser.elements
    for tag, attrs in elements:
        if any(k.startswith('on') for k in attrs):
            fail('ARTIFACT_UNSAFE_HTML', 'Inline event handlers are forbidden.')
        if tag in {'iframe', 'object', 'embed', 'base'} or tag == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh':
            fail('ARTIFACT_EXTERNAL_DEPENDENCY', 'Embedded resources, base URLs and redirects are forbidden.')
        if tag == 'script' and attrs.get('src') or attrs.get('srcset'):
            fail('ARTIFACT_EXTERNAL_DEPENDENCY', 'Executable sources and srcset resources must be embedded directly.')
        for key in ('src', 'srcset', 'poster', 'action'):
            if attrs.get(key) and not str(attrs[key]).startswith('data:'):
                fail('ARTIFACT_EXTERNAL_DEPENDENCY', 'Artifact references an external runtime asset.')
        if tag == 'link' or tag in {'image', 'use'} and any(attrs.get(k) and not str(attrs[k]).startswith('#') for k in ('href', 'xlink:href')):
            fail('ARTIFACT_EXTERNAL_DEPENDENCY', 'Linked runtime resources are forbidden.')
        if tag == 'a' and attrs.get('href'):
            href = attrs['href']
            try:
                safe_scheme = urlsplit(href).scheme.lower() in {'http', 'https'}
            except ValueError:
                safe_scheme = False
            if not href.startswith('#') and not safe_scheme:
                fail('ARTIFACT_UNSAFE_LINK', 'Unsafe or local citation link.')
    scripts = [s for attrs, s in parser.scripts if attrs.get('type') != 'application/json']
    if not scripts or not parser.styles:
        fail('ARTIFACT_ASSETS_MISSING', 'Embedded JavaScript and CSS are required.')
    js = '\n'.join(scripts)
    forbidden = r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|eval|Function|Worker|SharedWorker|importScripts)\s*\(|\bimport\s*(?:\(|[\w*{])|\b(?:sendBeacon|serviceWorker)\b'
    if re.search(forbidden, js):
        fail('ARTIFACT_FORBIDDEN_RUNTIME', 'Forbidden dynamic execution or network construct.')
    css = '\n'.join(parser.styles) + '\n' + '\n'.join(attrs.get('style', '') for _, attrs in elements)
    if re.search(r'@import|url\s*\(\s*["\']?(?!data:|#)', css, re.I):
        fail('ARTIFACT_EXTERNAL_DEPENDENCY', 'CSS requires a linked runtime resource.')
    manifests = [s for attrs, s in parser.scripts if attrs.get('id') == 'playground-manifest' and attrs.get('type') == 'application/json']
    if len(manifests) != 1:
        fail('ARTIFACT_MANIFEST_INVALID', 'Exactly one data-only manifest is required.')
        return report(findings, 'artifact')
    try:
        m = json.loads(manifests[0], parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        validate_manifest(m)
        if ir is not None and m != build_manifest(ir, asts=asts):
            fail('ARTIFACT_IR_COVERAGE', 'Manifest differs from the supplied ExplanationIR.')
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError) as exc:
        message = str(exc) if isinstance(exc, ValueError) else 'Invalid manifest field type or unresolved reference.'
        fail('ARTIFACT_MANIFEST_INVALID', message)
        return report(findings, 'artifact')
    roles = {attrs.get('data-role') for _, attrs in elements}
    if REQUIRED_ROLES - roles:
        fail('ARTIFACT_SECTIONS_MISSING', 'Required lesson sections or Reset are missing.')
    dom_ids = [attrs['id'] for _, attrs in elements if 'id' in attrs]
    if len(dom_ids) != len(set(dom_ids)):
        fail('ARTIFACT_DUPLICATE_DOM_ID', 'DOM IDs must be unique.')
    for attribute, expected, tags in [
        ('data-control-id', {c['id'] for c in m['controls']}, {'input', 'textarea', 'select'}),
        ('data-output-id', set(m['presentation']['output_refs']) if m.get('canonical_ast_version') else set(m['outputs']) | set(m['lesson_spec']['important_intermediates']), {'output'}),
        ('data-visual-id', {v['id'] for v in m['visuals']}, {'div'}),
        ('data-exploration-id', {e['id'] for e in m['explorations']}, {'article'}),
        ('data-computation-id', {c['id'] for c in m['computations']}, {'div'}),
    ]:
        matches = [(tag, attrs) for tag, attrs in elements if attribute in attrs]
        actual = [attrs[attribute] for _, attrs in matches]
        if set(actual) != expected or len(actual) != len(expected) or any(tag not in tags for tag, _ in matches):
            fail('ARTIFACT_DOM_COVERAGE', 'Manifest and semantic DOM disagree.', attribute)
        if attribute in {'data-control-id', 'data-output-id', 'data-visual-id'} and any(not a.get('data-depends-on') for _, a in matches):
            fail('ARTIFACT_METADATA_MISSING', 'Scientific dependency metadata is missing.', attribute)
    labels = {attrs.get('for') for tag, attrs in elements if tag == 'label'}
    control_specs = {c['id']: c for c in m['controls']}
    visual_specs = {v['id']: v for v in m['visuals']}
    for tag, attrs in elements:
        if 'data-control-id' in attrs and (attrs.get('id') not in labels or not attrs.get('aria-describedby')):
            fail('ARTIFACT_ACCESSIBILITY', 'Controls require labels and current-value descriptions.')
        if attrs.get('data-control-id') in control_specs:
            scientific_variable = control_specs[attrs['data-control-id']]['scientific_variable']
            if attrs.get('data-variable-id') != scientific_variable or attrs.get('data-depends-on') != scientific_variable:
                fail('ARTIFACT_DOM_COVERAGE', 'Control scientific metadata differs from its contract.')
        if attrs.get('data-visual-id') in visual_specs:
            if attrs.get('data-depends-on') != ' '.join(visual_specs[attrs['data-visual-id']]['data_refs']):
                fail('ARTIFACT_DOM_COVERAGE', 'Visual dependency metadata differs from its contract.')
    if {attrs.get('data-setup-id') for _, attrs in elements if attrs.get('data-role') == 'apply-setup'} != {e['id'] for e in m['explorations']}:
        fail('ARTIFACT_PRESETS_MISSING', 'Explorations require Apply Setup buttons.')
    if not findings:
        findings.append(ValidationFinding(ValidationStatus.PASS, 'ARTIFACT_VALID', 'artifact', 'Offline assets, scientific dependencies and IR/manifest/DOM coverage verified.'))
    return report(findings, 'artifact')
