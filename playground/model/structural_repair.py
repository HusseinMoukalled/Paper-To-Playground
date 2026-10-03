"""Known input-policy transformations, without altering paper mathematics."""
from dataclasses import replace
import re
from playground.computation.validate import control_value
from playground.ir.grounding import learner_claims


def normalize_wire_conventions(ir):
    """Resolve unambiguous symbol keys and known claim-path spellings only."""
    aliases = {}
    for variable in ir.scientific_model.variables:
        for name in (variable.id,variable.source_symbol,variable.display_symbol):
            if name:
                aliases.setdefault(name,set()).add(variable.id)
    for c in ir.computations:
        for name,ref in c.metadata.get('bindings',{}).items():
            if any(v.id == ref for v in ir.scientific_model.variables):
                aliases.setdefault(name,set()).add(ref)
    symbols = {}
    for key,text in ir.lesson_spec.symbol_explanations.items():
        resolved = next(iter(aliases[key])) if key in aliases and len(aliases[key]) == 1 else key
        if resolved in symbols:
            return ir,0  # Ambiguous merging is never a safe transformation.
        symbols[resolved] = text
    candidate = replace(ir,lesson_spec=replace(ir.lesson_spec,symbol_explanations=symbols))
    claims = learner_claims(candidate)
    used = set()
    records = []
    changes = sum(key not in ir.lesson_spec.symbol_explanations for key in symbols)
    for record in ir.grounding_records:
        key = record.claim_id.replace('scientific_model.','science.').replace('lesson_spec.','lesson.')
        key = re.sub(r'\.i(\d+)(?=\.|$)',r'.\1',key)
        key = re.sub(r'\[(\d+)\]',r'.\1',key)
        if key.startswith('symbol.'):
            name = key[7:]
            if name in aliases and len(aliases[name]) == 1:
                key = 'symbol.'+next(iter(aliases[name]))
        for suffix in ('.meaning','.description'):
            if key.endswith(suffix) and key[:-len(suffix)] in claims:
                key = key[:-len(suffix)]
        if key not in claims:
            matches = [name for name,text in claims.items() if text == record.claim]
            if len(matches) == 1:
                key = matches[0]
        if key in used:
            return ir,0
        used.add(key)
        changes += key != record.claim_id
        records.append(replace(record,claim_id=key))
    return replace(candidate,grounding_records=tuple(records)),changes


def normalize_declared_inputs(ir):
    variables = {v.id:v for v in ir.scientific_model.variables}
    changes = 0
    def fix(control,value):
        nonlocal changes
        if control.validation_rule not in {'normalize','clamp'} or control.scientific_variable not in variables:
            return value
        try:
            corrected = control_value(control,value,scientific_type=variables[control.scientific_variable].type)
        except (ValueError,TypeError,OverflowError,ZeroDivisionError):
            return value
        if corrected != value:
            changes += 1
        return corrected
    controls = tuple(replace(c,default=fix(c,c.default)) for c in ir.lesson_spec.controls)
    fixed = tuple(c for c in controls if c.control_type in {'slider','number'} and c.minimum is not None
                  and c.minimum == c.maximum == c.default)
    removed = set()
    if fixed and len(controls)-len(fixed) >= 2:
        removed = {c.id for c in fixed}
        controls = tuple(c for c in controls if c.id not in removed)
        changes += len(fixed)
    by_id = {c.id:c for c in controls}
    explorations = tuple(replace(e,setup={key:fix(by_id[key],value) if key in by_id else value
                                        for key,value in e.setup.items() if key not in removed}) for e in ir.lesson_spec.guided_explorations)
    metadata = dict(ir.metadata)
    if removed:
        metadata['defaults'] = {**metadata.get('defaults',{}), **{c.scientific_variable:c.default for c in fixed}}
    if isinstance(metadata.get('control_test_values'),dict):
        metadata['control_test_values'] = {key:[fix(by_id[key],v) for v in values] if key in by_id and isinstance(values,list) else values
                                          for key,values in metadata['control_test_values'].items()}
    coverage = replace(ir.focus_coverage,control_refs=tuple(c for c in ir.focus_coverage.control_refs if c not in removed)) if removed and ir.focus_coverage else ir.focus_coverage
    records = tuple(r for r in ir.grounding_records if not any(r.claim_id.startswith(c+'.') for c in removed))
    return replace(ir,lesson_spec=replace(ir.lesson_spec,controls=controls,guided_explorations=explorations),
                   metadata=metadata,focus_coverage=coverage,grounding_records=records),changes
