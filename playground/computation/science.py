"""Conservative equation-to-executable-AST consistency, never textbook correction."""
from playground.computation.ast import Node, MAX_DEPTH, MAX_NODES
from playground.computation.parser import parse, IDENTIFIER


def _bind(node, symbols):
    if node.kind == "variable":
        if node.value not in symbols:
            raise ValueError("Equation contains an unmapped scientific symbol")
        return Node("variable", symbols[node.value])
    return Node(node.kind, node.value, tuple(_bind(x, symbols) for x in node.args))


def check_equation_consistency(ir):
    """Direct links match canonical math modulo symbol renaming and declared DAG substitution.

    Context-only equations require explicit metadata.equation_scope[id]='context_only'.
    Algebraically different rewrites are not automatically asserted equivalent.
    """
    variables = {v.id: v for v in ir.scientific_model.variables}
    equations = {q.id: q for q in ir.scientific_model.equations}
    producers = {}
    for computation in ir.computations:
        for identity in (computation.id, *computation.output_refs):
            if identity in producers:
                raise ValueError('Ambiguous equation producer')
            producers[identity] = computation

    def expanded(node, owner, trail=(), depth=0, work=None):
        # Exact substitution of explicitly declared expression DAG edges is
        # not algebraic simplification. Cap work to reject cycles/AST blow-up.
        work = [0] if work is None else work
        work[0] += 1
        if depth > MAX_DEPTH or work[0] > MAX_NODES:
            raise ValueError('Equation dependency expansion exceeds bounds')
        if node.kind == 'variable' and node.value in producers:
            producer = producers[node.value]
            if producer.id != owner.id:
                if producer.id in trail or producer.id not in owner.dependencies:
                    raise ValueError('Equation producer is cyclic or undeclared')
                if producer.metadata.get('kind', 'expression') != 'expression':
                    raise ValueError('Cannot inline iterative/state computation into an equation')
                bound = _bind(parse(producer.expression), producer.metadata.get('bindings', {}))
                return expanded(bound, producer, (*trail, owner.id), depth + 1, work)
        return Node(node.kind, node.value, tuple(expanded(x, owner, trail, depth + 1, work) for x in node.args))

    linked = set()
    for spec in ir.computations:
        equation_refs = spec.metadata.get("equation_refs", [])
        if not isinstance(equation_refs, list) or not set(equation_refs) <= equations.keys():
            raise ValueError("Computation references unknown scientific equation")
        if not equation_refs:
            continue
        if spec.metadata.get("kind", "expression") != "expression":
            raise ValueError("Direct equation links apply only to expression computations")
        actual = _bind(parse(spec.expression), spec.metadata.get("bindings", {}))
        for ref in equation_refs:
            equation = equations[ref]
            expression = equation.expression
            if "=" in expression and not any(op in expression for op in ("==", "<=", ">=", "!=")):
                lhs, separator, rhs = expression.partition("=")
                if not IDENTIFIER.fullmatch(lhs.strip()) or "=" in rhs:
                    raise ValueError("Unsupported equation notation")
                expression = rhs.strip()
                output_symbols = {variables[v].source_symbol or variables[v].display_symbol for v in spec.output_refs}
                if lhs.strip() not in output_symbols:
                    raise ValueError("Equation left-hand side does not match computation output")
            symbols = {}
            for var_id in equation.variable_refs:
                var = variables[var_id]
                symbol = var.source_symbol or var.display_symbol
                if symbol in symbols and symbols[symbol] != var_id:
                    raise ValueError("Ambiguous source symbols")
                symbols[symbol] = var_id
            expected = _bind(parse(expression), symbols)
            if expanded(expected, spec) != expanded(actual, spec):
                raise ValueError("Scientific equation differs from executable canonical AST")
            linked.add(ref)
    context_only = ir.metadata.get("equation_scope", {})
    if not isinstance(context_only, dict) or not set(context_only) <= equations.keys():
        raise ValueError("Invalid context-only equation scope")
    if any(context_only.get(ref) != "context_only" for ref in equations.keys() - linked):
        raise ValueError("Scientific equations require executable linkage or explicit context-only scope")
