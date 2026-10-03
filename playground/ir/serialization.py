"""Strict adapters around the unchanged Milestone 0 dataclasses."""
from __future__ import annotations

from dataclasses import fields, is_dataclass, MISSING
from enum import Enum
import json
import math
import re
import types
from typing import Any, get_args, get_origin, get_type_hints, Union

from playground.ir.models import ExplanationIR

MAX_JSON_BYTES = 250_000


def to_mapping(value):
    if is_dataclass(value):
        return {f.name: to_mapping(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [to_mapping(x) for x in value]
    if isinstance(value, dict):
        return {k: to_mapping(v) for k, v in value.items()}
    return value


def decode(cls, value, path="$", depth=0):
    if depth > 40:
        raise ValueError("Schema nesting limit exceeded")
    origin, args = get_origin(cls), get_args(cls)
    child = lambda typ, item, label: decode(typ, item, label, depth + 1)
    if cls is Any:
        if value is None or type(value) in {str, bool, int}:
            return value
        if type(value) is float and math.isfinite(value):
            return value
        if isinstance(value, list):
            return [child(Any, x, path) for x in value]
        if isinstance(value, dict) and all(isinstance(k, str) for k in value):
            return {k: child(Any, v, path) for k, v in value.items()}
        raise ValueError(f"Invalid JSON value at {path}")
    if origin in {Union, types.UnionType}:
        for typ in args:
            try:
                return child(typ, value, path)
            except ValueError:
                pass
        raise ValueError(f"Invalid nullable/union field at {path}")
    if cls is type(None):
        if value is not None:
            raise ValueError(f"Expected null at {path}")
        return None
    if origin is tuple:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"Expected array at {path}")
        return tuple(child(args[0], x, path) for x in value)
    if origin is dict:
        if not isinstance(value, dict):
            raise ValueError(f"Expected object at {path}")
        return {child(args[0], k, path): child(args[1], v, path) for k, v in value.items()}
    if isinstance(cls, type) and issubclass(cls, Enum):
        try:
            return cls(value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid enum at {path}") from None
    if is_dataclass(cls):
        if not isinstance(value, dict):
            raise ValueError(f"Expected contract object at {path}")
        names = {f.name for f in fields(cls)}
        if set(value) - names:
            raise ValueError(f"Unknown schema fields at {path}")
        hints = get_type_hints(cls)
        result = {}
        for f in fields(cls):
            if f.name in value:
                result[f.name] = child(hints[f.name], value[f.name], path + "." + f.name)
            elif f.default is MISSING and f.default_factory is MISSING:
                raise ValueError(f"Missing field at {path}.{f.name}")
        try:
            return cls(**result)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid contract at {path}") from None
    if cls is float and type(value) in {int, float} and math.isfinite(value):
        return float(value)
    if type(value) is cls:
        return value
    raise ValueError(f"Invalid field type at {path}")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_json(content: str):
    """Recover only a single fenced JSON value and commas outside strings."""
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Model JSON is absent or oversized")
    text = content.strip().lstrip("\ufeff")
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1)
    def load(s):
        return json.loads(s, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    try:
        return load(text)
    except json.JSONDecodeError:
        result, quoted, escaped = [], False, False
        for i, char in enumerate(text):
            if not quoted and char == "," and text[i + 1:].lstrip().startswith(("}", "]")):
                continue
            result.append(char)
            if char == '"' and not escaped:
                quoted = not quoted
            escaped = quoted and char == "\\" and not escaped
        try:
            return load("".join(result))
        except (json.JSONDecodeError, RecursionError):
            raise ValueError("Malformed model JSON after conservative recovery") from None


def load_ir(content: str) -> ExplanationIR:
    return decode(ExplanationIR, parse_json(content))


def schema_contract(cls):
    """Compact field/type contract derived from the actual shared dataclasses."""
    seen, result = set(), {}
    def visit(typ):
        if is_dataclass(typ) and typ not in seen:
            seen.add(typ)
            hints = get_type_hints(typ)
            result[typ.__name__] = {f.name: str(hints[f.name]).replace("playground.ir.models.", "") for f in fields(typ)}
            for hint in hints.values():
                visit(hint)
        else:
            for arg in get_args(typ):
                visit(arg)
    visit(cls)
    return result
