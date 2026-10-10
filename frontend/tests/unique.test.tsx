// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import DecisionTablePreview from '../src/decision-table'
import { parseTable } from '../src/model'
import { first, collect, unique } from '../demo/fixtures'

const originalShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal')
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  if (originalShowModal) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShowModal)
  else Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal')
})

describe('UNIQUE read-only configuration preview', () => {
  it.each([undefined, 'compatible', 'strict'])('accepts literal UNIQUE with unknown_policy=%s and preserves the full table', (unknown_policy) => {
    const table = { ...unique, unknown_policy }
    const original = JSON.stringify(table)
    const parsed = parseTable(original)
    expect(parsed.kind).toBe('ready')
    if (parsed.kind !== 'ready') throw new Error(parsed.message)
    expect(parsed.matrix.table).toEqual(JSON.parse(original))
    expect(parsed.matrix.rows.map(row => row.rule.id)).toEqual(unique.rules.map(rule => rule.id))
    expect(parsed.matrix.fields).toEqual(['订单金额', '自提'])
    expect(parsed.matrix.outputs.map(output => output.label)).toEqual(['$["output"]["配送方式"]', '$["output"]["运费"]'])
    expect(JSON.stringify(table)).toBe(original)
  })

  it.each(['unique', 'Unique', 'UNIQUE ', 'ANY', '', null, 1])('rejects unsupported policy %s instead of normalizing it', (hit_policy) => {
    const parsed = parseTable(JSON.stringify({ ...unique, hit_policy }))
    expect(parsed).toEqual({ kind: 'error', message: '仅支持 FIRST / COLLECT / UNIQUE 命中策略' })
  })

  it.each([undefined, 'compatible', 'strict'])('explains all outcomes with unknown_policy=%s without selecting a rule', (unknown_policy) => {
    const { container } = render(<DecisionTablePreview value={JSON.stringify({ ...unique, unknown_policy })} readOnly/>)
    expect(screen.getByText('UNIQUE', { exact: true })).toBeVisible()
    expect(screen.getByText('只读面板')).toBeVisible()
    const help = screen.getByLabelText('UNIQUE 策略说明')
    expect(help).toHaveTextContent('恰有 1 条规则成立且没有未知规则时，才选中该规则（matched）')
    expect(help).toHaveTextContent('0 条成立且无未知时为 no_match')
    expect(help).toHaveTextContent('至少 2 条规则成立时为 conflict，不选中任何规则，即使输出相同也视为冲突')
    expect(help).toHaveTextContent('至多 1 条成立且存在未知规则时为 waiting_input，不选中任何规则')
    expect(help).toHaveTextContent('compatible / strict 均需等待唯一性确认')
    expect(screen.getByText(/本视图不修改配置，不计算命中结果/)).toBeVisible()
    expect(container.querySelectorAll('tbody tr')).toHaveLength(3)
    expect(container.querySelector('input,textarea,pre,[aria-selected="true"]')).toBeNull()
  })

  it('does not execute or transmit a table when rendering, expanding, or switching policies', () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) { this.open = true })
    const { container, rerender } = render(<DecisionTablePreview nodeId="unique" value={JSON.stringify(unique)} readOnly/>)
    fireEvent.click(screen.getByRole('button', { name: '展开大表 ↗' }))
    const dialog = container.querySelector('dialog')!
    expect(dialog).toHaveAttribute('open')
    expect(within(dialog).getByLabelText('UNIQUE 策略说明')).toHaveTextContent('conflict')
    expect(within(dialog).getByText(/本视图不计算命中结果/)).toBeVisible()
    rerender(<DecisionTablePreview nodeId="first" value={JSON.stringify(first)} readOnly/>)
    expect(screen.queryByLabelText('UNIQUE 策略说明')).toBeNull()
    expect(screen.getByText(/按顺序选择首个成立规则/)).toBeVisible()
    expect(container.querySelector('dialog')).not.toHaveAttribute('open')
    rerender(<DecisionTablePreview nodeId="collect" value={JSON.stringify(collect)} readOnly/>)
    expect(screen.queryByLabelText('UNIQUE 策略说明')).toBeNull()
    expect(screen.getByText(/按顺序收集所有成立规则/)).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('clears the UNIQUE table and guidance on malformed input', () => {
    const { rerender } = render(<DecisionTablePreview value={JSON.stringify(unique)}/>)
    rerender(<DecisionTablePreview value="{"/>)
    expect(screen.queryByRole('table')).toBeNull()
    expect(screen.queryByLabelText('UNIQUE 策略说明')).toBeNull()
    expect(screen.getByText('无法展示决策表')).toBeVisible()
  })
})
