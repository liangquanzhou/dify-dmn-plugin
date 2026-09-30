import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { DMN_IDENTITY, INITIAL_DMN, isDmnTool, readModelXml, withModelXml, checkXmlEnvelope, MAX_XML_BYTES } from '../overlay/contract.ts'
import { getDraft, putDraft } from '../overlay/drafts.ts'

test('only exact canonical provider + tool + type + plugin can activate editor', () => {
  assert.equal(isDmnTool(DMN_IDENTITY), true)
  const { plugin_id, ...legacyDsl } = DMN_IDENTITY
  assert.equal(isDmnTool(legacyDsl), true)
  for (const field of Object.keys(DMN_IDENTITY)) assert.equal(isDmnTool({ ...DMN_IDENTITY, [field]: 'other' }), false)
  assert.equal(isDmnTool({ tool_name: 'evaluate' }), false)
})
test('static XML and all unrelated configuration and bindings survive JSON DSL save/reload', () => {
  const config = { model_xml: { type: 'mixed', value: INITIAL_DMN }, decision_id: { type: 'mixed', value: 'eligibility' }, extra: { keep: true } }
  const bindings = { facts_json: { type: 'variable', value: ['start', 'facts_json'] } }
  const node = { tool_configurations: withModelXml(config, INITIAL_DMN), tool_parameters: bindings }
  const loaded = JSON.parse(JSON.stringify(node))
  assert.equal(readModelXml(loaded.tool_configurations), INITIAL_DMN)
  assert.equal(loaded.tool_configurations.model_xml.type, 'constant')
  assert.deepEqual(loaded.tool_parameters, bindings)
  assert.deepEqual(loaded.tool_configurations.decision_id, config.decision_id)
  assert.deepEqual(loaded.tool_configurations.extra, config.extra)
  assert.equal(readModelXml({ model_xml: INITIAL_DMN }), INITIAL_DMN)
  assert.equal(readModelXml({}), '')
  assert.throws(() => readModelXml({ model_xml: { type: 'variable', value: 'x' } }))
  assert.throws(() => readModelXml({ model_xml: 12 }))
})
test('XML byte limits and unsafe entities fail closed', () => {
  checkXmlEnvelope(INITIAL_DMN)
  assert.throws(() => checkXmlEnvelope(''))
  assert.throws(() => checkXmlEnvelope('<!DOCTYPE x><x/>'))
  assert.throws(() => checkXmlEnvelope('<!ENTITY x SYSTEM "file:///etc/passwd">'))
  assert.throws(() => checkXmlEnvelope('中'.repeat(MAX_XML_BYTES / 2)))
})
test('drafts survive panel remount but are isolated per workflow and node', () => {
  const scope = {}; const other = {}
  const draft = { base: 'old', xml: 'new', dirty: true }
  putDraft(scope, '1', draft)
  assert.deepEqual(getDraft(scope, '1'), draft)
  assert.equal(getDraft(other, '1'), undefined)
  assert.equal(getDraft(scope, '2'), undefined)
})
test('starter model is exactly the backend example', () => {
  assert.equal(INITIAL_DMN, readFileSync(new URL('../../examples/eligibility.dmn', import.meta.url), 'utf8').trimEnd())
})
