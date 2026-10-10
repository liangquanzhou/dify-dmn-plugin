// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import StructureViewer from '../src/structure-viewer'
import { example } from '../src/structure-fixture'
import { parseStructure } from '../src/structure-model'
import * as structureModel from '../src/structure-model'
beforeAll(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', '') }
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); this.dispatchEvent(new Event('close')) }
  globalThis.requestAnimationFrame = cb => { cb(0); return 0 }
})
afterEach(() => { cleanup(); vi.restoreAllMocks() })
const bytes = (contents: string) => new TextEncoder().encode(contents).buffer
function pendingFile(name: string) {
  let resolve!: (contents: ArrayBuffer) => void; let reject!: (error: Error) => void
  const file = new File(['pending'], name, { type: 'application/json' })
  const read = vi.fn(() => new Promise<ArrayBuffer>((success, failure) => { resolve = success; reject = failure }))
  Object.defineProperty(file, 'arrayBuffer', { value: read })
  return { file, read, resolve: (contents: string) => resolve(bytes(contents)), reject: (message: string) => reject(new Error(message)) }
}
function choose(file: File) { fireEvent.change(screen.getByLabelText('导入本地 JSON 文件'), { target: { files: [file] } }) }
async function upload(contents: string, name = 'sample.json') {
  const file = new File([contents], name, { type: 'application/json' }); Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode(contents).buffer })
  fireEvent.change(screen.getByLabelText('导入本地 JSON 文件'), { target: { files: [file] } })
  await waitFor(() => expect(screen.getByText('导入本地 JSON')).toBeTruthy())
}
describe('independent read-only viewer interactions', () => {
  it('renders actual counts and declared memberships', () => { render(<StructureViewer/>); expect(screen.getByText('2 workflows · 2 phases · 3 steps · 5 nodes · 2 edges')).toBeTruthy(); expect(screen.getByText('仅内存', { exact: false })).toBeTruthy() })
  it('opens local matrix, preserves nested logic, and restores focus on close', () => {
    render(<StructureViewer/>); const button = screen.getAllByRole('button', { name: /字段矩阵示例/ })[0]; button.focus(); fireEvent.click(button)
    const dialog = screen.getByRole('dialog'); expect(within(dialog).getByText('(A 或 (B 且 C))')).toBeTruthy()
    fireEvent.click(within(dialog).getByText('关闭详情 ×')); expect(document.activeElement).toBe(button)
  })
  it('searches rule IDs and still retains all canvas nodes', () => { render(<StructureViewer/>); fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ready-route' } }); expect(screen.getByText('1 个匹配节点')).toBeTruthy(); expect(document.querySelectorAll('.sv-node')).toHaveLength(4) })
  it('shows complete typed conditions and template state/data/actions', () => { render(<StructureViewer/>); fireEvent.click(screen.getAllByRole('button', { name: /结果模板示例/ })[0]); const d = screen.getByRole('dialog'); expect(within(d).getByRole('columnheader', { name: 'state' })).toBeTruthy(); expect(within(d).getByText('template: ready')).toBeTruthy(); expect(within(d).getAllByText(/"ready"/).length).toBeGreaterThan(0) })
  it('locates diagnostic nodes across workflows', () => { render(<StructureViewer/>); const details = document.querySelector('.sv-diagnostics')!; details.setAttribute('open', ''); fireEvent.click(within(details as HTMLElement).getByRole('button', { name: /MISSING_MODEL/ })); expect(screen.getByRole('dialog').textContent).toContain('sample.solve → P1 → S1 → missing') })
  it('retains prior import on broken, oversized and later successful imports', async () => { render(<StructureViewer/>); const b = structuredClone(example); b.workflows[0].workflow_id = 'own-workflow'; await upload(JSON.stringify(b), 'good.json'); expect(screen.getByText('来源：good.json')).toBeTruthy(); await upload('{', 'broken.json'); expect(screen.getByRole('alert').textContent).toContain('broken.json'); expect(screen.getByRole('alert').textContent).toContain('保留视图：good.json'); expect(screen.getByText('来源：good.json')).toBeTruthy(); await upload(' '.repeat(2 * 1024 * 1024 + 1), 'large.json'); expect(screen.getByRole('alert').textContent).toContain('2 MiB'); await upload(JSON.stringify(example), 'again.json'); expect(screen.queryByRole('alert')).toBeNull(); expect(screen.getByText('来源：again.json')).toBeTruthy() })
  it('shows unsupported model raw without pretending to be local matrix', () => { const b = structuredClone(example) as any; b.models['local@1'].profile = 'other-profile'; render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); fireEvent.click(screen.getAllByRole('button', { name: /字段矩阵示例/ })[0]); expect(screen.getByRole('dialog').textContent).toContain('未支持此 profile'); expect(within(screen.getByRole('dialog')).queryByRole('table')).toBeNull() })
  it('never falls back from missing typed template to inline output', () => { const b = structuredClone(example) as any; b.models['typed@1'].rules[0].output_template_ref = 'missing'; b.models['typed@1'].rules[0].output = { state: 'INLINE_SENTINEL' }; render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); fireEvent.click(screen.getAllByRole('button', { name: /结果模板示例/ })[0]); const table = within(screen.getByRole('dialog')).getByRole('table'); expect(table.textContent).toContain('缺少模板；不使用 inline output'); expect(table.querySelector('td:nth-child(3)')?.textContent).not.toContain('INLINE_SENTINEL') })
  it('paginates large typed rule tables without dropping raw definitions', () => { const b = structuredClone(example) as any; const m = b.models['typed@1']; m.rules = Array.from({ length: 121 }, (_, i) => ({ ...m.rules[0], rule_id: `r${i}` })); render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); fireEvent.click(screen.getAllByRole('button', { name: /结果模板示例/ })[0]); expect(document.querySelectorAll('.sv-rules tbody tr')).toHaveLength(50); fireEvent.click(screen.getByText('规则下一页')); expect(document.querySelectorAll('.sv-rules tbody tr')).toHaveLength(50); fireEvent.click(screen.getByText('规则下一页')); expect(document.querySelectorAll('.sv-rules tbody tr')).toHaveLength(21) })
  it('keeps simple-profile primitive/null outputs distinct without typed projection', () => { const b = structuredClone(example) as any; b.models['typed@1'] = { format: 'json-table-v1', hit_policy: 'FIRST', rules: [{ id: 'null-output', when: [], output: null }, { id: 'string-output', when: [], output: 'plain-value' }] }; render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); fireEvent.click(screen.getAllByRole('button', { name: /结果模板示例/ })[0]); const table = within(screen.getByRole('dialog')).getByRole('table'); expect(within(table).getByRole('columnheader', { name: 'output · 原始 JSON' })).toBeTruthy(); expect(table.textContent).toContain('null'); expect(table.textContent).toContain('"plain-value"'); expect(within(table).queryByRole('columnheader', { name: 'state' })).toBeNull() })
  it('paginates model diagnostics and reuses them for another referencing node', () => { const b = structuredClone(example) as any; const step = b.workflows[0].phases[0].steps[1]; step.graph.nodes.push({ ...step.graph.nodes[0], node_id: 'second', name: 'Second reference' }); b.models['typed@1'].rules = Array.from({ length: 121 }, (_, i) => ({ rule_id: `bad-${i}`, when: [], output_template_ref: 'absent' })); render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); fireEvent.click(screen.getAllByRole('button', { name: /Second reference/ })[0]); const section = within(screen.getByRole('dialog')).getByLabelText('当前定位诊断'); expect(section.querySelectorAll('li')).toHaveLength(50); expect(section.textContent).toContain('121'); fireEvent.click(within(section).getByText('诊断下一页')); expect(section.textContent).toContain('bad-50'); expect(section.querySelectorAll('li')).toHaveLength(50) })
  it('treats imported markup and URLs as text', () => { const b = structuredClone(example) as any; b.workflows[0].phases[0].steps[0].graph.nodes[0].name = '<img src=x onerror=alert(1)>'; render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); expect(document.querySelectorAll('img,script,iframe,a[href]')).toHaveLength(0); expect(screen.getAllByText('<img src=x onerror=alert(1)>').length).toBeGreaterThan(0) })
  it('switches between multiple workflows of the same flow type', () => { const b = structuredClone(example) as any; b.workflows.push({ ...structuredClone(b.workflows[0]), workflow_id: 'second.locate' }); render(<StructureViewer initialBundle={parseStructure(JSON.stringify(b))}/>); const select = screen.getByLabelText('Workflow'); expect(select.querySelectorAll('option')).toHaveLength(2); fireEvent.change(select, { target: { value: 'second.locate' } }); fireEvent.click(screen.getAllByRole('button', { name: /字段矩阵示例/ })[0]); expect(screen.getByRole('dialog').textContent).toContain('second.locate → LOCATE → L1 → eligibility') })
  it('searches malformed optional names safely and preserves that view after invalid import', async () => { const b = structuredClone(example) as any; const w = b.workflows[0]; const p = w.phases[0]; const step = p.steps[0]; for (const object of [w, p, step, ...step.graph.nodes]) object.name = { toString: null, valueOf: null }; render(<StructureViewer/>); await upload(JSON.stringify(b), 'malformed-names.json'); fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'eligibility' } }); expect(screen.getByText('1 个匹配节点')).toBeTruthy(); await upload('{', 'broken-after-names.json'); expect(screen.getByRole('alert').textContent).toContain('保留视图：malformed-names.json'); fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'ready-route' } }); expect(screen.getByText('1 个匹配节点')).toBeTruthy() })
  it('does not perform network requests or browser storage writes', () => { const fetch = vi.fn(); const previous = globalThis.fetch; globalThis.fetch = fetch; const storage = vi.spyOn(Storage.prototype, 'setItem'); render(<StructureViewer/>); fireEvent.click(screen.getAllByRole('button', { name: /字段矩阵示例/ })[0]); expect(fetch).not.toHaveBeenCalled(); expect(storage).not.toHaveBeenCalled(); globalThis.fetch = previous; storage.mockRestore() })
  it.each(['parse', 'read', 'render'])('rolls back a failed %s without replacing the committed DOM or UI state', async kind => {
    render(<StructureViewer/>); await upload(JSON.stringify(example), 'committed.json')
    const directory = document.querySelector('.sv-directory')!
    const viewport = document.querySelector('.sv-viewport')! as HTMLElement
    const disclosure = directory.querySelector('details')!
    disclosure.open = false; viewport.scrollTop = 145; viewport.scrollLeft = 76
    fireEvent.click(screen.getByRole('button', { name: '放大' }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'eligibility' } })
    const original = screen.getAllByRole('button', { name: /字段矩阵示例/ })[0]
    fireEvent.click(original)
    const dialog = screen.getByRole('dialog'); const close = within(dialog).getByText('关闭详情 ×'); close.focus()
    const originalCounts = structureModel.counts
    vi.spyOn(structureModel, 'counts').mockImplementation(bundle => {
      if (bundle.workflows[0].workflow_id === 'candidate-render-failure') throw new Error('Independent render failure')
      return originalCounts(bundle)
    })
    vi.spyOn(console, 'error').mockImplementation(() => {})
    if (kind === 'parse') await upload('{', 'failed.json')
    else if (kind === 'read') {
      const failed = pendingFile('failed.json'); choose(failed.file)
      await act(async () => { failed.reject('Independent read failure') })
    } else {
      const failed = structuredClone(example); failed.workflows[0].workflow_id = 'candidate-render-failure'
      await upload(JSON.stringify(failed), 'failed.json')
    }
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('保留视图：committed.json'))
    expect(screen.getByRole('alert').textContent).toContain('failed.json')
    expect(document.querySelector('.sv-directory')).toBe(directory)
    expect(screen.getByRole('dialog')).toBe(dialog)
    expect(document.activeElement).toBe(close)
    expect(disclosure.open).toBe(false)
    expect(viewport.scrollTop).toBe(145); expect(viewport.scrollLeft).toBe(76)
    expect((screen.getByRole('searchbox') as HTMLInputElement).value).toBe('eligibility')
    expect(screen.getByRole('button', { name: '110%' })).toBeTruthy()
    fireEvent.click(close); expect(document.activeElement).toBe(original)
    await upload(JSON.stringify(example), 'recovered.json')
    expect(screen.queryByRole('alert')).toBeNull(); expect(screen.getByText('来源：recovered.json')).toBeTruthy()
  })
  it.each(['success', 'failure'])('ignores stale read %s after a newer import commits', async outcome => {
    render(<StructureViewer/>)
    const old = pendingFile('old.json'); choose(old.file)
    await upload(JSON.stringify(example), 'new.json')
    const committed = document.querySelector('.sv-directory')
    await act(async () => { outcome === 'success' ? old.resolve(JSON.stringify(example)) : old.reject('Stale error') })
    expect(screen.getByText('来源：new.json')).toBeTruthy()
    expect(document.querySelector('.sv-directory')).toBe(committed)
    expect(screen.queryByRole('alert')).toBeNull()
  })
  it.each(['success', 'failure'])('stale %s cleanup cannot clear a newer pending same-file selection', async outcome => {
    render(<StructureViewer/>)
    const old = pendingFile('repeat.json'); const next = pendingFile('repeat.json')
    choose(old.file); choose(next.file)
    const input = screen.getByLabelText('导入本地 JSON 文件') as HTMLInputElement
    Object.defineProperty(input, 'value', { configurable: true, writable: true, value: 'newer-selection' })
    await act(async () => { outcome === 'success' ? old.resolve(JSON.stringify(example)) : old.reject('Stale error') })
    expect(input.value).toBe('newer-selection')
    expect(screen.getByRole('button', { name: '读取本地文件…' })).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    await act(async () => { next.resolve(JSON.stringify(example)) })
    await waitFor(() => expect(screen.getByText('来源：repeat.json')).toBeTruthy())
    expect(input.value).toBe('')
    // A second selection of the very same File must start a fresh read.
    choose(next.file); expect(next.read).toHaveBeenCalledTimes(2)
    await act(async () => { next.resolve(JSON.stringify(example)) })
    await waitFor(() => expect(screen.getByRole('button', { name: '导入本地 JSON' })).toBeTruthy())
    expect(input.value).toBe('')
  })
  it('suppresses detached-view animation callbacks after a successful replacement', async () => {
    render(<StructureViewer/>)
    const frames: FrameRequestCallback[] = []
    vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation(callback => { frames.push(callback); return frames.length })
    const original = screen.getAllByRole('button', { name: /字段矩阵示例/ })[0]
    fireEvent.click(original); fireEvent.click(within(screen.getByRole('dialog')).getByText('关闭详情 ×'))
    const oldFocus = vi.spyOn(original, 'focus')
    await upload(JSON.stringify(example), 'replacement.json')
    const search = screen.getByRole('searchbox'); search.focus()
    await act(async () => { frames.forEach(callback => callback(0)) })
    expect(oldFocus).not.toHaveBeenCalled(); expect(document.activeElement).toBe(search)
  })
})
