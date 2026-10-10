/** Independent display projection. Never validates execution or resolves external references. */
import { parseTable } from './model'
export type Obj = Record<string, unknown>
export type Node = Obj & { node_id: string; kind: string }
export type Edge = Obj & { edge_id: string; source: string; target: string; source_port: string }
export type Step = Obj & { step_id: string; graph: { nodes: Node[]; edges: Edge[] }; exits: Obj }
export type Phase = Obj & { phase_id: string; steps: Step[] }
export type Workflow = Obj & { workflow_id: string; phases: Phase[]; flow_type: string }
export type Bundle = Obj & { schema_version: string; workflows: Workflow[]; models: Obj }
export type Location = { workflow: Workflow; phase: Phase; step: Step; node?: Node }
export type Diagnostic = { code: string; message: string; location: Location; rule?: string; modelRef?: string }
export const LIMITS = { bytes: 2 * 1024 * 1024, depth: 40, values: 60000, workflows: 30, nodes: 600, edges: 1800 }
export const record = (v: unknown): v is Obj => !!v && typeof v === 'object' && !Array.isArray(v)
export const own = (v: Obj, key: string) => Object.prototype.hasOwnProperty.call(v, key)
export const text = (v: unknown) => typeof v === 'string' ? v : ''
export const raw = (v: unknown) => JSON.stringify(v, null, 2) ?? '未声明'
function fail(message: string): never { throw new Error(message) }
function object(v: unknown, path: string): Obj { return record(v) ? v : fail(`${path} 必须为对象`) }
function array(v: unknown, path: string): unknown[] { return Array.isArray(v) ? v : fail(`${path} 必须为数组；不推断层级`) }
function id(v: unknown, path: string): string { return typeof v === 'string' && v.trim() ? v : fail(`${path} 需要非空 ID`) }
function unique(items: unknown[], field: string, path: string) {
  const ids = new Set<string>()
  items.forEach(v => { const s = id(object(v, path)[field], `${path}.${field}`); if (ids.has(s)) fail(`${path} 重复 ${field}: ${s}`); ids.add(s) })
  return ids
}
export function parseStructure(source: string): Bundle {
  if (new TextEncoder().encode(source).length > LIMITS.bytes) fail('导入超过 2 MiB')
  let value: unknown
  try { value = JSON.parse(source) } catch { fail('JSON 格式错误') }
  // Iterative traversal prevents untrusted deep input from exhausting the JS call stack.
  const pending: [unknown, number][] = [[value, 0]]; let count = 0
  while (pending.length) {
    const [v, depth] = pending.pop()!
    if (++count > LIMITS.values) fail('JSON 值节点超过 60,000')
    if (depth > LIMITS.depth) fail('JSON 嵌套深度超过 40')
    if (typeof v === 'number' && !Number.isFinite(v)) fail('数值必须有限')
    if (v && typeof v === 'object') Object.values(v).forEach(x => pending.push([x, depth + 1]))
  }
  const root = object(value, 'root')
  if (!['structure-view.v1', 'service-decision-dsl.node-architecture.v2'].includes(text(root.schema_version))) fail('仅接受显式 structure-view.v1 或 node-architecture.v2；不转换 XML/json-plan')
  const workflows = array(root.workflows, 'workflows')
  if (!workflows.length || workflows.length > LIMITS.workflows) fail('workflow 数须为 1–30')
  unique(workflows, 'workflow_id', 'workflows'); object(root.models, 'models')
  let nodes = 0; let edges = 0
  workflows.forEach((w, wi) => {
    const wf = object(w, 'workflow'); const wp = `workflows[${wi}]`
    id(wf.flow_type, `${wp}.flow_type`)
    const phases = array(wf.phases, `${wp}.phases`); unique(phases, 'phase_id', `${wp}.phases`)
    phases.forEach((p, pi) => {
      const phase = object(p, 'phase'); const pp = `${wp}.phases[${pi}]`
      const steps = array(phase.steps, `${pp}.steps`); unique(steps, 'step_id', `${pp}.steps`)
      steps.forEach((s, si) => {
        const step = object(s, 'step'); const sp = `${pp}.steps[${si}]`; const graph = object(step.graph, `${sp}.graph`)
        const ns = array(graph.nodes, `${sp}.graph.nodes`); const es = array(graph.edges, `${sp}.graph.edges`)
        const ids = unique(ns, 'node_id', `${sp}.nodes`); unique(es, 'edge_id', `${sp}.edges`)
        object(step.exits, `${sp}.exits`)
        nodes += ns.length; edges += es.length
        if (nodes > LIMITS.nodes || edges > LIMITS.edges) fail('规模超过 600 nodes / 1,800 edges；请提供较小的显式展示包')
        ns.forEach(n => id(object(n, 'node').kind, `${sp}.node.kind`))
        es.forEach(e => {
          const edge = object(e, 'edge'); id(edge.source_port, `${sp}.edge.source_port`)
          if (!ids.has(text(edge.source)) || !ids.has(text(edge.target))) fail(`${sp} 悬空控制边 ${text(edge.edge_id)}；跨 Step 请用 exits 明确声明`)
        })
      })
    })
  })
  return root as Bundle
}
export function counts(bundle: Bundle) {
  const phases = bundle.workflows.flatMap(w => w.phases); const steps = phases.flatMap(p => p.steps)
  return { workflows: bundle.workflows.length, phases: phases.length, steps: steps.length, nodes: steps.reduce((n, s) => n + s.graph.nodes.length, 0), edges: steps.reduce((n, s) => n + s.graph.edges.length, 0) }
}
export function modelProfile(model: Obj): string {
  const profile = text(model.profile); const format = text(model.format)
  return profile && format && profile !== format ? `${profile} / ${format} (conflicting declarations)` : profile || format
}
export function localTable(model: Obj): { value?: string; error?: string } {
  if (model.profile !== 'dmn-local-table-v1') return { error: '未声明 dmn-local-table-v1 profile，不转换为本地条件矩阵' }
  const value = typeof model.table_json === 'string' ? model.table_json : JSON.stringify(model.table)
  const parsed = parseTable(value)
  return parsed.kind === 'ready' ? { value } : { error: parsed.message }
}
export function modelFor(bundle: Bundle, node: Node): Obj | undefined {
  const ref = text(node.model_ref)
  return ref && own(bundle.models, ref) && record(bundle.models[ref]) ? bundle.models[ref] as Obj : undefined
}
export function diagnostics(bundle: Bundle): Diagnostic[] {
  const result: Diagnostic[] = []
  const checkedModels = new Set<Obj>()
  for (const workflow of bundle.workflows) for (const phase of workflow.phases) for (const step of phase.steps) {
    const location = { workflow, phase, step }
    const add = (code: string, message: string, node?: Node, rule?: string) => result.push({ code, message, location: { ...location, node }, rule })
    const nodeIds = new Set(step.graph.nodes.map(n => n.node_id))
    for (const edge of step.graph.edges) {
      const source = step.graph.nodes.find(n => n.node_id === edge.source)!
      if (!Array.isArray(source.ports) || !source.ports.includes(edge.source_port)) add('UNDECLARED_PORT', `${edge.edge_id}: source_port ${edge.source_port} 未在源节点 ports 中声明`, source)
    }
    for (const [exitId, exit] of Object.entries(step.exits)) {
      if (!record(exit) || !record(exit.destination)) { add('INVALID_EXIT', `${exitId}: 缺少 destination`); continue }
      const d = exit.destination
      if (['STEP', 'PHASE', 'REENTER_STEP'].includes(text(d.kind))) {
        const p = workflow.phases.find(p => p.phase_id === d.phase_id)
        if (!p || (d.kind !== 'PHASE' && !p.steps.some(s => s.step_id === d.step_id))) add('MISSING_EXIT_TARGET', `${exitId}: 未找到已声明目的 Phase/Step ${text(d.phase_id)}/${text(d.step_id)}`)
      }
    }
    for (const node of step.graph.nodes) {
      if (node.exit_ref !== undefined && !own(step.exits, text(node.exit_ref))) add('MISSING_EXIT', `exit_ref ${text(node.exit_ref)} 未定义`, node)
      for (const field of ['input_bindings', 'event_bindings']) {
        if (node[field] === undefined) continue
        if (!record(node[field])) { add('INVALID_BINDING', `${field} 必须为对象`, node); continue }
        for (const [key, binding] of Object.entries(node[field] as Obj)) {
          if (!record(binding) || own(binding, 'literal') === own(binding, 'from')) { add('INVALID_BINDING', `${field}.${key}: 需要 literal 或 from，且只能一种`, node); continue }
          if (own(binding, 'from')) {
            const from = binding.from
            if (!record(from) || !Array.isArray(from.path) || !from.path.every(p => typeof p === 'string') || !['context', 'node', 'event', 'parameters', 'decision', 'inputs', 'api'].includes(text(from.source))) add('INVALID_BINDING', `${field}.${key}: 来源或 path 格式无效`, node)
            else if (from.source === 'node' && !nodeIds.has(text(from.node_id))) add('MISSING_BINDING_NODE', `${field}.${key}: node ${text(from.node_id)} 不在当前 Step`, node)
          }
        }
      }
      if (node.kind !== 'DECISION' && node.model_ref === undefined) continue
      const model = modelFor(bundle, node)
      if (!model) { add('MISSING_MODEL', `model_ref ${text(node.model_ref) || '(未声明)'} 未找到`, node); continue }
      if (checkedModels.has(model)) continue
      checkedModels.add(model)
      const addModel = (code: string, message: string, rule?: string) => result.push({ code, message, location: { ...location, node }, rule, modelRef: text(node.model_ref) })
      if (model.profile === 'dmn-local-table-v1') {
        const local = localTable(model); if (!local.value) addModel('INVALID_LOCAL_TABLE', local.error!)
        continue
      }
      if (modelProfile(model) !== 'service-decision-table-v1' && modelProfile(model) !== 'json-table-v1') addModel('UNSUPPORTED_PROFILE', `profile ${modelProfile(model) || '(未声明)'} 未被专用矩阵支持；保留完整原文`)
      if (!['FIRST', 'COLLECT', 'UNIQUE'].includes(text(model.hit_policy))) addModel('MISSING_HIT_POLICY', `hit_policy ${text(model.hit_policy) || '(未声明)'} 未识别；不假定默认策略`)
      if (!Array.isArray(model.rules)) { addModel('MISSING_RULES', '模型缺少 rules 数组'); continue }
      const templates = record(model.result_templates) ? model.result_templates : {}
      model.rules.forEach((rule, i) => {
        if (!record(rule)) { addModel('INVALID_RULE', `rules[${i}] 不是对象`); return }
        const rid = text(rule.rule_id) || text(rule.id) || `[${i}]`
        if (own(rule, 'output_template_ref') && !own(templates, text(rule.output_template_ref))) addModel('MISSING_TEMPLATE', `${rid}: output_template_ref ${text(rule.output_template_ref)} 未找到；不回退至 inline output`, rid)
        if (model.profile === 'service-decision-table-v1' && !own(rule, 'output_template_ref')) addModel('MISSING_TEMPLATE', `${rid}: 缺少 output_template_ref`, rid)
      })
      if (model.on_no_match === 'RESULT_TEMPLATE' && !own(templates, text(model.empty_template_ref))) addModel('MISSING_EMPTY_TEMPLATE', `empty_template_ref ${text(model.empty_template_ref) || '(未声明)'} 未找到`)
    }
  }
  return result
}
const ruleSearchCache = new WeakMap<Obj, string>()
function ruleSearch(model?: Obj) {
  if (!model) return ''
  const cached = ruleSearchCache.get(model)
  if (cached !== undefined) return cached
  let rules = Array.isArray(model.rules) ? model.rules : []
  if (model.profile === 'dmn-local-table-v1') {
    const local = localTable(model)
    if (local.value) rules = JSON.parse(local.value).rules
  }
  const value = rules.map(r => record(r) ? `${text(r.rule_id)} ${text(r.id)}` : '').join(' ')
  ruleSearchCache.set(model, value)
  return value
}
export function matches(bundle: Bundle, loc: Location, query: string) {
  if (!query.trim()) return true
  const model = loc.node && modelFor(bundle, loc.node)
  const rules = ruleSearch(model)
  return [loc.workflow.workflow_id, loc.workflow.name, loc.phase.phase_id, loc.phase.name, loc.step.step_id, loc.step.name, loc.node?.node_id, loc.node?.name, loc.node?.kind, rules].map(text).join(' ').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())
}
export const locationKey = (loc: Location) => JSON.stringify([loc.workflow.workflow_id, loc.phase.phase_id, loc.step.step_id, loc.node?.node_id])
