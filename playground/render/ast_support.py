"""Renderer-side consumer adapter; never parses or executes scientific DSL.

Milestone 0 has no concrete AST classes. The documented node vocabulary is
accepted here as JSON data in ComputationSpec.metadata['ast'], or supplied by
the producer in an explicit asts mapping. Keep producer adaptation at this
boundary; do not change scientific expressions inside the renderer.
"""

from __future__ import annotations

import math
from typing import Any

OPERATIONS = frozenset({
    'add', 'subtract', 'multiply', 'divide', 'power', 'sqrt', 'exp', 'log',
    'abs', 'min', 'max', 'sum', 'mean', 'variance', 'normalize', 'softmax',
    'sigmoid', 'dot', 'matmul', 'transpose', 'norm', 'distance', 'clip', 'argmax',
})
BINARY = frozenset({'+', '-', '*', '/', '**', '<', '<=', '>', '>=', '==', '!='})
FORBIDDEN_IDS = frozenset({'__proto__', 'prototype', 'constructor'})
MAX_AST_NODES = 4096
MAX_AST_DEPTH = 64


def validate_ast(node: Any) -> set[str]:
    """Validate the data-only wire tree and return its exact variable reads."""
    if isinstance(node, dict) and node.get('type') == 'Canonical':
        from playground.computation.evaluator import computation_references
        from playground.ir.models import ComputationSpec
        from playground.computation.ast import Node
        if set(node) != {'type', 'metadata', 'output_type'}:
            raise ValueError('Invalid canonical computation wrapper')
        meta = node['metadata']
        kind = meta.get('kind', 'expression')
        if kind not in {'expression', 'iteration', 'state_transition'}:
            raise ValueError('Unsupported canonical program')
        if kind != 'state_transition':
            Node.from_dict(meta['canonical_ast'])
        if kind == 'iteration':
            if type(meta.get('steps')) is not int or not 1 <= meta['steps'] <= 100:
                raise ValueError('Iteration bound invalid')
            if not meta['initial_ast'] or set(meta['initial_ast']) != set(meta['update_ast']):
                raise ValueError('Iteration state keys disagree')
            for tree in list(meta['initial_ast'].values()) + list(meta['update_ast'].values()) + meta.get('state_invariant_ast', []):
                Node.from_dict(tree)
        if kind == 'state_transition':
            if type(meta.get('steps', 1)) is not int or not 1 <= meta.get('steps', 1) <= 100:
                raise ValueError('State transition bound invalid')
            if meta['initial_state'] not in meta['states']:
                raise ValueError('Unknown initial state')
            for transition in meta['transition_ast']:
                if transition['from'] not in meta['states'] or transition['to'] not in meta['states']:
                    raise ValueError('Unknown transition state')
                Node.from_dict(transition['condition_ast'])
        refs = computation_references(ComputationSpec('wire', '', node['output_type'], metadata=meta))
        if set(meta.get('bindings', {})) != refs:
            raise ValueError('Canonical bindings disagree with AST reads')
        reads = set(meta['bindings'].values())
        if any(not isinstance(i, str) or not i or i in FORBIDDEN_IDS for i in reads):
            raise ValueError('Unsafe canonical binding')
        return reads
    reads: set[str] = set()
    count = 0

    def visit(n: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > MAX_AST_NODES or depth > MAX_AST_DEPTH:
            raise ValueError('AST exceeds bounded size or depth')
        if not isinstance(n, dict):
            raise ValueError('AST nodes must be objects')
        kind = n.get('type')
        fields: dict[str, set[str]] = {
            'Constant': {'type', 'value'}, 'Variable': {'type', 'id'},
            'Unary': {'type', 'op', 'operand'}, 'Binary': {'type', 'op', 'left', 'right'},
            'Call': {'type', 'function', 'args'}, 'Index': {'type', 'value', 'index'},
            'Vector': {'type', 'items'}, 'Matrix': {'type', 'rows'},
            'Conditional': {'type', 'condition', 'then', 'else'},
        }
        if kind not in fields or set(n) != fields[kind]:
            raise ValueError('Unsupported AST node or fields')
        if kind == 'Constant':
            value = n['value']
            if not isinstance(value, (int, float, bool, str)):
                raise ValueError('Constant must be scalar, boolean or categorical')
            if isinstance(value, (int, float)):
                try:
                    finite = math.isfinite(value)
                except OverflowError:
                    finite = False
                if not finite:
                    raise ValueError('AST constant is outside finite numeric range')
        elif kind == 'Variable':
            if not isinstance(n['id'], str) or not n['id'] or n['id'] in FORBIDDEN_IDS:
                raise ValueError('Invalid variable ID')
            reads.add(n['id'])
        elif kind == 'Unary':
            if n['op'] not in {'+', '-'}:
                raise ValueError('Unsupported unary operator')
            visit(n['operand'], depth + 1)
        elif kind == 'Binary':
            if n['op'] not in BINARY:
                raise ValueError('Unsupported binary operator')
            visit(n['left'], depth + 1)
            visit(n['right'], depth + 1)
        elif kind == 'Call':
            if n['function'] not in OPERATIONS or not isinstance(n['args'], list):
                raise ValueError('Unsupported scientific operation')
            for arg in n['args']:
                visit(arg, depth + 1)
        elif kind == 'Index':
            visit(n['value'], depth + 1)
            visit(n['index'], depth + 1)
        elif kind == 'Vector':
            if not isinstance(n['items'], list) or not n['items']:
                raise ValueError('Empty or invalid vector')
            for item in n['items']:
                visit(item, depth + 1)
        elif kind == 'Matrix':
            rows = n['rows']
            if (not isinstance(rows, list) or not rows or not all(isinstance(r, list) and r for r in rows)
                    or len({len(r) for r in rows}) != 1):
                raise ValueError('Ragged or empty matrix')
            for row in rows:
                for item in row:
                    visit(item, depth + 1)
        else:
            for key in ('condition', 'then', 'else'):
                visit(n[key], depth + 1)

    visit(node, 0)
    return reads


def computation_order(computations: list[dict], initial_ids: set[str]) -> list[dict]:
    """Topologically order computations by actual AST reads and declared deps."""
    pending = list(computations)
    available = set(initial_ids)
    done: set[str] = set()
    ordered: list[dict] = []
    while pending:
        ready = [c for c in pending if set(c['reads']) <= available and set(c['dependencies']) <= done]
        if not ready:
            raise ValueError('Unresolved variable, dependency or computation cycle')
        for computation in ready:
            pending.remove(computation)
            ordered.append(computation)
            done.add(computation['id'])
            available.update(computation['output_refs'])
    return ordered
