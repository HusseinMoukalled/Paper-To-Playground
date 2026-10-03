"""Deterministic learner-facing projection; scientific contracts stay intact."""
import math

from playground.computation.evaluator import execute, ExecutionGuard
from playground.computation.invariants import check_invariants
from playground.computation.validate import prepare_inputs


def display_projection(manifest):
    aliases = {c['id']:c['output_refs'][0] if c['output_refs'] else c['id']
               for c in manifest['computations']}
    refs = [r for c in manifest['computations'] for r in (c['output_refs'] or [c['id']])]
    refs += manifest['lesson_spec']['important_intermediates']
    return {'output_aliases':aliases, 'output_refs':list(dict.fromkeys(aliases.get(r,r) for r in refs))}


def plan_sweep(ir, visual, computations, variables):
    """Sample only the existing pure scalar mechanism inside validated controls.

    This is a teaching parameter sweep, never inferred experimental data. Reject
    unsafe domains/invariants instead of inventing a curve or bridging gaps.
    """
    if any(c.metadata.get('kind','expression') != 'expression' for c in ir.computations):
        return None
    by_id = {v['id']:v for v in variables}
    aliases = {c['id']:c['output_refs'][0] if c['output_refs'] else c['id'] for c in computations}
    consumed = {r for c in computations for r in c['reads']}
    refs = list(dict.fromkeys(aliases.get(r,r) for r in visual['data_refs']))
    candidates = [r for r in refs if r not in consumed and by_id[r]['type']=='scalar']
    if not candidates:
        return None
    target = candidates[0]
    for control in ir.lesson_spec.controls:
        if control.control_type not in {'slider','number'} or control.minimum is None or control.maximum is None:
            continue
        lo, hi = control.minimum, control.maximum
        if not math.isfinite(lo) or not math.isfinite(hi) or not math.isfinite(hi-lo) or hi <= lo:
            continue
        reached = {control.scientific_variable}
        for c in computations:
            if reached.intersection(c['reads']):
                reached.update(c['output_refs'])
                reached.add(c['id'])
        if target not in reached:
            continue
        step = control.step
        if step:
            if not math.isfinite((hi-lo)/step):
                continue
            count = math.floor((hi-lo)/step + 1e-8)
            indices = list(dict.fromkeys(round(i*count/min(count,80)) for i in range(min(count,80)+1))) if count else [0]
            values = [lo+i*step for i in indices]
        else:
            values = [lo+(hi-lo)*i/80 for i in range(81)]
        if len(values)<2:
            continue
        variable = by_id[control.scientific_variable]
        if variable['domain']=='integer':
            values = list(dict.fromkeys(round(x) for x in values))
        if len(values)<2 or any(x<lo or x>hi for x in values):
            continue
        if step and any(abs((x-lo)/step-round((x-lo)/step))>1e-7 for x in values):
            continue
        setups = [{}] + [e.setup for e in ir.lesson_spec.guided_explorations]
        for other in ir.lesson_spec.controls:
            if other.id!=control.id and other.control_type in {'slider','number'}:
                setups += [{other.id:x} for x in (other.minimum,other.maximum) if x is not None]
        guard = ExecutionGuard()
        try:
            for setup in setups:
                for value in values:
                    result,_ = execute(ir,prepare_inputs(ir,{**setup,control.id:value},strict=True),guard=guard)
                    if not all(passed for _,passed in check_invariants(ir,result,guard=guard)):
                        raise ValueError('Sweep violates invariant')
            return {'input_ref':control.scientific_variable,'control_id':control.id,
                    'output_ref':target,'sample_values':values,
                    'x_label':control.label,'y_label':by_id[target]['display_symbol']}
        except (ValueError,TypeError,KeyError,ArithmeticError):
            continue
    return None
