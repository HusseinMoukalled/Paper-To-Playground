"""Machine-checkable focus path. Objective refs are exact objective strings."""
from playground.validation.report import ValidationFinding, ValidationStatus as S


def validate_coverage(ir, evidence):
    findings = []
    def fail(message):
        findings.append(ValidationFinding(S.FAIL, "FOCUS_COVERAGE_INVALID", "coverage", message))
    coverage = ir.focus_coverage
    if coverage is None:
        fail("Missing focus coverage map")
        return findings
    if coverage.focus != evidence.focus:
        fail("Focus changed from the supplied EvidencePack")
    science, lesson = ir.scientific_model, ir.lesson_spec
    sets = {
        "learning_objective_refs": set(lesson.learning_objectives),
        "mechanism_refs": {x.id for x in science.mechanism_steps} | {x.id for x in science.relationships} | {x.id for x in science.equations},
        "control_refs": {x.id for x in lesson.controls},
        "computation_refs": {x.id for x in ir.computations},
        "visual_refs": {x.id for x in ir.visuals},
        "exploration_refs": {x.id for x in lesson.guided_explorations},
    }
    for field, valid in sets.items():
        refs = getattr(coverage, field)
        if not refs or len(refs) != len(set(refs)) or not set(refs) <= valid:
            fail("Missing or invalid " + field)
    controls = {c.id: c for c in lesson.controls}
    computations = {c.id: c for c in ir.computations}
    selected = set(coverage.computation_refs)
    # Traverse the variable/computation DAG without interpreting arbitrary code.
    def downstream(start):
        reached = {start}
        for _ in range(len(ir.computations) + 1):
            old = set(reached)
            for computation in ir.computations:
                if reached.intersection(computation.input_refs + computation.dependencies):
                    reached.add(computation.id)
                    reached.update(computation.output_refs)
            if reached == old:
                break
        return reached
    for cid in coverage.control_refs:
        if cid not in controls:
            continue
        var = controls[cid].scientific_variable
        if not downstream(var).intersection(selected):
            fail("Covered control is disconnected from covered computation")
    observed = {ref for visual in ir.visuals for ref in visual.data_refs}
    for control in lesson.controls:
        reached = downstream(control.scientific_variable)
        if not observed.intersection(reached) or not set(control.effect_targets) <= reached:
            fail("Control lacks a dependency path to declared effects and visible scientific output")
    produced = selected | {v for c in ir.computations if c.id in selected for v in c.output_refs}
    mechanisms = {x.id: x for collection in (science.equations, science.relationships, science.mechanism_steps) for x in collection}
    computed_variables = {v for c in ir.computations if c.id in selected for v in c.input_refs + c.output_refs}
    for ref in coverage.mechanism_refs:
        if ref in mechanisms:
            mechanism = mechanisms[ref]
            involved = getattr(mechanism, "variable_refs", ()) or getattr(mechanism, "input_refs", ()) + getattr(mechanism, "output_refs", ())
            if not set(involved).intersection(computed_variables):
                fail("Covered mechanism is disconnected from scientific computations")
    for visual in ir.visuals:
        if visual.id in coverage.visual_refs and not produced.intersection(visual.data_refs):
            fail("Covered visual is disconnected from computation")
    for exploration in lesson.guided_explorations:
        if exploration.id in coverage.exploration_refs and not set(exploration.setup).intersection(coverage.control_refs):
            fail("Covered exploration does not configure a covered control")
    return findings
