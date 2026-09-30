// Real dmn-js and React in a DOM simulator. This does NOT certify browser layout.
import { test, afterEach } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { Window } from 'happy-dom'
import { mkdirSync, readFileSync } from 'node:fs'
const window = new Window({ url: 'http://localhost/' })
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'Element', 'Node', 'Document', 'DOMParser', 'XMLSerializer', 'SVGElement', 'SVGSVGElement', 'MutationObserver', 'ResizeObserver', 'File', 'Blob', 'FileReader', 'Event', 'CustomEvent', 'MouseEvent', 'KeyboardEvent', 'getComputedStyle']) {
  Object.defineProperty(globalThis, key, { value: key === 'window' ? window : typeof window[key] === 'function' && key === 'getComputedStyle' ? window[key].bind(window) : window[key], configurable: true, writable: true })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
window.confirm = () => true
mkdirSync('test-results', { recursive: true })
await build({ entryPoints: ['overlay/dmn-editor.tsx'], bundle: true, format: 'esm', platform: 'browser', outfile: 'test-results/editor.mjs', jsx: 'automatic', loader: { '.css': 'empty' }, external: ['react', 'react-dom', 'react/jsx-runtime'], logLevel: 'silent' })
const React = await import('react')
const { render, screen, fireEvent, waitFor, cleanup, act } = await import('@testing-library/react')
const { default: DmnEditor } = await import('../test-results/editor.mjs')
const sample = readFileSync(new URL('../../examples/eligibility.dmn', import.meta.url), 'utf8')
const labels = { title:'DMN', save:'Save', reset:'Reset', export:'Export', import:'Import', fullscreen:'Fullscreen', view:'View', loading:'Loading', dirty:'Unsaved', saved:'Saved', help:'Save before running', replaceConfirm:'Discard?', conflict:'XML conflict', error:'DMN error' }
const saved = []
const props = (extra = {}) => ({ nodeId:'one', draftScope:{}, savedXml:sample, readOnly:false, onSave: xml => saved.push(xml), labels, ...extra })
async function ready() { await waitFor(() => assert.notEqual(screen.getByRole('status').textContent, 'Loading'), { timeout: 10000 }) }
afterEach(() => { cleanup(); saved.length = 0 })

test('actual dmn-js loads the table, preserves watermark, imports and exports XML into static config', async () => {
  render(React.createElement(DmnEditor, props()))
  await ready()
  assert.equal(screen.queryByRole('alert'), null)
  assert.ok(document.querySelector('.bjs-powered-by'))
  assert.match(document.body.textContent, /low_risk_adult/)
  const modified = sample.replace('low_risk_adult', 'dom_roundtrip')
  await act(async () => fireEvent.change(screen.getByLabelText('Import .dmn'), { target: { files: [new File([modified], 'model.dmn')] } }))
  await ready()
  assert.equal(screen.getByRole('status').textContent, 'Unsaved')
  assert.equal(saved.length, 0)
  await act(async () => fireEvent.click(screen.getByRole('button', { name:'Save', exact:true })))
  await ready()
  assert.equal(saved.length, 1)
  assert.match(saved[0], /dom_roundtrip/)
  assert.match(saved[0], /decision id="eligibility"/)
})

test('invalid imported XML retains previous table, reports error, and blocks Save', async () => {
  render(React.createElement(DmnEditor, props()))
  await ready()
  await act(async () => fireEvent.change(screen.getByLabelText('Import .dmn'), { target: { files: [new File(['<definitions><broken>'], 'broken.dmn')] } }))
  await ready()
  assert.match(screen.getByRole('alert').textContent, /DMN error/)
  assert.equal(screen.getByRole('button', { name:'Save', exact:true }).disabled, true)
  assert.match(document.body.textContent, /low_risk_adult/)
  assert.equal(saved.length, 0)
})

test('saved malformed XML is retained visibly and never auto-replaced', async () => {
  render(React.createElement(DmnEditor, props({ savedXml:'<invalid' })))
  await ready()
  assert.match(screen.getByRole('alert').textContent, /DMN error/)
  assert.equal(screen.getByRole('textbox', { name:'XML', exact:true }).value, '<invalid')
  assert.equal(screen.getByRole('button', { name:'Save', exact:true }).disabled, true)
  assert.equal(saved.length, 0)
})

test('read-only viewer has no import input or writable table and cannot save', async () => {
  render(React.createElement(DmnEditor, props({ readOnly:true })))
  await ready()
  assert.equal(screen.queryByLabelText('Import .dmn'), null)
  assert.equal(screen.getByRole('button', { name:'Save', exact:true }).disabled, true)
  assert.equal(document.querySelectorAll('[contenteditable=true]').length, 0)
})

test('unsaved XML survives close/reopen in the same workflow store and reset discards it', async () => {
  const scope = {}; const settings = props({ draftScope:scope })
  const view = render(React.createElement(DmnEditor, settings)); await ready()
  const modified = sample.replace('low_risk_adult', 'retained_draft')
  await act(async () => fireEvent.change(screen.getByLabelText('Import .dmn'), { target: { files: [new File([modified], 'model.dmn')] } })); await ready()
  view.unmount()
  render(React.createElement(DmnEditor, settings)); await ready()
  assert.match(document.body.textContent, /retained_draft/)
  assert.equal(screen.getByRole('status').textContent, 'Unsaved')
  await act(async () => fireEvent.click(screen.getByRole('button', { name:'Reset', exact:true }))); await ready()
  assert.match(document.body.textContent, /low_risk_adult/)
  assert.equal(screen.getByRole('status').textContent, 'Saved')
})

test('external XML update while dirty is conflict-protected', async () => {
  const settings = props()
  const view = render(React.createElement(DmnEditor, settings)); await ready()
  const modified = sample.replace('low_risk_adult', 'local_draft')
  await act(async () => fireEvent.change(screen.getByLabelText('Import .dmn'), { target: { files: [new File([modified], 'model.dmn')] } })); await ready()
  view.rerender(React.createElement(DmnEditor, { ...settings, savedXml:sample.replace('low_risk_adult', 'remote_change') })); await ready()
  assert.match(screen.getByRole('alert').textContent, /XML conflict/)
  assert.equal(screen.getByRole('button', { name:'Save', exact:true }).disabled, true)
})
