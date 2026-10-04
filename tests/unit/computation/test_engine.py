import json
import unittest
from dataclasses import replace

from playground.computation.ast import Node
from playground.computation.parser import parse
from playground.computation.evaluator import evaluate, compile_computations, execute, execute_spec
from playground.computation.operations import OPERATIONS, apply, validate_value
from playground.computation.invariants import check_invariants
from playground.computation.validate import prepare_inputs, validate_computation, representative_states, control_value
from playground.ir.models import ComputationSpec
from tests.fixtures.dev2_factory import explanation


class ComputationTests(unittest.TestCase):
    def test_array_entry_bounds_are_not_scalar_state_probes(self):
        ir = explanation()
        for kind, default in [('vector', [1, 2]), ('matrix', [[1, 2], [3, 4]])]:
            with self.subTest(kind=kind):
                control = replace(ir.lesson_spec.controls[0], control_type=kind,
                                  default=default, minimum=-5, maximum=5)
                candidate = replace(ir, lesson_spec=replace(ir.lesson_spec,
                                    controls=(control, *ir.lesson_spec.controls[1:])))
                self.assertFalse(any(label.startswith(control.id + ':')
                                     for label, _ in representative_states(candidate)))
                self.assertEqual(control.default, default)
                outside = [6, -6] if kind == 'vector' else [[6, -6]]
                with self.assertRaisesRegex(ValueError, 'Array entry outside'):
                    control_value(control, outside, strict=True)
                clamp = replace(control, validation_rule='clamp')
                expected = [5, -5] if kind == 'vector' else [[5, -5]]
                self.assertEqual(control_value(clamp, outside), expected)

    def test_ast_roundtrip(self):
        node = parse("softmax([a, b, 0])")
        restored = Node.from_dict(json.loads(json.dumps(node.to_dict())))
        self.assertEqual(node, restored)
        self.assertEqual(node.references, {"a", "b"})

    def test_scalar_and_boolean(self):
        self.assertEqual(evaluate(parse("(x**2 + 1) / 2"), {"x": 3}), 5)
        self.assertTrue(evaluate(parse("x > 0 and x <= 3"), {"x": 2}))
        self.assertEqual(evaluate(parse("1 if flag else 2"), {"flag": False}), 2)
        self.assertEqual(evaluate(parse("[1,2][0]"), {}), 1)

    def test_vectors_and_matrices(self):
        self.assertEqual(evaluate(parse("[1,2]+3"), {}), [4, 5])
        self.assertEqual(apply("matmul", [[[1, 2], [3, 4]], [2, 1]]), [4, 10])
        self.assertEqual(apply("matmul", [[[1, 0], [0, 1]], [[1, 2], [3, 4]]]), [[1, 2], [3, 4]])

    def test_cross_entropy_uses_only_negative_weighted_log_probabilities(self):
        import math
        self.assertAlmostEqual(apply('cross_entropy', [[0.5, 0.5], [0.5, 0.5]]), math.log(2))
        self.assertAlmostEqual(apply('cross_entropy', [[0.75, 0.25], [0.5, 0.5]]), math.log(2))
        for p, q in [([0.2, 0.2], [0.5, 0.5]), ([0.5, 0.5], [1, 0]), ([1], [0.5, 0.5])]:
            with self.subTest(p=p, q=q), self.assertRaises(ValueError):
                apply('cross_entropy', [p, q])

    def test_stable_distribution(self):
        result = apply("softmax", [[10000, 10001, 9999]])
        validate_value(result, "distribution", (3,))
        self.assertGreater(result[1], result[0])
        self.assertEqual(apply("entropy", [[1, 0]]), 0)
        self.assertEqual(apply("norm", [[1e200, 1e200]]) / 1e200, 2 ** 0.5)

    def test_registry_normal_cases(self):
        cases = {"add": ([2, 3], 5), "subtract": ([2, 3], -1), "multiply": ([2, 3], 6),
                 "divide": ([6, 3], 2), "power": ([2, 3], 8), "negate": ([2], -2),
                 "abs": ([-2], 2), "sqrt": ([4], 2), "exp": ([0], 1), "log": ([1], 0),
                 "sin": ([0], 0), "cos": ([0], 1), "sum": ([[1, 2]], 3), "mean": ([[1, 3]], 2),
                 "min": ([[1, 3]], 1), "max": ([[1, 3]], 3), "dot": ([[1, 2], [3, 4]], 11),
                 "matmul": ([[[1]], [[2]]], [[2]]), "transpose": ([[[1, 2]]], [[1], [2]]),
                 "norm": ([[3, 4]], 5), "normalize": ([[3, 4]], [0.6, 0.8]),
                 "softmax": ([[0, 0]], [0.5, 0.5]), "entropy": ([[1, 0]], 0),
                 "cross_entropy": ([[1, 0], [1, 0]], 0),
                 "xlogx": ([[0, 1]], [0, 0]), "take": ([[2, 3, 4], 2], [2, 3]),
                 "approx_equal": ([1, 1 + 1e-10], True)}
        self.assertEqual(set(cases), set(OPERATIONS))
        for name, (args, expected) in cases.items():
            with self.subTest(name=name):
                self.assertEqual(apply(name, args), expected)
                with self.assertRaises(ValueError):
                    apply(name, [])

    def test_rejects_malicious_and_oversized_dsl(self):
        attacks = ["__import__('os')", "x.__class__", "open('x')", "lambda: 1", "[x for x in y]",
                   "f(**x)", "x[0:2]", "{'x': 1}", "(x:=1)", "x[-1]", "softmax(x, axis=0)",
                   "1; 2", "a" * 4097, "[1]*1e301", "2**1000000000"]
        for expression in attacks:
            with self.subTest(expression=expression[:30]), self.assertRaises((ValueError, TypeError)):
                evaluate(parse(expression), {})
        self.assertEqual(evaluate(parse("[1]*1000000"), {}), [1000000])

    def test_shapes_domains_and_finite(self):
        invalid = [("add", [[1, 2], [1]]), ("dot", [[1], [1, 2]]),
                   ("matmul", [[[1, 2]], [[1]]]), ("sqrt", [-1]), ("log", [0]),
                   ("normalize", [[0, 0]]), ("divide", [1, 0]), ("exp", [1000]),
                   ("entropy", [[0.2, 0.2]]), ("softmax", [[[1]]])]
        for name, args in invalid:
            with self.subTest(name=name), self.assertRaises((ValueError, ZeroDivisionError, OverflowError)):
                apply(name, args)
        for value, typ, shape, domain in [([1, 2], "vector", (3,), None), (-1, "scalar", (), "positive"),
                                           (float("nan"), "scalar", (), None), (True, "scalar", (), None),
                                           ([[1], [1, 2]], "matrix", (), None), ([0.2, 0.2], "distribution", (), None)]:
            with self.assertRaises(ValueError):
                validate_value(value, typ, shape, domain)

    def test_prefix_and_zero_safe_entropy_contributions(self):
        import math
        self.assertEqual(apply('take', [[1, 2, 3, 4], 1]), [1])
        self.assertAlmostEqual(evaluate(parse('-sum(xlogx([0.25,0.25,0.25,0.25]))/log(2)'), {}), 2)
        self.assertEqual(evaluate(parse('-sum(xlogx([1,0,0,0]))/log(2)'), {}), 0)
        self.assertAlmostEqual(apply('xlogx', [0.5]), 0.5 * math.log(0.5))
        for count in (0, -1, 5, 1.5, True, '2'):
            with self.subTest(count=count), self.assertRaises(ValueError):
                apply('take', [[1, 2, 3, 4], count])
        with self.assertRaises(ValueError):
            apply('xlogx', [-0.1])

    def test_default_boundaries_presets_and_invariants(self):
        ir = compile_computations(explanation())
        self.assertEqual(validate_computation(ir).status.value, "PASS")
        self.assertGreaterEqual(len(representative_states(ir)), 9)
        values, _ = execute(ir, prepare_inputs(ir))
        self.assertEqual(values["var-y"], 2)
        self.assertTrue(all(passed for _, passed in check_invariants(ir, values)))
        values["var-y"] = 99
        self.assertFalse(check_invariants(ir, values)[0][1])

    def test_input_behaviors(self):
        control = explanation().lesson_spec.controls[0]
        self.assertEqual(control_value(control, 99), 4)
        with self.assertRaises(ValueError):
            control_value(replace(control, validation_rule="reject"), 99)
        self.assertEqual(control_value(replace(control, validation_rule="warn"), 99), 99)
        self.assertEqual(control_value(replace(control, validation_rule="normalize", control_type="vector", minimum=None, maximum=None), [3, 4]), [0.6, 0.8])

    def test_iterations_and_states(self):
        ir = explanation()
        iterative = ComputationSpec("compute-decay", "s", "scalar", ("var-a",),
                                    metadata={"kind": "iteration", "bindings": {"factor": "var-a"},
                                              "initial": {"s": "1"}, "updates": {"s": "s*factor"}, "steps": 4})
        compiled = compile_computations(replace(ir, computations=(iterative,))).computations[0]
        result, history = execute_spec(compiled, {"factor": 0.5})
        self.assertEqual(result, 0.0625)
        self.assertEqual(len(history), 5)
        transition = ComputationSpec("compute-switch", "", "state", ("var-a",), metadata={
            "kind": "state_transition", "states": ["off", "on"], "initial_state": "off", "steps": 2,
            "bindings": {"x": "var-a"}, "transitions": [{"from": "off", "to": "on", "when": "x > 1"}]})
        compiled = compile_computations(replace(ir, computations=(transition,))).computations[0]
        self.assertEqual(execute_spec(compiled, {"x": 2})[0], "on")
        with self.assertRaises(ValueError):
            compile_computations(replace(ir, computations=(replace(iterative, metadata={**iterative.metadata, "steps": 100000}),)))

    def test_no_unknown_ast_operation(self):
        with self.assertRaises(ValueError):
            evaluate(Node("call", "system", (Node("literal", "whoami"),)), {})
