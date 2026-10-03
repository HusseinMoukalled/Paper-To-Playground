(function () {
  'use strict';
  const manifest = JSON.parse(document.getElementById('playground-manifest').textContent);
  const AST = globalThis.ScientificAST;
  const clone = x => JSON.parse(JSON.stringify(x));
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const controls = new Map(manifest.controls.map(c => [c.scientific_variable, c]));
  const symbols = Object.fromEntries(manifest.variables.map(v => [v.id, v.display_symbol]));
  const elements = new Map(Array.from(document.querySelectorAll('[data-control-id]')).map(el => [el.dataset.variableId, el]));
  const outputs = Array.from(document.querySelectorAll('[data-output-id]'));
  const visualElements = new Map(Array.from(document.querySelectorAll('[data-visual-id]')).map(el => [el.dataset.visualId, el]));
  const status = document.querySelector('[data-role="status"]');
  let state = {}, histories = {}, ui = {step: 0, comparison: null, exploration: null}, error = null;
  const fail = message => { throw new Error(message); };
  function checkValue(control, raw) {
    let value = raw, warning = '';
    const kind = control.control_type;
    if (kind === 'select') {
      if (!control.options.includes(value)) fail('Choose a listed option.');
      return {value, warning};
    }
    if (kind === 'toggle') {
      if (typeof value !== 'boolean') fail('A boolean value is required.');
      return {value, warning};
    }
    if (kind === 'vector' || kind === 'matrix') {
      if (typeof value === 'string') { try { value = JSON.parse(value); } catch (_) { fail('Enter a JSON numeric array.'); } }
      if (!Array.isArray(value) || !value.length) fail('A nonempty array is required.');
    } else {
      if (typeof value === 'boolean' || value === '' || value === null) fail('A finite number is required.');
      value = Number(value);
    }
    const validNumber = x => {
      if (typeof x !== 'number' || !Number.isFinite(x)) fail('A finite number is required.');
      const lo = control.minimum, hi = control.maximum;
      const invalid = (lo !== null && x < lo) || (hi !== null && x > hi);
      if (invalid) {
        if (control.validation_rule === 'clamp') { warning = 'Input clamped to the allowed range.'; return Math.max(lo ?? -Infinity, Math.min(hi ?? Infinity, x)); }
        if (manifest.canonical_runtime && control.validation_rule === 'warn') { warning = 'Input is outside the teaching range.'; return x; }
        fail('Input is outside the allowed domain.');
      }
      return x;
    };
    if (control.validation_rule === 'normalize') {
      const euclidean = manifest.canonical_runtime && manifest.variables.find(v => v.id === control.scientific_variable).type !== 'distribution';
      if (!Array.isArray(value) || value.some(x => typeof x !== 'number' || !Number.isFinite(x) || (!euclidean && x < 0))) fail('Normalization requires a valid finite vector.');
      const total = euclidean ? Math.hypot(...value) : value.reduce((a, b) => a + b, 0);
      if (!(total > 0) || !Number.isFinite(total)) fail('Normalization requires positive finite total mass.');
      value = value.map(x => x / total); warning = euclidean ? 'Input normalized to unit length.' : 'Input normalized to unit sum.';
    }
    const walk = x => Array.isArray(x) ? x.map(walk) : validNumber(x);
    value = walk(value);
    return {value, warning};
  }
  function valueShape(value) {
    if (!Array.isArray(value)) return [];
    if (!value.length) fail('Empty scientific array.');
    const child = valueShape(value[0]);
    if (!value.every(x => JSON.stringify(valueShape(x)) === JSON.stringify(child))) fail('Ragged scientific array.');
    return [value.length, ...child];
  }
  function compute(inputs) {
    const next = clone(inputs), nextHistories = {}, dimensions = {};
    const resolveDimensions = variable => {
      if (!manifest.canonical_runtime || !own(next, variable.id)) return;
      const actual = valueShape(next[variable.id]);
      variable.shape.forEach((d, i) => { if (typeof d === 'string' && !own(next, d)) {
        if (own(dimensions, d) && dimensions[d] !== actual[i]) fail('Inconsistent symbolic shape.');
        dimensions[d] = actual[i];
      }});
    };
    manifest.variables.forEach(resolveDimensions);
    const expectedShape = variable => variable.shape.map(dimension => {
      const size = typeof dimension === 'string' ? (next[dimension] ?? dimensions[dimension]) : dimension;
      if (!Number.isInteger(size) || size < 1) fail('Scientific shape dimension must resolve to a positive integer.');
      return size;
    });
    for (const variable of manifest.variables) {
      if (own(next, variable.id) && (!manifest.canonical_runtime || variable.shape.length) && JSON.stringify(valueShape(next[variable.id])) !== JSON.stringify(expectedShape(variable))) fail('Input shape differs from the scientific variable.');
    }
    for (const c of manifest.computations) {
      const result = c.ast.type === 'Canonical' ? globalThis.ScientificCanonical.execute(c.ast, next) : {value: AST.evaluate(c.ast, next), history: []};
      for (const id of c.output_refs) next[id] = clone(result.value);
      nextHistories[c.id] = result.history;
    }
    manifest.variables.forEach(resolveDimensions);
    for (const variable of manifest.variables) {
      const value = next[variable.id];
      if (!AST.finite(value)) fail('Scientific state must be finite and defined.');
      if ((!manifest.canonical_runtime || variable.shape.length) && JSON.stringify(valueShape(value)) !== JSON.stringify(expectedShape(variable))) fail('Computed shape mismatch.');
      if (manifest.canonical_runtime) globalThis.ScientificCanonical.validateValue(value, variable.type, variable.shape, variable.domain);
      if (variable.type === 'scalar' && typeof value !== 'number') fail('Scalar output required.');
      if (variable.type === 'boolean' && typeof value !== 'boolean') fail('Boolean output required.');
      if (variable.type === 'categorical' && typeof value !== 'string') fail('Categorical output required.');
      const numericLeaves = x => Array.isArray(x) ? x.length > 0 && x.every(numericLeaves) : typeof x === 'number' && Number.isFinite(x);
      if (['vector', 'matrix', 'distribution'].includes(variable.type) && (!Array.isArray(value) || !numericLeaves(value))) fail('Numeric scientific array required.');
      if (variable.type === 'distribution') {
        const sum = value.reduce((a, b) => a + b, 0);
        if (value.some(x => x < 0) || Math.abs(sum - 1) > manifest.numeric_tolerance) fail('Probability distribution outside domain.');
      }
    }
    for (const invariant of manifest.invariant_programs || []) if (AST.evaluate(invariant, next) !== true) fail('Scientific invariant failed.');
    histories = nextHistories;
    return next;
  }
  // Editable number grids mirror array textareas so learners never type raw JSON.
  function renderGrid(el, value) {
    const grid = document.querySelector('[data-grid-for="' + el.id + '"]');
    if (!grid || !Array.isArray(value)) return;
    const matrix = value.every(Array.isArray);
    const rows = matrix ? value : [value];
    const signature = rows.length + 'x' + rows[0].length;
    if (grid.dataset.signature !== signature) {
      grid.dataset.signature = signature;
      grid.style.gridTemplateColumns = 'repeat(' + rows[0].length + ', minmax(0, 1fr))';
      grid.replaceChildren(...rows.flatMap((row, i) => row.map((_, j) => {
        const cell = document.createElement('input');
        cell.type = 'number'; cell.step = 'any'; cell.className = 'cell-input';
        cell.dataset.row = String(i); cell.dataset.col = String(j);
        cell.setAttribute('aria-label', (matrix ? 'row ' + (i + 1) + ', column ' + (j + 1) : 'entry ' + (j + 1)));
        const commit = () => {
          const current = JSON.parse(el.value);
          const parsed = Number(cell.value);
          if (matrix) current[i][j] = parsed; else current[j] = parsed;
          el.value = JSON.stringify(current);
          el.dispatchEvent(new Event('change', {bubbles: true}));
        };
        cell.addEventListener('change', commit);
        return cell;
      })));
      grid.removeAttribute('aria-hidden');
    }
    const cells = grid.querySelectorAll('input');
    rows.forEach((row, i) => row.forEach((x, j) => { const cell = cells[i * row.length + j]; if (cell && document.activeElement !== cell) cell.value = AST.short(x); }));
  }
  function refresh() {
    for (const [id, el] of elements) {
      const value = state[id];
      if (el.type === 'checkbox') el.checked = value;
      else el.value = Array.isArray(value) ? JSON.stringify(value) : String(value);
      const display = document.getElementById(el.getAttribute('aria-describedby').split(' ')[0]);
      if (Array.isArray(value)) { display.replaceChildren(AST.substituted({type: 'Constant', value}, symbols, null)); display.classList.add('math-value'); }
      else display.textContent = AST.format(value);
      el.removeAttribute('aria-invalid');
      renderGrid(el, value);
    }
    document.querySelectorAll('dl.symbols dt, .output .symbol').forEach(dt => {
      const label = dt.dataset.symbol || dt.textContent;
      dt.dataset.symbol = label;
      dt.replaceChildren(AST.symbol(label));
    });
    outputs.forEach(el => {
      const value = state[el.dataset.outputId];
      el.textContent = AST.format(value);
      el.dataset.value = JSON.stringify(value);
      // Arrays additionally get a typeset matrix view; the plain text stays canonical for validation.
      const view = el.parentElement.querySelector('[data-math-for]');
      if (view) {
        if (Array.isArray(value)) { view.replaceChildren(AST.substituted({type: 'Constant', value}, symbols, null)); el.classList.add('has-math'); }
        else { view.replaceChildren(); el.classList.remove('has-math'); }
      }
      el.classList.remove('tick');
      void el.offsetWidth;
      el.classList.add('tick');
    });
    for (const computation of manifest.computations) {
      const panel = document.getElementById('equation-' + computation.id);
      const target = computation.output_refs[0];
      panel.querySelector('[data-role="equation"]').replaceChildren(AST.math(computation.ast, symbols, symbols[target]));
      const substitutedPanel = panel.querySelector('[data-role="substituted"]');
      if (substitutedPanel) substitutedPanel.replaceChildren(AST.substituted(computation.ast, symbols, state, state[target]));
      panel.querySelector('[data-role="substitution"]').textContent = AST.equation(computation.ast, symbols, state) + ' = ' + AST.format(state[target]);
      panel.dataset.value = JSON.stringify(state[target]);
    }
    manifest.visuals.forEach(v => globalThis.ScientificVisuals.render(visualElements.get(v.id), v, state, {...ui, symbols, histories}));
    document.querySelectorAll('[data-exploration-id]').forEach(el => { el.dataset.active = String(el.dataset.explorationId === ui.exploration); });
    const step = document.querySelector('[data-role="step-value"]');
    if (step) step.textContent = 'Step ' + (ui.step + 1);
    const note = document.querySelector('[data-role="comparison-status"]');
    if (note) note.textContent = ui.comparison ? 'Comparison saved.' : 'No comparison saved.';
    error = null;
  }
  function apply(setup, exploration = null) {
    const inputs = clone(manifest.initial_state);
    Object.keys(inputs).forEach(key => { if (own(state, key)) inputs[key] = clone(state[key]); });
    let warning = '';
    for (const [id, value] of Object.entries(setup)) {
      if (!controls.has(id)) fail('Unknown scientific input.');
      const checked = checkValue(controls.get(id), value);
      inputs[id] = checked.value; warning = checked.warning || warning;
    }
    const next = compute(inputs); // Transaction: invalid math never partially updates state.
    state = next; ui.exploration = exploration; ui.step = 0;
    refresh(); status.textContent = warning || (exploration ? 'Setup applied. Observe the values and visual.' : 'Scientific state updated.');
    return clone(state);
  }
  function reset() {
    const inputs = clone(manifest.initial_state);
    for (const [id, control] of controls) {
      const checked = checkValue(control, inputs[id]);
      if (JSON.stringify(checked.value) !== JSON.stringify(inputs[id])) fail('Default requires normalization or clamping.');
    }
    state = compute(inputs); ui = {step: 0, comparison: null, exploration: null};
    refresh(); status.textContent = 'Default setup restored.';
  }
  function guarded(action, el = null) {
    try { action(); }
    catch (e) {
      error = String(e.message); refresh(); error = String(e.message);
      status.textContent = 'This setup is invalid: ' + error;
      if (el) el.setAttribute('aria-invalid', 'true');
    }
  }
  elements.forEach((el, id) => el.addEventListener(el.type === 'range' ? 'input' : 'change', () =>
    guarded(() => apply({[id]: el.type === 'checkbox' ? el.checked : el.value}), el)));
  document.querySelector('[data-role="reset"]').addEventListener('click', () => guarded(reset));
  document.querySelectorAll('[data-role="apply-setup"]').forEach(button => button.addEventListener('click', () => guarded(() => {
    const exploration = manifest.explorations.find(e => e.id === button.dataset.setupId);
    // Presets start from defaults for deterministic behavior independent of history.
    const previous = clone(state), previousUi = clone(ui), previousHistories = clone(histories);
    try { reset(); apply(exploration.runtime_setup, exploration.id); }
    catch (e) { state = previous; ui = previousUi; histories = previousHistories; throw e; }
  })));
  const save = document.querySelector('[data-role="save-comparison"]');
  if (save) save.addEventListener('click', () => guarded(() => { ui.comparison = clone(state); refresh(); }));
  const step = document.querySelector('[data-role="step-next"]');
  if (step) step.addEventListener('click', () => guarded(() => {
    const sequences = manifest.visuals.filter(v => v.component === 'process').map(v => histories[v.metadata.history_ref] || state[v.data_refs[0]]);
    const max = Math.max(...sequences.map(x => Array.isArray(x) ? x.length : 1));
    ui.step = Math.min(ui.step + 1, max - 1); refresh();
  }));
  rootAPI();
  function rootAPI() {
    globalThis.PlaygroundRuntime = Object.freeze({
      snapshot: () => ({state: clone(state), histories: clone(histories), ui: clone(ui), error}),
      apply, reset, evaluate: AST.evaluate, equation: AST.equation,
    });
  }
  try { reset(); document.documentElement.dataset.runtimeReady = 'true'; }
  catch (e) { error = String(e.message); status.textContent = 'This scientific setup cannot be evaluated: ' + error; throw e; }
})();
