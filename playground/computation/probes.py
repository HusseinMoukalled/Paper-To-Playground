"""Independent, bounded shape-preserving probes for editable numeric arrays."""
from copy import deepcopy


def array_probes(control, variable):
    original = control['default']
    if control['control_type'] not in {'vector', 'matrix'}:
        return []
    matrix = control['control_type'] == 'matrix'
    positions = [(i, j) for i, row in enumerate(original) for j in range(len(row))] if matrix else [(i,) for i in range(len(original))]
    result = []
    if (variable['type'] == 'distribution' and not matrix and variable.get('domain') != 'positive'
            and (control['minimum'] is None or control['minimum'] <= 0)
            and (control['maximum'] is None or control['maximum'] >= 1)):
        for i in sorted({0, len(original) // 2, len(original) - 1}):
            candidate = [1.0 if j == i else 0.0 for j in range(len(original))]
            if candidate != original:
                result.append(candidate)
    sampled = [positions[i] for i in sorted({0, len(positions) // 2, len(positions) - 1})] if positions else []
    for position in sampled:
        old = original[position[0]][position[1]] if matrix else original[position[0]]
        amount = max(1 if variable.get('domain') == 'integer' else 0.25, abs(old) * 0.25)
        for delta in (amount, -amount):
            value = old + delta
            lo, hi = control['minimum'], control['maximum']
            if lo is not None:
                value = max(value, lo)
            if hi is not None:
                value = min(value, hi)
            if variable.get('domain') in {'nonnegative', 'positive', 'probability', 'unit_interval'}:
                value = max(value, 1e-6 if variable.get('domain') == 'positive' else 0)
            if variable.get('domain') == 'unit_interval':
                value = min(value, 1)
            if variable.get('domain') == 'integer':
                value = round(value)
            candidate = deepcopy(original)
            if matrix:
                candidate[position[0]][position[1]] = value
            elif variable['type'] == 'distribution' and control['validation_rule'] != 'normalize':
                # Transfer mass rather than breaking the probability simplex.
                if len(candidate) < 2:
                    continue
                other = (position[0] + 1) % len(candidate)
                transfer = max(-old, min(value - old, candidate[other]))
                candidate[position[0]] += transfer
                candidate[other] -= transfer
            else:
                candidate[position[0]] = value
            if not matrix and control['validation_rule'] == 'normalize':
                from playground.computation.operations import normalize
                if variable['type'] == 'distribution':
                    total = sum(candidate)
                    if total <= 0:
                        continue
                    candidate = [x / total for x in candidate]
                else:
                    try:
                        candidate = normalize(candidate)
                    except ValueError:
                        continue
            if candidate != original and candidate not in result:
                result.append(candidate)
    return result
