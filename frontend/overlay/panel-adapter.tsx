'use client'

import type { EditorLabels } from './dmn-editor'
import { lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { readModelXml, withModelXml } from './contract'

const DmnEditor = lazy(() => import('./dmn-editor'))

type Props = {
  nodeId: string
  draftScope: object
  configuration: Record<string, unknown>
  readOnly: boolean
  onChange: (configuration: Record<string, unknown>) => void
}

export default function DmnPanelAdapter({ nodeId, draftScope, configuration, readOnly, onChange }: Props) {
  const { t } = useTranslation()
  let savedXml = ''
  let configurationError: string | undefined
  try { savedXml = readModelXml(configuration) }
  catch (error) { configurationError = error instanceof Error ? error.message : String(error) }
  const labels: EditorLabels = {
    title: 'DMN',
    save: t(($) => $['operation.save'], { ns: 'common' }),
    reset: t(($) => $['operation.reset'], { ns: 'common' }),
    export: t(($) => $['operation.export'], { ns: 'common' }),
    import: t(($) => $['operation.upload'], { ns: 'common' }),
    fullscreen: t(($) => $['operation.toggleFullscreen'], { ns: 'common' }),
    view: t(($) => $['operation.view'], { ns: 'common' }),
    loading: t(($) => $['operation.saving'], { ns: 'common' }),
    error: t(($) => $['api.actionFailed'], { ns: 'common' }),
    saved: t(($) => $['nodes.tool.dmn.saved'], { ns: 'workflow' }),
    dirty: t(($) => $['nodes.tool.dmn.dirty'], { ns: 'workflow' }),
    help: t(($) => $['nodes.tool.dmn.help'], { ns: 'workflow' }),
    replaceConfirm: t(($) => $['nodes.tool.dmn.replaceConfirm'], { ns: 'workflow' }),
    conflict: t(($) => $['nodes.tool.dmn.conflict'], { ns: 'workflow' }),
  }
  return <Suspense fallback={<p role="status">DMN…</p>}>
    <DmnEditor key={nodeId} nodeId={nodeId} draftScope={draftScope} savedXml={savedXml}
      configurationError={configurationError} readOnly={readOnly} labels={labels}
      onSave={xml => onChange(withModelXml(configuration, xml))} />
  </Suspense>
}
