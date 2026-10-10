import { parseTable, literal, outputValue } from './model'
import type { Snapshot } from './binding'
export function element(document: Document, tag: string, text?: string, className?: string): HTMLElement {
  const result = document.createElement(tag)
  if (text !== undefined) result.textContent = text
  if (className) result.className = className
  return result
}
export function renderSnapshot(container: HTMLElement, snapshot: Snapshot, page = 0): void {
  const document = container.ownerDocument
  container.replaceChildren()
  container.dataset.status = snapshot.status
  if (snapshot.nodeId) container.dataset.nodeId = snapshot.nodeId
  else delete container.dataset.nodeId
  const source = element(document, 'div', snapshot.nodeId ? `${snapshot.title} · 节点 ${snapshot.nodeId}` : '当前工作流节点', 'dmnp-source')
  container.append(source)
  if (snapshot.status !== 'ready') {
    const message = element(document, 'div', snapshot.message || '无法读取当前节点。', 'dmnp-status')
    message.setAttribute('role', snapshot.status === 'error' ? 'alert' : 'status')
    container.append(message)
    return
  }
  const parsed = parseTable(snapshot.raw)
  if (parsed.kind !== 'ready') {
    container.dataset.status = parsed.kind
    const message = element(document, 'div', parsed.message, 'dmnp-status')
    message.setAttribute('role', parsed.kind === 'error' ? 'alert' : 'status')
    container.append(message)
    return
  }
  const { matrix } = parsed
  const columns = matrix.fields.length + matrix.outputs.length + 2
  if (columns > 128) {
    container.dataset.status = 'error'
    container.append(element(document, 'div', `此表含 ${columns} 列，超过可读预览上限 128 列；未显示不完整表格。`, 'dmnp-status'))
    return
  }
  const pageSize = 50
  const pages = Math.max(1, Math.ceil(matrix.rows.length / pageSize))
  page = Math.max(0, Math.min(page, pages - 1))
  container.append(element(document, 'div', `${matrix.table.id} · ${matrix.table.hit_policy} · ${matrix.rows.length} 条规则 · 未执行`, 'dmnp-meta'))
  const scroll = element(document, 'div', undefined, 'dmnp-scroll')
  scroll.tabIndex = 0
  scroll.setAttribute('aria-label', '决策表，可横向滚动')
  const table = document.createElement('table')
  table.setAttribute('aria-label', `决策表 ${matrix.table.id}`)
  const head = table.createTHead()
  const header = head.insertRow()
  for (const label of ['规则', ...matrix.fields.map(field => `条件 · ${literal(field)}`), '逻辑', ...matrix.outputs.map(output => `输出 · ${output.label}`)]) {
    const th = document.createElement('th')
    th.textContent = label
    th.scope = 'col'
    header.append(th)
  }
  const body = table.createTBody()
  for (const row of matrix.rows.slice(page * pageSize, (page + 1) * pageSize)) {
    const tr = body.insertRow()
    const id = document.createElement('th')
    id.scope = 'row'
    id.textContent = row.rule.id
    tr.append(id)
    for (const field of matrix.fields) {
      const cell = tr.insertCell()
      const atoms = row.atoms.filter(atom => atom.field === field)
      cell.textContent = atoms.length ? atoms.map(atom => `${atom.id}: ${atom.label}`).join('\n') : '—'
    }
    const logic = tr.insertCell()
    const details = document.createElement('details')
    details.append(element(document, 'summary', row.logic), element(document, 'div', row.fullLogic, 'dmnp-full-logic'))
    logic.append(details)
    for (const output of matrix.outputs) {
      const cell = tr.insertCell()
      const value = outputValue(row.rule, output)
      cell.textContent = !value.present ? '未定义' : value.expanded ? '见展开列' : literal(value.value!)
    }
  }
  scroll.append(table)
  container.append(scroll)
  if (!matrix.rows.length) container.append(element(document, 'div', '此表没有规则。', 'dmnp-status'))
  if (pages > 1) {
    const paging = element(document, 'nav', undefined, 'dmnp-paging')
    paging.setAttribute('aria-label', '规则分页')
    const previous = element(document, 'button', '上一页') as HTMLButtonElement
    previous.disabled = page === 0
    previous.addEventListener('click', () => renderSnapshot(container, snapshot, page - 1))
    const next = element(document, 'button', '下一页') as HTMLButtonElement
    next.disabled = page === pages - 1
    next.addEventListener('click', () => renderSnapshot(container, snapshot, page + 1))
    paging.append(previous, element(document, 'span', `第 ${page + 1}/${pages} 页 · 每页最多 ${pageSize} 条`), next)
    container.append(paging)
  }
  container.append(element(document, 'div', '只读结构预览 · 点击逻辑查看完整条件 · 不判断命中、不运行工作流', 'dmnp-footnote'))
}
