"""Deterministic visual grammar, selected by mechanism and data shape."""

FAMILIES = {
    'scalar_relationship': 'bars', 'distribution': 'distribution',
    'matrix_transformation': 'matrix', 'sequential_algorithm': 'process',
    'state_transition': 'state_graph', 'optimization': 'trajectory',
    'signal_transformation': 'waveform', 'geometry': 'geometry',
    'information_flow': 'flow', 'iterative_process': 'process',
    'comparison': 'comparison', 'dynamical_system': 'trajectory',
}
COMPONENTS = frozenset({
    'bars', 'distribution', 'line', 'trajectory', 'scatter', 'matrix', 'vector',
    'flow', 'state_graph', 'waveform', 'geometry', 'comparison', 'process', 'scene',
})
ALIASES = {'scalar relationship': 'scalar_relationship', 'probability/distribution': 'distribution',
           'information/component flow': 'information_flow', 'comparative_mechanism': 'comparison',
           'comparative mechanism': 'comparison', 'signal': 'signal_transformation',
           'pipeline': 'information_flow'}


def plan_visual(visual: dict, family: str) -> dict:
    family = ALIASES.get(family, family.replace(' ', '_'))
    requested = visual['visual_type']
    component = requested if requested in COMPONENTS else FAMILIES.get(family, 'scene')
    return {**visual, 'component': component,
            'fallback_component': 'scene',
            'planning_level': 'specialized' if component != 'scene' else 'generic_scene'}
