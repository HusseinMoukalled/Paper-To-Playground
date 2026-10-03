"""Progressive schema/reference/science/grounding/pedagogy/computation gates."""
from __future__ import annotations

from playground.ir.serialization import decode, to_mapping
from playground.ir.models import ExplanationIR
from playground.ir.grounding import validate_grounding
from playground.ir.coverage import validate_coverage
from playground.computation.evaluator import compile_computations, computation_references
from playground.computation.operations import TYPES, DOMAINS
from playground.computation.science import check_equation_consistency
from playground.computation.validate import prepare_inputs, validate_computation
from playground.validation.report import ValidationFinding, ValidationReport, ValidationStatus as S
from playground.ids import IR_ID_PREFIXES
import re

MAX_IR_OBJECTS = 128


def validate_ir(ir, evidence, *, execute_science=True, budget=None):
    if budget and budget.remaining_seconds <= budget.finalization_reserve_seconds:
        budget._raise_budget_failure("IR validation reached the finalization window.")
    findings = []
    def fail(code, stage, message, target=None):
        findings.append(ValidationFinding(S.FAIL, code, stage, message, target))
    def report():
        status = S.FAIL if any(f.status == S.FAIL for f in findings) else S.WARN if findings else S.PASS
        return ValidationReport(status, tuple(findings), "ir")
    try:
        decode(ExplanationIR, to_mapping(ir))
    except (ValueError, TypeError):
        fail("IR_SCHEMA_INVALID", "schema", "Shared ExplanationIR schema validation failed")
        return report()
    for name in ("defaults", "invariant_bindings", "control_test_values", "equation_scope"):
        if name in ir.metadata and not isinstance(ir.metadata[name], dict):
            fail("IR_METADATA_INVALID", "schema", "Known IR metadata field must be an object", name)
    if "invariant_bindings" in ir.metadata and isinstance(ir.metadata["invariant_bindings"], dict):
        if not all(isinstance(k, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", k) and isinstance(v, str) for k, v in ir.metadata["invariant_bindings"].items()):
            fail("IR_METADATA_INVALID", "schema", "Invariant bindings must map safe symbols to stable IDs")
    if "control_test_values" in ir.metadata and isinstance(ir.metadata["control_test_values"], dict):
        if not all(isinstance(value, list) and len(value) <= 16 for value in ir.metadata["control_test_values"].values()):
            fail("IR_METADATA_INVALID", "schema", "Control test values must be bounded arrays")
    if findings:
        return report()
    science, lesson = ir.scientific_model, ir.lesson_spec
    groups = (science.variables, science.equations, science.relationships, science.mechanism_steps,
              lesson.controls, lesson.guided_explorations, ir.computations, ir.visuals)
    ids = [x.id for group in groups for x in group]
    if len(ids) != len(set(ids)) or any(not x or len(x) > 100 for x in ids):
        fail("IR_IDS_INVALID", "references", "IDs must be stable, nonempty and globally unique")
    kinds = ("variable", "equation", "relationship", "mechanism_step", "control", "exploration", "computation", "visual")
    for kind, group in zip(kinds, groups):
        for item in group:
            if not item.id.startswith(IR_ID_PREFIXES[kind]) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,99}", item.id):
                fail("IR_ID_PREFIX_INVALID", "references", "Object ID must use the shared stable prefix", item.id)
    if len(ids) > MAX_IR_OBJECTS:
        fail("IR_SIZE_INVALID", "references", "IR exceeds bounded runtime capacity")
        return report()
    variables = {v.id: v for v in science.variables}
    equations = {q.id for q in science.equations}
    computation_ids = {c.id for c in ir.computations}
    def refs(values, valid, target):
        if len(values) != len(set(values)):
            fail("IR_REFERENCE_DUPLICATE", "references", "References must not contain duplicates", target)
        if not set(values) <= set(valid):
            fail("IR_REFERENCE_INVALID", "references", "Reference does not resolve", target)
    for variable in science.variables:
        if variable.type not in TYPES or variable.domain not in DOMAINS:
            fail("SCIENTIFIC_TYPE_INVALID", "science", "Unsupported type/domain; narrow unsupported mechanism explicitly", variable.id)
        if any(type(x) is int and x <= 0 or type(x) not in {int, str} for x in variable.shape):
            fail("SCIENTIFIC_SHAPE_INVALID", "science", "Shape dimensions must be positive or symbolic", variable.id)
        if len(variable.shape) > 2 or any(isinstance(x, str) and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", x) for x in variable.shape):
            fail("SCIENTIFIC_SHAPE_INVALID", "science", "Symbolic dimensions must be safe identifiers and rank <=2", variable.id)
        expected_rank = {"scalar": 0, "boolean": 0, "categorical": 0, "state": 0, "vector": 1, "matrix": 2, "distribution": 1}
        if variable.shape and variable.type in expected_rank and len(variable.shape) != expected_rank[variable.type]:
            fail("SCIENTIFIC_SHAPE_INVALID", "science", "Type and declared shape rank disagree", variable.id)
        if not variable.meaning or not variable.display_symbol:
            fail("VARIABLE_INCOMPLETE", "science", "Variable meaning and display symbol required", variable.id)
    for equation in science.equations:
        refs(equation.variable_refs, variables, equation.id)
        if not equation.expression or not equation.meaning:
            fail("EQUATION_INCOMPLETE", "science", "Equation expression and meaning required", equation.id)
    for relation in science.relationships + science.mechanism_steps:
        # An abstract mechanism step may read and update the same state. Only
        # repetitions within each reference list are duplicates.
        refs(relation.input_refs, variables, relation.id)
        refs(relation.output_refs, variables, relation.id)
        refs(relation.equation_refs, equations, relation.id)
    if len({s.order for s in science.mechanism_steps}) != len(science.mechanism_steps):
        fail("MECHANISM_ORDER_INVALID", "science", "Mechanism step order must be unique")
    for field in ("concept", "purpose", "focus_alignment", "demonstration_scope"):
        if not getattr(science, field).strip():
            fail("SCIENCE_INCOMPLETE", "science", "Required scientific field missing", field)
    if not science.variables or not (science.equations or science.relationships or science.mechanism_steps):
        fail("MECHANISM_MISSING", "science", "Executable science requires variables and mechanism")
    if not science.limitations or not science.knowledge_classes:
        fail("SCIENCE_INCOMPLETE", "science", "Limitations and knowledge classes required")
    findings.extend(validate_grounding(ir, evidence))
    for field in ("central_learning_question", "intuition", "visual_question", "visual_intent",
                  "limitation_or_assumption", "misconception"):
        if not getattr(lesson, field).strip():
            fail("PEDAGOGY_INCOMPLETE", "pedagogy", "Required lesson field missing", field)
    for field in ("learning_objectives", "audience_prerequisites", "teaching_sequence",
                  "important_intermediates", "source_grounding_plan"):
        if not getattr(lesson, field):
            fail("PEDAGOGY_INCOMPLETE", "pedagogy", "Required teaching sequence/content missing", field)
    if ir.metadata.get("audience") != evidence.audience or not ir.metadata.get("audience_adaptation"):
        fail("AUDIENCE_ADAPTATION_MISSING", "pedagogy", "Audience and explicit adaptation rationale required")
    if set(variables) - set(lesson.symbol_explanations):
        fail("SYMBOL_EXPLANATION_MISSING", "pedagogy", "Every scientific variable needs a symbol explanation")
    refs(lesson.symbol_explanations, variables, "symbol_explanations")
    refs(lesson.important_intermediates, variables.keys() | computation_ids, "important_intermediates")
    if len(lesson.controls) < 2:
        fail("CONTROLS_MISSING", "pedagogy", "At least two meaningful controls required")
    if len({c.scientific_variable for c in lesson.controls}) != len(lesson.controls):
        fail("CONTROL_VARIABLE_DUPLICATE", "pedagogy", "Each control must own a distinct scientific input")
    for control in lesson.controls:
        refs((control.scientific_variable,), variables, control.id)
        refs(control.effect_targets, variables.keys() | computation_ids, control.id)
        if not all((control.label, control.learning_purpose, control.safe_range_reason, control.effect_targets)):
            fail("CONTROL_INCOMPLETE", "pedagogy", "Control needs purpose, safe-range rationale and effects", control.id)
        if control.minimum is not None and control.maximum is not None and control.minimum >= control.maximum:
            fail("CONTROL_RANGE_INVALID", "pedagogy", "Control range must increase", control.id)
        if control.control_type in {"slider", "number"} and (control.minimum is None or control.maximum is None):
            fail("CONTROL_RANGE_MISSING", "pedagogy", "Numeric controls require bounded ranges", control.id)
        if control.control_type == "select" and not control.options:
            fail("CONTROL_OPTIONS_MISSING", "pedagogy", "Select needs options", control.id)
        if len(control.options) != len(set(control.options)):
            fail("CONTROL_OPTIONS_DUPLICATE", "pedagogy", "Control options must be unique", control.id)
        if control.step is not None and control.step <= 0:
            fail("CONTROL_STEP_INVALID", "pedagogy", "Control step must be positive", control.id)
        if control.scientific_variable in variables and control.units != variables[control.scientific_variable].units:
            fail("CONTROL_UNITS_INVALID", "science", "Control units must match its scientific variable", control.id)
    if len(lesson.guided_explorations) < 2:
        fail("EXPLORATIONS_MISSING", "pedagogy", "Two explorations required")
    for exploration in lesson.guided_explorations:
        if not all((exploration.title, exploration.change, exploration.observe, exploration.why, exploration.setup)):
            fail("EXPLORATION_INCOMPLETE", "pedagogy", "Exploration needs change/observe/why and Apply Setup", exploration.id)
        try:
            prepare_inputs(ir, exploration.setup, strict=True)
        except (ValueError, KeyError, TypeError):
            fail("PRESET_INVALID", "pedagogy", "Exploration preset invalid", exploration.id)
    if len(lesson.guided_explorations) >= 2 and lesson.guided_explorations[0].setup == lesson.guided_explorations[1].setup:
        fail("EXPLORATION_CONTRAST_MISSING", "pedagogy", "Explorations must configure a meaningful contrast")
    if not ir.visuals:
        fail("VISUAL_MISSING", "pedagogy", "Visual intent requires a configured visual")
    for visual in ir.visuals:
        refs(visual.data_refs, variables.keys() | computation_ids, visual.id)
        if not visual.question or not visual.data_refs:
            fail("VISUAL_INCOMPLETE", "pedagogy", "Visual needs question and scientific data", visual.id)
    findings.extend(validate_coverage(ir, evidence))
    if any(f.status == S.FAIL for f in findings):
        return report()
    try:
        compiled = compile_computations(ir)
        output_owners = {}
        for spec in compiled.computations:
            refs(spec.input_refs + spec.output_refs, variables, spec.id)
            refs(spec.dependencies, computation_ids, spec.id)
            bindings = spec.metadata.get("bindings", {})
            if set(bindings) != computation_references(spec):
                fail("COMPUTATION_BINDINGS_INVALID", "computation", "DSL symbol bindings do not match expression", spec.id)
            refs(bindings.values(), variables.keys() | computation_ids, spec.id)
            if set(bindings.values()) - (set(spec.input_refs) | set(spec.dependencies)):
                fail("COMPUTATION_INPUTS_INVALID", "computation", "Binding inputs must be declared input_refs/dependencies", spec.id)
            for output in spec.output_refs:
                if output in output_owners or output in {c.scientific_variable for c in lesson.controls}:
                    fail("OUTPUT_OWNER_INVALID", "computation", "Output has multiple owners or overwrites a control", output)
                output_owners[output] = spec.id
        # A variable bound from another computation must declare the producing DAG edge.
        for spec in compiled.computations:
            for value in spec.metadata.get("bindings", {}).values():
                if value in output_owners and output_owners[value] not in spec.dependencies:
                    fail("COMPUTATION_DEPENDENCY_MISSING", "computation", "Derived variable requires producer dependency", spec.id)
        try:
            check_equation_consistency(compiled)
        except (ValueError, KeyError, TypeError):
            fail("EQUATION_COMPUTATION_MISMATCH", "science", "Equation/executable linkage cannot be deterministically verified")
        if execute_science and not any(f.status == S.FAIL for f in findings):
            findings.extend(validate_computation(compiled, budget=budget).findings)
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        fail("COMPUTATION_INVALID", "computation", "Computation compilation or validation failed")
    return report()
