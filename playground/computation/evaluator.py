"""Pure canonical AST interpreter and bounded declarative execution."""
from __future__ import annotations

from dataclasses import replace, dataclass
import operator
import time

from playground.computation.ast import Node, AST_VERSION, MAX_DEPTH
from playground.computation.operations import apply, finite, validate_value
from playground.computation.parser import parse, IDENTIFIER

MAX_ITERATIONS = 100
MAX_EVALUATION_NODES = 250_000
MAX_EVALUATION_SECONDS = 30
COMMON_METADATA = {"kind", "bindings", "equation_refs", "ast_version", "canonical_ast"}
KIND_METADATA = {
    "expression": COMMON_METADATA,
    "iteration": COMMON_METADATA | {"initial", "updates", "steps", "initial_ast", "update_ast", "state_specs", "state_invariants", "state_invariant_ast"},
    "state_transition": COMMON_METADATA | {"states", "initial_state", "transitions", "steps", "transition_ast"},
}
COMPARISONS = {"lt": operator.lt, "le": operator.le, "gt": operator.gt,
               "ge": operator.ge, "eq": operator.eq, "ne": operator.ne}


@dataclass
class ExecutionGuard:
    budget: object = None
    nodes: int = 0
    started: float = 0

    def __post_init__(self):
        self.started = time.monotonic()

    def check(self):
        self.nodes += 1
        if self.nodes > MAX_EVALUATION_NODES or time.monotonic() - self.started > MAX_EVALUATION_SECONDS:
            raise ValueError("Deterministic computation work limit exceeded")
        if self.budget and self.budget.remaining_seconds <= self.budget.finalization_reserve_seconds:
            self.budget._raise_budget_failure("Scientific validation reached the finalization window.")


def evaluate(node: Node, environment: dict, _depth=0, *, guard=None):
    guard = guard or ExecutionGuard()
    guard.check()
    if _depth > MAX_DEPTH:
        raise ValueError("AST depth exceeded")
    run = lambda x: evaluate(x, environment, _depth + 1, guard=guard)
    if node.kind == "literal" and not node.args:
        return finite(node.value)
    if node.kind == "variable" and not node.args and isinstance(node.value, str) and IDENTIFIER.fullmatch(node.value):
        if node.value not in environment:
            raise ValueError("Unbound scientific variable")
        return finite(environment[node.value])
    if node.kind == "array" and node.args:
        return finite([run(x) for x in node.args])
    if node.kind == "call":
        return apply(node.value, [run(x) for x in node.args])
    if node.kind == "index" and len(node.args) == 1 and type(node.value) is int and node.value >= 0:
        value = run(node.args[0])
        if not isinstance(value, list) or node.value >= len(value):
            raise ValueError("Invalid scientific array index")
        return value[node.value]
    if node.kind == "compare" and node.value in COMPARISONS and len(node.args) == 2:
        left, right = [run(x) for x in node.args]
        if isinstance(left, list) or isinstance(right, list):
            raise ValueError("Comparison requires scalars; use approx_equal for arrays")
        return COMPARISONS[node.value](left, right)
    if node.kind in {"and", "or", "not", "if"}:
        if node.kind == "if" and len(node.args) == 3:
            condition = run(node.args[0])
            if type(condition) is not bool:
                raise ValueError("Conditional requires boolean")
            return run(node.args[1] if condition else node.args[2])
        if node.kind == "not" and len(node.args) == 1:
            value = run(node.args[0])
            if type(value) is not bool:
                raise ValueError("Negation requires boolean")
            return not value
        if node.kind in {"and", "or"} and len(node.args) >= 2:
            values = [run(x) for x in node.args]
            if any(type(x) is not bool for x in values):
                raise ValueError("Boolean operation requires booleans")
            return all(values) if node.kind == "and" else any(values)
    raise ValueError("Invalid canonical AST")


def compile_computations(ir):
    """Return a new IR. metadata canonical_ast/version are deterministic, never trusted."""
    specs = []
    for spec in ir.computations:
        metadata = dict(spec.metadata)
        kind = metadata.get("kind", "expression")
        if kind not in KIND_METADATA or not set(metadata) <= KIND_METADATA[kind]:
            raise ValueError("Unknown computation metadata or custom code")
        bindings = metadata.get("bindings", {})
        if not isinstance(bindings, dict) or not all(isinstance(k, str) and IDENTIFIER.fullmatch(k) and isinstance(v, str) for k, v in bindings.items()):
            raise ValueError("Bindings must map safe DSL names to stable IDs")
        if kind == "expression":
            node = parse(spec.expression)
            metadata["canonical_ast"] = node.to_dict()
        elif kind == "iteration":
            initial = metadata.get("initial", {})
            updates = metadata.get("updates", {})
            steps = metadata.get("steps")
            if not isinstance(initial, dict) or not isinstance(updates, dict) or not initial or set(initial) != set(updates) or type(steps) is not int or not 1 <= steps <= MAX_ITERATIONS:
                raise ValueError("Invalid bounded iteration")
            if not all(IDENTIFIER.fullmatch(x) for x in initial):
                raise ValueError("Invalid iteration state names")
            metadata["initial_ast"] = {k: parse(v).to_dict() for k, v in initial.items()}
            metadata["update_ast"] = {k: parse(v).to_dict() for k, v in updates.items()}
            metadata["canonical_ast"] = parse(spec.expression).to_dict()
            state_specs = metadata.get("state_specs", {})
            if not isinstance(state_specs, dict) or not set(state_specs) <= initial.keys():
                raise ValueError("Invalid local state declarations")
            for declaration in state_specs.values():
                if not isinstance(declaration, dict) or not set(declaration) <= {"type", "shape", "domain"} or "type" not in declaration:
                    raise ValueError("Invalid local state type/shape/domain contract")
            state_invariants = metadata.get("state_invariants", [])
            if not isinstance(state_invariants, list) or len(state_invariants) > 16:
                raise ValueError("State invariants must be a bounded list")
            metadata["state_invariant_ast"] = [parse(text).to_dict() for text in state_invariants]
        elif kind == "state_transition":
            states = metadata.get("states", [])
            transitions = metadata.get("transitions", [])
            if not isinstance(states, list) or not states or not all(isinstance(s, str) for s in states) or len(set(states)) != len(states):
                raise ValueError("Invalid finite states")
            if metadata.get("initial_state") not in states or not isinstance(transitions, list) or len(transitions) > MAX_ITERATIONS:
                raise ValueError("Invalid state-transition bounds")
            steps = metadata.get("steps", 1)
            if type(steps) is not int or not 1 <= steps <= MAX_ITERATIONS:
                raise ValueError("Invalid state-transition steps")
            compiled = []
            for transition in transitions:
                if not isinstance(transition, dict) or set(transition) != {"from", "to", "when"} or transition["from"] not in states or transition["to"] not in states:
                    raise ValueError("Invalid finite transition")
                compiled.append({**transition, "condition_ast": parse(transition["when"]).to_dict()})
            metadata["transition_ast"] = compiled
        else:
            raise ValueError("Unsupported computation kind; custom code is disabled")
        metadata["ast_version"] = AST_VERSION
        specs.append(replace(spec, metadata=metadata))
    return replace(ir, computations=tuple(specs))


def computation_references(spec):
    meta = spec.metadata
    kind = meta.get("kind", "expression")
    refs = set()
    if kind in {"expression", "iteration"}:
        refs.update(Node.from_dict(meta["canonical_ast"]).references)
    if kind == "iteration":
        local = set(meta["initial"])
        refs -= local
        # Initial state expressions cannot refer to uninitialized local state.
        for node in meta["initial_ast"].values():
            initial_refs = Node.from_dict(node).references
            if initial_refs & local:
                raise ValueError("Initial state cannot refer to local update variables")
            refs.update(initial_refs)
        for node in meta["update_ast"].values():
            refs.update(Node.from_dict(node).references - local)
        for node in meta.get("state_invariant_ast", []):
            refs.update(Node.from_dict(node).references - local)
    if kind == "state_transition":
        for transition in meta["transition_ast"]:
            refs.update(Node.from_dict(transition["condition_ast"]).references)
        refs.discard("state")
    return frozenset(refs)


def execute_spec(spec, env, *, guard=None):
    guard = guard or ExecutionGuard()
    run = lambda node, context: evaluate(Node.from_dict(node), context, guard=guard)
    meta = spec.metadata
    kind = meta.get("kind", "expression")
    history = []
    if kind == "iteration":
        local = {k: run(v, env) for k, v in meta["initial_ast"].items()}
        from playground.computation.operations import shape
        initial_shapes = {k: shape(v) for k, v in local.items()}
        initial_types = {k: "boolean" if type(v) is bool else "categorical" if isinstance(v, str) else
                         "matrix" if len(shape(v)) == 2 else "vector" if isinstance(v, list) else "scalar"
                         for k, v in local.items()}
        def validate_local(state):
            for name, value in state.items():
                declaration = meta.get("state_specs", {}).get(name, {})
                validate_value(value, declaration.get("type", initial_types[name]),
                               declaration.get("shape", initial_shapes[name]), declaration.get("domain"))
            for node in meta.get("state_invariant_ast", []):
                result = run(node, {**env, **state})
                if type(result) is not bool or not result:
                    raise ValueError("Iterative state invariant failed")
        validate_local(local)
        history.append(dict(local))
        for _ in range(meta["steps"]):
            snapshot = {**env, **local}
            local = {k: run(v, snapshot) for k, v in meta["update_ast"].items()}
            validate_local(local)
            history.append(dict(local))
        result = run(meta["canonical_ast"], {**env, **local})
    elif kind == "state_transition":
        state = meta["initial_state"]
        history.append(state)
        for _ in range(meta.get("steps", 1)):
            active = []
            for transition in meta["transition_ast"]:
                if transition["from"] == state:
                    condition = run(transition["condition_ast"], {**env, "state": state})
                    if type(condition) is not bool:
                        raise ValueError("State guard must be boolean")
                    if condition:
                        active.append(transition["to"])
            if len(active) > 1:
                raise ValueError("Ambiguous active state transitions")
            state = active[0] if active else state
            history.append(state)
        result = state
    else:
        result = run(meta["canonical_ast"], env)
    validate_value(result, spec.output_type)
    return result, history


def execute(ir, inputs: dict, *, guard=None):
    """Topologically execute; expressions bind stable DSL names from metadata bindings.

    bindings maps Python-safe symbol -> variable ID or predecessor computation ID.
    output_refs assign the single computation result to declared scientific variables.
    """
    values = dict(inputs)
    guard = guard or ExecutionGuard()
    variables = {v.id: v for v in ir.scientific_model.variables}
    symbolic_dimensions = {}
    def validate_variable(var, value):
        from playground.computation.operations import shape
        validate_value(value, var.type, var.shape, var.domain)
        if var.shape:
            for expected, actual in zip(var.shape, shape(value)):
                if isinstance(expected, str):
                    if expected in symbolic_dimensions and symbolic_dimensions[expected] != actual:
                        raise ValueError("Symbolic shape dimension mismatch")
                    symbolic_dimensions[expected] = actual
    for key, value in values.items():
        if key not in variables:
            raise ValueError("Unknown scientific input")
        var = variables[key]
        validate_variable(var, value)
    pending = {s.id: s for s in ir.computations}
    if len(pending) != len(ir.computations):
        raise ValueError("Duplicate computation IDs")
    histories = {}
    while pending:
        ready = [s for s in pending.values() if all(d in values for d in s.dependencies)]
        if not ready:
            raise ValueError("Cyclic or missing computation dependency")
        for spec in ready:
            bindings = spec.metadata.get("bindings", {})
            if set(bindings) != computation_references(spec):
                raise ValueError("Every DSL symbol requires exactly one explicit binding")
            if any(not IDENTIFIER.fullmatch(k) for k in bindings) or any(v not in values for v in bindings.values()):
                raise ValueError("Unresolved scientific binding")
            guard.check()
            result, history = execute_spec(spec, {k: values[v] for k, v in bindings.items()}, guard=guard)
            values[spec.id] = result
            for output in spec.output_refs:
                if output not in variables:
                    raise ValueError("Unknown output variable")
                var = variables[output]
                validate_variable(var, result)
                values[output] = result
            if history:
                histories[spec.id] = history
            del pending[spec.id]
    return values, histories
