/* Data-only interpreter. No DSL parsing, generated code or network services. */
(function (root) {
  'use strict';
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const fail = message => { throw new Error(message); };
  const numeric = x => typeof x === 'number' && Number.isFinite(x);
  const finite = x => Array.isArray(x) ? x.length > 0 && x.every(finite) :
    numeric(x) || typeof x === 'boolean' || typeof x === 'string';
  const map = (a, fn) => Array.isArray(a) ? a.map(x => map(x, fn)) :
    numeric(a) ? fn(a) : fail('Numeric value required');
  const zip = (a, b, fn) => {
    if (Array.isArray(a) && Array.isArray(b)) {
      if (a.length !== b.length) fail('Shape mismatch');
      return a.map((x, i) => zip(x, b[i], fn));
    }
    if (Array.isArray(a)) return a.map(x => zip(x, b, fn));
    if (Array.isArray(b)) return b.map(x => zip(a, x, fn));
    if (!numeric(a) || !numeric(b)) fail('Numeric operands required');
    return fn(a, b);
  };
  const vector = x => {
    if (!Array.isArray(x) || !x.length || !x.every(numeric)) fail('Nonempty numeric vector required');
    return x;
  };
  const matrix = x => {
    if (!Array.isArray(x) || !x.length) fail('Matrix required');
    x.forEach(vector);
    if (!x.every(row => row.length === x[0].length)) fail('Ragged matrix');
    return x;
  };
  const sum = x => vector(x).reduce((a, b) => a + b, 0);
  const dot = (a, b) => {
    vector(a); vector(b);
    if (a.length !== b.length) fail('Dot product shape mismatch');
    return sum(a.map((x, i) => x * b[i]));
  };
  const transpose = a => matrix(a)[0].map((_, i) => a.map(row => row[i]));
  const arity = (args, n) => { if (args.length !== n) fail('Operation arity mismatch'); };
  const ops = Object.freeze({
    add: (a, b) => zip(a, b, (x, y) => x + y),
    subtract: (a, b) => zip(a, b, (x, y) => x - y),
    multiply: (a, b) => zip(a, b, (x, y) => x * y),
    divide: (a, b) => zip(a, b, (x, y) => y === 0 ? fail('Division by zero') : x / y),
    power: (a, b) => zip(a, b, (x, y) => x ** y),
    sqrt: a => map(a, x => x < 0 ? fail('Square root domain') : Math.sqrt(x)),
    exp: a => map(a, Math.exp),
    log: a => map(a, x => x <= 0 ? fail('Logarithm domain') : Math.log(x)),
    abs: a => map(a, Math.abs),
    min: a => Math.min(...vector(a)), max: a => Math.max(...vector(a)), sum,
    mean: a => sum(a) / a.length,
    variance: a => { const m = sum(a) / a.length; return sum(a.map(x => (x - m) ** 2)) / a.length; },
    normalize: a => { const s = sum(a); if (s === 0) fail('Zero normalization denominator'); return a.map(x => x / s); },
    softmax: a => { vector(a); const m = Math.max(...a); const e = a.map(x => Math.exp(x - m)); const s = sum(e); return e.map(x => x / s); },
    sigmoid: a => map(a, x => x >= 0 ? 1 / (1 + Math.exp(-x)) : Math.exp(x) / (1 + Math.exp(x))),
    dot, transpose,
    matmul: (a, b) => {
      const aMatrix = Array.isArray(a[0]), bMatrix = Array.isArray(b[0]);
      if (!aMatrix && !bMatrix) return dot(a, b);
      if (aMatrix && !bMatrix) return matrix(a).map(row => dot(row, b));
      if (!aMatrix && bMatrix) return transpose(b).map(col => dot(a, col));
      return matrix(a).map(row => transpose(b).map(col => dot(row, col)));
    },
    norm: a => Math.hypot(...vector(a)),
    distance: (a, b) => Math.hypot(...vector(zip(vector(a), vector(b), (x, y) => x - y))),
    clip: (a, lo, hi) => { if (!numeric(lo) || !numeric(hi) || lo > hi) fail('Invalid clip bounds'); return map(a, x => Math.max(lo, Math.min(hi, x))); },
    argmax: a => { vector(a); return a.indexOf(Math.max(...a)); },
  });
  const unaryOps = new Set(['sqrt', 'exp', 'log', 'abs', 'min', 'max', 'sum', 'mean', 'variance',
    'normalize', 'softmax', 'sigmoid', 'transpose', 'norm', 'argmax']);
  const evaluate = (node, state, depth = 0) => {
    if (depth > 64 || !node || typeof node !== 'object') fail('Invalid AST');
    const next = n => evaluate(n, state, depth + 1);
    let value;
    switch (node.type) {
      case 'Canonical': value = root.ScientificCanonical.execute(node, state).value; break;
      case 'Constant': value = node.value; break;
      case 'Variable': if (!own(state, node.id)) fail('Missing scientific variable'); value = state[node.id]; break;
      case 'Unary':
        if (!['+', '-'].includes(node.op)) fail('Unknown unary operator');
        value = map(next(node.operand), x => node.op === '-' ? -x : x); break;
      case 'Binary': {
        const a = next(node.left), b = next(node.right);
        const binary = {'+': 'add', '-': 'subtract', '*': 'multiply', '/': 'divide', '**': 'power'};
        if (own(binary, node.op)) value = ops[binary[node.op]](a, b);
        else {
          if (Array.isArray(a) || Array.isArray(b)) fail('Scalar comparison required');
          switch (node.op) {
            case '<': value = a < b; break; case '<=': value = a <= b; break;
            case '>': value = a > b; break; case '>=': value = a >= b; break;
            case '==': value = a === b; break; case '!=': value = a !== b; break;
            default: fail('Unknown binary operator');
          }
        }
        break;
      }
      case 'Call': {
        if (!own(ops, node.function)) fail('Unknown scientific operation');
        const args = node.args.map(next);
        arity(args, node.function === 'clip' ? 3 : unaryOps.has(node.function) ? 1 : 2);
        value = ops[node.function](...args); break;
      }
      case 'Index': {
        const a = next(node.value), i = next(node.index);
        if (!Array.isArray(a) || !Number.isInteger(i) || i < 0 || i >= a.length) fail('Index outside domain');
        value = a[i]; break;
      }
      case 'Vector': value = node.items.map(next); break;
      case 'Matrix': value = matrix(node.rows.map(row => row.map(next))); break;
      case 'Conditional': {
        const condition = next(node.condition);
        if (typeof condition !== 'boolean') fail('Conditional requires boolean');
        value = next(condition ? node.then : node.else); break;
      }
      default: fail('Unsupported AST node');
    }
    if (!finite(value)) fail('Undefined or nonfinite scientific result');
    return value;
  };
  const format = x => Array.isArray(x) ? '[' + x.map(format).join(', ') + ']' :
    numeric(x) ? String(Number(x.toPrecision(7))) : x && typeof x === 'object' ?
    Object.entries(x).map(([name,value]) => name + '=' + format(value)).join(', ') : String(x);
  const equation = (n, symbols = {}, state = null) => {
    const child = x => equation(x, symbols, state);
    switch (n.type) {
      case 'Canonical': return equation(root.ScientificCanonical.display(n), symbols, state);
      case 'Constant': return format(n.value);
      case 'Variable': return state && own(state, n.id) ? format(state[n.id]) : symbols[n.id] || n.id;
      case 'Unary': return '(' + n.op + child(n.operand) + ')';
      case 'Binary': return '(' + child(n.left) + ' ' + ({'*': '×', '/': '÷', '**': '^'}[n.op] || n.op) + ' ' + child(n.right) + ')';
      case 'Call': return n.function + '(' + n.args.map(child).join(', ') + ')';
      case 'Index': return child(n.value) + '[' + child(n.index) + ']';
      case 'Vector': return '[' + n.items.map(child).join(', ') + ']';
      case 'Matrix': return '[' + n.rows.map(row => '[' + row.map(child).join(', ') + ']').join('; ') + ']';
      case 'Conditional': return child(n.then) + ' if ' + child(n.condition) + ', otherwise ' + child(n.else);
      default: return fail('Unsupported equation AST');
    }
  };
  // Native MathML is local, accessible, and derived from the executable tree.
  const mathNode = (tag, children = [], value = '') => {
    const node = document.createElementNS('http://www.w3.org/1998/Math/MathML', tag);
    node.textContent = value;
    children.forEach(child => node.append(child));
    return node;
  };
  const mathematical = (n, symbols = {}) => {
    const child = x => mathematical(x, symbols);
    const op = x => mathNode('mo', [], x);
    const row = children => mathNode('mrow', children);
    switch (n.type) {
      case 'Canonical': return mathematical(root.ScientificCanonical.display(n), symbols);
      case 'Constant': return mathNode(typeof n.value === 'number' ? 'mn' : 'mtext', [], format(n.value));
      case 'Variable': return mathNode('mi', [], symbols[n.id] || n.id);
      case 'Unary': return row([op(n.op), child(n.operand)]);
      case 'Binary':
        if (n.op === '/') return mathNode('mfrac', [child(n.left), child(n.right)]);
        if (n.op === '**') return mathNode('msup', [row([op('('), child(n.left), op(')')]), child(n.right)]);
        return row([op('('), child(n.left), op(n.op === '*' ? '×' : n.op), child(n.right), op(')')]);
      case 'Call':
        if (n.function === 'sqrt' && n.args.length === 1) return mathNode('msqrt', [child(n.args[0])]);
        return row([mathNode(n.function === 'sum' ? 'mo' : 'mi', [], n.function === 'sum' ? '∑' : n.function), op('('),
          ...n.args.flatMap((a, i) => i ? [op(','), child(a)] : [child(a)]), op(')')]);
      case 'Index': return mathNode('msub', [child(n.value), child(n.index)]);
      case 'Vector': return row([op('['), ...n.items.flatMap((a, i) => i ? [op(','), child(a)] : [child(a)]), op(']')]);
      case 'Matrix': return row([op('['), mathNode('mtable', n.rows.map(r => mathNode('mtr', r.map(x => mathNode('mtd', [child(x)]))))), op(']')]);
      case 'Conditional': return row([child(n.then), mathNode('mtext', [], ' if '), child(n.condition), mathNode('mtext', [], ', otherwise '), child(n.else)]);
      default: return fail('Unsupported equation AST');
    }
  };
  const math = (ast, symbols, output) => mathNode('math', output ? [mathNode('mi', [], output), mathNode('mo', [], '='), mathematical(ast, symbols)] : [mathematical(ast, symbols)]);
  root.ScientificAST = Object.freeze({evaluate, equation, math, format, finite, operations: Object.keys(ops)});
})(globalThis);
