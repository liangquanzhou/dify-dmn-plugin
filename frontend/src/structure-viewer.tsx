import { Component, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import DecisionTablePreview from './decision-table'
import { counts, diagnostics, LIMITS, localTable, locationKey, matches, modelFor, modelProfile, own, parseStructure, raw, record, text } from './structure-model'
import type { Bundle, Diagnostic, Edge, Location, Node, Obj, Step } from './structure-model'
import { example } from './structure-fixture'
import './structure-viewer.css'
const initial = parseStructure(JSON.stringify(example))
const nodeHeight = 114
function JsonBlock({ title, value, open = false }: { title: string; value: unknown; open?: boolean }) {
  return <details className="sv-raw" open={open}><summary>{title}</summary><pre>{raw(value)}</pre></details>
}
function RuleTable({ model }: { model: Obj }) {
  const [page, setPage] = useState(0)
  const rules = Array.isArray(model.rules) ? model.rules : []
  const simple = modelProfile(model) === 'json-table-v1'
  const templates = record(model.result_templates) ? model.result_templates : {}
  return <><p>profile: {modelProfile(model)} · hit_policy: {text(model.hit_policy) || '未声明'} · {rules.length} 条规则</p>
    <p className="sv-muted">以下为原始条件与结果定义；对象路径不会转换为扁平字段，已知 null 与 UNKNOWN 不作合并。本视图不求值。</p>
    {rules.length > 50 && <div className="sv-toolbar"><button disabled={!page} onClick={() => setPage(page - 1)}>规则上一页</button><span>{page * 50 + 1}–{Math.min((page + 1) * 50, rules.length)} / {rules.length}</span><button disabled={(page + 1) * 50 >= rules.length} onClick={() => setPage(page + 1)}>规则下一页</button></div>}
    <div className="sv-rules-scroll" tabIndex={0} role="region" aria-label="类型化规则，可横向滚动"><table className="sv-rules"><thead><tr><th>规则 ID</th><th>条件 · 行内 AND / 原始逻辑</th>{simple ? <th>output · 原始 JSON</th> : <><th>state</th><th>data</th><th>actions</th></>}</tr></thead><tbody>{rules.slice(page * 50, (page + 1) * 50).map((r, i) => {
      const rule = record(r) ? r : {}; const ref = text(rule.output_template_ref)
      const missing = own(rule, 'output_template_ref') && !own(templates, ref)
      const template = own(rule, 'output_template_ref') ? templates[ref] : rule.output
      const result = record(template) ? template : {}
      return <tr key={page * 50 + i}><th scope="row">{text(rule.rule_id) || text(rule.id) || `#${page * 50 + i + 1}`}<small>{ref ? `template: ${ref}` : 'inline output'}</small><JsonBlock title="完整原始规则" value={r}/></th>
        <td><pre>{raw(own(rule, 'when') ? rule.when : rule.conditions)}</pre></td>{simple ? <td><pre>{raw(rule.output)}</pre></td> : <><td>{missing ? <strong className="sv-warning">缺少模板；不使用 inline output</strong> : <pre>{raw(result.state)}</pre>}</td>
        <td><pre>{missing ? '未解析' : raw(result.data)}</pre></td><td><pre>{missing ? '未解析' : raw(own(result, 'actions') ? result.actions : template)}</pre></td></>}</tr>
    })}</tbody></table></div>
    <JsonBlock title="参数契约" value={model.parameters}/><JsonBlock title="全部结果模板与未命中策略" value={{ result_templates: model.result_templates, on_no_match: model.on_no_match, empty_template_ref: model.empty_template_ref }}/>
  </>
}
function EdgeList({ edges, selected }: { edges: Edge[]; selected?: string }) {
  return <ul className="sv-edges">{edges.map(e => <li key={e.edge_id} className={e.source === selected ? 'sv-outgoing' : e.target === selected ? 'sv-incoming' : ''}><b>{e.edge_id}</b> · {e.source} <strong>[{e.source_port}] →</strong> {e.target}<JsonBlock title="完整边定义 / 条件" value={e}/></li>)}</ul>
}
function Detail({ bundle, location, issues }: { bundle: Bundle; location: Location; issues: Diagnostic[] }) {
  const { workflow, phase, step, node } = location
  const model = node ? modelFor(bundle, node) : undefined
  const local = model?.profile === 'dmn-local-table-v1' ? localTable(model) : undefined
  return <><p className="sv-breadcrumb">{workflow.workflow_id} → {phase.phase_id} → {step.step_id}{node ? ` → ${node.node_id}` : ''}</p>
    <h2>{text(node?.name) || node?.node_id || text(step.name) || step.step_id}</h2>
    <p>{node ? `${node.kind} · ports: ${raw(node.ports)}` : 'Step 详情'} · 只读定义，不表示已执行</p>
    {issues.length > 0 && <DetailDiagnostics issues={issues}/>}
    {node && <><JsonBlock title="完整绑定" value={{ input_bindings: node.input_bindings, event_bindings: node.event_bindings }} open/>
      <h3>进入 / 离开控制边</h3><p className="sv-muted">琥珀色：进入；紫色：离开；箭头仅为声明方向</p><EdgeList edges={step.graph.edges.filter(e => e.source === node.node_id || e.target === node.node_id)} selected={node.node_id}/>
      <JsonBlock title="完整节点定义" value={node}/></>}
    <JsonBlock title="Step exits · 跨 Step / Phase 目的地" value={step.exits} open/>
    <JsonBlock title="来源与声明摘要（未验证，不授予权限）" value={{ node_sources: node?.source_refs, model_sources: model?.source_refs, step_sources: step.source_refs, workflow_sources: workflow.source_refs, source_refs: bundle.source_refs, definition_sha256: bundle.definition_sha256, asset_locks: bundle.asset_locks }}/>
    {model && <section aria-label="模型详情"><h3>模型 {text(node?.model_ref)}</h3>
      {local?.value ? <DecisionTablePreview key={locationKey(location)} value={local.value} nodeId={node!.node_id} readOnly/> : modelProfile(model) === 'service-decision-table-v1' || modelProfile(model) === 'json-table-v1' ? <RuleTable key={locationKey(location)} model={model}/> : <p className="sv-warning">未支持此 profile 的专用矩阵。{local?.error} 不推断或改写条件语义，完整模型如下。</p>}
      <JsonBlock title="完整原始模型" value={model} open={!local?.value && !['service-decision-table-v1', 'json-table-v1'].includes(modelProfile(model))}/>
    </section>}
    <JsonBlock title="完整 Step 定义" value={step}/>
  </>
}
function DetailDiagnostics({ issues }: { issues: Diagnostic[] }) {
  const [page, setPage] = useState(0)
  return <section aria-label="当前定位诊断" className="sv-warning"><h3>定位诊断 · {issues.length}</h3><DiagnosticPager page={page} count={issues.length} setPage={setPage}/><ul>{issues.slice(page * 50, (page + 1) * 50).map((d, i) => <li key={i}>{d.code}: {d.message}</li>)}</ul></section>
}
function DiagnosticPager({ page, count, setPage }: { page: number; count: number; setPage: (n: number) => void }) {
  return count > 50 ? <div className="sv-toolbar"><button disabled={!page} onClick={() => setPage(page - 1)}>诊断上一页</button><span>{page * 50 + 1}–{Math.min((page + 1) * 50, count)} / {count}</span><button disabled={(page + 1) * 50 >= count} onClick={() => setPage(page + 1)}>诊断下一页</button></div> : null
}
type ViewTransaction = { revision: number; bundle: Bundle; source: string }
class ImportBoundary extends Component<{ children: ReactNode; onFailure: (error: Error) => void }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  componentDidCatch(error: Error) { this.props.onFailure(error) }
  render() { return this.state.failed ? null : this.props.children }
}
export default function StructureViewer({ initialBundle = initial }: { initialBundle?: Bundle }) {
  const [committed, setCommitted] = useState<ViewTransaction>({ revision: 0, bundle: initialBundle, source: '内置独立 SYNTHETIC 示例' })
  const committedRef = useRef(committed)
  const [candidate, setCandidate] = useState<ViewTransaction>()
  const [error, setError] = useState(''); const [loading, setLoading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null); const generation = useRef(0)
  useEffect(() => () => { generation.current++ }, [])
  function finish(revision: number) {
    if (generation.current !== revision) return
    setLoading(false)
    // Only the current request owns the input. A stale read must not clear a
    // newer selection, including a second selection of exactly the same File.
    if (fileInput.current) fileInput.current.value = ''
  }
  function reject(revision: number, name: string, reason: unknown) {
    if (generation.current !== revision) return
    setCandidate(undefined)
    setError(`导入 ${name} 失败：${reason instanceof Error ? reason.message : '文件不可读或视图无法显示'}。保留视图：${committedRef.current.source}`)
    finish(revision)
  }
  function commit(next: ViewTransaction) {
    if (generation.current !== next.revision) return
    committedRef.current = next; setCommitted(next); setCandidate(undefined); finish(next.revision)
  }
  async function importFile(file?: File) {
    if (!file) return
    const revision = ++generation.current
    setCandidate(undefined); setLoading(true); setError('')
    try {
      if (file.size > LIMITS.bytes) throw new Error('导入超过 2 MiB')
      const bytes = await file.arrayBuffer()
      if (generation.current !== revision) return
      const bundle = parseStructure(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
      setCandidate({ revision, bundle, source: file.name })
    } catch (reason) { reject(revision, file.name, reason) }
  }
  // Mount candidates separately, hidden and inert. The last committed tree is
  // never reconciled with unproven data, so rollback preserves its actual DOM,
  // listeners, selection, focus, directory state and scroll positions.
  return <div className="sv-app"><header className="sv-header"><div><span className="sv-eyebrow">DEFINITION EXPLORER · READ ONLY</span><h1>Phase → Step → Node</h1><p>浏览声明结构与规则，保留每一层的明确归属</p></div><button onClick={() => fileInput.current?.click()} disabled={loading}>{loading ? '读取本地文件…' : '导入本地 JSON'}</button><input ref={fileInput} aria-label="导入本地 JSON 文件" type="file" accept=".json,application/json" hidden onChange={e => void importFile(e.target.files?.[0])}/></header>
    <div className="sv-notice">只读 / 仅内存 · 不上传、不执行、不持久化 · 展示校验不等于执行合同校验或授权</div>
    {error && <p role="alert" className="sv-error">{error}</p>}
    {[committed, ...(candidate ? [candidate] : [])].map(transaction => <ImportBoundary key={transaction.revision} onFailure={reason => reject(transaction.revision, transaction.source, reason)}>
      <div hidden={transaction !== committed} inert={transaction !== committed}>
        <StructureView transaction={transaction} active={transaction === committed} onReady={() => commit(transaction)}/>
      </div>
    </ImportBoundary>)}
  </div>
}
function StructureView({ transaction, active, onReady }: { transaction: ViewTransaction; active: boolean; onReady: () => void }) {
  const { bundle, source } = transaction
  const [flow, setFlow] = useState(bundle.workflows[0].flow_type); const [workflowId, setWorkflowId] = useState(bundle.workflows[0].workflow_id)
  const [diagnosticPage, setDiagnosticPage] = useState(0)
  const [query, setQuery] = useState(''); const [selected, setSelected] = useState<Location>(); const [scale, setScale] = useState(1)
  const dialog = useRef<HTMLDialogElement>(null); const origin = useRef<HTMLElement | null>(null)
  const viewport = useRef<HTMLDivElement>(null); const canvas = useRef<HTMLDivElement>(null); const alive = useRef(false)
  const [canvasSize, setCanvasSize] = useState({ width: 748, height: 550 })
  const [fitStep, setFitStep] = useState(''); const pan = useRef<{ x: number; y: number; left: number; top: number } | undefined>(undefined)
  const totals = useMemo(() => counts(bundle), [bundle]); const issues = useMemo(() => diagnostics(bundle), [bundle])
  const workflow = bundle.workflows.find(w => w.workflow_id === workflowId) || bundle.workflows[0]
    const visibleNodes = workflow.phases.flatMap(phase => phase.steps.flatMap(step => step.graph.nodes.map(node => ({ workflow, phase, step, node })))).filter(loc => matches(bundle, loc, query))
  useLayoutEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    if (active) return
    let pending = true
    // Wait through the candidate's complete React commit, including effects.
    // A failed/unmounted candidate cannot publish itself from a stale callback.
    Promise.resolve().then(() => { if (pending && alive.current) onReady() })
    return () => { pending = false }
  }, [active, onReady])
  useEffect(() => { if (selected && active) dialog.current?.showModal() }, [selected, active])
  useEffect(() => {
    const el = canvas.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const measure = () => setCanvasSize(current => current.width === el.offsetWidth && current.height === el.offsetHeight ? current : { width: el.offsetWidth, height: el.offsetHeight })
    const observer = new ResizeObserver(measure); observer.observe(el); measure()
    return () => observer.disconnect()
  }, [active])
  useEffect(() => {
    const el = viewport.current
    const zoom = (e: WheelEvent) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); setScale(s => Math.max(.25, Math.min(1.5, s + (e.deltaY < 0 ? .1 : -.1)))) } }
    el?.addEventListener('wheel', zoom, { passive: false }); return () => el?.removeEventListener('wheel', zoom)
  }, [])
  function open(location: Location, target: HTMLElement) { origin.current = target; setSelected(location) }
  function nextFrame(callback: () => void) { requestAnimationFrame(() => { if (alive.current) callback() }) }
  function closed() { setSelected(undefined); nextFrame(() => { if (origin.current?.isConnected) origin.current.focus() }) }
  function fit(which: 'all' | 'step') {
    const view = viewport.current; if (!view || !canvas.current) return
    const cards = [...canvas.current.querySelectorAll<HTMLElement>('[data-step-key]')]
    const card = cards.find(c => c.dataset.stepKey === fitStep) || cards[0]
    if (which === 'step' && card) { setScale(Math.min(1.25, Math.max(.65, (view.clientWidth - 48) / card.offsetWidth))); nextFrame(() => card.scrollIntoView({ block: 'nearest', inline: 'start' })) }
    else setScale(Math.min(1, Math.max(.0001, Math.min((view.clientWidth - 48) / Math.max(1, canvas.current.offsetWidth), (view.clientHeight - 48) / Math.max(1, canvas.current.offsetHeight)))))
  }
  function startPan(e: ReactPointerEvent<HTMLDivElement>) {
    if (e.button !== 0 || (e.target as HTMLElement).closest('button,a,input,summary,details,select')) return
    pan.current = { x: e.clientX, y: e.clientY, left: e.currentTarget.scrollLeft, top: e.currentTarget.scrollTop }; e.currentTarget.setPointerCapture(e.pointerId)
  }
  return <>
    <section className="sv-source" aria-label="当前导入来源"><strong>来源：{source}</strong><span>{bundle.schema_version}</span><span>{totals.workflows} workflows · {totals.phases} phases · {totals.steps} steps · {totals.nodes} nodes · {totals.edges} edges</span></section>
    <div className="sv-toolbar"><label>流程类型 <select value={flow} onChange={e => { setFlow(e.target.value); setWorkflowId(bundle.workflows.find(w => w.flow_type === e.target.value)!.workflow_id) }}>{[...new Set(bundle.workflows.map(w => w.flow_type))].map(f => <option key={f}>{f}</option>)}</select></label>
      <label>Workflow <select value={workflow.workflow_id} onChange={e => setWorkflowId(e.target.value)}>{bundle.workflows.filter(w => w.flow_type === flow).map(w => <option key={w.workflow_id}>{w.workflow_id}</option>)}</select></label><span className="sv-scope">{text(workflow.scope) || 'scope 未声明'}</span>
      <label>搜索 <input type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="名称、ID、规则 ID"/></label><span>{visibleNodes.length} 个匹配节点</span></div>
    <main className="sv-main"><aside className="sv-directory"><details open><summary>Phase / Step 目录</summary>{workflow.phases.map(phase => <details key={phase.phase_id} open><summary>{phase.phase_id}{text(phase.name) && ` · ${text(phase.name)}`}</summary>{phase.steps.map(step => <details key={step.step_id} open><summary>{step.step_id} · {text(step.name)}</summary><button className="sv-step-link" onClick={e => open({ workflow, phase, step }, e.currentTarget)}>Step 详情 / exits</button>{step.graph.nodes.filter(node => matches(bundle, { workflow, phase, step, node }, query)).map(node => <button key={node.node_id} className="sv-directory-node" onClick={e => open({ workflow, phase, step, node }, e.currentTarget)}>{text(node.name) || node.node_id}<small>{node.node_id} · {node.kind}</small></button>)}</details>)}</details>)}</details>
      <details className="sv-diagnostics"><summary>定位诊断 · {issues.length}</summary><DiagnosticPager page={diagnosticPage} count={issues.length} setPage={setDiagnosticPage}/>{issues.slice(diagnosticPage * 50, (diagnosticPage + 1) * 50).map((d, i) => <button key={i} onClick={e => { setFlow(d.location.workflow.flow_type); setWorkflowId(d.location.workflow.workflow_id); open(d.location, e.currentTarget) }}><b>{d.code}</b><small>{d.location.workflow.workflow_id} / {d.location.step.step_id} / {d.location.node?.node_id || 'Step'}</small>{d.message}</button>)}</details></aside>
      <section className="sv-workspace" aria-label="结构画布"><div className="sv-toolbar sv-zoom"><button aria-label="缩小" onClick={() => setScale(s => Math.max(.25, s - .1))}>−</button><button onClick={() => setScale(1)}>{Math.round(scale * 100)}%</button><button aria-label="放大" onClick={() => setScale(s => Math.min(1.5, s + .1))}>＋</button><label>Step <select aria-label="适配 Step" value={fitStep} onChange={e => setFitStep(e.target.value)}><option value="">首个 Step</option>{workflow.phases.flatMap(p => p.steps.map(s => <option key={JSON.stringify([p.phase_id, s.step_id])} value={JSON.stringify([p.phase_id, s.step_id])}>{p.phase_id} / {s.step_id}</option>))}</select></label><button onClick={() => fit('step')}>Fit Step</button><button onClick={() => fit('all')}>Fit All</button><span>拖动空白 / 滚动 · Ctrl/⌘ + 滚轮缩放</span></div>
        <p className="sv-muted sv-order">节点按 graph.nodes 声明顺序排列，不推断执行顺序或 Phase/Step 归属。搜索在目录筛选，画布保留所有节点。</p>
        <div className="sv-viewport" ref={viewport} tabIndex={0} onPointerDown={startPan} onPointerMove={e => { if (pan.current) { e.currentTarget.scrollLeft = pan.current.left - (e.clientX - pan.current.x); e.currentTarget.scrollTop = pan.current.top - (e.clientY - pan.current.y) } }} onPointerUp={() => { pan.current = undefined }} onPointerCancel={() => { pan.current = undefined }}>
          <div className="sv-scale-space" style={{ width: `${canvasSize.width * scale}px`, height: `${canvasSize.height * scale}px` }}><div className="sv-canvas" ref={canvas} style={{ transform: `scale(${scale})` }}>{workflow.phases.map(phase => <section className="sv-phase" key={phase.phase_id}><h2>{phase.phase_id} {text(phase.name)}</h2><div className="sv-steps">{phase.steps.map(step => <article className="sv-step" key={step.step_id} data-step-key={JSON.stringify([phase.phase_id, step.step_id])}><button className="sv-step-title" onClick={e => open({ workflow, phase, step }, e.currentTarget)}>{step.step_id} · {text(step.name)}<small>{step.graph.nodes.length} nodes · {step.graph.edges.length} edges · {Object.keys(step.exits).length} exits</small></button>
            <div className="sv-node-stack" style={{ height: Math.max(1, step.graph.nodes.length) * nodeHeight }}><Connectors step={step} selected={selected?.step === step ? selected.node?.node_id : undefined}/>{step.graph.nodes.map((node, ni) => <button className={`sv-node ${query && matches(bundle, { workflow, phase, step, node }, query) ? 'sv-match' : ''}`} key={node.node_id} style={{ top: ni * nodeHeight }} onClick={e => open({ workflow, phase, step, node }, e.currentTarget)}><span>{node.kind}</span><strong>{text(node.name) || node.node_id}</strong><small>{node.node_id}</small><small className="sv-port-label">ports: {Array.isArray(node.ports) ? node.ports.map(text).join(' · ') || '[]' : '未声明'}</small></button>)}</div>
            <details className="sv-step-edges"><summary>控制边 / ports · {step.graph.edges.length}</summary><EdgeList edges={step.graph.edges} selected={selected?.step === step ? selected.node?.node_id : undefined}/></details>
          </article>)}</div></section>)}</div></div>
        </div>
      </section></main>
    <details className="sv-root-raw"><summary>完整导入定义 / 未验证来源</summary><pre>{raw(bundle)}</pre></details>
    <footer className="sv-footer">预算：UTF-8 2 MiB · 深度 40 · 60,000 值 · 30 workflows · 600 nodes · 1,800 edges。链接和摘要仅为文本。刷新会丢弃本地导入。</footer>
    <dialog className="sv-dialog" aria-label="节点与步骤定义详情" ref={dialog} onClose={closed}><div className="sv-dialog-bar"><strong>定义详情</strong><button autoFocus={active} onClick={() => dialog.current?.close()}>关闭详情 ×</button></div>{selected && <Detail key={locationKey(selected)} bundle={bundle} location={selected} issues={issues.filter(d => (d.location.step === selected.step && (!selected.node || d.location.node === selected.node)) || (!!selected.node && d.modelRef !== undefined && d.modelRef === selected.node.model_ref))}/>}</dialog>
  </>
}
function Connectors({ step, selected }: { step: Step; selected?: string }) {
  const positions = new Map(step.graph.nodes.map((n, i) => [n.node_id, i * nodeHeight + 42]))
  const uid = useId().replace(/:/g, '')
  return <svg className="sv-connectors" width="328" height={Math.max(1, step.graph.nodes.length) * nodeHeight} aria-label="声明控制边"><defs>{['normal', 'in', 'out'].map(k => <marker key={k} id={`${uid}-${k}`} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L8 4L0 8Z" fill={k === 'in' ? '#a56a00' : k === 'out' ? '#823dc4' : '#078c9a'}/></marker>)}</defs>{step.graph.edges.map((e, i) => {
    const y1 = positions.get(e.source)!; const y2 = positions.get(e.target)!; const x = 286 + i % 5 * 7; const mode = e.source === selected ? 'out' : e.target === selected ? 'in' : 'normal'
    return <path key={e.edge_id} d={e.source === e.target ? `M272 ${y1} C${x + 25} ${y1 - 30},${x + 25} ${y1 + 30},272 ${y1 + 12}` : `M272 ${y1} H${x} V${y2} H274`} className={`sv-edge-${mode}`} markerEnd={`url(#${uid}-${mode})`}><title>{e.edge_id}: {e.source} [{e.source_port}] → {e.target}</title></path>
  })}</svg>
}
