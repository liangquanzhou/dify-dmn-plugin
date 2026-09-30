import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
const sample = readFileSync(new URL('../../examples/eligibility.dmn', import.meta.url), 'utf8')
const modified = sample.replaceAll('low_risk_adult', 'edited_result')
async function ready(page) {
  await expect(page.getByRole('status')).not.toHaveText('Loading…')
}
async function importDmn(page, xml = modified) {
  await page.getByLabel('Import .dmn').setInputFiles({ name: 'model.dmn', mimeType: 'application/xml', buffer: Buffer.from(xml) })
  await ready(page)
}
async function graph(page) { return JSON.parse(await page.getByLabel('Workflow DSL JSON').inputValue()) }

test.beforeEach(async ({ page }) => { page.on('dialog', dialog => dialog.accept()) })

test('real dmn-js import, export, save, JSON DSL reload and panel reopen', async ({ page }) => {
  await page.goto('/'); await ready(page)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByText('low_risk_adult', { exact: false }).first()).toBeVisible()
  await expect(page.locator('.bjs-powered-by')).toBeVisible()
  await importDmn(page)
  await expect(page.getByRole('status')).toHaveText('Unsaved DMN changes')
  expect((await graph(page)).nodes[0].data.tool_configurations.model_xml.value).toContain('low_risk_adult')
  const downloaded = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export .dmn', exact: true }).click()
  const file = await downloaded
  expect(readFileSync(await file.path(), 'utf8')).toContain('edited_result')
  await page.getByRole('button', { name: 'Save', exact: true }).click(); await ready(page)
  const saved = (await graph(page)).nodes[0].data
  expect(saved.tool_configurations.model_xml.type).toBe('constant')
  expect(saved.tool_configurations.model_xml.value).toContain('edited_result')
  expect(saved.tool_configurations.decision_id.value).toBe('eligibility')
  expect(saved.tool_configurations.unchanged).toBe(42)
  expect(saved.tool_parameters.facts_json).toEqual({ type: 'variable', value: ['start', 'facts_json'] })
  await page.getByRole('button', { name: 'Serialize and reload DSL' }).click()
  await page.getByRole('button', { name: 'Close panel' }).click()
  await expect(page.getByRole('region', { name: 'DMN', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Reopen panel' }).click(); await ready(page)
  await expect(page.getByText('edited_result', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  await page.screenshot({ path: 'test-results/editor-saved.png', fullPage: true })
})

test('unsaved draft survives node switch and reset discards it', async ({ page }) => {
  await page.goto('/'); await ready(page); await importDmn(page)
  await page.getByRole('button', { name: 'Unrelated tool' }).click()
  await expect(page.getByRole('region', { name: 'DMN', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'DMN tool', exact: true }).click(); await ready(page)
  await expect(page.getByText('edited_result', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Unsaved DMN changes')
  await page.getByRole('button', { name: 'Reset', exact: true }).click(); await ready(page)
  await expect(page.getByText('low_risk_adult', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('status')).toHaveText('Saved to workflow draft')
})

test('invalid import is visible, keeps saved XML, and never silently replaces with a sample', async ({ page }) => {
  await page.goto('/'); await ready(page)
  const before = await graph(page)
  await importDmn(page, '<definitions><not-closed>')
  await expect(page.getByRole('alert')).toContainText('DMN error')
  expect(await graph(page)).toEqual(before)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  await page.getByText('XML', { exact: true }).click()
  await expect(page.getByRole('textbox', { name: 'XML', exact: true })).toHaveValue('<definitions><not-closed>')
  await page.screenshot({ path: 'test-results/editor-invalid.png', fullPage: true })
  await page.getByRole('button', { name: 'Reset', exact: true }).click(); await ready(page)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('invalid saved XML remains recoverable and unsavable', async ({ page }) => {
  await page.goto('/?invalid'); await ready(page)
  await expect(page.getByRole('alert')).toContainText('DMN error')
  expect((await graph(page)).nodes[0].data.tool_configurations.model_xml.value).toBe('<invalid')
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  await importDmn(page, sample)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await page.getByRole('button', { name: 'Save', exact: true }).click(); await ready(page)
  expect((await graph(page)).nodes[0].data.tool_configurations.model_xml.value).toContain('eligibility')
})

test('read-only panel uses viewer and cannot import or save', async ({ page }) => {
  await page.goto('/?readonly'); await ready(page)
  await expect(page.getByLabel('Import .dmn')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Reset', exact: true })).toBeDisabled()
  await expect(page.locator('[contenteditable=true]')).toHaveCount(0)
  await expect(page.locator('.bjs-powered-by')).toBeVisible()
})

test('new model is explicitly dirty, and remote XML conflict blocks overwrite', async ({ page }) => {
  await page.goto('/?empty'); await ready(page)
  await expect(page.getByRole('status')).toHaveText('Unsaved DMN changes')
  expect((await graph(page)).nodes[0].data.tool_configurations.model_xml.value).toBe('')
  await page.getByRole('button', { name: 'Save', exact: true }).click(); await ready(page)
  await importDmn(page)
  await page.getByRole('button', { name: 'External XML change' }).click(); await ready(page)
  await expect(page.getByRole('alert')).toContainText('workflow XML changed')
  await expect(page.getByRole('button', { name: 'Save', exact: true })).toBeDisabled()
  await page.getByRole('button', { name: 'Reset', exact: true }).click(); await ready(page)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByText('external_change', { exact: false }).first()).toBeVisible()
})
