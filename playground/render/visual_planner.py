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


def plan_visual(visual: dict, family: str, variables=None) -> dict:
    family = ALIASES.get(family, family.replace(' ', '_'))
    requested = visual['visual_type']
    component = requested if requested in COMPONENTS else FAMILIES.get(family, 'scene')
    reason = None
    if variables is not None and component in {'line', 'trajectory', 'waveform', 'scatter'}:
        by_id = {v['id']:v for v in variables}
        refs = visual['data_refs']
        data = by_id.get(refs[0], {}) if len(refs) == 1 else {}
        series = data.get('type') in {'vector','sequence'}
        pairs = data.get('type') == 'matrix' and len(data.get('shape', [])) == 2 and data['shape'][1] == 2
        if not series and not pairs:
            component = 'scene'
            reason = 'No sampled series or coordinate pairs are computed; show labeled current values instead.'
    return {**visual, 'component': component,
            'fallback_component': 'scene',
            **({'fallback_reason':reason} if reason else {}),
            'planning_level': 'specialized' if component != 'scene' else 'generic_scene'}
