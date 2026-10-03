"""Claim-level provenance checks; citation existence is not semantic proof."""
from playground.ir.models import KnowledgeClass as K, GroundingStatus as G
from playground.validation.report import ValidationFinding, ValidationStatus as S


def claim_locations(ir):
    """Exact JSON-pointer locations, used only for format lowering/leaf repair."""
    paths = {}
    science, lesson = ir.scientific_model, ir.lesson_spec
    for field in ('concept', 'purpose', 'focus_alignment', 'demonstration_scope'):
        paths['science.' + field] = '/scientific_model/' + field
    for field in ('assumptions', 'limitations', 'misconceptions', 'edge_cases'):
        for i, _ in enumerate(getattr(science, field)):
            paths[f'science.{field}.{i}'] = f'/scientific_model/{field}/{i}'
    for field in ('intuition', 'limitation_or_assumption', 'misconception', 'central_learning_question', 'visual_question', 'visual_intent'):
        paths['lesson.' + field] = '/lesson_spec/' + field
    for field in ('teaching_sequence', 'source_grounding_plan', 'learning_objectives', 'audience_prerequisites'):
        for i, _ in enumerate(getattr(lesson, field)):
            paths[f'lesson.{field}.{i}'] = f'/lesson_spec/{field}/{i}'
    for collection, field in (('variables','meaning'), ('equations','meaning'), ('relationships','description'), ('mechanism_steps','description')):
        for i, item in enumerate(getattr(science, collection)):
            paths[item.id] = f'/scientific_model/{collection}/{i}/{field}'
    for var in lesson.symbol_explanations:
        paths['symbol.' + var] = '/lesson_spec/symbol_explanations/' + var
    for i, item in enumerate(lesson.controls):
        for field in ('learning_purpose','safe_range_reason'):
            paths[item.id + '.' + field] = f'/lesson_spec/controls/{i}/{field}'
    for i, item in enumerate(lesson.guided_explorations):
        for field in ('change','observe','why'):
            paths[item.id + '.' + field] = f'/lesson_spec/guided_explorations/{i}/{field}'
    for i, item in enumerate(ir.visuals):
        paths[item.id + '.question'] = f'/visuals/{i}/question'
    return paths


def claim_aliases(ir):
    """Only unambiguous pointers/field suffixes; never fuzzy semantic matching."""
    aliases = {}
    for canonical, pointer in claim_locations(ir).items():
        aliases[pointer] = canonical
        dotted = pointer[1:].replace('/', '.')
        aliases[dotted] = canonical
        aliases[dotted.replace('scientific_model.', 'science.', 1).replace('lesson_spec.', 'lesson.', 1)] = canonical
        if canonical.startswith(('var-', 'eq-', 'rel-', 'step-')) and '.' not in canonical:
            aliases[canonical + '.' + pointer.rsplit('/', 1)[-1]] = canonical
            aliases[canonical.split('-', 1)[0] + '-' + canonical] = canonical
        if canonical.startswith('symbol.var-'):
            aliases['symbol-' + canonical.removeprefix('symbol.')] = canonical
    return aliases


def learner_claims(ir):
    """Canonical paths identify free-text scientific claims lacking their own IDs.

    Every entry needs a GroundingRecord with that claim_id and identical claim text.
    Object IDs identify variable meanings, equation meanings, relationships and steps.
    """
    science, lesson = ir.scientific_model, ir.lesson_spec
    claims = {"science.concept": science.concept, "science.purpose": science.purpose,
              "science.focus_alignment": science.focus_alignment,
              "science.demonstration_scope": science.demonstration_scope,
              "lesson.intuition": lesson.intuition,
              "lesson.limitation_or_assumption": lesson.limitation_or_assumption,
              "lesson.misconception": lesson.misconception}
    for field in ("assumptions", "limitations", "misconceptions", "edge_cases"):
        claims.update({f"science.{field}.{i}": text for i, text in enumerate(getattr(science, field))})
    for field in ("teaching_sequence", "source_grounding_plan"):
        claims.update({f"lesson.{field}.{i}": text for i, text in enumerate(getattr(lesson, field))})
    for field in ("learning_objectives", "audience_prerequisites"):
        claims.update({f"lesson.{field}.{i}": text for i, text in enumerate(getattr(lesson, field))})
    for field in ("central_learning_question", "visual_question", "visual_intent"):
        claims["lesson." + field] = getattr(lesson, field)
    for visual in ir.visuals:
        claims[visual.id + ".question"] = visual.question
    for collection, field in ((science.variables, "meaning"), (science.equations, "meaning"),
                              (science.relationships, "description"), (science.mechanism_steps, "description")):
        claims.update({item.id: getattr(item, field) for item in collection})
    for variable, text in lesson.symbol_explanations.items():
        claims["symbol." + variable] = text
    for control in lesson.controls:
        claims[control.id + ".learning_purpose"] = control.learning_purpose
        claims[control.id + ".safe_range_reason"] = control.safe_range_reason
    for exploration in lesson.guided_explorations:
        for field in ("change", "observe", "why"):
            claims[exploration.id + "." + field] = getattr(exploration, field)
    return {k: v for k, v in claims.items() if v}


def validate_grounding(ir, evidence):
    findings = []
    evidence_ids = set(evidence.evidence_ids)
    computations = {s.id for s in ir.computations}
    def finding(code, text, target, status=S.FAIL):
        findings.append(ValidationFinding(status, code, "grounding", text, target))
    records = {record.claim_id: record for record in ir.grounding_records}
    declared_classes = set(ir.scientific_model.knowledge_classes)
    if len(records) != len(ir.grounding_records):
        finding("DUPLICATE_CLAIM_ID", "Grounding claim IDs must be unique", None)
    for claim_id, claim in learner_claims(ir).items():
        if claim_id not in records or records[claim_id].claim != claim:
            finding("CLAIM_UNCLASSIFIED", "Learner-facing claim needs an exact grounding record", claim_id)
    objects = {x.id: x for collection in (ir.scientific_model.variables, ir.scientific_model.equations,
                                         ir.scientific_model.relationships) for x in collection}
    for record in ir.grounding_records:
        if record.knowledge_class not in declared_classes:
            finding("KNOWLEDGE_CLASS_UNDECLARED", "ScientificModel must declare every claim knowledge class", record.claim_id)
        if not set(record.evidence_refs) <= evidence_ids:
            finding("EVIDENCE_REFERENCE_INVALID", "Evidence reference does not exist", record.claim_id)
        if not set(record.computation_refs) <= computations:
            finding("COMPUTATION_REFERENCE_INVALID", "Derived computation reference does not exist", record.claim_id)
        if record.knowledge_class == K.SOURCE_GROUNDED and not record.evidence_refs:
            finding("SOURCE_CLAIM_UNGROUNDED", "Paper claim requires evidence IDs", record.claim_id)
        if record.knowledge_class == K.DERIVED and not record.computation_refs:
            finding("DERIVED_CLAIM_UNBOUND", "Derived claim requires executable computation", record.claim_id)
        if record.status == G.UNSUPPORTED:
            finding("GROUNDING_UNSUPPORTED", "Unsupported claims cannot be presented in a validated lesson", record.claim_id)
        elif record.status == G.PARTIAL:
            finding("GROUNDING_PARTIAL", "Partial support requires narrow semantic verification", record.claim_id, S.WARN)
        if record.claim_id in objects and record.knowledge_class != objects[record.claim_id].knowledge_class:
            finding("KNOWLEDGE_CLASS_MISMATCH", "Object and claim knowledge classes disagree", record.claim_id)
        if record.claim_id in objects and objects[record.claim_id].knowledge_class == K.SOURCE_GROUNDED and not set(objects[record.claim_id].evidence_refs) <= set(record.evidence_refs):
            finding("EVIDENCE_LINEAGE_MISMATCH", "Claim must preserve its object's source evidence references", record.claim_id)
    for item in objects.values():
        if not set(item.evidence_refs) <= evidence_ids:
            finding("EVIDENCE_REFERENCE_INVALID", "Object evidence references do not exist", item.id)
        if item.knowledge_class == K.SOURCE_GROUNDED and not item.evidence_refs:
            finding("SOURCE_OBJECT_UNGROUNDED", "Source-grounded object requires evidence", item.id)
    if not set(ir.scientific_model.provenance) <= evidence_ids:
        finding("PROVENANCE_INVALID", "Provenance must preserve canonical evidence IDs", "science.provenance")
    if not ir.scientific_model.provenance:
        finding("PROVENANCE_MISSING", "ScientificModel requires provenance", "science.provenance")
    return findings
