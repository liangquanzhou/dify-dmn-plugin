/** In-memory only, scoped to the actual Dify workflow store. No XML in browser storage.
 * A draft survives switching nodes/panels, but does not leak between workflow stores.
 */
export type Draft = { xml: string; base: string; dirty: boolean }
const scopes = new WeakMap<object, Map<string, Draft>>()

export function getDraft(scope: object, nodeId: string): Draft | undefined {
  return scopes.get(scope)?.get(nodeId)
}

export function putDraft(scope: object, nodeId: string, draft: Draft): void {
  let nodes = scopes.get(scope)
  if (!nodes) {
    nodes = new Map()
    scopes.set(scope, nodes)
  }
  nodes.set(nodeId, draft)
}

const pending = new WeakMap<object, Map<string, Promise<void>>>()
export function getPendingDraft(scope: object, nodeId: string): Promise<void> | undefined {
  return pending.get(scope)?.get(nodeId)
}
export function putPendingDraft(scope: object, nodeId: string, promise: Promise<void>): void {
  let nodes = pending.get(scope)
  if (!nodes) { nodes = new Map(); pending.set(scope, nodes) }
  nodes.set(nodeId, promise)
  void promise.finally(() => { if (nodes?.get(nodeId) === promise) nodes.delete(nodeId) })
}
