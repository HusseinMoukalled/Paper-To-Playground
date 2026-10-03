"""Versioned, renderer-independent scientific AST. No executable source objects."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math
import re

AST_VERSION = 1
MAX_NODES = 256
MAX_DEPTH = 32
MAX_ITEMS = 4096


@dataclass(frozen=True, slots=True)
class Node:
    kind: str
    value: Any = None
    args: tuple[Node, ...] = ()

    def to_dict(self) -> dict:
        return {"kind": self.kind, "value": self.value,
                "args": [arg.to_dict() for arg in self.args]}

    @classmethod
    def from_dict(cls, data: dict) -> Node:
        count = 0

        def load(item: dict, depth: int) -> Node:
            nonlocal count
            count += 1
            if count > MAX_NODES or depth > MAX_DEPTH:
                raise ValueError("AST complexity limit exceeded")
            if not isinstance(item, dict) or set(item) != {"kind", "value", "args"}:
                raise ValueError("Invalid canonical AST fields")
            if not isinstance(item["args"], list):
                raise ValueError("AST args must be an array")
            kind, value, arguments = item["kind"], item["value"], item["args"]
            arities = {"literal": (0, 0), "variable": (0, 0), "array": (1, MAX_NODES),
                       "call": (1, 2), "compare": (2, 2), "index": (1, 1),
                       "and": (2, MAX_NODES), "or": (2, MAX_NODES), "not": (1, 1), "if": (3, 3)}
            if not isinstance(kind, str) or kind not in arities or not arities[kind][0] <= len(arguments) <= arities[kind][1]:
                raise ValueError("Invalid canonical node kind or arity")
            if kind == "literal":
                if type(value) not in {int, float, bool, str} or isinstance(value, str) and len(value) > 128:
                    raise ValueError("Invalid AST literal")
                if type(value) in {int, float} and (abs(value) > 1e300 or not math.isfinite(value)):
                    raise ValueError("Nonfinite AST literal")
            elif kind == "variable":
                if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", value):
                    raise ValueError("Invalid AST variable")
            elif kind == "call":
                # Local import prevents a dependency cycle with operation shape limits.
                from playground.computation.operations import OPERATIONS
                if not isinstance(value, str) or value not in OPERATIONS or len(arguments) != OPERATIONS[value].arity:
                    raise ValueError("Unknown AST operation")
            elif kind == "compare":
                if value not in ("lt", "le", "gt", "ge", "eq", "ne"):
                    raise ValueError("Invalid AST comparison")
            elif kind == "index":
                if type(value) is not int or not 0 <= value < MAX_ITEMS:
                    raise ValueError("Invalid AST index")
            elif value is not None:
                raise ValueError("Unexpected canonical AST value")
            return cls(kind, value, tuple(load(x, depth + 1) for x in arguments))

        return load(data, 0)

    @property
    def references(self) -> frozenset[str]:
        refs = {self.value} if self.kind == "variable" else set()
        for arg in self.args:
            refs.update(arg.references)
        return frozenset(refs)
