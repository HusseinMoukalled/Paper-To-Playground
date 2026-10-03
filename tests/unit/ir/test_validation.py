import unittest
import json
from dataclasses import replace

from playground.ir.serialization import load_ir, to_mapping, parse_json
from playground.ir.validate import validate_ir
from playground.ir.models import GroundingStatus, KnowledgeClass
from tests.fixtures.dev2_factory import explanation, evidence_pack


class IRTests(unittest.TestCase):
    def test_shared_contract_roundtrip(self):
        ir = explanation()
        self.assertEqual(load_ir(json.dumps(to_mapping(ir))), ir)
        self.assertEqual(validate_ir(ir, evidence_pack()).status.value, "PASS")

    def test_json_recovery_does_not_change_strings(self):
        self.assertEqual(parse_json('```json\n{"a": [1,2,], "text": ",}",}\n```'), {"a": [1, 2], "text": ",}"})
        for text in ('{"a": 1, "a": 2}', '{"x": NaN}', 'prefix {"x":1}', '{"x":', "{'x':1}"):
            with self.assertRaises(ValueError):
                parse_json(text)

    def test_schema_strictness(self):
        for mutate in (lambda x: x.update(extra=1), lambda x: x.pop("lesson_spec"),
                       lambda x: x["scientific_model"].update(variables="wrong")):
            data = to_mapping(explanation())
            mutate(data)
            with self.assertRaises(ValueError):
                load_ir(json.dumps(data))

    def codes(self, ir):
        return {f.code for f in validate_ir(ir, evidence_pack()).findings}

    def test_evidence_and_grounding(self):
        ir = explanation()
        records = list(ir.grounding_records)
        records[0] = replace(records[0], evidence_refs=("E404",))
        self.assertIn("EVIDENCE_REFERENCE_INVALID", self.codes(replace(ir, grounding_records=tuple(records))))
        records = list(ir.grounding_records)
        records[0] = replace(records[0], status=GroundingStatus.UNSUPPORTED)
        self.assertIn("GROUNDING_UNSUPPORTED", self.codes(replace(ir, grounding_records=tuple(records))))
        records[0] = replace(records[0], status=GroundingStatus.PARTIAL)
        self.assertEqual(validate_ir(replace(ir, grounding_records=tuple(records)), evidence_pack()).status.value, "WARN")
        self.assertIn("CLAIM_UNCLASSIFIED", self.codes(replace(ir, grounding_records=ir.grounding_records[1:])))

    def test_derived_requires_computation(self):
        ir = explanation()
        records = tuple(replace(r, knowledge_class=KnowledgeClass.DERIVED, evidence_refs=(), computation_refs=())
                        if r.claim_id == "lesson.intuition" else r for r in ir.grounding_records)
        self.assertIn("DERIVED_CLAIM_UNBOUND", self.codes(replace(ir, grounding_records=records)))

    def test_references_focus_and_audience(self):
        ir = explanation()
        self.assertIn("FOCUS_COVERAGE_INVALID", self.codes(replace(ir, focus_coverage=replace(ir.focus_coverage, focus="unrelated"))))
        self.assertIn("FOCUS_COVERAGE_INVALID", self.codes(replace(ir, focus_coverage=None)))
        self.assertIn("AUDIENCE_ADAPTATION_MISSING", self.codes(replace(ir, metadata={**ir.metadata, "audience": "other"})))
        control = replace(ir.lesson_spec.controls[0], scientific_variable="var-missing")
        self.assertIn("IR_REFERENCE_INVALID", self.codes(replace(ir, lesson_spec=replace(ir.lesson_spec, controls=(control, ir.lesson_spec.controls[1])))))

    def test_presets_dead_controls_and_dag(self):
        ir = explanation()
        explorations = (replace(ir.lesson_spec.guided_explorations[0], setup={"missing": 1}), ir.lesson_spec.guided_explorations[1])
        self.assertIn("PRESET_INVALID", self.codes(replace(ir, lesson_spec=replace(ir.lesson_spec, guided_explorations=explorations))))
        dead = replace(ir.computations[0], expression="a*x + 0*b", metadata={**ir.computations[0].metadata, "equation_refs": []})
        context = {**ir.metadata, "equation_scope": {"eq-response": "context_only"}}
        self.assertIn("DEAD_CONTROL", self.codes(replace(ir, computations=(dead,), metadata=context)))
        bad = replace(ir.computations[0], metadata={"bindings": {"a": "var-a"}})
        self.assertIn("COMPUTATION_BINDINGS_INVALID", self.codes(replace(ir, computations=(bad,))))

    def test_invalid_domains_and_units(self):
        ir = explanation()
        controls = (replace(ir.lesson_spec.controls[0], units="seconds"), ir.lesson_spec.controls[1])
        self.assertIn("CONTROL_UNITS_INVALID", self.codes(replace(ir, lesson_spec=replace(ir.lesson_spec, controls=controls))))
        variables = (replace(ir.scientific_model.variables[0], domain="mystery"),) + ir.scientific_model.variables[1:]
        self.assertIn("SCIENTIFIC_TYPE_INVALID", self.codes(replace(ir, scientific_model=replace(ir.scientific_model, variables=variables))))
