"""Small explicit operation registry; exact shapes, finite values, stable numerics."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Any

from playground.computation.ast import MAX_ITEMS
from playground.config import NUMERIC_TOLERANCE


def shape(value: Any) -> tuple[int, ...]:
    if not isinstance(value, list):
        return ()
    if not value or len(value) > MAX_ITEMS:
        raise ValueError("Empty or oversized scientific array")
    children = [shape(x) for x in value]
    if any(x != children[0] for x in children):
        raise ValueError("Ragged scientific array")
    result = (len(value),) + children[0]
    if math.prod(result) > MAX_ITEMS or len(result) > 2:
        raise ValueError("Array shape exceeds runtime capabilities")
    return result


def leaves(value):
    if isinstance(value, list):
        for x in value:
            yield from leaves(x)
    else:
        yield value


def finite(value):
    shape(value)
    for x in leaves(value):
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            if abs(x) > 1e300 or not math.isfinite(x):
                raise ValueError("Nonfinite or oversized numeric value")
        elif not isinstance(x, (bool, str)):
            raise ValueError("Unsupported scientific value")
    return value


def numeric(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError("Expected a number")
    finite(x)
    return x


def unary(fn, x):
    return [unary(fn, y) for y in x] if isinstance(x, list) else fn(numeric(x))


def binary(fn, a, b):
    if isinstance(a, list) and isinstance(b, list):
        if shape(a) != shape(b):
            raise ValueError("Shape mismatch (only scalar broadcasting is allowed)")
        return [binary(fn, x, y) for x, y in zip(a, b)]
    if isinstance(a, list):
        return [binary(fn, x, b) for x in a]
    if isinstance(b, list):
        return [binary(fn, a, y) for y in b]
    return fn(numeric(a), numeric(b))


def vector(x):
    if len(shape(x)) != 1:
        raise ValueError("Expected a vector")
    return [numeric(y) for y in x]


def total(x):
    return math.fsum(numeric(y) for y in leaves(x))


def dot(a, b):
    a, b = vector(a), vector(b)
    if len(a) != len(b):
        raise ValueError("Dot product shape mismatch")
    return math.fsum(x * y for x, y in zip(a, b))


def transpose(a):
    if len(shape(a)) != 2:
        raise ValueError("Expected a matrix")
    for entry in leaves(a):
        numeric(entry)
    return [list(row) for row in zip(*a)]


def matmul(a, b):
    sa, sb = shape(a), shape(b)
    if len(sa) != 2 or len(sb) not in (1, 2) or sa[1] != sb[0]:
        raise ValueError("Matrix multiplication shape mismatch")
    if len(sb) == 1:
        return [dot(row, b) for row in a]
    return [[dot(row, col) for col in transpose(b)] for row in a]


def softmax(x):
    x = vector(x)
    peak = max(x)
    terms = [math.exp(y - peak) for y in x]
    z = math.fsum(terms)
    return [y / z for y in terms]


def normalize(x):
    x = vector(x)
    norm = math.hypot(*x)
    if norm == 0:
        raise ValueError("Cannot normalize a zero vector")
    return [y / norm for y in x]


def entropy(x):
    x = vector(x)
    if any(y < 0 or y > 1 for y in x) or not math.isclose(total(x), 1, abs_tol=NUMERIC_TOLERANCE):
        raise ValueError("Entropy requires a probability distribution")
    return -math.fsum(y * math.log(y) for y in x if y > 0)


def power(a, b):
    if abs(b) > 128 or (a == 0 and b < 0) or (a < 0 and not float(b).is_integer()):
        raise ValueError("Power outside the real bounded domain")
    return a ** b


def approx_equal(a, b):
    if shape(a) != shape(b):
        return False
    return all(math.isclose(numeric(x), numeric(y), rel_tol=NUMERIC_TOLERANCE,
                            abs_tol=NUMERIC_TOLERANCE) for x, y in zip(leaves(a), leaves(b)))


@dataclass(frozen=True)
class Operation:
    arity: int
    function: Callable
    purpose: str


OPERATIONS = {
    "add": Operation(2, lambda a, b: binary(lambda x, y: x + y, a, b), "elementwise addition"),
    "subtract": Operation(2, lambda a, b: binary(lambda x, y: x - y, a, b), "elementwise subtraction"),
    "multiply": Operation(2, lambda a, b: binary(lambda x, y: x * y, a, b), "elementwise product"),
    "divide": Operation(2, lambda a, b: binary(lambda x, y: x / y, a, b), "real nonzero division"),
    "power": Operation(2, lambda a, b: binary(power, a, b), "bounded real power"),
    "negate": Operation(1, lambda x: unary(lambda y: -y, x), "elementwise negation"),
    "abs": Operation(1, lambda x: unary(abs, x), "absolute value"),
    "sqrt": Operation(1, lambda x: unary(math.sqrt, x), "nonnegative square root"),
    "exp": Operation(1, lambda x: unary(math.exp, x), "exponential"),
    "log": Operation(1, lambda x: unary(math.log, x), "positive natural logarithm"),
    "sin": Operation(1, lambda x: unary(math.sin, x), "sine in radians"),
    "cos": Operation(1, lambda x: unary(math.cos, x), "cosine in radians"),
    "sum": Operation(1, total, "sum all entries"),
    "mean": Operation(1, lambda x: total(x) / len(list(leaves(x))), "mean all entries"),
    "min": Operation(1, lambda x: min(vector(x)), "vector minimum"),
    "max": Operation(1, lambda x: max(vector(x)), "vector maximum"),
    "dot": Operation(2, dot, "vector inner product"),
    "matmul": Operation(2, matmul, "matrix-vector or matrix-matrix product"),
    "transpose": Operation(1, transpose, "matrix transpose"),
    "norm": Operation(1, lambda x: math.hypot(*vector(x)), "stable Euclidean norm"),
    "normalize": Operation(1, normalize, "unit Euclidean vector"),
    "softmax": Operation(1, softmax, "stable probability distribution"),
    "entropy": Operation(1, entropy, "distribution entropy in nats, 0 log 0 = 0"),
    "approx_equal": Operation(2, approx_equal, "tolerance-based equality"),
}


def apply(name, args):
    op = OPERATIONS.get(name)
    if op is None or len(args) != op.arity:
        raise ValueError("Unknown operation or invalid arity")
    for argument in args:
        finite(argument)
    return finite(op.function(*args))


TYPES = {"scalar", "boolean", "categorical", "vector", "matrix", "sequence", "state", "distribution"}
DOMAINS = {None, "real", "positive", "nonnegative", "unit_interval", "probability", "integer"}


def validate_value(value, type_name, expected_shape=(), domain=None):
    finite(value)
    actual = shape(value)
    if type_name not in TYPES or domain not in DOMAINS:
        raise ValueError("Unsupported scientific type or domain")
    if type_name == "boolean" and type(value) is not bool:
        raise ValueError("Expected boolean")
    if type_name in {"categorical", "state"} and not isinstance(value, str):
        raise ValueError("Expected a categorical state string")
    if type_name == "scalar" and (actual or isinstance(value, (str, bool))):
        raise ValueError("Expected scalar")
    ranks = {"vector": 1, "distribution": 1, "matrix": 2}
    if type_name in ranks and len(actual) != ranks[type_name]:
        raise ValueError("Scientific rank mismatch")
    if type_name == "sequence" and not actual:
        raise ValueError("Expected a sequence")
    if expected_shape and (len(actual) != len(expected_shape) or any(
            isinstance(b, int) and a != b for a, b in zip(actual, expected_shape))):
        raise ValueError("Declared shape mismatch")
    if type_name not in {"boolean", "categorical", "state"}:
        for x in leaves(value):
            numeric(x)
            if domain == "positive" and x <= 0 or domain == "nonnegative" and x < 0:
                raise ValueError("Scientific domain violated")
            if domain in {"unit_interval", "probability"} and not 0 <= x <= 1:
                raise ValueError("Probability domain violated")
            if domain == "integer" and not float(x).is_integer():
                raise ValueError("Integer domain violated")
    if type_name == "distribution" and (any(x < 0 for x in value) or not math.isclose(
            total(value), 1, rel_tol=NUMERIC_TOLERANCE, abs_tol=NUMERIC_TOLERANCE)):
        raise ValueError("Distribution must be nonnegative and sum to one")
