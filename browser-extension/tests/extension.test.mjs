import { test } from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import { extractTable, snapshotDocument, createPageReader, readRenderedNode, parseTable, outputValue, renderSnapshot, PROVIDER } from '../dist/test-api.mjs'
const require = createRequire(import.meta.url)
const { JSDOM } = require('jsdom')
const basic = { id:'shipping', hit_policy:'FIRST', rules:[{id:'priority',when:{all:[{gte:['amount',100]},{eq:['vip',true]}]},output:{fee:0,service:'express'}},{id:'standard',when:true,output:{fee:10,service:'normal'}}] }
const raw = JSON.stringify(basic)
const data = (table=raw, more={}) => ({type:'tool',selected:true,provider_type:'builtin',provider_id:PROVIDER,tool_name:'evaluate',title:'Test DMN',tool_configurations:{table_json:{type:'constant',value:table}},...more})
function dom() { return new JSDOM('<!doctype html><html><body><main></main></body></html>',{url:'http://localhost/app/synthetic/workflow'}) }
function node(document,id,d) {
  const e=document.createElement('div'); e.className='react-flow__node'; e.dataset.id=id
  e.__reactProps$test={children:{props:{id,data:d}}}; document.querySelector('main').append(e);return e
}
test('MV3 permissions are activeTab + scripting only; no persistent hosts/remote content',()=>{
 const m=JSON.parse(fs.readFileSync(new URL('../dist/extension/manifest.json',import.meta.url)))
 assert.equal(m.manifest_version,3);assert.deepEqual(m.permissions,['activeTab','scripting']);assert.equal(m.host_permissions,undefined);assert.equal(m.content_scripts,undefined);assert.equal(m.web_accessible_resources,undefined)
 for(const f of ['content.js','reader.js','background.js']) { const text=fs.readFileSync(new URL(`../dist/extension/${f}`,import.meta.url),'utf8');assert.doesNotMatch(text,/\bfetch\s*\(|new\s+XMLHttpRequest|\beval\s*\(|innerHTML\s*=/) }
})
test('exact identity accepts only evaluate',()=>{
 assert.equal(extractTable(data(),'A').raw,raw)
 for(const more of [{type:'llm'},{provider_type:'api'},{provider_id:'other/dmn_decision/dmn'},{tool_name:'execute_query'},{tool_name:'evaluate_json_table'},{provider_id:PROVIDER+':0.7'}]) assert.equal(extractTable(data(raw,more),'A').status,'unsupported')
})
test('unrelated node cannot expose table_json or credential fields',()=>{
 const other={type:'tool',provider_id:'other'}
 Object.defineProperty(other,'tool_configurations',{get(){throw Error('should not read unrelated config')}})
 assert.equal(extractTable(other,'A').status,'unsupported')
 const d=data();Object.defineProperty(d,'credentials',{get(){throw Error('no credential reads')}});assert.equal(extractTable(d,'A').status,'ready')
})
test('constant, mixed static, empty, variable, malformed bindings fail safely',()=>{
 const read=setting=>extractTable(data(raw,{tool_configurations:{table_json:setting}}),'A')
 assert.equal(read(raw).status,'ready');assert.equal(read({type:'mixed',value:raw}).status,'ready')
 assert.equal(read({type:'variable',value:['start','table']}).status,'dynamic')
 assert.equal(read({type:'mixed',value:'{{#start.table#}}'}).status,'dynamic')
 assert.equal(read({type:'mixed',value:'xx {{#start.\ntable#}} yy'}).status,'dynamic')
 assert.equal(read({type:'new-binding',value:raw}).status,'dynamic')
 assert.equal(read({type:'constant',value:{rules:[]}}).status,'error')
 assert.equal(read({type:'constant',value:''}).status,'empty')
 assert.equal(read({type:'constant',value:'x'.repeat(512*1024+1)}).status,'error')
})
test('uses current DOM props, not stale fiber alternates',()=>{
 const {window:{document}}=dom();const e=node(document,'A',data())
 e.__reactFiber$test={memoizedProps:{id:'wrong',data:data('stale')}}
 assert.equal(readRenderedNode(e).data.tool_configurations.table_json.value,raw)
 e.__reactProps$test={children:{props:{id:'A',data:data('{broken')}}}
 assert.equal(snapshotDocument(document).raw,'{broken')
})
test('selection switches, deselection, unsupported nodes and route changes clear source',()=>{
 const {window:{document}}=dom();const a=node(document,'A',data());const b=node(document,'B',data(JSON.stringify({...basic,id:'B'}),{selected:false}))
 assert.equal(snapshotDocument(document).nodeId,'A')
 a.__reactProps$test.children.props.data.selected=false;b.__reactProps$test.children.props.data.selected=true
 assert.equal(snapshotDocument(document).nodeId,'B')
 b.__reactProps$test.children.props.data=data(raw,{tool_name:'other'})
 assert.equal(snapshotDocument(document).status,'unsupported')
 b.__reactProps$test.children.props.data.selected=false;assert.equal(snapshotDocument(document).status,'idle')
 document.defaultView.history.pushState({},'', '/apps');assert.equal(snapshotDocument(document).status,'unsupported')
})
test('missing private DOM props fails closed, not empty fake matrix',()=>{
 const {window:{document}}=dom();const e=node(document,'A',data());delete e.__reactProps$test;assert.equal(snapshotDocument(document).status,'error')
})
test('accessor props are never invoked',()=>{
 const {window:{document}}=dom();const e=node(document,'A',data());Object.defineProperty(e,'__reactProps$test',{get(){throw Error('should not run')}});assert.equal(readRenderedNode(e),null)
})
test('renderer shows actual fields, rule order, outputs, logic',()=>{
 const {window:{document}}=dom();const c=document.createElement('div');renderSnapshot(c,extractTable(data(),'A'))
 assert.equal(c.querySelectorAll('tbody tr').length,2);assert.deepEqual([...c.querySelectorAll('tbody th')].map(e=>e.textContent),['priority','standard'])
 assert.match(c.textContent,/条件 · "amount"/);assert.match(c.textContent,/条件 · "vip"/);assert.match(c.textContent,/\(A 且 B\)/);assert.match(c.textContent,/express/);assert.match(c.textContent,/未执行/)
})
test('invalid JSON removes previous valid matrix immediately',()=>{
 const {window:{document}}=dom();const c=document.createElement('div');renderSnapshot(c,extractTable(data(),'A'));assert(c.querySelector('table'))
 renderSnapshot(c,extractTable(data('{broken'),'A'));assert.equal(c.querySelector('table'),null);assert.equal(c.dataset.status,'error');assert.match(c.textContent,/JSON 格式错误/)
})
test('dynamic and unsupported selection remove previous matrix and old node identity',()=>{
 const {window:{document}}=dom();const c=document.createElement('div');renderSnapshot(c,extractTable(data(),'A'))
 renderSnapshot(c,{status:'dynamic',nodeId:'B',message:'unresolved'});assert.equal(c.querySelector('table'),null);assert.equal(c.dataset.nodeId,'B');assert.doesNotMatch(c.textContent,/priority/)
 renderSnapshot(c,{status:'unsupported',message:'unsupported'});assert.equal(c.dataset.nodeId,undefined)
})
test('no HTML execution: user strings are text only',()=>{
 const {window:{document}}=dom();const c=document.createElement('div');const s='<img src=x onerror=alert(1)>'
 renderSnapshot(c,extractTable(data(JSON.stringify({id:s,hit_policy:'FIRST',rules:[{id:s,when:{eq:[s,s]},output:s}]})),'A'))
 assert.equal(c.querySelector('img'),null);assert.match(c.textContent,/<img/)
})
test('pagination includes all rules and switch resets page',()=>{
 const {window:{document}}=dom();const c=document.createElement('div');const big={id:'big',hit_policy:'COLLECT',rules:Array.from({length:125},(_,i)=>({id:`r${i}`,when:true,output:i}))}
 renderSnapshot(c,extractTable(data(JSON.stringify(big)),'A'));assert.equal(c.querySelectorAll('tbody tr').length,50)
 c.querySelectorAll('nav button')[1].click();assert.equal(c.querySelector('tbody th').textContent,'r50')
 c.querySelectorAll('nav button')[1].click();assert.equal(c.querySelectorAll('tbody tr').length,25);assert.equal(c.querySelector('tbody th').textContent,'r100')
 renderSnapshot(c,extractTable(data(),'B'));assert.equal(c.querySelector('tbody th').textContent,'priority');assert.equal(c.querySelector('nav'),null)
})
test('too wide tables fail clearly without truncated misleading matrix',()=>{
 const {window:{document}}=dom();const c=document.createElement('div');const output=Object.fromEntries(Array.from({length:130},(_,i)=>[`c${i}`,i]))
 renderSnapshot(c,extractTable(data(JSON.stringify({id:'wide',hit_policy:'FIRST',rules:[{id:'r',when:true,output}]})),'A'));assert.equal(c.querySelector('table'),null);assert.equal(c.dataset.status,'error')
})
test('parser preserves FIRST COLLECT UNIQUE, nested OR, no conditions mutation',()=>{
 for(const policy of ['FIRST','COLLECT','UNIQUE']) { const t={...basic,hit_policy:policy};assert.equal(parseTable(JSON.stringify(t)).matrix.table.hit_policy,policy) }
 const t={id:'nested',hit_policy:'COLLECT',rules:[{id:'r',when:{any:[{eq:['a',1]},{all:[{gt:['b',2]},{eq:['a',3]}]}]}}]};const original=JSON.stringify(t);const result=parseTable(original);assert.equal(result.matrix.rows[0].logic,'(A 或 (B 且 C))');assert.equal(JSON.stringify(t),original)
})
test('strict parser rejects duplicate keys, malformed operators and unsafe numbers',()=>{
 for(const s of ['{','[]','null','{"id":"x","id":"y","hit_policy":"FIRST","rules":[]}','{"id":"x","hit_policy":"FIRST","rules":[],"n":9007199254740993}']) assert.equal(parseTable(s).kind,'error')
 for(const when of [{eq:['x']},{all:true},{foo:1},{constraint_set:{record:'x',mode:'wrong'}}]) assert.equal(parseTable(JSON.stringify({...basic,rules:[{id:'x',when}]})).kind,'error')
})
test('missing versus false zero null and string outputs remain distinct',()=>{
 const t={id:'values',hit_policy:'FIRST',rules:[{id:'missing',when:true},...([false,0,null,''].map((output,i)=>({id:String(i),when:true,output})))]};const m=parseTable(JSON.stringify(t)).matrix
 assert.deepEqual(m.rows.map(r=>outputValue(r.rule,m.outputs[0])),[{present:false},{present:true,value:false},{present:true,value:0},{present:true,value:null},{present:true,value:''}])
})
test('page bridge stays live >6s, clears stopped reader, supports close and re-enable', async()=>{
 const vm=await import('node:vm')
 const d=new JSDOM('<!doctype html><main></main>',{url:'http://localhost/app/synthetic/workflow',runScripts:'outside-only'})
 const {window:w}=d;node(w.document,'A',data())
 let now=100000;w.Date.now=()=>now
 const tasks=new Map();let next=0
 w.setInterval=(fn,ms)=>{const id=++next;tasks.set(id,{fn,ms,at:now+ms});return id}
 w.clearInterval=id=>tasks.delete(id)
 w.requestAnimationFrame=fn=>{fn();return 1}
 w.chrome={runtime:{sendMessage:()=>Promise.resolve()}}
 w.TextEncoder=TextEncoder
 const content=fs.readFileSync(new URL('../dist/extension/content.js',import.meta.url),'utf8')
 const reader=fs.readFileSync(new URL('../dist/extension/reader.js',import.meta.url),'utf8')
 const run=text=>vm.runInContext(text,d.getInternalVMContext())
 function advance(ms){const end=now+ms;while(now<end){now=Math.min(end,now+250);for(const [id,t]of [...tasks])if(tasks.has(id)&&t.at<=now){t.at=now+t.ms;t.fn()}}}
 run(content);run(reader);assert(w.document.querySelector('#dmn-preview-extension-root table'))
 advance(8000);assert(w.document.querySelector('#dmn-preview-extension-root table'),'stable table must remain after >6 sec')
 w.document.dispatchEvent(new w.CustomEvent('dmn-preview:stop:v1'));advance(6000);assert.equal(w.document.querySelector('#dmn-preview-extension-root table'),null);assert.match(w.document.querySelector('#dmn-preview-extension-root').textContent,/读取已中断/)
 run(content);run(reader);assert(w.document.querySelector('#dmn-preview-extension-root table'))
 w.document.querySelector('#dmn-preview-extension-root > header button:last-child').click();assert.equal(w.document.querySelector('#dmn-preview-extension-root'),null);assert.equal(tasks.size,0)
 run(content);run(reader);assert(w.document.querySelector('#dmn-preview-extension-root table'));assert.equal(w.document.querySelectorAll('#dmn-preview-extension-root').length,1)
 w.document.querySelector('#dmn-preview-extension-root > header button:last-child').click();d.window.close()
})

test('SPA app A to B and Back cannot reuse the old app matrix without new activation',()=>{
 const {window:{document}}=dom();node(document,'A',data());const read=createPageReader(document)
 assert.equal(read().status,'ready')
 document.defaultView.history.pushState({},'', '/app/another/workflow');assert.equal(read().status,'unsupported')
 document.defaultView.history.pushState({},'', '/app/synthetic/workflow');assert.equal(read().status,'unsupported')
 const reactivated=createPageReader(document);assert.equal(reactivated().status,'ready')
})
test('constraint_set requires a literal valid mode string without coercion',()=>{
 for(const mode of [['satisfied'],['violated'],{},null,0]) {
  const result=parseTable(JSON.stringify({...basic,rules:[{id:'r',when:{constraint_set:{record:'checks',mode}}}]}))
  assert.equal(result.kind,'error')
 }
})
test('closing between content and reader injection does not restart hidden polling',async()=>{
 const vm=await import('node:vm');const d=new JSDOM('<!doctype html><main></main>',{url:'http://localhost/app/synthetic/workflow',runScripts:'outside-only'})
 const w=d.window;node(w.document,'A',data());w.TextEncoder=TextEncoder
 const timers=new Set();const messages=[];let count=0
 w.setInterval=()=>{timers.add(++count);return count};w.clearInterval=id=>timers.delete(id);w.requestAnimationFrame=()=>1
 w.chrome={runtime:{sendMessage:message=>{messages.push(message.type);return Promise.resolve()}}}
 const run=file=>vm.runInContext(fs.readFileSync(new URL(`../dist/extension/${file}.js`,import.meta.url),'utf8'),d.getInternalVMContext())
 run('content');w.document.querySelector('#dmn-preview-extension-root > header button:last-child').click();run('reader')
 assert.equal(w.document.querySelector('#dmn-preview-extension-root'),null);assert.equal(timers.size,0);assert.deepEqual(messages,['dmn-preview-closed']);d.window.close()
})
test('over 1500 rendered workflow nodes fail instead of silently truncating selection',()=>{
 const {window:{document}}=dom();for(let i=0;i<1501;i++)node(document,String(i),data(raw,{selected:i===0||i===1500}))
 assert.equal(snapshotDocument(document).status,'error')
})

test('partly unreadable node scan cannot establish a unique current selection',()=>{
 const {window:{document}}=dom();node(document,'A',data());const b=node(document,'B',data())
 assert.equal(snapshotDocument(document).status,'idle')
 delete b.__reactProps$test;assert.equal(snapshotDocument(document).status,'error')
})
