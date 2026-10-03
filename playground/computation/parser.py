"""Python syntax is parsed, never executed, then translated into our own AST."""
import ast as syntax
import re

from playground.computation.ast import Node, MAX_NODES, MAX_DEPTH
from playground.computation.operations import OPERATIONS, finite

MAX_EXPRESSION_LENGTH = 4096
IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
BIN = {syntax.Add: "add", syntax.Sub: "subtract", syntax.Mult: "multiply",
       syntax.Div: "divide", syntax.Pow: "power"}
CMP = {syntax.Lt: "lt", syntax.LtE: "le", syntax.Gt: "gt", syntax.GtE: "ge",
       syntax.Eq: "eq", syntax.NotEq: "ne"}


def parse(expression: str) -> Node:
    if not isinstance(expression, str) or not expression.strip() or len(expression) > MAX_EXPRESSION_LENGTH:
        raise ValueError("Expression must be nonempty and bounded")
    try:
        tree = syntax.parse(expression, mode="eval")
    except (SyntaxError, RecursionError, MemoryError):
        raise ValueError("Invalid mathematical syntax") from None
    count = 0

    def convert(item, depth=0):
        nonlocal count
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError("Expression complexity exceeded")
        child = lambda x: convert(x, depth + 1)
        if isinstance(item, syntax.Constant) and type(item.value) in {int, float, bool, str}:
            finite(item.value)
            if isinstance(item.value, str) and len(item.value) > 128:
                raise ValueError("Categorical constant too long")
            return Node("literal", item.value)
        if isinstance(item, syntax.Name) and IDENTIFIER.fullmatch(item.id):
            return Node("variable", item.id)
        if isinstance(item, (syntax.List, syntax.Tuple)) and item.elts:
            return Node("array", args=tuple(child(x) for x in item.elts))
        if isinstance(item, syntax.BinOp) and type(item.op) in BIN:
            return Node("call", BIN[type(item.op)], (child(item.left), child(item.right)))
        if isinstance(item, syntax.UnaryOp) and isinstance(item.op, (syntax.USub, syntax.UAdd, syntax.Not)):
            if isinstance(item.op, syntax.UAdd):
                return child(item.operand)
            return Node("not" if isinstance(item.op, syntax.Not) else "call",
                        None if isinstance(item.op, syntax.Not) else "negate", (child(item.operand),))
        if isinstance(item, syntax.Call) and isinstance(item.func, syntax.Name) and not item.keywords:
            name = item.func.id
            if name in OPERATIONS and len(item.args) == OPERATIONS[name].arity:
                return Node("call", name, tuple(child(x) for x in item.args))
        if isinstance(item, syntax.Compare) and len(item.ops) == 1 and type(item.ops[0]) in CMP:
            return Node("compare", CMP[type(item.ops[0])], (child(item.left), child(item.comparators[0])))
        if isinstance(item, syntax.BoolOp):
            return Node("and" if isinstance(item.op, syntax.And) else "or", args=tuple(child(x) for x in item.values))
        if isinstance(item, syntax.IfExp):
            return Node("if", args=(child(item.test), child(item.body), child(item.orelse)))
        if isinstance(item, syntax.Subscript) and isinstance(item.slice, syntax.Constant) and type(item.slice.value) is int and 0 <= item.slice.value < 4096:
            return Node("index", item.slice.value, (child(item.value),))
        raise ValueError("Construct is outside the scientific DSL whitelist")

    return convert(tree.body)
