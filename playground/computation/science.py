"""Conservative equation-to-executable-AST consistency, never textbook correction."""
from playground.computation.ast import Node
from playground.computation.parser import parse, IDENTIFIER


def _bind(node, symbols):
    if node.kind == "variable":
        if node.value not in symbols:
            raise ValueError("Equation contains an unmapped scientific symbol")
        return Node("variable", symbols[node.value])
    return Node(node.kind, node.value, tuple(_bind(x, symbols) for x in node.args))


def check_equation_consistency(ir):
    """Direct links must match the canonical math, modulo explicit symbol renaming.

    Context-only equations require explicit metadata.equation_scope[id]='context_only'.
    Algebraically different rewrites are not automatically asserted equivalent.
    """
    variables = {v.id: v for v in ir.scientific_model.variables}
    equations = {q.id: q for q in ir.scientific_model.equations}
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
                output_symbols = {symbol for v in spec.output_refs for symbol in
                                  (variables[v].source_symbol, variables[v].display_symbol) if symbol}
                if lhs.strip() not in output_symbols:
                    raise ValueError("Equation left-hand side does not match computation output")
            symbols = {}
            for var_id in equation.variable_refs:
                var = variables[var_id]
                for symbol in (var.source_symbol, var.display_symbol):
                    if symbol:
                        if symbol in symbols and symbols[symbol] != var_id:
                            raise ValueError("Ambiguous source symbols")
                        symbols[symbol] = var_id
            # Explicit compiler bindings also name safe DSL aliases for source
            # notation such as d_k. They must resolve to declared equation vars.
            for symbol, var_id in spec.metadata.get('bindings', {}).items():
                if var_id in equation.variable_refs:
                    if symbol in symbols and symbols[symbol] != var_id:
                        raise ValueError('Ambiguous equation binding alias')
                    symbols[symbol] = var_id
            expected = _bind(parse(expression), symbols)
            if expected != actual:
                raise ValueError("Scientific equation differs from executable canonical AST")
            linked.add(ref)
    context_only = ir.metadata.get("equation_scope", {})
    if not isinstance(context_only, dict) or not set(context_only) <= equations.keys():
        raise ValueError("Invalid context-only equation scope")
    if any(context_only.get(ref) != "context_only" for ref in equations.keys() - linked):
        raise ValueError("Scientific equations require executable linkage or explicit context-only scope")
