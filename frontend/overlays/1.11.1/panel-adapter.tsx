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
    save: t('common.operation.save'),
    reset: t('common.operation.reset'),
    export: t('workflow.nodes.tool.dmn.export'),
    import: t('workflow.nodes.tool.dmn.import'),
    fullscreen: t('workflow.nodes.tool.dmn.fullscreen'),
    view: t('common.operation.view'),
    loading: t('workflow.nodes.tool.dmn.loading'),
    error: t('workflow.nodes.tool.dmn.error'),
    saved: t('workflow.nodes.tool.dmn.saved'),
    dirty: t('workflow.nodes.tool.dmn.dirty'),
    help: t('workflow.nodes.tool.dmn.help'),
    replaceConfirm: t('workflow.nodes.tool.dmn.replaceConfirm'),
    conflict: t('workflow.nodes.tool.dmn.conflict'),
  }
  return <Suspense fallback={<p role="status">DMN…</p>}>
    <DmnEditor key={nodeId} nodeId={nodeId} draftScope={draftScope} savedXml={savedXml}
      configurationError={configurationError} readOnly={readOnly} labels={labels}
      onSave={xml => onChange(withModelXml(configuration, xml))} />
  </Suspense>
}
