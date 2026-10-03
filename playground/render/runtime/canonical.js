/* Data-only canonical AST v1; mirrors the Python operation registry. */
(function(root){
  'use strict';
  const fail=m=>{throw new Error(m);}, own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
  const numeric=x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=1e300;
  const leaves=x=>Array.isArray(x)?x.flatMap(leaves):[x];
  function shape(x){
    if(!Array.isArray(x))return [];
    if(!x.length)fail('Empty array');
    const child=shape(x[0]);
    if(!x.every(y=>JSON.stringify(shape(y))===JSON.stringify(child)))fail('Ragged array');
    const result=[x.length,...child];
    if(result.length>2||result.reduce((a,b)=>a*b,1)>4096)fail('Array limit');
    return result;
  }
  const finite=x=>{shape(x);if(!leaves(x).every(v=>numeric(v)||typeof v==='string'||typeof v==='boolean'))fail('Nonfinite value');return x;};
  const number=x=>numeric(x)?x:fail('Number required');
  const vector=x=>shape(x).length===1?x.map(number):fail('Vector required');
  const map=(x,f)=>Array.isArray(x)?x.map(y=>map(y,f)):f(number(x));
  function zip(a,b,f){
    if(Array.isArray(a)&&Array.isArray(b)){if(JSON.stringify(shape(a))!==JSON.stringify(shape(b)))fail('Shape mismatch');return a.map((x,i)=>zip(x,b[i],f));}
    if(Array.isArray(a))return a.map(x=>zip(x,b,f));
    if(Array.isArray(b))return b.map(x=>zip(a,x,f));
    return f(number(a),number(b));
  }
  const total=x=>{let s=0,c=0;for(const item of leaves(x)){const y=number(item),t=s+y;c+=Math.abs(s)>=Math.abs(y)?(s-t)+y:(y-t)+s;s=t;}return s+c;};
  const close=(a,b)=>Math.abs(a-b)<=Math.max(1e-8,1e-8*Math.max(Math.abs(a),Math.abs(b)));
  const approx=(a,b)=>JSON.stringify(shape(a))===JSON.stringify(shape(b))&&leaves(a).every((x,i)=>close(number(x),number(leaves(b)[i])));
  const dot=(a,b)=>{vector(a);vector(b);if(a.length!==b.length)fail('Dot shape mismatch');return total(a.map((x,i)=>x*b[i]));};
  const transpose=a=>{if(shape(a).length!==2)fail('Matrix required');leaves(a).forEach(number);return a[0].map((_,i)=>a.map(row=>row[i]));};
  const boundedPower=(a,b)=>{if(Math.abs(b)>128||a===0&&b<0||a<0&&!Number.isInteger(b))fail('Power domain');return a**b;};
  const ops=Object.freeze({
    add:(a,b)=>zip(a,b,(x,y)=>x+y),subtract:(a,b)=>zip(a,b,(x,y)=>x-y),multiply:(a,b)=>zip(a,b,(x,y)=>x*y),divide:(a,b)=>zip(a,b,(x,y)=>y===0?fail('Division by zero'):x/y),power:(a,b)=>zip(a,b,boundedPower),
    negate:a=>map(a,x=>-x),abs:a=>map(a,Math.abs),sqrt:a=>map(a,x=>x<0?fail('Sqrt domain'):Math.sqrt(x)),exp:a=>map(a,Math.exp),log:a=>map(a,x=>x<=0?fail('Log domain'):Math.log(x)),sin:a=>map(a,Math.sin),cos:a=>map(a,Math.cos),
    sum:total,mean:a=>total(a)/leaves(a).length,min:a=>Math.min(...vector(a)),max:a=>Math.max(...vector(a)),dot,transpose,
    matmul:(a,b)=>{const sa=shape(a),sb=shape(b);if(sa.length!==2||![1,2].includes(sb.length)||sa[1]!==sb[0])fail('Matmul shape mismatch');return sb.length===1?a.map(row=>dot(row,b)):a.map(row=>transpose(b).map(col=>dot(row,col)));},
    norm:a=>Math.hypot(...vector(a)),normalize:a=>{vector(a);const n=Math.hypot(...a);if(n===0)fail('Zero normalization');return a.map(x=>x/n);},
    softmax:a=>{vector(a);const peak=Math.max(...a),e=a.map(x=>Math.exp(x-peak)),z=total(e);return e.map(x=>x/z);},
    entropy:a=>{vector(a);if(a.some(x=>x<0||x>1)||!close(total(a),1))fail('Entropy domain');return -total(a.map(x=>x===0?0:x*Math.log(x)));},approx_equal:approx
  });
  const unary=new Set(['negate','abs','sqrt','exp','log','sin','cos','sum','mean','min','max','transpose','norm','normalize','softmax','entropy']);
  function evaluate(n,env,guard={nodes:0},depth=0){
    if(++guard.nodes>250000||depth>32||!n)fail('AST work limit');
    const run=x=>evaluate(x,env,guard,depth+1),a=n.args;let result;
    switch(n.kind){
      case 'literal':result=n.value;break;
      case 'variable':if(!own(env,n.value))fail('Unbound symbol');result=env[n.value];break;
      case 'array':result=a.map(run);break;
      case 'call':if(!own(ops,n.value)||a.length!==(unary.has(n.value)?1:2))fail('Operation/arity');result=ops[n.value](...a.map(run));break;
      case 'index':{const x=run(a[0]);if(!Array.isArray(x)||!Number.isInteger(n.value)||n.value<0||n.value>=x.length)fail('Index domain');result=x[n.value];break;}
      case 'compare':{const [x,y]=a.map(run);if(Array.isArray(x)||Array.isArray(y))fail('Scalar comparison');if(typeof x!==typeof y)fail('Compatible scalar types required');const c={lt:()=>x<y,le:()=>x<=y,gt:()=>x>y,ge:()=>x>=y,eq:()=>x===y,ne:()=>x!==y};if(!own(c,n.value))fail('Comparison');result=c[n.value]();break;}
      case 'if':{const c=run(a[0]);if(typeof c!=='boolean')fail('Boolean condition');result=run(a[c?1:2]);break;}
      case 'not':{const x=run(a[0]);if(typeof x!=='boolean')fail('Boolean required');result=!x;break;}
      case 'and':case 'or':{const x=a.map(run);if(!x.every(v=>typeof v==='boolean'))fail('Boolean operands');result=n.kind==='and'?x.every(Boolean):x.some(Boolean);break;}
      default:fail('Unknown canonical node');
    }return finite(result);
  }
  function validate(value,type,expected=[],domain=null,dimensions={}){
    finite(value);const actual=shape(value);
    if(expected.length&&expected.length!==actual.length)fail('Scientific rank');
    expected.forEach((d,i)=>{if(typeof d==='string'){if(own(dimensions,d)&&dimensions[d]!==actual[i])fail('Symbolic shape');dimensions[d]=actual[i];}else if(d!==actual[i])fail('Scientific shape');});
    if(type==='scalar'&&(actual.length||!numeric(value)))fail('Scalar required');
    if(type==='boolean'&&typeof value!=='boolean')fail('Boolean required');
    if(['categorical','state'].includes(type)&&typeof value!=='string')fail('State required');
    const ranks={vector:1,distribution:1,matrix:2};if(own(ranks,type)&&actual.length!==ranks[type])fail('Scientific rank');
    if(type==='sequence'&&!actual.length)fail('Sequence required');
    if(!['boolean','categorical','state'].includes(type))leaves(value).forEach(x=>{number(x);if(domain==='positive'&&x<=0||domain==='nonnegative'&&x<0||['unit_interval','probability'].includes(domain)&&(x<0||x>1)||domain==='integer'&&!Number.isInteger(x))fail('Scientific domain');});
    if(type==='distribution'&&(value.some(x=>x<0)||!close(total(value),1)))fail('Distribution domain');
  }
  function execute(spec,state){
    const m=spec.metadata,env={},guard={nodes:0};if(m.ast_version!==1)fail('AST version');
    for(const [name,id]of Object.entries(m.bindings||{})){if(!own(state,id))fail('Missing binding');env[name]=state[id];}
    let result,history=[];
    if(m.kind==='iteration'){
      let local=Object.fromEntries(Object.entries(m.initial_ast).map(([k,v])=>[k,evaluate(v,env,guard)]));
      const specs=Object.fromEntries(Object.entries(local).map(([k,v])=>[k,{type:typeof v==='boolean'?'boolean':typeof v==='string'?'categorical':shape(v).length===2?'matrix':Array.isArray(v)?'vector':'scalar',shape:shape(v),...(m.state_specs||{})[k]}]));
      const check=()=>{for(const [k,v]of Object.entries(local)){const s=specs[k];validate(v,s.type,s.shape,s.domain);}for(const n of m.state_invariant_ast||[])if(evaluate(n,{...env,...local},guard)!==true)fail('Iterative invariant');};
      check();history.push({...local});if(!Number.isInteger(m.steps)||m.steps<1||m.steps>100)fail('Iteration bound');
      for(let i=0;i<m.steps;i++){const snapshot={...env,...local};local=Object.fromEntries(Object.entries(m.update_ast).map(([k,v])=>[k,evaluate(v,snapshot,guard)]));check();history.push({...local});}result=evaluate(m.canonical_ast,{...env,...local},guard);
    }else if(m.kind==='state_transition'){
      let current=m.initial_state;history.push(current);const steps=m.steps??1;if(!Number.isInteger(steps)||steps<1||steps>100)fail('State bound');
      for(let i=0;i<steps;i++){const active=[];for(const t of m.transition_ast)if(t.from===current){const yes=evaluate(t.condition_ast,{...env,state:current},guard);if(typeof yes!=='boolean')fail('State guard');if(yes)active.push(t.to);}if(active.length>1)fail('Ambiguous transition');current=active.length?active[0]:current;history.push(current);}result=current;
    }else result=evaluate(m.canonical_ast,env,guard);
    validate(result,spec.output_type);return {result,history};
  }
  function equation(wire,symbols={},state=null){
    const m=wire.spec.metadata,b=m.bindings||{};
    function text(n){const a=n.args.map(text);if(n.kind==='literal')return JSON.stringify(n.value);if(n.kind==='variable'){const id=b[n.value];return state&&own(state,id)?root.ScientificAST.format(state[id]):symbols[id]||n.value;}if(n.kind==='array')return '['+a.join(', ')+']';if(n.kind==='index')return a[0]+'['+n.value+']';if(n.kind==='call')return n.value+'('+a.join(', ')+')';if(n.kind==='compare')return '('+a[0]+' '+n.value+' '+a[1]+')';return n.kind+'('+a.join(', ')+')';}
    if(m.kind==='state_transition')return 'State transition ('+(m.steps??1)+' steps from '+m.initial_state+')';
    if(m.kind==='iteration')return 'Iterate '+m.steps+' steps: '+Object.entries(m.update_ast).map(([k,v])=>k+' ← '+text(v)).join('; ')+'; return '+text(m.canonical_ast);
    return text(m.canonical_ast);
  }
  root.CanonicalScience=Object.freeze({evaluate,execute,validate,shape,operations:Object.keys(ops),equation});
})(globalThis);
