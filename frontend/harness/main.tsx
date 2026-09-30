import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import DmnEditor from '../overlay/dmn-editor'
import { INITIAL_DMN, isDmnTool, readModelXml, withModelXml, DMN_IDENTITY } from '../overlay/contract'
import type { EditorLabels } from '../overlay/dmn-editor'

const scope = {}
const labels: EditorLabels = {
  title: 'DMN', save: 'Save', reset: 'Reset', export: 'Export', import: 'Import', fullscreen: 'Toggle fullscreen', view: 'View',
  loading: 'Loading…', saved: 'Saved to workflow draft', dirty: 'Unsaved DMN changes',
  help: 'Save DMN changes before running or publishing. Facts use the native input fields.',
  replaceConfirm: 'Discard unsaved DMN changes?', conflict: 'The workflow XML changed. Export your draft, then reset before saving.', error: 'DMN error',
}

function Harness() {
  const params = new URLSearchParams(location.search)
  const initialXml = params.has('invalid') ? '<invalid' : params.has('empty') ? '' : INITIAL_DMN
  const [configuration, setConfiguration] = useState<Record<string, unknown>>({
    model_xml: { type: 'constant', value: initialXml }, decision_id: { type: 'mixed', value: 'eligibility' }, unchanged: 42,
  })
  const [open, setOpen] = useState(true)
  const [identity, setIdentity] = useState({ ...DMN_IDENTITY } as Record<string, string>)
  const facts = { facts_json: { type: 'variable', value: ['start', 'facts_json'] } }
  const graph = { nodes: [{ id: 'tool_1', data: { ...identity, tool_configurations: configuration, tool_parameters: facts } }] }
  return <main style={{ maxWidth: 1200, margin: '20px auto', fontFamily: 'sans-serif' }}>
    <h1>Dify DMN integration verification harness</h1>
    <p>This isolated harness exercises the production editor component. It is not a full Dify installation.</p>
    <button onClick={() => setOpen(!open)}>{open ? 'Close panel' : 'Reopen panel'}</button>{' '}
    <button onClick={() => setIdentity({ ...DMN_IDENTITY, provider_id: 'another/plugin/dmn' })}>Unrelated tool</button>{' '}
    <button onClick={() => setIdentity({ ...DMN_IDENTITY })}>DMN tool</button>{' '}
    <button onClick={() => setConfiguration(withModelXml(configuration, INITIAL_DMN.replace('low_risk_adult', 'external_change')))}>External XML change</button>{' '}
    <button onClick={() => setConfiguration(JSON.parse(JSON.stringify(graph)).nodes[0].data.tool_configurations)}>Serialize and reload DSL</button>
    {open && isDmnTool(identity) && <DmnEditor nodeId="tool_1" draftScope={scope} savedXml={readModelXml(configuration)}
      readOnly={params.has('readonly')} onSave={xml => setConfiguration(previous => withModelXml(previous, xml))} labels={labels} />}
    <label>Workflow DSL JSON<textarea aria-label="Workflow DSL JSON" value={JSON.stringify(graph)} readOnly style={{ width: '100%', height: 120 }} /></label>
  </main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><Harness /></React.StrictMode>)
