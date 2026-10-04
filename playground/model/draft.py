"""A smaller authoring contract; Python owns duplicate text and coverage bookkeeping."""
from copy import deepcopy
from dataclasses import replace

from playground.ir.grounding import learner_claims
from playground.ir.models import ExplanationIR, FocusCoverageMap, GroundingRecord, GroundingStatus, KnowledgeClass
from playground.ir.serialization import decode, json_schema, restore_structural_defaults, schema_contract
from playground.computation.operations import TYPES, DOMAINS


def authoring_schema():
    schema = json_schema(ExplanationIR)
    for field in ('grounding_records', 'focus_coverage'):
        schema['properties'].pop(field)
        schema['required'].remove(field)
    science = schema['properties']['scientific_model']
    science['properties'].pop('knowledge_classes')
    science['required'].remove('knowledge_classes')
    variable = science['properties']['variables']['items']['properties']
    variable['type']['enum'] = sorted(TYPES)
    variable['domain'] = {'anyOf': [{'type': 'null'}, {'type': 'string', 'enum': sorted(d for d in DOMAINS if d)}]}
    controls = schema['properties']['lesson_spec']['properties']['controls']['items']['properties']
    controls['control_type']['enum'] = ['slider', 'number', 'select', 'toggle', 'vector', 'matrix']
    controls['validation_rule']['enum'] = ['clamp', 'reject', 'normalize', 'warn']
    schema['properties']['computations']['items']['properties']['output_type']['enum'] = sorted(TYPES)
    schema['properties']['metadata'] = {'type': 'object', 'properties': {
        'audience_adaptation': {'type': 'string'},
        'defaults': {'type': 'object', 'additionalProperties': {}},
        'invariant_bindings': {'type': 'object', 'additionalProperties': {'type': 'string'}},
        'control_test_values': {'type': 'object', 'additionalProperties': {'type': 'array', 'items': {}}},
        'equation_scope': {'type': 'object', 'additionalProperties': {'type': 'string', 'enum': ['context_only']}},
        'mechanism_family': {'type': 'string', 'enum': ['scalar_relationship', 'distribution', 'matrix_transformation',
            'sequential_algorithm', 'state_transition', 'optimization', 'signal_transformation', 'geometry',
            'information_flow', 'iterative_process', 'comparison', 'dynamical_system']}},
        'required': ['audience_adaptation', 'defaults', 'invariant_bindings', 'control_test_values', 'equation_scope', 'mechanism_family'],
        'additionalProperties': False}
    return schema


def authoring_contract():
    contract = schema_contract(ExplanationIR)
    contract.pop('GroundingRecord')
    contract.pop('FocusCoverageMap')
    for field in ('grounding_records', 'focus_coverage'):
        contract['ExplanationIR'].pop(field)
    contract['ScientificModel'].pop('knowledge_classes')
    return contract


def decode_authoring(value, evidence):
    """Accept old IRs too, but never replace their submitted grounding or coverage."""
    if not isinstance(value, dict):
        raise ValueError('Expected a lesson authoring object')
    if 'grounding_records' in value or 'focus_coverage' in value:
        return decode(ExplanationIR, restore_structural_defaults(ExplanationIR, value)), False
    value = deepcopy(value)
    # Authoring omits only mechanically derived fields, never scientific prose.
    science = value.get('scientific_model')
    if not isinstance(science, dict):
        raise ValueError('Missing scientific_model')
    science['knowledge_classes'] = [kind.value for kind in KnowledgeClass]
    metadata = value.setdefault('metadata', {})
    if not isinstance(metadata, dict):
        raise ValueError('metadata must be an object')
    metadata['audience'] = evidence.audience
    ir = decode(ExplanationIR, restore_structural_defaults(ExplanationIR, value))
    involved = {ref for c in ir.computations for ref in c.input_refs + c.output_refs}
    mechanisms = tuple(x.id for group in (ir.scientific_model.equations, ir.scientific_model.relationships,
                                          ir.scientific_model.mechanism_steps) for x in group
                       if set(getattr(x, 'variable_refs', ()) or
                              getattr(x, 'input_refs', ()) + getattr(x, 'output_refs', ())).intersection(involved))
    coverage = FocusCoverageMap(evidence.focus, ir.lesson_spec.learning_objectives, mechanisms,
                                tuple(c.id for c in ir.lesson_spec.controls), tuple(c.id for c in ir.computations),
                                tuple(v.id for v in ir.visuals), tuple(e.id for e in ir.lesson_spec.guided_explorations))
    ir = replace(ir, focus_coverage=coverage)
    claims = learner_claims(ir)
    records = []
    # An object's explicit source classification/citations can be copied exactly.
    # This establishes lineage, not truth: the semantic review still checks it.
    for group in (ir.scientific_model.variables, ir.scientific_model.equations, ir.scientific_model.relationships):
        for obj in group:
            if obj.knowledge_class != KnowledgeClass.DERIVED:
                records.append(GroundingRecord(obj.id, claims[obj.id], obj.knowledge_class,
                                               GroundingStatus.SUPPORTED, obj.evidence_refs))
    return replace(ir, grounding_records=tuple(records)), True


def as_authoring(ir):
    """Remove compiler artifacts before a bounded model revision."""
    from playground.ir.serialization import to_mapping
    value = to_mapping(ir)
    value.pop('grounding_records')
    value.pop('focus_coverage')
    value['scientific_model'].pop('knowledge_classes')
    for spec in value['computations']:
        for key in ('canonical_ast', 'ast_version', 'initial_ast', 'update_ast', 'state_invariant_ast', 'transition_ast'):
            spec['metadata'].pop(key, None)
    return value
