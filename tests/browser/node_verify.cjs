/* Optional development verifier using an existing Node Playwright installation. */
const fs = require('fs');
const {pathToFileURL} = require('url');
const assert = require('assert/strict');
const {chromium} = require('playwright');
const payload = JSON.parse(fs.readFileSync(0, 'utf8'));
function close(a,b){
  if(typeof a==='number'&&typeof b==='number')return Number.isFinite(a)&&Number.isFinite(b)&&Math.abs(a-b)<=Math.max(1e-8,1e-8*Math.max(Math.abs(a),Math.abs(b)));
  if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((x,i)=>close(x,b[i]));
  return a===b;
}
(async () => {
  const browser = await chromium.launch({executablePath:payload.executable,headless:true,args:['--disable-background-networking','--disable-component-update']});
  try {
    const context = await browser.newContext({offline:true,viewport:{width:1280,height:900}});
    await context.route('**/*',route => /^https?:/.test(route.request().url()) ? route.abort() : route.continue());
    const page = await context.newPage(), errors = [], requests=[];
    page.on('pageerror',e=>errors.push(String(e)));
    page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
    await page.goto(pathToFileURL(payload.artifact).href);
    assert.equal(await page.evaluate(()=>document.documentElement.dataset.runtimeReady),'true');
    const parity = await page.evaluate(cases=>cases.map(c=>{
      try{return {value:CanonicalScience.evaluate(c.ast,c.env)}}catch{return {rejected:true}}
    }),payload.cases||[]);
    const baseline = await page.evaluate(()=>PlaygroundRuntime.snapshot());
    async function inspect(expected,curves) {
      const snapshot = await page.evaluate(()=>PlaygroundRuntime.snapshot());
      assert.equal(snapshot.error,null);
      const coherent = await page.evaluate(()=>{
        const m=JSON.parse(document.getElementById('playground-manifest').textContent),s=PlaygroundRuntime.snapshot().state;
        return Array.from(document.querySelectorAll('[data-output-id]')).every(e=>e.dataset.value===JSON.stringify(s[e.dataset.outputId])&&e.textContent===ScientificAST.format(s[e.dataset.outputId])) &&
          Array.from(document.querySelectorAll('[data-visual-id]')).every((e,i)=>e.dataset.values===JSON.stringify(m.visuals[i].data_refs.map(r=>s[r]))&&e.querySelector('svg')) &&
          m.computations.every(c=>{const e=document.getElementById('equation-'+c.id),target=c.output_refs[0]||c.id;return e.querySelector('[data-role=substitution]').textContent===ScientificAST.equation(c.ast,{},s)+' = '+ScientificAST.format(s[target]);});
      });
      assert.ok(coherent,'Numbers, equations and visuals must use the same state');
      for(const [id,value]of Object.entries(expected||{}))assert.ok(close(snapshot.state[id],value),'Python/browser mismatch: '+id);
      for(const [id,points]of Object.entries(curves||{})){
        const plotted=await page.locator('[data-visual-id="'+id+'"]').evaluate(e=>({points:JSON.parse(e.dataset.curve),component:e.dataset.component,marker:JSON.parse(e.querySelector('.current-point').dataset.markValue)}));
        assert.equal(plotted.component,'curve');
        assert.ok(close(plotted.points,points),'Python/browser plotted-series mismatch: '+id);
        const descriptor=await page.evaluate(id=>JSON.parse(document.getElementById('playground-manifest').textContent).visuals.find(v=>v.id===id).sweep,id);
        assert.ok(close(plotted.marker,[snapshot.state[descriptor.input_ref],snapshot.state[descriptor.output_ref]]),'Current curve marker mismatch');
      }
      return snapshot;
    }
    await inspect(payload.baseline,payload.baseline_curves);
    for(const probe of payload.probes||[]){
      await page.locator('[data-role=reset]').click();
      const control=page.locator('[data-control-id]').nth(probe.control_index);
      if(probe.kind==='toggle')await control.setChecked(probe.value);
      else if(probe.kind==='select')await control.selectOption(probe.value);
      else {await control.fill(Array.isArray(probe.value)?JSON.stringify(probe.value):String(probe.value));await control.dispatchEvent(probe.kind==='slider'?'input':'change');}
      const changed=await inspect(probe.expected,probe.curves);
      assert.notDeepEqual(changed.state,baseline.state,'Control must change scientific state');
      await page.locator('[data-role=reset]').click();
      assert.deepEqual(await page.evaluate(()=>PlaygroundRuntime.snapshot()),baseline);
    }
    for(let i=0;i<(payload.presets||[]).length;i++){
      await page.locator('[data-role=apply-setup]').nth(i).click();await inspect(payload.presets[i],payload.preset_curves?.[i]);
    }
    await page.locator('[data-role=reset]').click();
    assert.deepEqual(await page.evaluate(()=>PlaygroundRuntime.snapshot()),baseline);
    assert.ok(await page.evaluate(()=>{
      const text=document.body.innerText;
      return !/SOURCE_GROUNDED|PEDAGOGICAL|Executable intermediate:|Claim-level grounding|No sampled series|compute-[a-z]/.test(text)&&
        Array.from(document.querySelectorAll('[data-role=equation]')).every(e=>!/(?:power|divide|multiply)\(/.test(e.textContent))&&
        document.querySelector('[data-role=status]').textContent==='';
    }),'The learner page must not contain internal diagnostics');
    for(const width of [375,768]){await page.setViewportSize({width,height:900});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
    console.log(JSON.stringify({status:'PASS',parity,probes:(payload.probes||[]).length,presets:(payload.presets||[]).length,offline:true}));
  } finally {await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1;});
