/** Dify 1.11.1 provider IDs are plugin author/name/provider, without a version suffix. */
export const DMN_PROVIDER_ID = 'liangquanzhou/dmn_decision/dmn'
type ToolIdentity = {
  provider_type?: unknown;
  provider_id?: unknown;
  tool_name?: unknown;
}
export function isDmnDecisionTool(tool: ToolIdentity): boolean {
  return tool.provider_type === 'builtin'
        && tool.provider_id === DMN_PROVIDER_ID
        && tool.tool_name === 'evaluate'
}
type StaticSetting = {
  available: true;
  value: unknown;
} | {
  available: false;
}
/** Unwrap Dify's form envelope without executing variables or rewriting the saved value. */
export function readStaticTableSetting(setting: unknown): StaticSetting {
  if (setting === null || typeof setting !== 'object' || Array.isArray(setting))
    return { available: true, value: setting }
  const wrapped = setting as Record<string, unknown>
  if (wrapped.type !== 'constant' && wrapped.type !== 'mixed')
    return { available: false }
  if (wrapped.type === 'mixed' && typeof wrapped.value === 'string') {
    const referenceStart = wrapped.value.indexOf('{{#')
    if (referenceStart !== -1 && wrapped.value.includes('#}}', referenceStart + 3))
      return { available: false }
  }
  return { available: true, value: wrapped.value }
}
