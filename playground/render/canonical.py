"""Consumer of the science engine's versioned AST, not a second DSL compiler."""
from dataclasses import asdict

from playground.computation.evaluator import compile_computations, computation_references, execute
from playground.computation.operations import shape
from playground.computation.validate import prepare_inputs
from playground.ir.models import ComputationSpec, ExplanationIR
from playground.ir.serialization import decode
from playground.computation.parser import parse


def wire_spec(spec):
    return {"type": "Canonical", "spec": asdict(spec)}


def validate_wire(node):
    if set(node) != {"type", "spec"}:
        raise ValueError("Invalid canonical wire envelope")
    spec = decode(ComputationSpec, node["spec"])
    compiled = compile_computations(ExplanationIR(None, None, (spec,))).computations[0]
    if compiled.metadata != spec.metadata:
        raise ValueError("Canonical trees differ from compiled expressions")
    if spec.metadata.get("ast_version") != 1:
        raise ValueError("Unsupported canonical AST version")
    refs = computation_references(spec)
    bindings = spec.metadata.get("bindings", {})
    if set(bindings) != refs:
        raise ValueError("Canonical binding mismatch")
    return set(bindings.values())


def build_canonical_manifest(ir):
    # Recompilation detects forged serialized ASTs. No source science is rewritten.
    ir = compile_computations(ir)
    data = asdict(ir)
    initial = prepare_inputs(ir, strict=True)
    baseline, _ = execute(ir, initial)
    variables = list(data["scientific_model"]["variables"])
    known = {v["id"] for v in variables}
    # Computation IDs are valid IR visual/intermediate refs, not only variable IDs.
    for spec in ir.computations:
        if spec.id not in known:
            variables.append({"id": spec.id, "display_symbol": spec.id,
                              "source_symbol": None, "meaning": "Executable intermediate: " + spec.expression,
                              "type": spec.output_type, "shape": [],
                              "domain": None, "units": None, "evidence_refs": [], "knowledge_class": "DERIVED"})
    runtime_variables = [dict(v) for v in variables]
    computations = []
    for spec in ir.computations:
        wire = wire_spec(spec)
        computations.append({**asdict(spec), "ast": wire, "reads": sorted(validate_wire(wire))})
    from playground.render.ast_support import computation_order
    from playground.render.visual_planner import plan_visual
    from playground.config import NUMERIC_TOLERANCE
    ordered = computation_order(computations, set(initial))
    controls = data["lesson_spec"]["controls"]
    by_control = {c["id"]: c["scientific_variable"] for c in controls}
    explorations = data["lesson_spec"]["guided_explorations"]
    for exploration in explorations:
        exploration["runtime_setup"] = {by_control[k]: v for k, v in exploration["setup"].items()}
    family = data["metadata"].get("mechanism_family", "scalar_relationship")
    from playground.render.presentation import plan_sweep, display_projection
    visuals = [plan_visual(v,family,runtime_variables) for v in data['visuals']]
    for visual in visuals:
        if visual.get('fallback_reason'):
            sweep = plan_sweep(ir,visual,ordered,runtime_variables)
            if sweep:
                visual.update(component='curve',sweep=sweep,planning_level='validated_parameter_sweep')
                visual.pop('fallback_reason',None)
    manifest = {**data, "generator_version": "scientific-ui-2.0", "config_version": "render-2.0",
            "canonical_ast_version": 1, "numeric_tolerance": NUMERIC_TOLERANCE,
            "concept": ir.scientific_model.concept, "mechanism_family": family,
            "variables": runtime_variables, "controls": controls, "computations": ordered,
            "dependencies": {c["id"]: c["reads"] for c in ordered},
            "outputs": sorted(set(baseline) - set(initial)),
            "visuals": visuals,
            "explorations": explorations, "initial_state": initial,
            "invariants": {"bindings": ir.metadata.get('invariant_bindings', {}),
                           "asts": [parse(text).to_dict() for text in ir.scientific_model.invariants]},
            "source_references": data["scientific_model"]["provenance"],
            "knowledge_classes": sorted({r["knowledge_class"] for r in data["grounding_records"]}),
            "simplifications": [r for r in data["grounding_records"] if r["knowledge_class"] == "PEDAGOGICAL"],
            "limitations": data["scientific_model"]["limitations"]}
    manifest['presentation'] = display_projection(manifest)
    return manifest
