import { REFRESH_EVENT, SNAPSHOT_EVENT, STOP_EVENT, createPageReader } from './binding'
function startReader() {
  const root = document.getElementById('dmn-preview-extension-root')
  if (!root) return
  // This script runs in MAIN only after the user invokes the extension on this tab.
  // No fetch/XHR interception, stores, cookies, credentials, eval, writes or workflow execution.
  document.dispatchEvent(new CustomEvent(STOP_EVENT))
  const readCurrentPage = createPageReader(document)
  let previous = ''
  let lastSent = 0
  let timer: ReturnType<typeof setInterval>
  let stopped = false
  let scheduled = false
  function emit() {
    if (stopped) return
    if (!root?.isConnected) { stop(); return }
    let snapshot
    try { snapshot = readCurrentPage() }
    catch { snapshot = { status: 'error', message: '读取当前节点失败，旧预览已清除。请重新打开工作流后启用扩展。' } }
    const detail = JSON.stringify(snapshot)
    if (detail !== previous || Date.now() - lastSent >= 1000) {
      previous = detail
      lastSent = Date.now()
      document.dispatchEvent(new CustomEvent(SNAPSHOT_EVENT, { detail }))
    }
  }
  function schedule() {
    if (scheduled || stopped) return
    scheduled = true
    requestAnimationFrame(() => { scheduled = false; emit() })
  }
  function refresh() { previous = ''; emit() }
  function stop() {
    stopped = true
    clearInterval(timer)
    document.removeEventListener('click', schedule, true)
    document.removeEventListener('input', schedule, true)
    document.removeEventListener('change', schedule, true)
    document.removeEventListener(STOP_EVENT, stop)
    document.removeEventListener(REFRESH_EVENT, refresh)
    window.removeEventListener('pagehide', stop)
  }
  document.addEventListener('click', schedule, true)
  document.addEventListener('input', schedule, true)
  document.addEventListener('change', schedule, true)
  document.addEventListener(STOP_EVENT, stop)
  document.addEventListener(REFRESH_EVENT, refresh)
  window.addEventListener('pagehide', stop)
  timer = setInterval(emit, 250)
  emit()
}
startReader()
