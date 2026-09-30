/** Narrow public dmn-js contract used by this integration (upstream ships no TS types). */
export type DmnView = { id: string; name?: string; type: string }
export type DmnViewer = {
  on: (event: string, handler: () => void) => void
}
export type DmnInstance = {
  importXML: (xml: string) => Promise<{ warnings: Error[] }>
  saveXML: (options: { format: boolean }) => Promise<{ xml?: string }>
  getViews: () => DmnView[]
  getActiveView: () => DmnView | undefined
  open: (view: DmnView) => Promise<unknown>
  on: (event: string, handler: (event: { viewer: DmnViewer }) => void) => void
  destroy: () => void
}
export type DmnConstructor = new (options: { container: HTMLElement; width: string; height: string }) => DmnInstance
