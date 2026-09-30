// The version-specific wrapper uses the exact Dify 1.11.1 React/i18n versions.
// The editor is stubbed here: the separate 11-case suite tests real dmn-js behavior.
import { test, after } from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { Window } from 'happy-dom'
import { mkdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
const absolute = path => fileURLToPath(new URL(path, import.meta.url))
const deps = '../compatibility/1.11.1/node_modules/'
const window = new Window({ url: 'http://localhost/' })
for (const name of ['window', 'document', 'navigator', 'HTMLElement', 'Node', 'MutationObserver']) {
  Object.defineProperty(globalThis, name, { value: name === 'window' ? window : window[name], configurable: true })
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true
const React = await import(deps+'react/index.js')
const { createRoot } = await import(deps+'react-dom/client.js')
const { default: i18n } = await import(deps+'i18next/dist/esm/i18next.js')
const { I18nextProvider } = await import(deps+'react-i18next/dist/es/index.js')
const common = { operation: { save: 'Save', reset: 'Reset', view: 'View' } }
const labels = JSON.parse(readFileSync(new URL('../scripts/locales.json', import.meta.url)))
const extra = JSON.parse(readFileSync(new URL('../scripts/locales-1.11.1.json', import.meta.url)))
const resource = locale => ({ common, workflow: { nodes: { tool: { dmn: { ...Object.fromEntries(['saved','dirty','help','replaceConfirm','conflict'].map((key, i) => [key, labels[locale][i]])), ...extra[locale] } } } } })
await i18n.init({ lng:'en-US', fallbackLng:'en-US', resources: { 'en-US': { translation:resource('en-US') }, 'zh-Hans': { translation:resource('zh-Hans') } } })
mkdirSync('test-results', { recursive: true })
const externals = {
  'react': absolute(deps+'react/index.js'),
  'react/jsx-runtime': absolute(deps+'react/jsx-runtime.js'),
  'react-i18next': absolute(deps+'react-i18next/dist/es/index.js'),
}
await build({
  entryPoints:['overlays/1.11.1/panel-adapter.tsx'], outfile:'test-results/legacy-adapter.mjs', bundle:true, format:'esm', platform:'browser', jsx:'automatic', logLevel:'silent',
  plugins:[{ name:'test-boundaries', setup(builder) {
    builder.onResolve({ filter:/^(react|react\/jsx-runtime|react-i18next)$/ }, args => ({ path:externals[args.path], external:true }))
    builder.onResolve({ filter:/^\.\/contract$/ }, () => ({ path:absolute('../overlay/contract.ts') }))
    builder.onResolve({ filter:/^\.\/dmn-editor$/ }, () => ({ path:'editor', namespace:'stub' }))
    builder.onLoad({ filter:/.*/, namespace:'stub' }, () => ({ contents:`import { createElement } from 'react'; export default function Editor(props) { globalThis.receivedLegacyProps = props; return createElement('button', { onClick: () => props.onSave('<definitions>saved</definitions>') }, props.labels.save); }` }))
  } }],
})
const { default: Adapter } = await import('../test-results/legacy-adapter.mjs')
const container = document.createElement('div'); document.body.append(container)
const root = createRoot(container)
const changed = []
const scope = {}
const configuration = { model_xml: { type:'constant', value:'<definitions>original</definitions>' }, decision_id:{ type:'mixed', value:'eligibility' }, other:42 }
async function render(extraProps={}) {
  await React.act(async () => {
    root.render(React.createElement(I18nextProvider, { i18n }, React.createElement(Adapter, { nodeId:'node-111', draftScope:scope, configuration, readOnly:false, onChange:value => changed.push(value), ...extraProps })))
    await new Promise(resolve => setTimeout(resolve, 0))
  })
}
after(async () => { await React.act(async () => root.unmount()); window.happyDOM.abort() })

test('1.11.1 actual i18n runtime resolves string keys and preserves persistence callback', async () => {
  await render()
  assert.equal(globalThis.receivedLegacyProps.nodeId, 'node-111')
  assert.equal(globalThis.receivedLegacyProps.draftScope, scope)
  assert.equal(globalThis.receivedLegacyProps.savedXml, configuration.model_xml.value)
  assert.equal(globalThis.receivedLegacyProps.labels.help, labels['en-US'][2])
  assert.equal(globalThis.receivedLegacyProps.labels.export, extra['en-US'].export)
  assert.equal(globalThis.receivedLegacyProps.labels.error, extra['en-US'].error)
  for (const label of Object.values(globalThis.receivedLegacyProps.labels)) assert.doesNotMatch(label, /^(common|workflow)\./)
  await React.act(async () => container.querySelector('button').click())
  assert.deepEqual(changed, [{ ...configuration, model_xml:{ type:'constant', value:'<definitions>saved</definitions>' } }])
  assert.equal(configuration.model_xml.value, '<definitions>original</definitions>')
})
test('1.11.1 passes read-only and invalid static binding errors to shared editor', async () => {
  await render({ readOnly:true, configuration:{ ...configuration, model_xml:{ type:'variable', value:'binding' } } })
  assert.equal(globalThis.receivedLegacyProps.readOnly, true)
  assert.match(globalThis.receivedLegacyProps.configurationError, /static constant/)
  assert.equal(globalThis.receivedLegacyProps.savedXml, '')
})
test('1.11.1 nested Chinese resources resolve after language switch', async () => {
  await React.act(async () => i18n.changeLanguage('zh-Hans'))
  await render()
  assert.equal(globalThis.receivedLegacyProps.labels.help, labels['zh-Hans'][2])
  assert.equal(globalThis.receivedLegacyProps.labels.conflict, labels['zh-Hans'][4])
  assert.equal(globalThis.receivedLegacyProps.labels.import, extra['zh-Hans'].import)
})
