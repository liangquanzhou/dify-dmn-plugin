/** Dify 1.17.1 plugin identity. Deliberately exact: never match by tool name alone. */
export const DMN_IDENTITY = {
  plugin_id: 'liangquanzhou/dmn_decision',
  provider_id: 'liangquanzhou/dmn_decision/dmn',
  provider_type: 'builtin',
  tool_name: 'evaluate',
} as const

export function isDmnTool(node: {
  plugin_id?: string
  provider_id?: string
  provider_type?: string
  tool_name?: string
}): boolean {
  return node.provider_type === DMN_IDENTITY.provider_type
    && node.provider_id === DMN_IDENTITY.provider_id
    && node.tool_name === DMN_IDENTITY.tool_name
    // Older imported DSL can omit plugin_id; the canonical provider still contains it.
    && (node.plugin_id === undefined || node.plugin_id === DMN_IDENTITY.plugin_id)
}

/** Static form values in Dify 1.17.1 are ResourceVarInputs, not raw XML strings. */
export function readModelXml(config: Record<string, unknown>): string {
  const field = config.model_xml
  if (field === undefined || field === null) return ''
  if (typeof field === 'string') return field // migrated/legacy DSL
  if (typeof field === 'object' && 'value' in field && typeof field.value === 'string') {
    if ('type' in field && field.type !== 'constant' && field.type !== 'mixed')
      throw new Error('model_xml must be a static constant, not a variable binding')
    return field.value
  }
  throw new Error('model_xml must contain a static XML string')
}

export function withModelXml(config: Record<string, unknown>, xml: string): Record<string, unknown> {
  return { ...config, model_xml: { type: 'constant', value: xml } }
}

export const INITIAL_DMN = `<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="https://www.omg.org/spec/DMN/20191111/MODEL/"
             id="eligibility_model" name="Eligibility" namespace="urn:example:eligibility">
  <inputData id="input_age" name="age"><variable id="var_age" name="age" typeRef="number"/></inputData>
  <inputData id="input_risk" name="risk_score"><variable id="var_risk" name="risk_score" typeRef="number"/></inputData>
  <decision id="eligibility" name="Eligibility result">
    <variable id="var_result" name="Eligibility result"/>
    <informationRequirement><requiredInput href="#input_age"/></informationRequirement>
    <informationRequirement><requiredInput href="#input_risk"/></informationRequirement>
    <decisionTable id="eligibility_table" hitPolicy="UNIQUE">
      <input id="age_clause" label="Age"><inputExpression id="age_expression" typeRef="number"><text>age</text></inputExpression></input>
      <input id="risk_clause" label="Risk score"><inputExpression id="risk_expression" typeRef="number"><text>risk_score</text></inputExpression></input>
      <output id="out_eligible" name="eligible" typeRef="boolean"/>
      <output id="out_reason" name="reason" typeRef="string"/>
      <rule id="rule_minor"><inputEntry id="minor_age"><text>[0..18)</text></inputEntry><inputEntry id="minor_risk"><text>[0..100]</text></inputEntry><outputEntry id="minor_eligible"><text>false</text></outputEntry><outputEntry id="minor_reason"><text>"under_age"</text></outputEntry></rule>
      <rule id="rule_eligible"><inputEntry id="eligible_age"><text>&gt;= 18</text></inputEntry><inputEntry id="eligible_risk"><text>[0..60)</text></inputEntry><outputEntry id="eligible_value"><text>true</text></outputEntry><outputEntry id="eligible_reason"><text>"low_risk_adult"</text></outputEntry></rule>
      <rule id="rule_high_risk"><inputEntry id="high_age"><text>&gt;= 18</text></inputEntry><inputEntry id="high_risk"><text>[60..100]</text></inputEntry><outputEntry id="high_value"><text>false</text></outputEntry><outputEntry id="high_reason"><text>"high_risk"</text></outputEntry></rule>
    </decisionTable>
  </decision>
</definitions>`

export const MAX_XML_BYTES = 512 * 1024

export function checkXmlEnvelope(xml: string): void {
  if (!xml.trim()) throw new Error('Empty DMN XML')
  if (new TextEncoder().encode(xml).length > MAX_XML_BYTES)
    throw new Error('DMN XML exceeds 512 KiB')
  if (/<!DOCTYPE|<!ENTITY/i.test(xml))
    throw new Error('DOCTYPE and ENTITY declarations are not accepted')
}
