"""Executable predicates use the same restricted AST as computations."""
from playground.computation.evaluator import evaluate
from playground.computation.parser import parse


def check_invariants(ir, values, *, guard=None):
    bindings = ir.metadata.get("invariant_bindings", {})
    env = {k: values[v] for k, v in bindings.items() if v in values}
    results = []
    for expression in ir.scientific_model.invariants:
        node = parse(expression)
        if not node.references <= env.keys():
            raise ValueError("Invariant references do not resolve")
        result = evaluate(node, env, guard=guard)
        if type(result) is not bool:
            raise ValueError("An invariant must return boolean")
        results.append((expression, result))
    return tuple(results)
