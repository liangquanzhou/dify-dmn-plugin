import { useState } from 'react'
import { createRoot } from 'react-dom/client'
import DecisionTablePreview from '../src/decision-table'
import { first, collect, edge, unique } from './fixtures'
import './demo.css'
const samples = [first, collect, edge, unique]
function App() {
  const [node, setNode] = useState(0), [wide, setWide] = useState(true), [readOnly, setReadOnly] = useState(false)
  const [tables, setTables] = useState(samples.map(x => JSON.stringify(x, null, 2)))
  const [values, setValues] = useState('{"地区":"华北","订单金额":800,"会员":true}')
  const [result, setResult] = useState<null | Record<string, unknown>>(null)
  const [busy, setBusy] = useState(false)
  const choose = (i: number) => { setNode(i); setResult(null); setValues(i === 1 ? '{"region":"north","score":85}' : i === 2 ? '{"a.b":0}' : i === 3 ? '{"订单金额":800,"自提":false}' : '{"地区":"华北","订单金额":800,"会员":true}') }
  const run = async () => { setBusy(true); setResult(null); try { const r = await fetch('/api/evaluate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ table_json: tables[node], values_json: values }) }); setResult(await r.json()) } catch { setResult({ error: '此离线查看器只展示配置。真实执行请在 Dify 或云端验证服务进行。' }) } finally { setBusy(false) } }
  return <div className="app"><header className="topbar"><div className="brand"><span className="logo">▦</span><span>JSON 决策表<span className="version">0.5.0 candidate</span></span></div><span className="environment">云端验证 / 离线查看 · 非公司 Dify 实例</span></header>
    <main><div className="intro"><div><div className="kicker">WORKFLOW / TOOL NODE</div><h1>一行规则，一列字段</h1><p>按输入条件读规则，沿同一行查看输出；原始逻辑和执行顺序保持不变。</p></div><div className="viewToggle"><button className={wide ? 'active' : ''} onClick={() => setWide(true)}>完整矩阵</button><button className={!wide ? 'active' : ''} onClick={() => setWide(false)}>440px 侧栏</button></div></div>
    <div className={wide ? 'workspace' : 'workspace narrow'}><aside><span className="sectionLabel">工作流节点</span>{['FIRST · 订单履约','COLLECT · 嵌套条件','数据边界 · 输出类型','UNIQUE · 唯一配送','其他 Tool 节点'].map((x, i) => <button key={x} className={node === i ? 'selected' : ''} onClick={() => choose(i)}><span className="nodeNum">{String(i + 1).padStart(2, '0')}</span>{x}</button>)}<label className="readonly"><input type="checkbox" checked={readOnly} onChange={e => setReadOnly(e.target.checked)}/>模拟只读面板</label><p>示例均为合成数据。这里直接使用交付的 React 组件，无第二套表格实现。</p></aside>
    <section className="panel"><div className="panelTitle"><span>工具配置</span><span className="panelSubtitle">{node === samples.length ? '其他工具' : 'JSON Decision Table'}</span></div>{node === samples.length ? <div className="otherTool">其他工具保留原生配置，不插入决策表。</div> : <><DecisionTablePreview key={`node-${node}`} nodeId={`node-${node}`} value={tables[node]} readOnly={readOnly}/><details className="source" key={`source-${node}`}><summary>原始配置 · table_json</summary><textarea aria-label="table_json" spellCheck={false} readOnly={readOnly} value={tables[node]} onChange={e => { const v = [...tables]; v[node] = e.target.value; setTables(v); setResult(null) }}/></details>
    <details className="runner" key={`runner-${node}`}><summary>验证执行 · 同一份 JSON → Python 内核</summary><p>仅云端验证服务可执行；下载的离线 HTML 为配置查看器。</p><textarea aria-label="values_json" value={values} onChange={e => { setValues(e.target.value); setResult(null) }}/><button disabled={busy || location.protocol === 'file:'} onClick={run}>{busy ? '执行中…' : '执行原始 table_json'}</button>{result && <div className="result"><strong>{String(result.decision_status || result.error || '执行结果')}</strong><div>选中规则：{JSON.stringify(result.selected_rule_ids || [])}</div><details><summary>完整执行结果</summary><pre>{JSON.stringify(result, null, 2)}</pre></details></div>}</details></>}</section></div><footer>字段按首次出现顺序列出 · 不重写业务 JSON · 只读展示，不自动保存</footer></main></div>
}
createRoot(document.getElementById('root')!).render(<App/> )
