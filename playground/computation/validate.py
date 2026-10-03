"""Control validation and representative-state scientific execution gate."""
from __future__ import annotations

from playground.computation.evaluator import execute, ExecutionGuard
from playground.computation.invariants import check_invariants
from playground.computation.operations import validate_value, normalize, approx_equal
from playground.computation.operations import vector, total
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus as S

MAX_TEST_STATES = 128


def control_value(control, value, *, strict=False, scientific_type=None):
    rule = control.validation_rule
    if rule not in {"clamp", "reject", "normalize", "warn"}:
        raise ValueError("Unknown invalid-input behavior")
    if control.control_type not in {"slider", "number", "select", "toggle", "vector", "matrix"}:
        raise ValueError("Unsupported control type")
    if rule == "normalize" and not strict:
        if scientific_type == "distribution":
            value = vector(value)
            if any(x < 0 for x in value) or total(value) <= 0:
                raise ValueError("Cannot normalize invalid probability mass")
            mass = total(value)
            value = [x / mass for x in value]
        else:
            value = normalize(value)
    if control.options and value not in control.options:
        raise ValueError("Unknown categorical option")
    if control.control_type == "toggle" and type(value) is not bool:
        raise ValueError("Toggle requires boolean")
    if control.control_type in {"slider", "number"}:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Numeric control requires a number")
        outside = (control.minimum is not None and value < control.minimum or
                   control.maximum is not None and value > control.maximum)
        if outside:
            if rule == "clamp" and not strict:
                if control.minimum is not None:
                    value = max(value, control.minimum)
                if control.maximum is not None:
                    value = min(value, control.maximum)
            elif rule != "warn" or strict:
                raise ValueError("Control value outside declared range")
    return value


def prepare_inputs(ir, setup=None, *, strict=False):
    """Setup uses control IDs; defaults uses variable IDs. Unknown setup IDs reject."""
    setup = setup or {}
    controls = {c.id: c for c in ir.lesson_spec.controls}
    variables = {v.id: v for v in ir.scientific_model.variables}
    if not set(setup) <= controls.keys():
        raise ValueError("Preset references unknown control")
    inputs = dict(ir.metadata.get("defaults", {}))
    for control in controls.values():
        if control.scientific_variable not in variables:
            raise ValueError("Control references unknown scientific variable")
        inputs[control.scientific_variable] = control_value(
            control, setup.get(control.id, control.default), strict=strict,
            scientific_type=variables[control.scientific_variable].type)
    for key, value in inputs.items():
        if key not in variables:
            raise ValueError("Default references unknown variable")
        var = variables[key]
        validate_value(value, var.type, var.shape, var.domain)
    return inputs


def representative_states(ir):
    states = [("default", {})]
    for c in ir.lesson_spec.controls:
        if c.minimum is not None:
            states.append((c.id + ":minimum", {c.id: c.minimum}))
        if c.maximum is not None:
            states.append((c.id + ":maximum", {c.id: c.maximum}))
        if c.minimum is not None and c.maximum is not None:
            middle = (c.minimum + c.maximum) / 2
            var = next(v for v in ir.scientific_model.variables if v.id == c.scientific_variable)
            if var.domain == "integer":
                middle = round(middle)
            states.append((c.id + ":interior", {c.id: middle}))
        for option in c.options:
            states.append((c.id + ":option", {c.id: option}))
        if c.control_type == "toggle":
            states.extend([(c.id + ":false", {c.id: False}), (c.id + ":true", {c.id: True})])
    states.extend((e.id, e.setup) for e in ir.lesson_spec.guided_explorations)
    if len(states) > MAX_TEST_STATES:
        raise ValueError("Representative-state limit exceeded")
    return states


def validate_computation(ir, *, budget=None):
    findings = []
    results = {}
    guard = ExecutionGuard(budget=budget)
    for label, setup in representative_states(ir):
        guard.check()
        try:
            values, history = execute(ir, prepare_inputs(ir, setup, strict=True), guard=guard)
            failed = [expr for expr, passed in check_invariants(ir, values, guard=guard) if not passed]
            if failed:
                raise ValueError("Scientific invariant failed")
            # Declarative history is validated too, not just the last step.
            for records in history.values():
                from playground.computation.operations import finite
                for state in records:
                    if isinstance(state, dict):
                        for value in state.values():
                            finite(value)
                    else:
                        finite(state)
            results[label] = values
        except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError) as error:
            findings.append(ValidationFinding(S.FAIL, "COMPUTATION_STATE_INVALID", "computation",
                                              str(error), target=label))
    baseline = results.get("default")
    if baseline:
        for control in ir.lesson_spec.controls:
            variants = [v for label, v in results.items() if label.startswith(control.id + ":")]
            # Array controls can declare test_values in metadata without model-generated code.
            for value in ir.metadata.get("control_test_values", {}).get(control.id, []):
                try:
                    tested, _ = execute(ir, prepare_inputs(ir, {control.id: value}, strict=True), guard=guard)
                    if not all(passed for _, passed in check_invariants(ir, tested, guard=guard)):
                        raise ValueError("Control test invariant failed")
                    variants.append(tested)
                except (ValueError, TypeError, KeyError, ZeroDivisionError, OverflowError):
                    findings.append(ValidationFinding(S.FAIL, "CONTROL_TEST_INVALID", "computation",
                                                      "Declared control test failed", control.id))
            if not variants:
                findings.append(ValidationFinding(S.FAIL, "CONTROL_UNTESTED", "computation",
                                                  "Control requires representative test values", control.id))
                continue
            def different(a, b):
                if isinstance(a, (str, bool)) or isinstance(b, (str, bool)):
                    return a != b
                return not approx_equal(a, b)
            if not any(any(t in value and t in baseline and different(value[t], baseline[t])
                           for t in control.effect_targets) for value in variants):
                findings.append(ValidationFinding(S.FAIL, "DEAD_CONTROL", "computation",
                                                  "Control has no observed declared scientific effect", control.id))
        # Distinct preset inputs are insufficient if the scientific outputs never differ.
        if len(ir.lesson_spec.guided_explorations) >= 2:
            first, second = ir.lesson_spec.guided_explorations[:2]
            a, b = results.get(first.id), results.get(second.id)
            targets = {ref for visual in ir.visuals for ref in visual.data_refs}
            if a and b and not any(t in a and t in b and different(a[t], b[t]) for t in targets):
                findings.append(ValidationFinding(S.FAIL, "EXPLORATION_CONTRAST_UNOBSERVABLE", "computation",
                                                  "Exploration presets have identical observable science"))
    return ValidationReport(S.FAIL if findings else S.PASS, tuple(findings), "computation")
