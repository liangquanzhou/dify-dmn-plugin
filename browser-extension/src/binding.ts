/** Page-owned data is untrusted. This adapter only reads own data properties. */
export const PROVIDER = 'liangquanzhou/dmn_decision/dmn'
export const SNAPSHOT_EVENT = 'dmn-preview:snapshot:v1'
export const STOP_EVENT = 'dmn-preview:stop:v1'
export const REFRESH_EVENT = 'dmn-preview:refresh:v1'
export const MAX_TABLE_CHARS = 512 * 1024
export type Snapshot = { status: 'ready' | 'empty' | 'dynamic' | 'unsupported' | 'idle' | 'error'; nodeId?: string; title?: string; raw?: string; message?: string }
export function ownValue(object: unknown, name: string): unknown {
  if (!object || typeof object !== 'object') return undefined
  return Object.getOwnPropertyDescriptor(object, name)?.value
}
export function extractTable(data: unknown, nodeId: string): Snapshot {
  if (ownValue(data, 'type') !== 'tool' || ownValue(data, 'provider_type') !== 'builtin'
    || ownValue(data, 'provider_id') !== PROVIDER || ownValue(data, 'tool_name') !== 'evaluate')
    return { status: 'unsupported', message: '当前节点不在支持范围。仅支持指定 DMN 插件的 evaluate 工具。' }
  const titleValue = ownValue(data, 'title')
  const base = { nodeId, title: typeof titleValue === 'string' ? titleValue.slice(0, 300) : 'DMN evaluate' }
  const config = ownValue(data, 'tool_configurations')
  const setting = ownValue(config, 'table_json')
  let raw = setting
  if (setting && typeof setting === 'object') {
    const type = ownValue(setting, 'type')
    if (type !== 'constant' && type !== 'mixed') return { ...base, status: 'dynamic', message: 'table_json 是变量或未支持的绑定；运行前没有可确认的完整表格。' }
    raw = ownValue(setting, 'value')
    if (type === 'mixed' && typeof raw === 'string' && /\{\{#.*?#\}\}/s.test(raw))
      return { ...base, status: 'dynamic', message: 'table_json 含未解析的变量；不显示推测表格。' }
  }
  if (raw === undefined || raw === null || raw === '') return { ...base, status: 'empty', message: '此节点尚未配置 table_json。' }
  if (typeof raw !== 'string') return { ...base, status: 'error', message: 'table_json 必须是 JSON 字符串。' }
  if (raw.length > MAX_TABLE_CHARS) return { ...base, status: 'error', message: 'table_json 超过预览大小限制。' }
  return { ...base, status: 'ready', raw }
}
/** Read only the rendered ReactFlow node's current DOM props children, never Fiber/store/network. */
export function readRenderedNode(element: Element): { id: string; data: unknown } | null {
  const id = element.getAttribute('data-id')
  if (!id) return null
  const key = Object.getOwnPropertyNames(element).find(name => name.startsWith('__reactProps$'))
  if (!key) return null
  const props = ownValue(element, key)
  const queue: { value: unknown; depth: number }[] = [{ value: ownValue(props, 'children'), depth: 0 }]
  let examined = 0
  while (queue.length && examined++ < 96) {
    const { value, depth } = queue.shift()!
    if (depth > 6 || !value || typeof value !== 'object') continue
    if (Array.isArray(value)) { for (const child of value.slice(0, 48)) queue.push({ value: child, depth: depth + 1 }); continue }
    const childProps = ownValue(value, 'props')
    const data = ownValue(childProps, 'data')
    if (ownValue(childProps, 'id') === id && data && typeof ownValue(data, 'type') === 'string') return { id, data }
    queue.push({ value: ownValue(childProps, 'children'), depth: depth + 1 })
  }
  return null
}
/** Supported editor URLs: /app/<id>/workflow and AgentHub's /v2/app/<id>?mode=workflow. */
export function isWorkflowEditorLocation(location: { pathname: string; search: string }): boolean {
  if (/^\/app\/[^/]+\/workflow\/?$/.test(location.pathname)) return true
  return /^\/v2\/app\/[^/]+\/?$/.test(location.pathname) && new URLSearchParams(location.search).get('mode') === 'workflow'
}
export function snapshotDocument(document: Document): Snapshot {
  if (!isWorkflowEditorLocation(document.location))
    return { status: 'unsupported', message: '请打开 Dify 1.11.1 的 Workflow 编辑页面。' }
  const rendered = document.querySelectorAll('.react-flow__node[data-id]')
  if (rendered.length > 1500) return { status: 'error', message: '工作流节点超过 1,500，无法可靠识别当前选择；未显示部分扫描结果。' }
  if (!rendered.length) return { status: 'idle', message: '等待工作流节点；打开工作流并点击 DMN evaluate 节点。' }
  let readable = 0
  const selected: { id: string; data: unknown }[] = []
  for (const element of Array.from(rendered).slice(0, 1500)) {
    const node = readRenderedNode(element)
    if (!node) continue
    readable++
    if (ownValue(node.data, 'selected') === true) selected.push(node)
  }
  if (readable !== rendered.length) return { status: 'error', message: '无法完整读取此 Dify 页面结构。预览仅适配经验证的 1.11.1；不会显示缓存或猜测数据。' }
  if (selected.length !== 1) return { status: 'idle', message: selected.length ? '请只选择一个 DMN evaluate 节点。' : '点击 DMN evaluate 节点即可预览当前 table_json。' }
  return extractTable(selected[0].data, selected[0].id)
}

/** An activation never follows a different workflow, even if the old DOM lingers or Back is used. */
export function createPageReader(document: Document): () => Snapshot {
  const activationPath = document.location.pathname
  let navigated = false
  return () => {
    if (document.location.pathname !== activationPath) navigated = true
    if (navigated) return { status: 'unsupported', message: '工作流页面已切换，旧预览已清除。请再次点击扩展启用当前页面。' }
    return snapshotDocument(document)
  }
}
