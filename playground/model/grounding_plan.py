"""Expand an explicit compact classification policy into claim-level records."""
from playground.ir.models import ExplanationIR
from playground.ir.serialization import decode
from playground.ir.grounding import learner_claims, claim_aliases


def expand_grounding_plan(value):
    if not isinstance(value, dict):
        return value
    metadata = value.get('metadata', {})
    plan = metadata.get('grounding_plan') if isinstance(metadata, dict) else None
    if plan is None:
        return value
    if not isinstance(plan, dict) or set(plan) != {'teaching_default', 'overrides'} or value.get('grounding_records') != []:
        raise ValueError('Grounding plan requires an explicit policy and an empty record array')
    default = plan['teaching_default']
    if default != {'knowledge_class':'PEDAGOGICAL', 'status':'SUPPORTED'} or not isinstance(plan['overrides'], list):
        raise ValueError('Only explicitly declared pedagogical teaching defaults are supported')
    ir = decode(ExplanationIR, value)
    claims = learner_claims(ir)
    aliases = claim_aliases(ir)
    records = {key: {'claim_id':key,'claim':text,**default,'evidence_refs':[],'computation_refs':[]}
               for key,text in claims.items()}
    # Objects already carry explicit scientific classification/citations. Derived
    # lineage comes only from declared producer/equation links, never model memory.
    for group in (ir.scientific_model.variables, ir.scientific_model.equations, ir.scientific_model.relationships):
        for item in group:
            producers = [c.id for c in ir.computations if item.id in c.output_refs or
                         item.id in c.metadata.get('equation_refs', []) or
                         hasattr(item,'output_refs') and set(item.output_refs) & set(c.output_refs)]
            records[item.id].update(knowledge_class=item.knowledge_class.value,
                                    evidence_refs=list(item.evidence_refs), computation_refs=producers if item.knowledge_class.value == 'DERIVED' else [])
    seen = set()
    for override in plan['overrides']:
        if not isinstance(override, dict) or set(override) != {'claim_ids','knowledge_class','status','evidence_refs','computation_refs'}:
            raise ValueError('Invalid grounding override')
        if not isinstance(override['claim_ids'],list):
            raise ValueError('Grounding claim IDs must be explicit arrays')
        for key in override['claim_ids']:
            if not isinstance(key,str): raise ValueError('Invalid grounding key')
            key = aliases.get(key,key)
            if key not in records or key in seen: raise ValueError('Unknown or repeated grounding override')
            seen.add(key)
            records[key].update({k:v for k,v in override.items() if k != 'claim_ids'})
    return dict(value, grounding_records=list(records.values()))
