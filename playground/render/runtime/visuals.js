/* Generic scientific SVG components. Every mark encodes actual state data. */
(function (root) {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const W = 560, H = 320;
  const PAD = {left: 56, right: 24, top: 36, bottom: 48};
  const svg = (tag, attrs = {}, text = '') => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
    if (text) node.textContent = text;
    return node;
  };
  const fmt = x => root.ScientificAST.short(x);
  const flatten = x => Array.isArray(x) ? x.flat(Infinity) : [x];
  const numbers = values => values.flatMap(flatten).filter(x => typeof x === 'number' && Number.isFinite(x));
  const text = (scene, x, y, content, attrs = {}) => scene.append(svg('text', {x, y, ...attrs}, content));
  const line = (scene, x1, y1, x2, y2, attrs = {}) => scene.append(svg('line', {x1, y1, x2, y2, ...attrs}));
  // Readable axis ticks: a handful of round numbers spanning the data.
  const ticks = (lo, hi, count = 5) => {
    if (!(hi > lo)) { hi = lo + 1; }
    const span = hi - lo, rough = span / count, mag = Math.pow(10, Math.floor(Math.log10(rough)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= count) || mag;
    const start = Math.ceil(lo / step) * step, out = [];
    for (let v = start; v <= hi + step * 1e-6; v += step) out.push(Number(v.toFixed(10)));
    return out;
  };
  const frame = (scene, xlo, xhi, ylo, yhi, labels = {}) => {
    const sx = x => PAD.left + (x - xlo) / (xhi - xlo) * (W - PAD.left - PAD.right);
    const sy = y => H - PAD.bottom - (y - ylo) / (yhi - ylo) * (H - PAD.top - PAD.bottom);
    ticks(ylo, yhi).forEach(v => {
      line(scene, PAD.left, sy(v), W - PAD.right, sy(v), {class: 'grid'});
      text(scene, PAD.left - 8, sy(v) + 4, fmt(v), {class: 'tick', 'text-anchor': 'end'});
    });
    line(scene, PAD.left, sy(Math.max(ylo, Math.min(yhi, 0))), W - PAD.right, sy(Math.max(ylo, Math.min(yhi, 0))), {class: 'axis'});
    line(scene, PAD.left, PAD.top, PAD.left, H - PAD.bottom, {class: 'axis'});
    if (labels.y) text(scene, 14, PAD.top - 12, labels.y, {class: 'axis-label'});
    if (labels.x) text(scene, W - PAD.right, H - 10, labels.x, {class: 'axis-label', 'text-anchor': 'end'});
    return {sx, sy};
  };
  const bars = (scene, values, labels, options = {}) => {
    const data = numbers(values);
    if (!data.length) throw new Error('Numeric data required for bars');
    const distribution = options.distribution && data.every(x => x >= 0) && Math.abs(data.reduce((a, b) => a + b, 0) - 1) < 1e-6;
    const ylo = Math.min(0, ...data), yhi = distribution ? 1 : Math.max(0, ...data) || 1;
    const padded = yhi + (yhi - ylo) * .12;
    const {sx, sy} = frame(scene, 0, data.length, ylo, padded, {y: labels[0] || '', x: distribution ? 'outcome' : 'index'});
    const slot = (W - PAD.left - PAD.right) / data.length, bw = Math.min(64, slot * .62);
    data.forEach((value, i) => {
      const x = sx(i + .5) - bw / 2, y0 = sy(0), y1 = sy(value);
      scene.append(svg('rect', {x, y: Math.min(y0, y1), width: bw, height: Math.max(1, Math.abs(y0 - y1)), rx: 4,
        class: 'mark', 'data-mark-value': value, style: 'animation-delay:' + (i * 40) + 'ms'}));
      text(scene, sx(i + .5), value >= 0 ? y1 - 7 : y1 + 15, distribution ? (value * 100).toFixed(1) + '%' : fmt(value), {class: 'value', 'text-anchor': 'middle'});
      text(scene, sx(i + .5), H - PAD.bottom + 18, String(i + 1), {class: 'tick', 'text-anchor': 'middle'});
    });
    if (distribution) text(scene, W - PAD.right, PAD.top - 12, 'sums to 1', {class: 'note', 'text-anchor': 'end'});
  };
  const plot = (scene, values, labels, scatter = false, geometry = false) => {
    const raw = values[0];
    const explicitPairs = Array.isArray(raw) && raw.every(p => Array.isArray(p) && p.length === 2);
    const singleVector = geometry && Array.isArray(raw) && raw.length === 2 && raw.every(Number.isFinite);
    if (geometry && !explicitPairs && !singleVector) throw new Error('Geometry needs coordinate pairs');
    const data = singleVector ? [raw] : explicitPairs ? raw : numbers(values).map((y, i) => [i, y]);
    if (!data.length || !data.every(p => p.every(Number.isFinite))) throw new Error('Coordinates required');
    const xs = data.map(p => p[0]), ys = data.map(p => p[1]);
    const xlo = Math.min(0, ...xs), xhi = Math.max(1, ...xs) + (explicitPairs ? 0 : .5);
    const yspan = Math.max(1e-9, Math.max(...ys) - Math.min(0, ...ys));
    const ylo = Math.min(0, ...ys) - yspan * .08, yhi = Math.max(1e-9, ...ys) + yspan * .12;
    const {sx, sy} = frame(scene, xlo, xhi, ylo, yhi, {y: labels[0] || '', x: explicitPairs ? 'x' : 'index'});
    if (!scatter) {
      const pts = data.map(([x, y]) => sx(x) + ',' + sy(y)).join(' ');
      scene.append(svg('polygon', {points: pts + ' ' + sx(xs[xs.length - 1]) + ',' + sy(0) + ' ' + sx(xs[0]) + ',' + sy(0), class: 'area'}));
      scene.append(svg('polyline', {points: pts, class: 'curve'}));
    }
    data.forEach(([x, y]) => {
      if (geometry) scene.append(svg('line', {x1: sx(0), y1: sy(0), x2: sx(x), y2: sy(y), class: 'curve', 'marker-end': 'url(#arrow)'}));
      scene.append(svg('circle', {cx: sx(x), cy: sy(y), r: 5, class: 'mark', 'data-mark-value': JSON.stringify([x, y])}));
      text(scene, sx(x) + 8, Math.max(PAD.top + 4, sy(y) - 8), geometry ? '(' + fmt(x) + ', ' + fmt(y) + ')' : fmt(y), {class: 'value'});
    });
  };
  const heatmap = (scene, values, labels) => {
    const rows = values[0];
    if (!Array.isArray(rows) || !rows.length || !rows.every(r => Array.isArray(r) && r.length === rows[0].length)) throw new Error('Matrix required');
    const flat = numbers([rows]);
    const max = Math.max(...flat.map(Math.abs), 1e-12);
    const cols = rows[0].length;
    const size = Math.min((W - PAD.left - PAD.right - 40) / cols, (H - PAD.top - PAD.bottom + 10) / rows.length, 72);
    const x0 = (W - size * cols) / 2 + 10, y0 = PAD.top + 6;
    text(scene, x0, y0 - 14, labels[0] || 'matrix', {class: 'axis-label'});
    rows.forEach((row, i) => row.forEach((v, j) => {
      if (!Number.isFinite(v)) throw new Error('Numeric matrix required');
      const strength = Math.abs(v) / max;
      scene.append(svg('rect', {x: x0 + j * size, y: y0 + i * size, width: size - 4, height: size - 4, rx: 6,
        class: v < 0 ? 'cell negative' : 'cell', opacity: .15 + .85 * strength, 'data-mark-value': v}));
      text(scene, x0 + (j + .5) * size - 2, y0 + (i + .5) * size + 3, fmt(v), {'text-anchor': 'middle', class: strength > .55 ? 'cell-label light' : 'cell-label'});
    }));
    rows.forEach((_, i) => text(scene, x0 - 10, y0 + (i + .5) * size + 2, 'row ' + (i + 1), {class: 'tick', 'text-anchor': 'end'}));
    rows[0].forEach((_, j) => text(scene, x0 + (j + .5) * size - 2, y0 + rows.length * size + 12, 'col ' + (j + 1), {class: 'tick', 'text-anchor': 'middle'}));
    // Legend: lighter means closer to zero, darker means larger magnitude.
    const lx = W - PAD.right - 120, ly = H - 26;
    [0, .25, .5, .75, 1].forEach((s, i) => scene.append(svg('rect', {x: lx + i * 18, y: ly - 10, width: 16, height: 10, class: 'cell', opacity: .15 + .85 * s})));
    text(scene, lx - 6, ly, '0', {class: 'tick', 'text-anchor': 'end'});
    text(scene, lx + 96, ly, fmt(max), {class: 'tick'});
  };
  const flow = (scene, values, labels, active = -1) => {
    if (values.length > 8) throw new Error('Use readable generic scene for long processes');
    const slot = (W - 40) / values.length, bw = slot - 22;
    values.forEach((v, i) => {
      const x = 20 + slot * i, cy = H / 2;
      if (i) line(scene, x - 20, cy, x - 2, cy, {class: 'curve', 'marker-end': 'url(#arrow)'});
      scene.append(svg('rect', {x, y: cy - 58, width: bw, height: 116, rx: 12,
        class: active === i ? 'active-cell' : 'flow-cell', 'data-mark-value': JSON.stringify(v)}));
      scene.append(svg('title', {}, root.ScientificAST.format(v)));
      text(scene, x + bw / 2, cy - 30, labels[i] || 'Step ' + (i + 1), {class: 'axis-label', 'text-anchor': 'middle'});
      const shown = root.ScientificAST.format(v);
      text(scene, x + bw / 2, cy + 6, shown.length > 18 ? shown.slice(0, 16) + '…' : shown, {class: 'value', 'text-anchor': 'middle'});
      text(scene, x + bw / 2, cy + 40, String(i + 1), {class: 'tick', 'text-anchor': 'middle'});
    });
  };
  const generic = (scene, values, labels) => {
    scene.setAttribute('viewBox', '0 0 ' + W + ' ' + Math.max(H, values.length * 36 + 60));
    values.forEach((v, i) => {
      text(scene, 30, 44 + i * 36, (labels[i] || 'Value') + ' = ', {class: 'axis-label'});
      text(scene, 30 + 10 + (labels[i] || 'Value').length * 9, 44 + i * 36, root.ScientificAST.format(v), {class: 'value'});
    });
  };
  const render = (container, spec, state, ui = {}) => {
    const values = spec.data_refs.map(ref => state[ref]);
    const labels = spec.data_refs.map(ref => ui.symbols?.[ref] || ref);
    const scene = svg('svg', {viewBox: '0 0 ' + W + ' ' + H, role: 'img', 'aria-label': spec.question});
    scene.append(svg('title', {}, spec.question));
    const defs = svg('defs'), marker = svg('marker', {id: 'arrow', markerWidth: 9, markerHeight: 9, refX: 8, refY: 4, orient: 'auto', markerUnits: 'userSpaceOnUse'});
    marker.append(svg('path', {d: 'M0,0 L0,8 L9,4 z', class: 'arrowhead'})); defs.append(marker); scene.append(defs);
    let component = spec.component;
    try {
      switch (component) {
        case 'bars': bars(scene, values, labels); break;
        case 'distribution': bars(scene, values, labels, {distribution: true}); break;
        case 'line': case 'trajectory': case 'waveform': plot(scene, values, labels); break;
        case 'scatter': plot(scene, values, labels, true); break;
        case 'geometry': case 'vector': plot(scene, values, labels, true, true); break;
        case 'matrix': heatmap(scene, values, labels); break;
        case 'flow': flow(scene, values, labels); break;
        case 'process': {
          const steps = ui.histories?.[spec.metadata.history_ref] || (Array.isArray(values[0]) ? values[0] : values);
          const selected = Math.min(ui.step || 0, steps.length - 1), start = Math.max(0, Math.min(selected - 3, steps.length - 8));
          const window = steps.slice(start, start + 8);
          flow(scene, window, window.map((_, i) => 'Step ' + (start + i + 1)), selected - start);
          text(scene, 20, 24, 'Step ' + (selected + 1) + ' of ' + steps.length + ': ' + root.ScientificAST.format(steps[selected]), {class: 'axis-label'}); break;
        }
        case 'state_graph': {
          const nodes = spec.metadata.nodes;
          if (!Array.isArray(nodes) || !nodes.length) { generic(scene, values, labels); break; }
          const edges = spec.metadata.edges || [];
          nodes.forEach((node, i) => {
            const x = 60 + i * (W - 120) / Math.max(1, nodes.length - 1), cy = H / 2 - 10;
            if (edges.some(edge => edge.from === nodes[i - 1]?.id && edge.to === node.id)) line(scene, x - 90, cy, x - 30, cy, {class: 'curve', 'marker-end': 'url(#arrow)'});
            scene.append(svg('circle', {cx: x, cy, r: 26, class: node.id === values[0] ? 'active-cell' : 'flow-cell'}));
            text(scene, x, cy + 52, node.label || node.id, {'text-anchor': 'middle', class: 'axis-label'});
          });
          text(scene, 24, H - 20, 'Current state: ' + root.ScientificAST.format(values[0]), {class: 'value'}); break;
        }
        case 'comparison': {
          const prior = ui.comparison;
          const previous = prior ? spec.data_refs.map(ref => prior[ref]) : null;
          if (numbers(values).length) bars(scene, previous ? [...previous, ...values] : values, labels);
          else generic(scene, values, labels);
          text(scene, PAD.left, PAD.top - 12, prior ? 'Saved inputs → current inputs' : 'Save a comparison to contrast inputs', {class: 'note'}); break;
        }
        default: generic(scene, values, labels);
      }
    } catch (error) {
      scene.replaceChildren(svg('title', {}, spec.question));
      generic(scene, values, labels);
      component = 'scene';
    }
    container.replaceChildren(scene);
    container.dataset.values = JSON.stringify(values);
    container.dataset.component = component;
    container.dataset.visualState = JSON.stringify({values, step: ui.step || 0, comparison: ui.comparison || null});
  };
  root.ScientificVisuals = Object.freeze({render});
})(globalThis);
