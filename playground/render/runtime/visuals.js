/* Generic scientific SVG components. Every mark encodes actual state data. */
(function (root) {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const svg = (tag, attrs = {}, text = '') => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
    if (text) node.textContent = text;
    return node;
  };
  const flatten = x => Array.isArray(x) ? x.flat(Infinity) : [x];
  const numbers = values => values.flatMap(flatten).filter(x => typeof x === 'number' && Number.isFinite(x));
  const text = (scene, x, y, content, attrs = {}) => scene.append(svg('text', {x, y, ...attrs}, content));
  const line = (scene, x1, y1, x2, y2, attrs = {}) => scene.append(svg('line', {x1, y1, x2, y2, ...attrs}));
  const bars = (scene, values) => {
    const data = numbers(values);
    if (!data.length) throw new Error('Numeric data required for bars');
    const scale = Math.max(...data.map(Math.abs), 1e-12), width = 440 / data.length;
    line(scene, 35, 145, 485, 145, {class: 'axis'});
    data.forEach((value, i) => {
      const h = Math.abs(value) / scale * 90, x = 40 + i * width;
      scene.append(svg('rect', {x, y: value >= 0 ? 145 - h : 145, width: Math.max(2, width - 12),
        height: h, class: 'mark', 'data-mark-value': value}));
      text(scene, x + 2, value >= 0 ? 140 - h : 162 + h, root.ScientificAST.format(value));
      text(scene, x + 2, 273, String(i + 1));
    });
  };
  const plot = (scene, values, scatter = false, geometry = false) => {
    const raw = values[0];
    const explicitPairs = Array.isArray(raw) && raw.every(p => Array.isArray(p) && p.length === 2);
    const singleVector = geometry && Array.isArray(raw) && raw.length === 2 && raw.every(Number.isFinite);
    if (geometry && !explicitPairs && !singleVector) throw new Error('Geometry needs coordinate pairs');
    const data = singleVector ? [raw] : explicitPairs ? raw : numbers(values).map((y, i) => [i, y]);
    if (!data.length || !data.every(p => p.every(Number.isFinite))) throw new Error('Coordinates required');
    const xs = data.map(p => p[0]), ys = data.map(p => p[1]);
    const xlo = Math.min(0, ...xs), xhi = Math.max(1, ...xs);
    const ylo = Math.min(0, ...ys), yhi = Math.max(1, ...ys);
    const sx = x => 40 + (x - xlo) / (xhi - xlo) * 430;
    const sy = y => 250 - (y - ylo) / (yhi - ylo) * 215;
    line(scene, 40, sy(0), 480, sy(0), {class: 'axis'});
    line(scene, sx(0), 25, sx(0), 250, {class: 'axis'});
    if (!scatter) scene.append(svg('polyline', {points: data.map(([x, y]) => sx(x) + ',' + sy(y)).join(' '), class: 'curve'}));
    data.forEach(([x, y], i) => {
      if (geometry) line(scene, sx(0), sy(0), sx(x), sy(y), {class: 'curve'});
      scene.append(svg('circle', {cx: sx(x), cy: sy(y), r: 5, class: 'mark', 'data-mark-value': JSON.stringify([x, y])}));
      text(scene, sx(x) + 5, Math.max(18, sy(y) - 9), root.ScientificAST.format(y));
    });
    text(scene, 40, 280, explicitPairs ? 'Coordinate pairs' : 'Sequence index → value');
  };
  const heatmap = (scene, values) => {
    const rows = values[0];
    if (!Array.isArray(rows) || !rows.length || !rows.every(r => Array.isArray(r) && r.length === rows[0].length)) throw new Error('Matrix required');
    const max = Math.max(...numbers([rows]).map(Math.abs), 1e-12);
    const w = 420 / rows[0].length, h = 220 / rows.length;
    rows.forEach((row, i) => row.forEach((v, j) => {
      if (!Number.isFinite(v)) throw new Error('Numeric matrix required');
      scene.append(svg('rect', {x: 40 + j * w, y: 30 + i * h, width: w - 3, height: h - 3,
        class: 'cell', opacity: .18 + .72 * Math.abs(v) / max, 'data-mark-value': v}));
      text(scene, 40 + (j + .5) * w, 34 + (i + .5) * h, root.ScientificAST.format(v), {'text-anchor': 'middle', class: 'cell-label'});
    }));
  };
  const flow = (scene, values, labels, active = -1) => {
    if (values.length > 8) throw new Error('Use readable generic scene for long processes');
    const width = 440 / values.length;
    values.forEach((v, i) => {
      const x = 35 + width * i;
      if (i) line(scene, x - 12, 138, x, 138, {class: 'curve', 'marker-end': 'url(#flow-arrow)'});
      scene.append(svg('rect', {x, y: 74, width: Math.max(20, width - 15), height: 128, rx: 8,
        class: active === i ? 'active-cell' : 'flow-cell', 'data-mark-value': JSON.stringify(v)}));
      text(scene, x + 8, 98, labels[i] || 'Step ' + (i + 1));
      // Scientific values remain available as text even for long tensors.
      text(scene, x + 8, 131, root.ScientificAST.format(v).slice(0, 26));
      text(scene, x + 8, 175, String(i + 1));
    });
  };
  const generic = (scene, values, labels) => {
    scene.setAttribute('viewBox', '0 0 520 ' + Math.max(300, values.length * 32 + 60));
    values.forEach((v, i) => text(scene, 30, 40 + i * 32,
      (labels[i] || 'Value') + ' = ' + root.ScientificAST.format(v)));
  };
  const modelCurve = (scene,spec,state,points) => {
    if(!points||points.length<2)throw new Error('Curve domain unavailable');
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);
    const xlo=Math.min(...xs),xhi=Math.max(...xs),lo=Math.min(0,...ys),hi=Math.max(0,...ys);
    const padding=Math.max((hi-lo)*.12,1e-6),ylo=lo-padding,yhi=hi+padding;
    const sx=x=>64+(x-xlo)/(xhi-xlo)*404,sy=y=>236-(y-ylo)/(yhi-ylo)*192;
    for(let i=0;i<=4;i++){
      const y=ylo+(yhi-ylo)*i/4;
      line(scene,64,sy(y),468,sy(y),{class:'grid-line'});
      text(scene,54,sy(y)+4,String(Number(y.toPrecision(3))),{'text-anchor':'end',class:'tick'});
      const x=xlo+(xhi-xlo)*i/4;
      text(scene,sx(x),258,root.ScientificAST.format(x),{'text-anchor':'middle',class:'tick'});
    }
    scene.append(svg('polyline',{points:points.map(([x,y])=>sx(x)+','+sy(y)).join(' '),class:'model-curve'}));
    if(points.length<=25)points.forEach(([x,y])=>scene.append(svg('circle',{cx:sx(x),cy:sy(y),r:2.5,fill:'var(--accent)'})));
    const current=[state[spec.sweep.input_ref],state[spec.sweep.output_ref]],cx=sx(current[0]),cy=sy(current[1]);
    line(scene,cx,cy,cx,236,{class:'current-guide'});
    scene.append(svg('circle',{cx,cy,r:10,class:'current-halo'}));
    scene.append(svg('circle',{cx,cy,r:5,class:'current-point','data-mark-value':JSON.stringify(current)}));
    text(scene,Math.min(380,Math.max(90,cx+12)),Math.max(28,cy-15),'Value '+root.ScientificAST.format(current[1]),{class:'point-label'});
    text(scene,64,22,String(spec.sweep.y_label).slice(0,48),{class:'axis-label'});
    text(scene,266,288,String(spec.sweep.x_label).slice(0,48),{'text-anchor':'middle',class:'axis-label'});
  };
  const render = (container, spec, state, ui = {}) => {
    const values = spec.data_refs.map(ref => state[ref]);
    const labels = spec.data_refs.map(ref => ui.symbols?.[ref] || ref);
    const scene = svg('svg', {viewBox: '0 0 520 300', role: 'img', 'aria-label': spec.question});
    scene.append(svg('title', {}, spec.question));
    const defs = svg('defs'), marker = svg('marker', {id: 'flow-arrow', markerWidth: 8, markerHeight: 8, refX: 7, refY: 3, orient: 'auto'});
    marker.append(svg('path', {d: 'M0,0 L0,6 L7,3 z'})); defs.append(marker); scene.append(defs);
    let component = spec.component;
    try {
      switch (component) {
        case 'curve': modelCurve(scene,spec,state,ui.curve); break;
        case 'bars': case 'distribution': bars(scene, values); break;
        case 'line': case 'trajectory': case 'waveform': plot(scene, values); break;
        case 'scatter': plot(scene, values, true); break;
        case 'geometry': case 'vector': plot(scene, values, true, true); break;
        case 'matrix': heatmap(scene, values); break;
        case 'flow': flow(scene, values, labels); break;
        case 'process': {
          const steps = Array.isArray(values[0]) ? values[0] : values;
          flow(scene, steps, [], Math.min(ui.step || 0, steps.length - 1)); break;
        }
        case 'state_graph': {
          const nodes = spec.metadata.nodes;
          if (!Array.isArray(nodes) || !nodes.length) { generic(scene, values, labels); break; }
          const edges = spec.metadata.edges || [];
          nodes.forEach((node, i) => {
            const x = 50 + i * 430 / Math.max(1, nodes.length - 1);
            if (edges.some(edge => edge.from === nodes[i - 1]?.id && edge.to === node.id)) line(scene, x - 90, 140, x - 20, 140, {class: 'curve'});
            scene.append(svg('circle', {cx: x, cy: 140, r: 22, class: node.id === values[0] ? 'active-cell' : 'flow-cell'}));
            text(scene, x, 184, node.label || node.id, {'text-anchor': 'middle'});
          });
          text(scene, 30, 260, 'Current state: ' + root.ScientificAST.format(values[0])); break;
        }
        case 'comparison': {
          const prior = ui.comparison;
          const previous = prior ? spec.data_refs.map(ref => prior[ref]) : null;
          if (numbers(values).length) bars(scene, previous ? [...previous, ...values] : values);
          else generic(scene, values, labels);
          text(scene, 30, 24, prior ? 'Saved inputs → current inputs' : 'Save a comparison to contrast inputs'); break;
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
    container.dataset.curve = JSON.stringify(ui.curve||null);
    container.dataset.component = component;
    container.dataset.visualState = JSON.stringify({values, step: ui.step || 0, comparison: ui.comparison || null});
  };
  root.ScientificVisuals = Object.freeze({render});
})(globalThis);
