"""Lossless formatting recovery before lowering to the strict shared contracts."""
import copy
from playground.computation.parser import parse


def lower_wire(value, evidence):
    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    if isinstance(result.get('status'), str) and result['status'] in {'ok', 'supported', 'success'}:
        result.pop('status')  # Harmless success envelope, not a scientific verdict.
    science, lesson = result.get('scientific_model'), result.get('lesson_spec')
    if not isinstance(science, dict) or not isinstance(lesson, dict):
        return result
    variables = science.get('variables', [])
    if not isinstance(variables, list):
        return result
    aliases, duplicate = {}, set()
    for variable in variables:
        if not isinstance(variable, dict): continue
        for key in (variable.get('id'), variable.get('source_symbol'), variable.get('display_symbol')):
            if not isinstance(key, str) or not key: continue
            if key in aliases and aliases[key] != variable.get('id'): duplicate.add(key)
            aliases[key] = variable.get('id')
    for key in duplicate: aliases.pop(key, None)
    def rekey(mapping):
        if not isinstance(mapping, dict): return mapping
        converted = {}
        for key, item in mapping.items():
            target = aliases.get(key,key)
            if target in converted: raise ValueError('Ambiguous symbol-keyed metadata')
            converted[target] = item
        return converted
    if 'symbol_explanations' in lesson:
        lesson['symbol_explanations'] = rekey(lesson['symbol_explanations'])
    metadata = result.get('metadata')
    if isinstance(metadata, dict):
        metadata.setdefault('audience', evidence.audience)
        if 'defaults' in metadata: metadata['defaults'] = rekey(metadata['defaults'])
    computations = result.get('computations', [])
    if not isinstance(computations, list):
        return result
    for computation in computations:
        if not isinstance(computation, dict): continue
        meta = computation.get('metadata', {})
        if isinstance(meta, dict) and meta.get('kind','expression') == 'expression' and isinstance(meta.get('bindings'), dict):
            # Unused bindings have no executable effect. Do not invent missing ones.
            try: reads = parse(computation.get('expression')).references
            except (ValueError, TypeError): continue
            meta['bindings'] = {k:v for k,v in meta['bindings'].items() if k in reads}
    return result
