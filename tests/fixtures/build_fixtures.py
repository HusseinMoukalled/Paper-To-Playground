"""Regenerate test data from independent Python expected results (dev only)."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from tests.fixtures.runtime_fixtures import binary, call, constant, fixture_ir, matrix, variable, vector


def parity_cases():
    cases = []

    def add(name, ast, expected, state=None, operation=True):
        cases.append({'name': name, 'ast': ast, 'state': state or {}, 'expected': expected, 'operation': operation})

    v = vector(*(constant(x) for x in [1, 2, 3]))
    w = vector(*(constant(x) for x in [4, 5, 6]))
    m = matrix([[constant(1), constant(2)], [constant(3), constant(4)]])
    identity = matrix([[constant(1), constant(0)], [constant(0), constant(1)]])
    for name, a, b, expected in [('add', 2, 3, 2 + 3), ('subtract', 2, 3, 2 - 3), ('multiply', 2, 3, 2 * 3), ('divide', 2, 3, 2 / 3), ('power', 2, 3, 2 ** 3)]:
        add(name, call(name, constant(a), constant(b)), expected)
    for name, value, expected in [('sqrt', 9, math.sqrt(9)), ('exp', 2, math.exp(2)), ('log', 2, math.log(2)), ('abs', -2, abs(-2))]:
        add(name, call(name, constant(value)), expected)
    for name, expected in [('min', min([1, 2, 3])), ('max', max([1, 2, 3])), ('sum', sum([1, 2, 3])), ('mean', sum([1, 2, 3]) / 3), ('variance', sum((x - 2) ** 2 for x in [1, 2, 3]) / 3), ('normalize', [x / 6 for x in [1, 2, 3]]), ('norm', math.sqrt(14)), ('argmax', 2)]:
        add(name, call(name, v), expected)
    add('softmax', call('softmax', vector(constant(1000), constant(1001))), [1 / (1 + math.exp(1)), math.exp(1) / (1 + math.exp(1))])
    add('sigmoid', call('sigmoid', vector(constant(-1000), constant(0), constant(1000))), [0, .5, 1])
    add('dot', call('dot', v, w), sum(x * y for x, y in zip([1, 2, 3], [4, 5, 6])))
    add('matmul', call('matmul', m, identity), [[1, 2], [3, 4]])
    add('transpose', call('transpose', m), [[1, 3], [2, 4]])
    add('distance', call('distance', v, w), math.sqrt(27))
    add('clip', call('clip', v, constant(1.5), constant(2.5)), [1.5, 2, 2.5])
    add('broadcast-vector', binary('*', v, constant(2)), [2, 4, 6], operation=False)
    add('broadcast-matrix', binary('+', m, constant(2)), [[3, 4], [5, 6]], operation=False)
    add('matmul-vector', call('matmul', m, vector(constant(2), constant(3))), [8, 18], operation=False)
    add('matmul-left-vector', call('matmul', vector(constant(2), constant(3)), m), [11, 16], operation=False)
    add('variable', variable('x'), 4, {'x': 4}, False)
    add('unary-minus', {'type': 'Unary', 'op': '-', 'operand': v}, [-1, -2, -3], operation=False)
    add('unary-plus', {'type': 'Unary', 'op': '+', 'operand': constant(3)}, 3, operation=False)
    add('index', {'type': 'Index', 'value': m, 'index': constant(1)}, [3, 4], operation=False)
    add('conditional-lazy', {'type': 'Conditional', 'condition': binary('>', constant(3), constant(2)), 'then': constant(5), 'else': binary('/', constant(1), constant(0))}, 5, operation=False)
    for op, expected in [('<', False), ('<=', False), ('>', True), ('>=', True), ('==', False), ('!=', True)]:
        add('comparison-' + op, binary(op, constant(3), constant(2)), expected, operation=False)
    return cases


def main():
    here = Path(__file__).parent
    for family in ('scalar_relationship', 'distribution', 'matrix_transformation', 'signal_transformation', 'state_transition'):
        (here / (family + '.json')).write_text(json.dumps(asdict(fixture_ir(family)), indent=2) + '\n', encoding='utf-8')
    (here / 'ast_parity.json').write_text(json.dumps(parity_cases(), indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
