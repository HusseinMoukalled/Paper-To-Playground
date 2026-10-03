"""Lossless IR metadata plus bounded executable runtime data."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from typing import Any, Mapping

from playground.config import NUMERIC_TOLERANCE
from playground.ir.models import ExplanationIR
from playground.render.ast_support import FORBIDDEN_IDS, computation_order, validate_ast
from playground.render.visual_planner import plan_visual

GENERATOR_VERSION = 'scientific-ui-1.0'
CONFIG_VERSION = 'render-1.0'


def safe_json(value: Any) -> str:
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(',', ':'))
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


def build_manifest(ir: ExplanationIR, *, asts: Mapping[str, dict] | None = None) -> dict:
    data = asdict(ir)
    scientific = data['scientific_model']
    lesson = data['lesson_spec']
    family = data['metadata'].get('mechanism_family', 'scalar_relationship')
    variables = scientific['variables']
    ids = [v['id'] for v in variables]
    if len(ids) != len(set(ids)) or any(not i or i in FORBIDDEN_IDS for i in ids):
        raise ValueError('Invalid or duplicate scientific variable IDs')
    native = any('canonical_ast' in c['metadata'] or 'transition_ast' in c['metadata'] for c in data['computations'])
    aliases = {c['id']: c['output_refs'][0] for c in data['computations'] if c['output_refs']}
    for variable in variables:
        for dimension in variable['shape']:
            if not (isinstance(dimension, int) and not isinstance(dimension, bool) and dimension > 0 or isinstance(dimension, str) and (native or dimension in ids)):
                raise ValueError('Shape dimensions require positive integers or declared variable IDs')
    controls = lesson['controls']
    if len(controls) < 2 or len(lesson['guided_explorations']) != 2:
        raise ValueError('At least two meaningful controls and exactly two explorations are required')
    initial = dict(data['metadata'].get('defaults', data['metadata'].get('initial_state', {})))
    if native:
        lesson['important_intermediates'] = list(dict.fromkeys(aliases.get(i, i) for i in lesson['important_intermediates']))
        for visual in data['visuals']:
            visual['data_refs'] = list(dict.fromkeys(aliases.get(i, i) for i in visual['data_refs']))
    controlled: set[str] = set()
    for control in controls:
        variable = control['scientific_variable']
        if variable not in ids or variable in controlled:
            raise ValueError('Control variables must resolve uniquely')
        controlled.add(variable)
        if control['validation_rule'] not in {'clamp', 'reject', 'normalize', 'warn'}:
            raise ValueError('Unsupported invalid-input policy')
        if control['control_type'] not in {'slider', 'range', 'number', 'select', 'toggle', 'vector', 'matrix'}:
            raise ValueError('Unsupported scientific control type')
        if control['minimum'] is not None and control['maximum'] is not None and control['minimum'] > control['maximum']:
            raise ValueError('Control bounds are reversed')
        if control['step'] is not None and (not math.isfinite(control['step']) or control['step'] <= 0):
            raise ValueError('Control step must be positive and finite')
        if not control['learning_purpose'] or not control['effect_targets']:
            raise ValueError('Controls require scientific purpose and effects')
        initial[variable] = control['default']
    if set(initial) - set(ids):
        raise ValueError('Initial state contains unknown variables')
    computations = []
    produced: set[str] = set()
    for computation in data['computations']:
        tree = (asts or {}).get(computation['id'], computation['metadata'].get('ast'))
        if tree is None and native:
            metadata = dict(computation['metadata'])
            metadata['bindings'] = {k: aliases.get(v, v) for k, v in metadata.get('bindings', {}).items()}
            tree = {'type': 'Canonical', 'metadata': metadata, 'output_type': computation['output_type']}
        if tree is None:
            raise ValueError('Validated canonical AST is required; the renderer does not interpret DSL')
        reads = validate_ast(tree)
        outputs = computation['output_refs']
        if not outputs or len(outputs) != len(set(outputs)) or any(o not in ids or o in produced or o in initial for o in outputs):
            raise ValueError('Each computation must uniquely produce declared variables')
        if not native and set(computation['input_refs']) != reads:
            raise ValueError('Declared input refs must match canonical AST reads')
        produced.update(outputs)
        computations.append({**computation, 'input_refs': sorted(reads), 'ast': tree, 'reads': sorted(reads)})
    ordered = computation_order(computations, set(initial))
    invariant_programs = []
    if native:
        from playground.computation.parser import parse
        bindings = {k: aliases.get(v, v) for k, v in data['metadata'].get('invariant_bindings', {}).items()}
        for expression in scientific['invariants']:
            node = parse(expression)
            program = {'type': 'Canonical', 'output_type': 'boolean', 'metadata': {
                'kind': 'expression', 'canonical_ast': node.to_dict(),
                'bindings': {k: bindings[k] for k in node.references}, 'ast_version': 1}}
            validate_ast(program)
            invariant_programs.append(program)
        for visual in data['visuals']:
            for computation in ordered:
                if set(visual['data_refs']) & set(computation['output_refs']) and computation['metadata'].get('kind') in {'iteration', 'state_transition'}:
                    visual['metadata']['history_ref'] = computation['id']
                    if computation['metadata'].get('kind') == 'state_transition':
                        visual['metadata'].setdefault('nodes', [{'id': s, 'label': s} for s in computation['metadata']['states']])
                        visual['metadata'].setdefault('edges', [{'from': t['from'], 'to': t['to']} for t in computation['metadata']['transitions']])
                    break
    if set(ids) != set(initial) | produced:
        raise ValueError('All variables require initial or computed values')
    unique_ids = [c['id'] for c in computations] + [c['id'] for c in controls]
    unique_ids += [v['id'] for v in data['visuals']] + [e['id'] for e in lesson['guided_explorations']]
    if len(unique_ids) != len(set(unique_ids)) or any(not i or i in FORBIDDEN_IDS for i in unique_ids):
        raise ValueError('Runtime IDs must be unique and safe')
    if not data['visuals'] or not data['focus_coverage'] or not data['grounding_records']:
        raise ValueError('Visual, focus coverage and grounding are required')
    for visual in data['visuals']:
        if not visual['question'] or not visual['data_refs'] or set(visual['data_refs']) - set(ids):
            raise ValueError('Visuals require a scientific question and resolvable data')
    if set(lesson['important_intermediates']) - set(ids):
        raise ValueError('Unknown important intermediate')
    control_ids = {c['id']: c['scientific_variable'] for c in controls}
    for exploration in lesson['guided_explorations']:
        if not all(exploration[k] for k in ('change', 'observe', 'why', 'setup')):
            raise ValueError('Incomplete guided exploration')
        setup = {}
        for key, value in exploration['setup'].items():
            variable = control_ids.get(key, key)
            if variable not in controlled or variable in setup:
                raise ValueError('Preset must assign known controls once')
            setup[variable] = value
        exploration['runtime_setup'] = setup
    manifest = {
        **data, 'generator_version': GENERATOR_VERSION, 'config_version': CONFIG_VERSION,
        'numeric_tolerance': NUMERIC_TOLERANCE, 'concept': scientific['concept'],
        'mechanism_family': family, 'variables': variables, 'controls': controls,
        'computations': ordered, 'dependencies': {c['id']: c['reads'] for c in ordered},
        'outputs': sorted(produced), 'visuals': [plan_visual(v, family) for v in data['visuals']],
        'explorations': lesson['guided_explorations'], 'initial_state': initial,
        'source_references': scientific['provenance'],
        'knowledge_classes': sorted({r['knowledge_class'] for r in data['grounding_records']}),
        'simplifications': [r for r in data['grounding_records'] if r['knowledge_class'] == 'PEDAGOGICAL'],
        'limitations': scientific['limitations'], 'canonical_runtime': native,
        'invariant_programs': invariant_programs,
    }
    # Roundtrip removes tuples/Enums and rejects nonfinite/unsupported metadata.
    return json.loads(safe_json(manifest))
