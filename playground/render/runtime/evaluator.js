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
  // Short numerals keep substituted equations readable; full precision stays in the data attributes.
  const short = x => numeric(x) ? String(Number(x.toPrecision(4))) : String(x);
  const prettyCall = (name, args) => {
    const [a, b] = args;
    if (name === 'divide' && args.length === 2) return '(' + a + ' / ' + b + ')';
    if (name === 'sqrt' && args.length === 1) return '√(' + a + ')';
    if (name === 'power' && args.length === 2) return a + '^' + b;
    if (name === 'transpose' && args.length === 1) return a + 'ᵀ';
    if (name === 'matmul' && args.length === 2) return a + ' ' + b;
    if (name === 'multiply' && args.length === 2) return '(' + a + ' × ' + b + ')';
    if (name === 'dot' && args.length === 2) return '(' + a + ' · ' + b + ')';
    if (name === 'add' && args.length === 2) return '(' + a + ' + ' + b + ')';
    if (name === 'subtract' && args.length === 2) return '(' + a + ' − ' + b + ')';
    if (name === 'abs' && args.length === 1) return '|' + a + '|';
    return name + '(' + args.join(', ') + ')';
  };
  const equation = (n, symbols = {}, state = null) => {
    const child = x => equation(x, symbols, state);
    switch (n.type) {
      case 'Canonical': return equation(root.ScientificCanonical.display(n), symbols, state);
      case 'Constant': return format(n.value);
      case 'Variable': return state && own(state, n.id) ? format(state[n.id]) : symbols[n.id] || n.id;
      case 'Unary': return '(' + n.op + child(n.operand) + ')';
      case 'Binary': return '(' + child(n.left) + ' ' + ({'*': '×', '/': '÷', '**': '^'}[n.op] || n.op) + ' ' + child(n.right) + ')';
      case 'Call': return prettyCall(n.function, n.args.map(child));
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
  // Fences stretch to the height of the matrix they enclose.
  const fence = text => { const node = mathNode('mo', [], text); node.setAttribute('stretchy', 'true'); node.setAttribute('symmetric', 'true'); return node; };
  // Concrete values typeset as numerals, column vectors and bracketed matrices.
  const valueNode = value => {
    if (Array.isArray(value)) {
      const isMatrix = value.every(Array.isArray);
      const rows = isMatrix ? value : value.map(x => [x]);
      if (rows.length > 6 || rows.some(r => r.length > 6)) return mathNode('mtext', [], format(value));
      const table = mathNode('mtable', rows.map(r => mathNode('mtr', r.map(x => mathNode('mtd', [valueNode(x)])))));
      return mathNode('mrow', [fence('['), table, fence(']')]);
    }
    if (numeric(value)) {
      const text = short(value);
      return text.startsWith('-') ? mathNode('mrow', [mathNode('mo', [], '−'), mathNode('mn', [], text.slice(1))]) : mathNode('mn', [], text);
    }
    return mathNode('mtext', [], String(value));
  };
  // Authored display symbols arrive as plain text or light LaTeX ("d_k", "\alpha^2", "sqrt(d_k)",
  // "q·k_i / sqrt(d_k)", "\frac{a}{b}"). A small recursive-descent parser typesets them generically.
  const GREEK = {alpha: 'α', beta: 'β', gamma: 'γ', delta: 'δ', epsilon: 'ε', varepsilon: 'ε', zeta: 'ζ', eta: 'η', theta: 'θ', iota: 'ι', kappa: 'κ', lambda: 'λ', mu: 'μ', nu: 'ν', xi: 'ξ', pi: 'π', rho: 'ρ', sigma: 'σ', tau: 'τ', upsilon: 'υ', phi: 'φ', varphi: 'φ', chi: 'χ', psi: 'ψ', omega: 'ω', Gamma: 'Γ', Delta: 'Δ', Theta: 'Θ', Lambda: 'Λ', Xi: 'Ξ', Pi: 'Π', Sigma: 'Σ', Phi: 'Φ', Psi: 'Ψ', Omega: 'Ω', infty: '∞', cdot: '·', times: '×', pm: '±', le: '≤', ge: '≥', ne: '≠', approx: '≈', to: '→', rightarrow: '→', sum: '∑', prod: '∏', partial: '∂', nabla: '∇', ell: 'ℓ', hbar: 'ℏ'};
  const identifier = text => {
    const node = mathNode('mi', [], GREEK[text] || text);
    if (!GREEK[text] && text.length > 1) node.setAttribute('mathvariant', 'normal');
    return node;
  };
  const tokenizeSymbol = raw => {
    const tokens = [];
    const re = /\\[A-Za-z]+|[A-Za-z]+|\d+(?:\.\d+)?|\s+|./gu;
    for (const m of raw.matchAll(re)) { if (!/^\s+$/.test(m[0])) tokens.push(m[0]); }
    return tokens;
  };
  const parseSymbol = raw => {
    const tokens = tokenizeSymbol(raw);
    let i = 0;
    const peek = () => tokens[i];
    const take = () => tokens[i++];
    const wrap = nodes => nodes.length === 1 ? nodes[0] : mathNode('mrow', nodes);
    const group = () => {
      if (peek() === '{') { take(); const inner = sequence(t => t === '}'); if (peek() === '}') take(); return inner; }
      return atom();
    };
    const atom = () => {
      const t = take();
      if (t === undefined) return mathNode('mrow');
      if (t === '(' || t === '[' || t === '|') {
        const close = {'(': ')', '[': ']', '|': '|'}[t];
        const inner = sequence(x => x === close);
        if (peek() === close) take();
        return mathNode('mrow', [fence(t), inner, fence(close)]);
      }
      if (t === '\\frac') { const a = group(); const b = group(); return mathNode('mfrac', [a, b]); }
      if (t === '\\sqrt' || t === 'sqrt') {
        if (peek() === '{') return mathNode('msqrt', [group()]);
        if (peek() === '(') { take(); const inner = sequence(x => x === ')'); if (peek() === ')') take(); return mathNode('msqrt', [inner]); }
        return identifier('sqrt');
      }
      if (t.startsWith('\\')) { const name = t.slice(1); return GREEK[name] ? mathNode(/^(sum|prod|partial|nabla|infty)$/.test(name) ? 'mo' : 'mi', [], GREEK[name]) : identifier(name); }
      if (/^\d/.test(t)) return mathNode('mn', [], t);
      if (/^[A-Za-z]+$/u.test(t)) {
        // Function application when immediately followed by "(".
        if (peek() === '(' && t.length > 1 && !GREEK[t]) { const fn = identifier(t); const args = atom(); return mathNode('mrow', [fn, mathNode('mo', [], '\u2061'), args]); }
        return identifier(t);
      }
      return mathNode('mo', [], t === '*' ? '·' : t);
    };
    const scripted = () => {
      let base = atom();
      let sub = null, sup = null;
      while (peek() === '_' || peek() === '^') {
        const which = take();
        const script = group();
        if (which === '_') sub = sub ? mathNode('mrow', [sub, script]) : script; else sup = sup ? mathNode('mrow', [sup, script]) : script;
      }
      if (sub && sup) return mathNode('msubsup', [base, sub, sup]);
      if (sub) return mathNode('msub', [base, sub]);
      if (sup) return mathNode('msup', [base, sup]);
      return base;
    };
    // "a / b" becomes a fraction when both sides are single scripted terms.
    const sequence = stop => {
      const items = [];
      while (i < tokens.length && !stop(peek())) {
        if (peek() === '/' && items.length) {
          take();
          const denominator = scripted();
          const numerator = items.pop();
          items.push(mathNode('mfrac', [numerator, denominator]));
          continue;
        }
        items.push(scripted());
      }
      return wrap(items);
    };
    return sequence(() => false);
  };
  const symbolNode = text => {
    const raw = String(text ?? '').trim();
    if (!raw) return mathNode('mi');
    try { return parseSymbol(raw); } catch (_) { return identifier(raw); }
  };
  // Operator precedence decides where parentheses are actually needed.
  const PRECEDENCE = {sum: 1, compare: 2, add: 3, subtract: 3, multiply: 4, dot: 4, matmul: 5, unary: 6, power: 7, atom: 9};
  const binaryName = op => ({'+': 'add', '-': 'subtract', '*': 'multiply', '/': 'divide', '**': 'power'}[op] || 'compare');
  const precedenceOf = n => {
    if (n.type === 'Binary') { const name = binaryName(n.op); return name === 'divide' ? PRECEDENCE.atom : PRECEDENCE[name]; }
    if (n.type === 'Unary') return PRECEDENCE.unary;
    if (n.type === 'Call') return PRECEDENCE[n.function] ?? PRECEDENCE.atom;
    if (n.type === 'Conditional') return PRECEDENCE.compare;
    return PRECEDENCE.atom;
  };
  // When state is supplied, variables render as their current numerals for the substituted form.
  const mathematical = (n, symbols = {}, state = null) => {
    const child = x => mathematical(x, symbols, state);
    const op = x => mathNode('mo', [], x);
    const row = children => mathNode('mrow', children);
    const wrap = (x, minimum) => precedenceOf(x) < minimum ? row([op('('), child(x), op(')')]) : child(x);
    const fname = name => {
      const node = mathNode(name === 'sum' ? 'mo' : 'mi', [], name === 'sum' ? '∑' : name);
      if (name !== 'sum' && name.length > 1) node.setAttribute('mathvariant', 'normal');
      return node;
    };
    const callArgs = args => args.flatMap((a, i) => i ? [op(','), child(a)] : [child(a)]);
    switch (n.type) {
      case 'Canonical': return mathematical(root.ScientificCanonical.display(n), symbols, state);
      case 'Constant': return typeof n.value === 'number' || Array.isArray(n.value) ? valueNode(n.value) : mathNode('mtext', [], String(n.value));
      case 'Variable': return state && own(state, n.id) ? valueNode(state[n.id]) : symbolNode(symbols[n.id] || n.id);
      case 'Unary': return row([op(n.op === '-' ? '−' : n.op), wrap(n.operand, PRECEDENCE.unary)]);
      case 'Binary': {
        const name = binaryName(n.op);
        if (name === 'divide') return mathNode('mfrac', [child(n.left), child(n.right)]);
        if (name === 'power') return mathNode('msup', [wrap(n.left, PRECEDENCE.atom), child(n.right)]);
        const glyph = {add: '+', subtract: '−', multiply: '×'}[name] || ({'<': '<', '<=': '≤', '>': '>', '>=': '≥', '==': '=', '!=': '≠'}[n.op] || n.op);
        const level = PRECEDENCE[name];
        return row([wrap(n.left, level), op(glyph), wrap(n.right, level + (name === 'subtract' ? 1 : 0))]);
      }
      case 'Call': {
        const name = n.function, args = n.args;
        if (name === 'sqrt' && args.length === 1) return mathNode('msqrt', [child(args[0])]);
        if (name === 'divide' && args.length === 2) return mathNode('mfrac', [child(args[0]), child(args[1])]);
        if (name === 'power' && args.length === 2) return mathNode('msup', [wrap(args[0], PRECEDENCE.atom), child(args[1])]);
        if (name === 'transpose' && args.length === 1) return mathNode('msup', [wrap(args[0], PRECEDENCE.atom), mathNode('mi', [], 'T')]);
        if (name === 'abs' && args.length === 1) return row([op('|'), child(args[0]), op('|')]);
        if (name === 'exp' && args.length === 1) return mathNode('msup', [mathNode('mi', [], 'e'), child(args[0])]);
        if (name === 'norm' && args.length === 1) return row([op('‖'), child(args[0]), op('‖')]);
        if (name === 'matmul' && args.length === 2) return row([wrap(args[0], PRECEDENCE.matmul), op('\u2062'), wrap(args[1], PRECEDENCE.matmul)]);
        const infix = {add: '+', subtract: '−', multiply: '×', dot: '·'};
        if (infix[name] && args.length === 2) {
          const level = PRECEDENCE[name];
          return row([wrap(args[0], level), op(infix[name]), wrap(args[1], level + (name === 'subtract' ? 1 : 0))]);
        }
        if (name === 'sum' && args.length === 1) return row([op('∑'), wrap(args[0], PRECEDENCE.multiply)]);
        return row([fname(name), op('('), ...callArgs(args), op(')')]);
      }
      case 'Index': return mathNode('msub', [wrap(n.value, PRECEDENCE.atom), child(n.index)]);
      case 'Vector': return row([op('['), ...n.items.flatMap((a, i) => i ? [op(','), child(a)] : [child(a)]), op(']')]);
      case 'Matrix': return row([fence('['), mathNode('mtable', n.rows.map(r => mathNode('mtr', r.map(x => mathNode('mtd', [child(x)]))))), fence(']')]);
      case 'Conditional': return row([child(n.then), mathNode('mtext', [], ' if '), child(n.condition), mathNode('mtext', [], ', otherwise '), child(n.else)]);
      default: return fail('Unsupported equation AST');
    }
  };
  const math = (ast, symbols, output) => {
    const node = mathNode('math', output ? [symbolNode(output), mathNode('mo', [], '='), mathematical(ast, symbols)] : [mathematical(ast, symbols)]);
    node.setAttribute('display', 'block');
    return node;
  };
  // Substituted form: symbols replaced by current numerals, then the evaluated result.
  const substituted = (ast, symbols, state, result) => {
    const parts = [mathematical(ast, symbols, state)];
    if (result !== undefined) parts.push(mathNode('mo', [], '='), valueNode(result));
    const node = mathNode('math', parts);
    node.setAttribute('display', 'block');
    return node;
  };
  const symbol = text => {
    const node = mathNode('math', [symbolNode(text)]);
    node.setAttribute('display', 'inline');
    return node;
  };
  root.ScientificAST = Object.freeze({evaluate, equation, math, substituted, symbol, format, short, finite, operations: Object.keys(ops)});
})(globalThis);
