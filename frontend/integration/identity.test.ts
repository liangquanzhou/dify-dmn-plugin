import { describe, expect, it } from 'vitest'
import { DMN_PROVIDER_ID, isDmnDecisionTool, readStaticTableSetting } from './identity'

const target = { provider_type: 'builtin', provider_id: DMN_PROVIDER_ID, tool_name: 'evaluate' }
describe('exact Dify tool identity', () => {
  it('accepts only the exact builtin provider and evaluate tool', () => {
    expect(isDmnDecisionTool(target)).toBe(true)
    for (const provider_id of ['dmn', 'liangquanzhou/dmn_decision', 'other/dmn_decision/dmn', `${DMN_PROVIDER_ID}:0.4.1`, `prefix/${DMN_PROVIDER_ID}`, `${DMN_PROVIDER_ID}/extra`])
      expect(isDmnDecisionTool({ ...target, provider_id })).toBe(false)
    for (const provider_type of ['api', 'workflow', 'mcp', '', undefined])
      expect(isDmnDecisionTool({ ...target, provider_type })).toBe(false)
    for (const tool_name of ['evaluate_other', 'Evaluate', '', undefined])
      expect(isDmnDecisionTool({ ...target, tool_name })).toBe(false)
    expect(isDmnDecisionTool({})).toBe(false)
  })
})
describe('Dify native static form envelopes', () => {
  const raw = '{"id":"test","hit_policy":"FIRST","rules":[]}'
  it('passes raw JSON and static constant/mixed text without reserializing', () => {
    expect(readStaticTableSetting(raw)).toEqual({ available: true, value: raw })
    for (const type of ['constant', 'mixed']) {
      const value = Object.freeze({ type, value: raw })
      expect(readStaticTableSetting(value)).toEqual({ available: true, value: raw })
      expect(value).toEqual({ type, value: raw })
    }
  })
  it('never resolves dynamic or unknown form kinds', () => {
    for (const value of [{ type: 'variable', value: ['node', 'field'] }, { type: 'mixed', value: '{"id":"{{#node.field#}}"}' }, { type: 'future', value: raw }])
      expect(readStaticTableSetting(Object.freeze(value))).toEqual({ available: false })
  })
  it('preserves literal ref-like text for constant values', () => {
    const value = '{"id":"{{#literal#}}"}'
    expect(readStaticTableSetting({ type: 'constant', value })).toEqual({ available: true, value })
  })
  it('preserves empty and invalid values for the preview error/empty boundary', () => {
    for (const value of ['', undefined, null, 0, false, [], '{bad'])
      expect(readStaticTableSetting(value)).toEqual({ available: true, value })
    expect(readStaticTableSetting({ type: 'mixed', value: null })).toEqual({ available: true, value: null })
  })
})
