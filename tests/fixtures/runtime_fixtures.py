"""Independent small Python oracles. Production code never imports fixtures."""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

from playground.ir.models import (ComputationSpec, ControlSpec, ExplanationIR, ExplorationSpec, FocusCoverageMap,
                                  GroundingRecord, GroundingStatus, KnowledgeClass, LessonSpec, MechanismStep,
                                  ScientificEquation, ScientificModel, ScientificRelationship, ScientificVariable, VisualSpec)

FIXTURES = Path(__file__).parent


def constant(value):
    return {'type': 'Constant', 'value': value}


def variable(key):
    return {'type': 'Variable', 'id': key}


def binary(op, left, right):
    return {'type': 'Binary', 'op': op, 'left': left, 'right': right}


def call(name, *args):
    return {'type': 'Call', 'function': name, 'args': list(args)}


def vector(*items):
    return {'type': 'Vector', 'items': list(items)}


def matrix(rows):
    return {'type': 'Matrix', 'rows': rows}


def fixture_ir(family='scalar_relationship') -> ExplanationIR:
    x, y = variable('var-x'), variable('var-y')
    product = binary('*', x, y)
    tree = binary('+', variable('var-product'), x)
    expression = 'p + x'
    shape, output_type = (), 'scalar'
    if family == 'distribution':
        tree = call('softmax', vector(x, y, constant(0)))
        expression = 'softmax([x, y, 0])'
        shape, output_type = (3,), 'distribution'
    elif family == 'matrix_transformation':
        tree = matrix([[x, y], [y, variable('var-product')]])
        expression = '[[x, y], [y, p]]'
        shape, output_type = (2, 2), 'matrix'
    elif family in {'signal_transformation', 'optimization', 'dynamical_system', 'iterative_process', 'sequential_algorithm'}:
        tree = vector(x, variable('var-product'), binary('+', x, y), binary('-', x, y))
        expression = '[x, p, x + y, x - y]'
        shape, output_type = (4,), 'sequence'
    elif family == 'geometry':
        tree = matrix([[x, y], [y, variable('var-product')]])
        expression = '[[x, y], [y, p]]'
        shape, output_type = (2, 2), 'matrix'
    elif family == 'state_transition':
        tree = {'type': 'Conditional', 'condition': binary('>', x, y), 'then': constant('active'), 'else': constant('rest')}
        expression = '"active" if x > y else "rest"'
        output_type = 'categorical'
    variables = (
        ScientificVariable('var-x', 'x', 'x', 'First input', 'scalar', evidence_refs=('E001',)),
        ScientificVariable('var-y', 'y', 'y', 'Second input', 'scalar', evidence_refs=('E001',)),
        ScientificVariable('var-product', None, 'p', 'Shared intermediate product', 'scalar', knowledge_class=KnowledgeClass.DERIVED),
        ScientificVariable('var-result', None, 'r', 'Mechanism output', output_type, shape, knowledge_class=KnowledgeClass.DERIVED),
    )
    controls = tuple(ControlSpec('control-' + name, label, 'var-' + name, 'number', default, None, 'reject',
                                 ('var-product', 'var-result'), 'Observe the dependency on this input.',
                                 'Small positive toy inputs.', minimum=.5, maximum=4, step=.5)
                     for name, label, default in [('x', 'First input x', 1), ('y', 'Second input y', 2)])
    computations = (
        ComputationSpec('compute-product', 'x * y', 'scalar', ('var-x', 'var-y'), ('var-product',), metadata={'ast': product}),
        ComputationSpec('compute-result', expression, output_type, tuple(sorted(ast_reads(tree))), ('var-result',), ('compute-product',), {'ast': tree}),
    )
    visual_data = ('var-x', 'var-product', 'var-result') if family == 'information_flow' else ('var-result',)
    metadata = {'nodes': [{'id': 'rest', 'label': 'Rest'}, {'id': 'active', 'label': 'Active'}], 'edges': [{'from': 'rest', 'to': 'active'}]} if family == 'state_transition' else {}
    science = ScientificModel('Fixture ' + family, 'Trace how two inputs change this small mechanism.', 'A controlled mechanism fixture.',
                              variables=variables, mechanism_steps=(MechanismStep('step-product', 0, 'Compute the shared product.'), MechanismStep('step-output', 1, 'Compute the mechanism output.')),
                              limitations=('Toy inputs do not reproduce a full research experiment.',),
                              provenance=('E001: synthetic fixture equation, page 1',), knowledge_classes=tuple(KnowledgeClass),
                              demonstration_scope='A small executable teaching example, with no experimental claims.')
    lesson = LessonSpec('How do the two inputs affect the result?', ('Trace both input dependencies.',), ('Basic algebra',),
                        'A change in either input flows through the shared intermediate.', ('intuition', 'mechanism', 'playground'),
                        {'x': 'First input', 'y': 'Second input'}, controls, ('var-product',),
                        'How does the mechanism output respond?', 'Read actual computed values and their representation.',
                        (ExplorationSpec('explore-baseline', 'Start with small inputs', 'Use the first setup.', 'Inspect the intermediate and output.', 'It establishes the mechanism at a small scale.', {'var-x': .5, 'var-y': 1.5}),
                         ExplorationSpec('explore-contrast', 'Contrast a stronger input', 'Use the second setup.', 'Compare the output and intermediate.', 'It reveals the dependence on both inputs.', {'control-x': 3, 'control-y': 2})),
                        'This demonstration uses small synthetic inputs.', 'A visual trend is not a paper benchmark result.', ('Synthetic fixture evidence E001.',))
    grounding = (GroundingRecord('claim-mechanism', 'The fixture defines the shared product.', KnowledgeClass.SOURCE_GROUNDED, GroundingStatus.SUPPORTED, ('E001',)),
                 GroundingRecord('claim-output', 'The displayed output follows the executable AST.', KnowledgeClass.DERIVED, GroundingStatus.SUPPORTED, computation_refs=('compute-result',)),
                 GroundingRecord('claim-toy', 'Input ranges and diagrams were chosen for teaching.', KnowledgeClass.PEDAGOGICAL, GroundingStatus.SUPPORTED))
    focus = FocusCoverageMap('Trace both inputs', ('0',), ('step-product', 'step-output'), tuple(c.id for c in controls),
                             tuple(c.id for c in computations), ('visual-result',), tuple(e.id for e in lesson.guided_explorations))
    return ExplanationIR(science, lesson, computations, (VisualSpec('visual-result', 'auto', lesson.visual_question, visual_data, metadata),), grounding, focus, {'mechanism_family': family})


def ast_reads(tree):
    # Test-only traversal, independent of the renderer adapter.
    if tree.get('type') == 'Variable':
        return {tree['id']}
    result = set()
    for value in tree.values():
        if isinstance(value, dict):
            result |= ast_reads(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    result |= ast_reads(item)
                elif isinstance(item, list):
                    for node in item:
                        result |= ast_reads(node)
    return result


def reference(family):
    def compute(inputs):
        x, y = inputs['var-x'], inputs['var-y']
        p = x * y
        r = p + x
        if family == 'distribution':
            m = max(x, y, 0)
            values = [math.exp(v - m) for v in (x, y, 0)]
            r = [v / sum(values) for v in values]
        elif family in {'matrix_transformation', 'geometry'}:
            r = [[x, y], [y, p]]
        elif family in {'signal_transformation', 'optimization', 'dynamical_system', 'iterative_process', 'sequential_algorithm'}:
            r = [x, p, x + y, x - y]
        elif family == 'state_transition':
            r = 'active' if x > y else 'rest'
        return {**inputs, 'var-product': p, 'var-result': r}
    return compute


def control_fixture(kind):
    ir = fixture_ir('distribution' if kind == 'vector' else 'matrix_transformation' if kind == 'matrix' else 'scalar_relationship')
    x, y = variable('var-x'), variable('var-y')
    controls = list(ir.lesson_spec.controls)
    variables = list(ir.scientific_model.variables)
    if kind in {'vector', 'matrix'}:
        shape = (3,) if kind == 'vector' else (2, 2)
        default = [.2, .3, .5] if kind == 'vector' else [[1, 2], [2, 1]]
        variables[0] = replace(variables[0], type=kind, shape=shape)
        variables[2] = replace(variables[2], type=kind, shape=shape)
        variables[3] = replace(variables[3], shape=shape)
        controls[0] = replace(controls[0], control_type=kind, default=default,
                              validation_rule='normalize' if kind == 'vector' else 'reject', minimum=0, maximum=4)
        first = replace(ir.computations[0], expression='x / y', output_type=kind, metadata={'ast': binary('/', x, y)})
        tree = call('softmax', variable('var-product')) if kind == 'vector' else call('transpose', variable('var-product'))
        second = replace(ir.computations[1], expression='softmax(p)' if kind == 'vector' else 'transpose(p)', input_refs=('var-product',), metadata={'ast': tree})
        setups = ({'var-x': default, 'var-y': 1}, {'var-x': [.6, .3, .1] if kind == 'vector' else [[3, 2], [1, 3]], 'var-y': 3})
    else:
        variables[0] = replace(variables[0], type='boolean')
        variables[1] = replace(variables[1], type='categorical')
        controls[0] = replace(controls[0], control_type='toggle', default=False, minimum=None, maximum=None, step=None)
        controls[1] = replace(controls[1], control_type='select', default='low', options=('low', 'high'), minimum=None, maximum=None, step=None, effect_targets=('var-result',))
        first = replace(ir.computations[0], expression='1 if x else 2', input_refs=('var-x',), metadata={'ast': {'type': 'Conditional', 'condition': x, 'then': constant(1), 'else': constant(2)}})
        second = replace(ir.computations[1], expression='p * 2 if y == "high" else p', input_refs=('var-product', 'var-y'), metadata={'ast': {'type': 'Conditional', 'condition': binary('==', y, constant('high')), 'then': binary('*', variable('var-product'), constant(2)), 'else': variable('var-product')}})
        setups = ({'var-x': True, 'var-y': 'high'}, {'var-x': False, 'var-y': 'high'})
    explorations = tuple(replace(e, setup=setup) for e, setup in zip(ir.lesson_spec.guided_explorations, setups))
    return replace(ir, scientific_model=replace(ir.scientific_model, variables=tuple(variables)),
                   lesson_spec=replace(ir.lesson_spec, controls=tuple(controls), guided_explorations=explorations), computations=(first, second))


def load_ir(name):
    """Load dataclass-shaped JSON fixtures without adding an upstream IR loader."""
    data = json.loads((FIXTURES / (name + '.json')).read_text(encoding='utf-8'))
    science = data['scientific_model']
    science['variables'] = tuple(ScientificVariable(**{**v, 'shape': tuple(v['shape']), 'evidence_refs': tuple(v['evidence_refs']), 'knowledge_class': KnowledgeClass(v['knowledge_class'])}) for v in science['variables'])
    science['equations'] = tuple(ScientificEquation(**v) for v in science['equations'])
    science['relationships'] = tuple(ScientificRelationship(**v) for v in science['relationships'])
    science['mechanism_steps'] = tuple(MechanismStep(**v) for v in science['mechanism_steps'])
    lesson = data['lesson_spec']
    lesson['controls'] = tuple(ControlSpec(**v) for v in lesson['controls'])
    lesson['guided_explorations'] = tuple(ExplorationSpec(**v) for v in lesson['guided_explorations'])
    return ExplanationIR(ScientificModel(**science), LessonSpec(**lesson), tuple(ComputationSpec(**v) for v in data['computations']),
                         tuple(VisualSpec(**v) for v in data['visuals']),
                         tuple(GroundingRecord(**{**v, 'knowledge_class': KnowledgeClass(v['knowledge_class']), 'status': GroundingStatus(v['status'])}) for v in data['grounding_records']),
                         FocusCoverageMap(**data['focus_coverage']), data['metadata'])
