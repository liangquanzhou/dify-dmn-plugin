import 'i18next'
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common'
    enableSelector: 'optimize'
    keySeparator: false
    resources: { common: Record<string, string>; workflow: Record<string, string> }
  }
}
