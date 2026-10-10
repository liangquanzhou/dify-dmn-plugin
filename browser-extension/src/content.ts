import { REFRESH_EVENT, SNAPSHOT_EVENT, STOP_EVENT, MAX_TABLE_CHARS } from './binding'
import type { Snapshot } from './binding'
import { element, renderSnapshot } from './view'
declare const chrome: { runtime: { sendMessage: (message: unknown) => Promise<unknown> } }
const existing = document.getElementById('dmn-preview-extension-root')
if (existing) {
  existing.hidden = false
  document.dispatchEvent(new CustomEvent(REFRESH_EVENT))
} else {
  const root = element(document, 'section')
  root.id = 'dmn-preview-extension-root'
  root.setAttribute('aria-label', 'DMN 扩展只读预览')
  const header = element(document, 'header')
  const title = element(document, 'strong', 'DMN 决策表')
  const readonly = element(document, 'span', '浏览器扩展 · 只读', 'dmnp-badge')
  const grow = element(document, 'button', '展开') as HTMLButtonElement
  grow.setAttribute('aria-label', '展开或还原决策表')
  grow.addEventListener('click', () => {
    const expanded = root.classList.toggle('dmnp-expanded')
    grow.textContent = expanded ? '还原' : '展开'
  })
  const close = element(document, 'button', '关闭')
  const body = element(document, 'div', undefined, 'dmnp-body')
  let lastSnapshot = ''
  let lastReceived = Date.now()
  let stale = false
  let announced = false
  function notify(type: string) {
    try {
      if (typeof chrome !== 'undefined' && typeof chrome.runtime?.sendMessage === 'function')
        chrome.runtime.sendMessage({ type }).catch(() => {})
    } catch { /* The extension context can disappear after a reload. */ }
  }
  function receive(event: Event) {
    const detail = (event as CustomEvent).detail
    if (typeof detail !== 'string' || detail.length > MAX_TABLE_CHARS * 2 + 8192) return
    let snapshot: Snapshot
    try { snapshot = JSON.parse(detail) } catch { return }
    if (!snapshot || !['ready', 'empty', 'dynamic', 'unsupported', 'idle', 'error'].includes(snapshot.status)) return
    if (snapshot.raw !== undefined && (typeof snapshot.raw !== 'string' || snapshot.raw.length > MAX_TABLE_CHARS)) return
    if (snapshot.nodeId !== undefined && typeof snapshot.nodeId !== 'string') return
    if (snapshot.title !== undefined && typeof snapshot.title !== 'string') return
    if (snapshot.message !== undefined && typeof snapshot.message !== 'string') return
    lastReceived = Date.now()
    if (!announced) { announced = true; notify('dmn-preview-active') }
    if (detail === lastSnapshot && !stale) return
    stale = false
    lastSnapshot = detail
    renderSnapshot(body, snapshot)
  }
  const watchdog = setInterval(() => {
    if (Date.now() - lastReceived > 5000 && !stale) {
      stale = true
      renderSnapshot(body, { status: 'error', message: '当前节点读取已中断，旧预览已清除。请再次点击扩展启用。' })
    }
  }, 1000)
  function cleanup() {
    clearInterval(watchdog)
    document.removeEventListener(SNAPSHOT_EVENT, receive)
    document.dispatchEvent(new CustomEvent(STOP_EVENT))
    root.remove()
    notify('dmn-preview-closed')
  }
  close.addEventListener('click', cleanup)
  header.append(title, readonly, grow, close)
  root.append(header, body)
  document.documentElement.append(root)
  document.addEventListener(SNAPSHOT_EVENT, receive)
  renderSnapshot(body, { status: 'idle', message: '正在读取当前选中的 DMN 节点…' })
}
