"""Exploration observations are computed facts, not model-predicted numbers."""
from dataclasses import replace
import json

from playground.computation.evaluator import execute
from playground.computation.validate import prepare_inputs
from playground.ir.models import KnowledgeClass as K, GroundingStatus as G


def calculated_observations(ir):
    """Replace only the numeric observation field; retain explanations for review."""
    baseline = execute(ir, prepare_inputs(ir))[0]
    outputs = tuple(ref for c in ir.computations for ref in c.output_refs)
    variables = {v.id: v for v in ir.scientific_model.variables}
    def rounded(value):
        if isinstance(value, list):
            return [rounded(x) for x in value]
        if type(value) is float:
            return float(format(value, '.8g'))
        return value
    def display(value):
        return json.dumps(rounded(value), ensure_ascii=True)
    observations, explorations = {}, []
    for exploration in ir.lesson_spec.guided_explorations:
        values = execute(ir, prepare_inputs(ir, exploration.setup))[0]
        details = []
        for ref in outputs:
            variable = variables[ref]
            units = (' ' + variable.units) if variable.units else ''
            details.append(f'{variable.display_symbol} = {display(values[ref])}{units} '
                           f'(starting value: {display(baseline[ref])}{units})')
        text = 'Calculated results for this setup, compared with the starting inputs: ' + '; '.join(details) + '.'
        observations[exploration.id + '.observe'] = text
        explorations.append(replace(exploration, observe=text))
    records = tuple(replace(record, claim=observations[record.claim_id], knowledge_class=K.DERIVED,
                            status=G.SUPPORTED, evidence_refs=(),
                            computation_refs=tuple(c.id for c in ir.computations))
                    if record.claim_id in observations else record for record in ir.grounding_records)
    return replace(ir, lesson_spec=replace(ir.lesson_spec, guided_explorations=tuple(explorations)),
                   grounding_records=records)
