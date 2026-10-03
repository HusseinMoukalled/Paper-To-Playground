/* Version-1 canonical science interpreter. Source expressions are never executed. */
(function (root) {
  'use strict';
  const AST = root.ScientificAST;
  const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
  const fail = message => { throw new Error(message); };
  const clone = x => JSON.parse(JSON.stringify(x));
  const leaves = x => Array.isArray(x) ? x.flat(Infinity) : [x];
  const numeric = x => typeof x === 'number' && Number.isFinite(x) && Math.abs(x) <= 1e300;
  const shape = x => {
    if (!Array.isArray(x)) return [];
    if (!x.length || x.length > 4096) fail('Empty or oversized array');
    const sub = shape(x[0]);
    if (!x.every(y => JSON.stringify(shape(y)) === JSON.stringify(sub))) fail('Ragged array');
    const result = [x.length, ...sub];
    if (result.length > 2 || result.reduce((a,b)=>a*b,1) > 4096) fail('Array limit exceeded');
    return result;
  };
  const finite = x => { shape(x); if (!leaves(x).every(y => numeric(y) || typeof y === 'boolean' || typeof y === 'string')) fail('Invalid finite scientific value'); return x; };
  const vector = x => { if (shape(x).length !== 1 || !x.every(numeric)) fail('Numeric vector required'); return x; };
  const total = values => {
    let sum=0, correction=0;
    for(const value of values){const next=sum+value;correction+=Math.abs(sum)>=Math.abs(value)?(sum-next)+value:(value-next)+sum;sum=next;}
    return sum+correction;
  };
  const dot = (a,b) => {vector(a);vector(b);if(a.length!==b.length)fail('Dot shape mismatch');return total(a.map((x,i)=>x*b[i]));};
  const valueNode = x => Array.isArray(x) ? {type:'Vector',items:x.map(valueNode)} : {type:'Constant',value:x};
  const approx = (a,b) => JSON.stringify(shape(a)) === JSON.stringify(shape(b)) && leaves(a).every((x,i)=>{
    const y=leaves(b)[i]; if (!numeric(x)||!numeric(y)) fail('Numeric equality required');
    return Math.abs(x-y)<=Math.max(1e-8,1e-8*Math.max(Math.abs(x),Math.abs(y)));
  });
  const op = (name,args) => {
    args.forEach(finite);
    if (['add','subtract','multiply','divide','power'].includes(name) && args.every(Array.isArray) && JSON.stringify(shape(args[0])) !== JSON.stringify(shape(args[1]))) fail('Binary shape mismatch');
    if (name==='normalize') { const a=vector(args[0]), n=Math.hypot(...a); if (!n) fail('Zero vector normalization'); return a.map(x=>x/n); }
    if (name==='negate') return AST.evaluate({type:'Unary',op:'-',operand:valueNode(args[0])},{});
    if (name==='sin'||name==='cos') { const walk=x=>Array.isArray(x)?x.map(walk):numeric(x)?Math[name](x):fail('Numeric trigonometric input required'); return walk(args[0]); }
    if (name==='sum'||name==='mean') { const a=leaves(args[0]); if (!a.every(numeric)) fail('Numeric reduction required'); const s=total(a); return name==='mean'?s/a.length:s; }
    if (name==='entropy') { const a=vector(args[0]), s=total(a); if (a.some(x=>x<0||x>1)||Math.abs(s-1)>Math.max(1e-8,1e-8*Math.abs(s))) fail('Entropy requires a distribution'); return -total(a.map(x=>x===0?0:x*Math.log(x))); }
    if (name==='dot') return dot(...args);
    if (name==='softmax') {const a=vector(args[0]),peak=Math.max(...a),terms=a.map(x=>Math.exp(x-peak)),z=total(terms);return terms.map(x=>x/z);}
    if (name==='approx_equal') return approx(args[0],args[1]);
    if (name==='matmul') {const [a,b]=args,sa=shape(a),sb=shape(b);if(sa.length!==2||![1,2].includes(sb.length)||sa[1]!==sb[0])fail('Matrix multiplication rank mismatch');return sb.length===1?a.map(row=>dot(row,b)):a.map(row=>b[0].map((_,i)=>dot(row,b.map(r=>r[i]))));}
    if (name==='power') { const check=(a,b)=>{if(Array.isArray(a)&&Array.isArray(b)){if(JSON.stringify(shape(a))!==JSON.stringify(shape(b)))fail('Power shape mismatch');a.forEach((x,i)=>check(x,b[i]));}else if(Array.isArray(a))a.forEach(x=>check(x,b));else if(Array.isArray(b))b.forEach(x=>check(a,x));else if(!numeric(a)||!numeric(b)||Math.abs(b)>128||(a===0&&b<0)||(a<0&&!Number.isInteger(b)))fail('Power outside real bounded domain');};check(...args); }
    return AST.evaluate({type:'Call',function:name,args:args.map(valueNode)},{});
  };
  function evaluateNode(node, env, guard={nodes:0,start:performance.now()}, depth=0) {
    if (++guard.nodes>250000 || depth>32 || performance.now()-guard.start>30000) fail('Canonical work limit exceeded');
    const run=n=>evaluateNode(n,env,guard,depth+1);
    let value;
    switch(node.kind) {
      case 'literal': value=node.value; break;
      case 'variable': if(!own(env,node.value))fail('Unbound canonical variable'); value=env[node.value]; break;
      case 'array': value=node.args.map(run); break;
      case 'call': value=op(node.value,node.args.map(run)); break;
      case 'index': {const a=run(node.args[0]);if(!Array.isArray(a)||!Number.isInteger(node.value)||node.value<0||node.value>=a.length)fail('Canonical index outside domain');value=a[node.value];break;}
      case 'compare': {let [a,b]=node.args.map(run);if(Array.isArray(a)||Array.isArray(b))fail('Scalar comparison required');if(typeof a==='boolean')a=Number(a);if(typeof b==='boolean')b=Number(b);if(!['eq','ne'].includes(node.value)&&typeof a!==typeof b)fail('Incomparable scalar types');const comparisons={lt:()=>a<b,le:()=>a<=b,gt:()=>a>b,ge:()=>a>=b,eq:()=>a===b,ne:()=>a!==b};if(!own(comparisons,node.value))fail('Unknown comparison');value=comparisons[node.value]();break;}
      case 'if': {const condition=run(node.args[0]);if(typeof condition!=='boolean')fail('Boolean condition required');value=run(node.args[condition?1:2]);break;}
      case 'and': case 'or': {const a=node.args.map(run);if(a.some(x=>typeof x!=='boolean'))fail('Boolean operands required');value=node.kind==='and'?a.every(Boolean):a.some(Boolean);break;}
      case 'not': {const a=run(node.args[0]);if(typeof a!=='boolean')fail('Boolean negation required');value=!a;break;}
      default: fail('Unsupported canonical node');
    }
    return finite(value);
  }
  function validateValue(value,type,expected=[],domain=null) {
    finite(value); const actual=shape(value);
    if (type==='scalar' && (actual.length||!numeric(value)))fail('Scalar required');
    if (type==='boolean'&&typeof value!=='boolean')fail('Boolean required');
    if (['categorical','state'].includes(type)&&typeof value!=='string')fail('State string required');
    const ranks={vector:1,matrix:2,distribution:1};
    if(own(ranks,type)&&actual.length!==ranks[type])fail('Scientific rank mismatch');
    if(type==='sequence'&&!actual.length)fail('Sequence required');
    if(expected.length&&(expected.length!==actual.length||expected.some((n,i)=>typeof n==='number'&&n!==actual[i])))fail('Declared shape mismatch');
    if(!['boolean','categorical','state'].includes(type))for(const x of leaves(value)) {
      if(!numeric(x))fail('Numeric scientific value required');
      if(domain==='positive'&&x<=0||domain==='nonnegative'&&x<0||['unit_interval','probability'].includes(domain)&&(x<0||x>1)||domain==='integer'&&!Number.isInteger(x))fail('Scientific domain violated');
    }
    if(type==='distribution'&&(value.some(x=>x<0)||Math.abs(value.reduce((a,b)=>a+b,0)-1)>1e-8))fail('Distribution must sum to one');
  }
  function execute(node,state) {
    const meta=node.metadata,env={},guard={nodes:0,start:performance.now()};
    for(const [name,id] of Object.entries(meta.bindings||{})){if(!own(state,id))fail('Missing canonical binding');env[name]=state[id];}
    const run=(ast,context)=>evaluateNode(ast,context,guard);
    let value,history=[];
    if(meta.kind==='iteration') {
      let local=Object.fromEntries(Object.entries(meta.initial_ast).map(([k,n])=>[k,run(n,env)]));
      const initialShapes=Object.fromEntries(Object.entries(local).map(([k,x])=>[k,shape(x)]));
      const types=Object.fromEntries(Object.entries(local).map(([k,x])=>[k,typeof x==='boolean'?'boolean':typeof x==='string'?'categorical':shape(x).length===2?'matrix':Array.isArray(x)?'vector':'scalar']));
      const check=()=>{for(const [k,x]of Object.entries(local)){const d=meta.state_specs?.[k]||{};validateValue(x,d.type||types[k],d.shape||initialShapes[k],d.domain||null);}for(const n of meta.state_invariant_ast||[])if(run(n,{...env,...local})!==true)fail('Iterative invariant failed');};
      check();history.push(clone(local));
      for(let i=0;i<meta.steps;i++){const snapshot={...env,...local};local=Object.fromEntries(Object.entries(meta.update_ast).map(([k,n])=>[k,run(n,snapshot)]));check();history.push(clone(local));}
      value=run(meta.canonical_ast,{...env,...local});
    } else if(meta.kind==='state_transition') {
      let current=meta.initial_state;history.push(current);
      for(let i=0;i<(meta.steps??1);i++){const active=[];for(const t of meta.transition_ast)if(t.from===current){const enabled=run(t.condition_ast,{...env,state:current});if(typeof enabled!=='boolean')fail('Boolean transition guard required');if(enabled)active.push(t.to);}if(active.length>1)fail('Ambiguous transitions');current=active[0]??current;history.push(current);}
      value=current;
    } else value=run(meta.canonical_ast,env);
    validateValue(value,node.output_type);return {value,history};
  }
  function display(node) {
    const meta=node.metadata;
    if(meta.kind==='state_transition')return {type:'Constant',value:'bounded state transitions ('+(meta.steps??1)+' steps)'};
    const convert=n=>{
      const args=n.args.map(convert);
      switch(n.kind){
        case 'literal': return {type:'Constant',value:n.value};
        case 'variable': return {type:'Variable',id:meta.bindings?.[n.value]||n.value};
        case 'array': return args.every(a=>a.type==='Vector')?{type:'Matrix',rows:args.map(a=>a.items)}:{type:'Vector',items:args};
        case 'call':return {type:'Call',function:n.value,args};
        case 'compare':return {type:'Binary',op:{lt:'<',le:'<=',gt:'>',ge:'>=',eq:'==',ne:'!='}[n.value],left:args[0],right:args[1]};
        case 'index':return {type:'Index',value:args[0],index:{type:'Constant',value:n.value}};
        case 'if':return {type:'Conditional',condition:args[0],then:args[1],else:args[2]};
        default:return {type:'Call',function:n.kind,args};
      }
    };return convert(meta.canonical_ast);
  }
  root.ScientificCanonical=Object.freeze({execute,display,validateValue,shape,evaluateNode});
})(globalThis);
