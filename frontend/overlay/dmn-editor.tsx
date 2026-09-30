'use client'

import type { ChangeEvent, FormEvent } from 'react'
import type { DmnConstructor, DmnInstance, DmnView } from './dmn-types'
import { useEffect, useId, useRef, useState } from 'react'
import { checkXmlEnvelope, INITIAL_DMN, MAX_XML_BYTES } from './contract'
import { getDraft, getPendingDraft, putDraft, putPendingDraft } from './drafts'
import 'dmn-js/dist/assets/diagram-js.css'
import 'dmn-js/dist/assets/dmn-js-shared.css'
import 'dmn-js/dist/assets/dmn-js-drd.css'
import 'dmn-js/dist/assets/dmn-js-decision-table.css'
import 'dmn-js/dist/assets/dmn-js-decision-table-controls.css'
import 'dmn-js/dist/assets/dmn-js-literal-expression.css'
import 'dmn-js/dist/assets/dmn-js-boxed-expression.css'
import 'dmn-js/dist/assets/dmn-js-boxed-expression-controls.css'
import 'dmn-js/dist/assets/dmn-font/css/dmn.css'
import './dmn-editor.css'

export type EditorLabels = {
  title: string
  save: string
  reset: string
  export: string
  import: string
  fullscreen: string
  view: string
  loading: string
  dirty: string
  saved: string
  help: string
  replaceConfirm: string
  conflict: string
  error: string
}

type Props = {
  nodeId: string
  draftScope: object
  savedXml: string
  configurationError?: string
  readOnly: boolean
  onSave: (xml: string) => void
  labels: EditorLabels
}

type Session = {
  modeler: DmnInstance
  xml: string
  base: string
  valid: boolean
  dirty: boolean
  importing: boolean
  revision: number
  disposed: boolean
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

async function importChecked(modeler: DmnInstance, xml: string): Promise<void> {
  checkXmlEnvelope(xml)
  const document = new DOMParser().parseFromString(xml, 'application/xml')
  if (document.querySelector('parsererror'))
    throw new Error(document.querySelector('parsererror')?.textContent || 'Malformed XML')
  const { warnings } = await modeler.importXML(xml)
  if (warnings.length)
    throw new Error(warnings.map(errorMessage).join('\n'))
}

async function exportChecked(modeler: DmnInstance): Promise<string> {
  const { xml } = await modeler.saveXML({ format: true })
  if (!xml) throw new Error('dmn-js returned no XML')
  checkXmlEnvelope(xml)
  return xml
}

export default function DmnEditor({ nodeId, draftScope, savedXml, configurationError, readOnly, onSave, labels }: Props) {
  const canvas = useRef<HTMLDivElement>(null)
  const root = useRef<HTMLElement>(null)
  const session = useRef<Session | null>(null)
  const props = useRef({ savedXml, onSave, configurationError })
  const fileId = useId()
  const statusId = useId()
  const [busy, setBusy] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [valid, setValid] = useState(false)
  const [baseXml, setBaseXml] = useState(savedXml)
  const [error, setError] = useState(configurationError || '')
  const [rejectedXml, setRejectedXml] = useState('')
  const [views, setViews] = useState<DmnView[]>([])
  const [activeView, setActiveView] = useState('')
  const conflict = dirty && savedXml !== baseXml

  useEffect(() => {
    props.current = { savedXml, onSave, configurationError }
  }, [savedXml, onSave, configurationError])

  // dmn-js is a browser-only imperative widget; each node session owns its lifetime.
  useEffect(() => {
    let cancelled = false
    let current: Session | null = null
    let initial = { xml: savedXml || INITIAL_DMN, base: savedXml, dirty: !savedXml && !readOnly }
    const remember = (s: Session) => {
      if (!readOnly) putDraft(draftScope, nodeId, { xml: s.xml, base: s.base, dirty: s.dirty })
    }
    const capture = async () => {
      const s = current
      if (!s || s.importing || s.disposed || readOnly) return
      s.dirty = true
      const revision = ++s.revision
      setDirty(true)
      try {
        const xml = await exportChecked(s.modeler)
        if (revision !== s.revision) return
        s.xml = xml
        remember(s)
      } catch (cause) {
        if (!s.disposed) setError(errorMessage(cause))
      }
    }
    const refreshViews = () => {
      if (!current || current.disposed) return
      setViews(current.modeler.getViews())
      setActiveView(current.modeler.getActiveView()?.id || '')
    }
    const start = async () => {
      setBusy(true)
      setValid(false)
      setError(configurationError || '')
      setRejectedXml('')
      try {
        await getPendingDraft(draftScope, nodeId)
        if (cancelled) return
        const cache = getDraft(draftScope, nodeId)
        if (!readOnly && cache?.dirty) initial = cache
        const module = readOnly ? await import('dmn-js/lib/NavigatedViewer') : await import('dmn-js/lib/Modeler')
        if (cancelled || !canvas.current) return
        const Constructor = module.default as DmnConstructor
        const modeler = new Constructor({ container: canvas.current, width: '100%', height: '100%' })
        current = { modeler, ...initial, valid: false, importing: true, revision: 0, disposed: false }
        session.current = current
        modeler.on('viewer.created', ({ viewer }) => viewer.on('commandStack.changed', () => { void capture() }))
        modeler.on('views.changed', refreshViews)
        modeler.on('view.changed', refreshViews)
        if (props.current.configurationError) throw new Error(props.current.configurationError)
        await importChecked(modeler, initial.xml)
        if (cancelled) return
        current.valid = true
        current.importing = false
        setValid(true)
        setDirty(initial.dirty)
        setBaseXml(initial.base)
        remember(current)
        refreshViews()
      } catch (cause) {
        if (!cancelled) {
          setError(errorMessage(cause))
          setRejectedXml(initial.xml)
        }
      } finally {
        if (!cancelled) setBusy(false)
      }
    }
    void start()
    return () => {
      cancelled = true
      if (current) {
        const s = current
        s.disposed = true
        // Save the final snapshot before destruction, including same-tick edits/navigation.
        if (!readOnly && s.valid && !s.importing) {
          const pending = exportChecked(s.modeler).then((xml) => {
            s.xml = xml
            remember(s)
          }).finally(() => s.modeler.destroy()).catch(() => {})
          putPendingDraft(draftScope, nodeId, pending)
        } else {
          s.modeler.destroy()
        }
      }
      session.current = null
    }
  }, [draftScope, nodeId, readOnly, savedXml, configurationError])

  useEffect(() => {
    if (!dirty) return
    const beforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', beforeUnload)
    return () => window.removeEventListener('beforeunload', beforeUnload)
  }, [dirty])

  const replaceXml = async (xml: string, reset = false) => {
    const s = session.current
    if (!s || readOnly || busy) return
    if (dirty && !window.confirm(labels.replaceConfirm)) return
    setBusy(true)
    s.importing = true
    let validator: DmnInstance | undefined
    try {
      // Validate in a disposable viewer, so failed input cannot erase the current canvas.
      const { default: Viewer } = await import('dmn-js/lib/NavigatedViewer')
      validator = new Viewer({ container: document.createElement('div'), width: '100%', height: '100%' })
      await importChecked(validator, xml)
      await importChecked(s.modeler, xml)
      s.xml = xml
      s.base = props.current.savedXml
      s.dirty = !reset || !props.current.savedXml
      s.valid = true
      ++s.revision
      putDraft(draftScope, nodeId, { xml, base: s.base, dirty: s.dirty })
      if (s.disposed) return
      setDirty(s.dirty)
      setBaseXml(s.base)
      setValid(true)
      setError('')
      setRejectedXml('')
      setViews(s.modeler.getViews())
      setActiveView(s.modeler.getActiveView()?.id || '')
    } catch (cause) {
      if (!s.disposed) {
        setError(errorMessage(cause))
        setRejectedXml(xml)
      }
      // A rendering-only failure may occur after validation. Restore the previous model.
      if (s.valid) {
        try { await importChecked(s.modeler, s.xml) }
        catch (restoreError) {
          s.valid = false
          if (!s.disposed) {
            setValid(false)
            setError(`${errorMessage(cause)}\n${errorMessage(restoreError)}`)
          }
        }
      }
    } finally {
      validator?.destroy()
      s.importing = false
      if (!s.disposed) setBusy(false)
    }
  }

  const importFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = '' // selecting the same filename again must work
    if (!file) return
    try {
      if (!/\.dmn$/i.test(file.name)) throw new Error('Select a .dmn file')
      if (file.size > MAX_XML_BYTES) throw new Error('DMN XML exceeds 512 KiB')
      await replaceXml(await file.text())
    } catch (cause) { setError(errorMessage(cause)) }
  }

  const save = async (event: FormEvent) => {
    event.preventDefault()
    const s = session.current
    if (!s || !s.valid || readOnly || busy || conflict || error) return
    setBusy(true)
    try {
      const xml = await exportChecked(s.modeler)
      if (s.disposed) return
      props.current.onSave(xml)
      s.xml = xml
      s.base = xml
      s.dirty = false
      ++s.revision
      putDraft(draftScope, nodeId, { xml, base: xml, dirty: false })
      setDirty(false)
      setBaseXml(xml)
    } catch (cause) { setError(errorMessage(cause)) }
    finally { if (!s.disposed) setBusy(false) }
  }

  const download = async () => {
    const s = session.current
    if (!s?.valid || busy || error) return
    try {
      const xml = await exportChecked(s.modeler)
      const url = URL.createObjectURL(new Blob([xml], { type: 'application/xml;charset=utf-8' }))
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = 'decision-model.dmn'
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (cause) { setError(errorMessage(cause)) }
  }

  return (
    <section ref={root} className="dify-dmn-editor" aria-label={labels.title}>
      <strong>{labels.title}</strong>
      <p className="dify-dmn-status">{labels.help}</p>
      <form onSubmit={save} aria-label={labels.title} aria-describedby={statusId}>
        <div className="dify-dmn-toolbar">
          <button type="submit" disabled={readOnly || busy || !valid || !dirty || conflict || !!error}>{labels.save}</button>
          <button type="button" disabled={readOnly || busy} onClick={() => { void replaceXml(props.current.savedXml || INITIAL_DMN, true) }}>{labels.reset}</button>
          <button type="button" disabled={busy || !valid || !!error} onClick={() => { void download() }}>{labels.export} .dmn</button>
          <button type="button" onClick={() => {
            const promise = document.fullscreenElement ? document.exitFullscreen() : root.current?.requestFullscreen()
            void promise?.catch(cause => setError(errorMessage(cause)))
          }}>{labels.fullscreen}</button>
        </div>
        {!readOnly && <div className="dify-dmn-toolbar">
          <label htmlFor={fileId}>{labels.import} .dmn</label>
          <input id={fileId} type="file" accept=".dmn" disabled={busy} onChange={event => { void importFile(event) }} />
        </div>}
      </form>
      <div id={statusId} className="dify-dmn-status" role="status" aria-live="polite">
        {busy ? labels.loading : error || configurationError ? labels.error : dirty ? labels.dirty : labels.saved}
      </div>
      {conflict && <p role="alert" className="dify-dmn-error">{labels.conflict}</p>}
      {(error || configurationError) && <div role="alert" className="dify-dmn-error">
        <strong>{labels.error}</strong>{' '}{error || configurationError}
        {rejectedXml && <details><summary>XML</summary><textarea aria-label="XML" readOnly value={rejectedXml} /></details>}
      </div>}
      {views.length > 1 && <label className="dify-dmn-toolbar">
        {labels.view}
        <select disabled={busy} value={activeView} onChange={async event => {
          const view = views.find(item => item.id === event.target.value)
          const s = session.current
          if (!view || !s) return
          setBusy(true)
          try { await s.modeler.open(view); setActiveView(view.id) }
          catch (cause) { setError(errorMessage(cause)) }
          finally { if (!s.disposed) setBusy(false) }
        }}>{views.map(view => <option key={view.id} value={view.id}>{view.name || view.type}</option>)}</select>
      </label>}
      <div ref={canvas} className="dify-dmn-canvas" aria-busy={busy} />
    </section>
  )
}
