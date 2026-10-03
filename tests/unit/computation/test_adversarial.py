import json
from pathlib import Path
from dataclasses import replace
import unittest

from playground.computation.ast import Node
from playground.computation.evaluator import ExecutionGuard, evaluate, compile_computations, execute_spec, execute
from playground.computation.operations import OPERATIONS, apply, validate_value
from playground.computation.validate import control_value, prepare_inputs
from playground.computation.science import check_equation_consistency
from playground.computation.parser import parse
from playground.ir.models import ComputationSpec, ScientificVariable
from playground.ir.serialization import load_ir
from playground.ir.validate import validate_ir
from playground.model.repair import apply_patches
from playground.budget import RunBudget
from playground.failures import PlaygroundError
from tests.fixtures.dev2_factory import explanation, evidence_pack


class AdversarialTests(unittest.TestCase):
    def test_comparisons_do_not_coerce_boolean_categorical_and_numeric_types(self):
        for expression in ('True == 1','True < 1','\"1\" < 2'):
            with self.assertRaises(ValueError): evaluate(parse(expression), {})
        self.assertTrue(evaluate(parse('1 == 1.0'), {}))

    def test_unknown_and_forged_ast_rejected(self):
        for data in ({"kind": "system", "value": "x", "args": []},
                     {"kind": "variable", "value": "__class__", "args": []},
                     {"kind": "literal", "value": {}, "args": []},
                     {"kind": "literal", "value": float("inf"), "args": []},
                     {"kind": "call", "value": "open", "args": [{"kind": "literal", "value": "x", "args": []}]},
                     {"kind": "call", "value": "sqrt", "args": []},
                     {"kind": "index", "value": -1, "args": [{"kind": "literal", "value": 1, "args": []}]}):
            with self.assertRaises(ValueError):
                Node.from_dict(data)

    def test_each_operation_rejects_invalid_numeric_shape_or_domain(self):
        for name, operation in OPERATIONS.items():
            with self.subTest(name=name), self.assertRaises((ValueError, TypeError)):
                apply(name, [None] * operation.arity)
            with self.subTest(name=name, boundary="empty_array"), self.assertRaises(ValueError):
                apply(name, [[]] * operation.arity)
        with self.assertRaises(ValueError):
            validate_value([1, "a"], "vector")
        with self.assertRaises(ValueError):
            evaluate(parse("1 if 1 else 2"), {})

    def test_operation_boundary_and_finite_cases(self):
        boundary = {"add": [0, 0], "subtract": [0, 0], "multiply": [0, 1e300], "divide": [0, 1],
                    "power": [0, 0], "negate": [0], "abs": [0], "sqrt": [0], "exp": [-1000],
                    "log": [1e-300], "sin": [0], "cos": [0], "sum": [[0]], "mean": [[0]],
                    "min": [[0]], "max": [[0]], "dot": [[0], [0]], "matmul": [[[0]], [[0]]],
                    "transpose": [[[0]]], "norm": [[0]], "normalize": [[1e-300]],
                    "softmax": [[1e300, -1e300]], "entropy": [[0, 1]], "approx_equal": [[0, 0]]}
        boundary["approx_equal"] = [0, 0]
        self.assertEqual(set(boundary), set(OPERATIONS))
        from playground.computation.operations import finite
        for name, arguments in boundary.items():
            with self.subTest(name=name):
                finite(apply(name, arguments))

    def test_probability_normalization_not_euclidean(self):
        control = replace(explanation().lesson_spec.controls[0], validation_rule="normalize", control_type="vector")
        self.assertEqual(control_value(control, [2, 2], scientific_type="distribution"), [0.5, 0.5])
        with self.assertRaises(ValueError):
            control_value(control, [-1, 2], scientific_type="distribution")

    def test_symbolic_shape_consistency(self):
        ir = explanation()
        variables = (ScientificVariable("var-u", None, "u", "Input", "vector", ("n",)),
                     ScientificVariable("var-v", None, "v", "Input", "vector", ("n",)))
        ir = replace(ir, scientific_model=replace(ir.scientific_model, variables=variables), computations=())
        with self.assertRaises(ValueError):
            execute(ir, {"var-u": [1, 2], "var-v": [1]})

    def test_budget_and_work_limits(self):
        guard = ExecutionGuard(nodes=250000)
        with self.assertRaises(ValueError):
            evaluate(parse("1"), {}, guard=guard)
        budget = RunBudget(max_runtime_seconds=1, finalization_reserve_seconds=0.9)
        budget.start_time -= 0.2
        with self.assertRaises(PlaygroundError):
            validate_ir(explanation(), evidence_pack(), budget=budget)

    def test_equation_consistency_and_notation(self):
        ir = explanation()
        equation = replace(ir.scientific_model.equations[0], expression="y = a*x + b")
        check_equation_consistency(replace(ir, scientific_model=replace(ir.scientific_model, equations=(equation,))))
        bad = replace(ir.computations[0], expression="a*x-b")
        with self.assertRaises(ValueError):
            check_equation_consistency(replace(ir, computations=(bad,)))

    def test_equation_consistency_follows_only_declared_expression_dependencies(self):
        ir = explanation()
        intermediate = ComputationSpec('compute-intermediate', 'a*x', 'scalar',
            input_refs=('var-a','var-x'), output_refs=('var-product',),
            metadata={'bindings':{'a':'var-a','x':'var-x'}, 'equation_refs':[]})
        output = replace(ir.computations[0], expression='product+b',
            input_refs=('var-product','var-b'), dependencies=('compute-intermediate',),
            metadata={'bindings':{'product':'var-product','b':'var-b'},'equation_refs':['eq-response']})
        check_equation_consistency(replace(ir, computations=(intermediate,output)))
        with self.assertRaises(ValueError):
            check_equation_consistency(replace(ir, computations=(intermediate,replace(output,dependencies=()))))
        with self.assertRaises(ValueError):
            check_equation_consistency(replace(ir, computations=(replace(intermediate,expression='a+x'),output)))

    def test_state_ambiguity_and_iteration_initialization(self):
        ir = explanation()
        transition = ComputationSpec("compute-state", "", "state", metadata={"kind": "state_transition",
            "states": ["a", "b"], "initial_state": "a", "transitions": [
                {"from": "a", "to": "b", "when": "True"}, {"from": "a", "to": "a", "when": "True"}], "bindings": {}})
        spec = compile_computations(replace(ir, computations=(transition,))).computations[0]
        with self.assertRaises(ValueError):
            execute_spec(spec, {})
        iteration = ComputationSpec("compute-iteration", "s", "scalar", metadata={"kind": "iteration",
                                   "initial": {"s": "s"}, "updates": {"s": "s+1"}, "steps": 2, "bindings": {}})
        candidate = compile_computations(replace(ir, computations=(iteration,)))
        with self.assertRaises(ValueError):
            execute(candidate, {})

    def test_serialized_ir_fixture_for_dev3(self):
        path = Path(__file__).resolve().parents[2] / "fixtures" / "dev2_explanation_ir.json"
        ir = load_ir(path.read_text(encoding="utf-8"))
        self.assertEqual(validate_ir(ir, evidence_pack()).status.value, "PASS")
        self.assertEqual(execute(ir, prepare_inputs(ir))[0]["var-y"], 2)

    def test_failed_scientific_repair_preserves_valid_candidate(self):
        ir = explanation()
        path = "/computations/0/expression"
        with self.assertRaises(ValueError):
            apply_patches(ir, evidence_pack(), [{"op": "replace", "path": path, "value": "a*x-b"}], allowed_paths={path})
        self.assertEqual(validate_ir(ir, evidence_pack()).status.value, "PASS")
