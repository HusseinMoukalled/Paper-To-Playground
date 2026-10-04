"""Known input-policy transformations, without altering paper mathematics."""
from dataclasses import replace
import re
from playground.computation.validate import control_value
from playground.ir.grounding import learner_claims
from playground.ir.models import KnowledgeClass


def normalize_wire_conventions(ir):
    """Resolve unambiguous symbol keys and known claim-path spellings only."""
    control_types = {'vector_editor':'vector','matrix_editor':'matrix','range':'slider'}
    ir = replace(ir,lesson_spec=replace(ir.lesson_spec,controls=tuple(
        replace(c,control_type=control_types.get(c.control_type,c.control_type)) for c in ir.lesson_spec.controls)))
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
    control_aliases = {}
    for control in ir.lesson_spec.controls:
        names = {control.id,control.scientific_variable}
        names.update(name for name,refs in aliases.items() if refs == {control.scientific_variable})
        for name in names:
            control_aliases.setdefault(name,set()).add(control.id)
    explorations = []
    for exploration in candidate.lesson_spec.guided_explorations:
        setup = {}
        for name,value in exploration.setup.items():
            key = next(iter(control_aliases[name])) if name in control_aliases and len(control_aliases[name]) == 1 else name
            if key in setup:
                return ir,0
            setup[key] = value
        explorations.append(replace(exploration,setup=setup))
    candidate = replace(candidate,lesson_spec=replace(candidate.lesson_spec,guided_explorations=tuple(explorations)))
    claims = learner_claims(candidate)
    used = set()
    records = []
    changes = sum(key not in ir.lesson_spec.symbol_explanations for key in symbols)
    changes += sum(a.setup != b.setup for a,b in zip(ir.lesson_spec.guided_explorations,explorations))
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
    # Invariants use the same scientific aliases as computations. Resolve only
    # uniquely declared names; never guess an ambiguous mathematical binding.
    from playground.computation.parser import parse, IDENTIFIER
    metadata = dict(candidate.metadata)
    bindings = metadata.get('invariant_bindings', {})
    if isinstance(bindings, dict):
        valid_bindings = {key: value for key, value in bindings.items() if IDENTIFIER.fullmatch(key)}
        changes += len(bindings) - len(valid_bindings)
        for expression in candidate.scientific_model.invariants:
            try:
                names = parse(expression).references
            except ValueError:
                continue  # The scientific validator reports invalid predicates.
            for name in names - valid_bindings.keys():
                if name in aliases and len(aliases[name]) == 1:
                    valid_bindings[name] = next(iter(aliases[name]))
                    changes += 1
        metadata['invariant_bindings'] = valid_bindings
    return replace(candidate,grounding_records=tuple(records),metadata=metadata),changes


def reconcile_equation_links(ir):
    """Drop equation links whose AST does not match. Do not rewrite expressions.

    Unlinked scientific equations stay visible as explicit context, which is the
    contract for a paper formula the demonstration does not execute directly.
    """
    from playground.computation.evaluator import compile_computations
    from playground.computation.science import check_equation_consistency, link_matches
    try:
        check_equation_consistency(compile_computations(ir))
        return ir, 0
    except (ValueError, KeyError, TypeError):
        pass
    variables = {v.id: v for v in ir.scientific_model.variables}
    equations = {q.id: q for q in ir.scientific_model.equations}
    computations = []
    linked = set()
    changes = 0
    for spec in ir.computations:
        refs = spec.metadata.get("equation_refs", [])
        original = list(refs) if isinstance(refs, list) else []
        kept = []
        if isinstance(refs, list) and spec.metadata.get("kind", "expression") == "expression":
            for ref in refs:
                if ref in equations and link_matches(spec, equations[ref], variables):
                    kept.append(ref)
                    linked.add(ref)
        if kept != original:
            changes += 1
        meta = {**spec.metadata, "equation_refs": kept}
        computations.append(replace(spec, metadata=meta))
    scope = ir.metadata.get("equation_scope")
    scope = dict(scope) if isinstance(scope, dict) else {}
    new_scope = {key: "context_only" for key in equations if key not in linked}
    if new_scope != scope:
        changes += 1
    candidate = replace(ir, computations=tuple(computations), metadata={**ir.metadata, "equation_scope": new_scope})
    try:
        check_equation_consistency(compile_computations(candidate))
    except (ValueError, KeyError, TypeError):
        return ir, 0
    return candidate, changes


def declare_used_knowledge_classes(ir):
    """Record classes already present on claims and objects. Do not invent a class."""
    existing = ir.scientific_model.knowledge_classes
    used = set(existing)
    for record in ir.grounding_records:
        used.add(record.knowledge_class)
    for collection in (ir.scientific_model.variables, ir.scientific_model.equations, ir.scientific_model.relationships):
        for item in collection:
            used.add(item.knowledge_class)
    added = tuple(kind for kind in KnowledgeClass if kind in used and kind not in existing)
    if not added:
        return ir, 0
    return replace(ir, scientific_model=replace(ir.scientific_model, knowledge_classes=existing + added)), len(added)


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
