export type Json = null | boolean | number | string | Json[] | {
  [key: string]: Json;
}
export type Rule = {
  id: string;
  when: Json;
  [key: string]: Json;
}
export type Table = {
  id: string;
  hit_policy: 'FIRST' | 'COLLECT' | 'UNIQUE';
  unknown_policy?: 'compatible' | 'strict';
  rules: Rule[];
}
export type Atom = {
  id: string;
  field: string;
  label: string;
}
export type MatrixRow = {
  rule: Rule;
  atoms: Atom[];
  logic: string;
  fullLogic: string;
}
export type OutputColumn = {
  key: string;
  parent: string;
  child?: string;
  label: string;
}
export type Matrix = {
  table: Table;
  fields: string[];
  outputs: OutputColumn[];
  rows: MatrixRow[];
}
export const isRecord = (v: unknown): v is Record<string, Json> => v !== null && typeof v === 'object' && !Array.isArray(v)
export const own = (v: object, k: string) => Object.prototype.hasOwnProperty.call(v, k)
export const literal = (v: Json): string => JSON.stringify(v)
const binary = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'not_contains', 'all_values', 'is_minimum']
const tolerance = ['within', 'below', 'above']
const symbols: Record<string, string> = { eq: '=', ne: '≠', gt: '>', gte: '≥', lt: '<', lte: '≤', contains: '包含', not_contains: '不包含', all_values: '全部值等于', is_minimum: '为最小值于', within: '接近', below: '低于', above: '高于' }
function fail(message: string): never {
  throw new Error(message)
}
function validString(s: string) {
  if (/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(s))
    fail('JSON 含无效 Unicode')
}
// JSON.parse cannot detect duplicate keys. Scan the already syntax-checked source.
function uniqueKeys(raw: string) {
  let p = 0
  const ws = () => {
    while (/\s/.test(raw[p] || '') && p < raw.length)
      p++
  }
  const str = () => {
    const start = p++
    while (p < raw.length) {
      if (raw[p] === '\\')
        p += 2
      else if (raw[p++] === '"')
        break
    }
    return JSON.parse(raw.slice(start, p)) as string
  }
  function visit(depth: number) {
    if (depth > 32)
      fail('JSON 嵌套深度超过 32')
    ws()
    if (raw[p] === '{') {
      p++
      ws()
      const keys = new Set<string>()
      while (raw[p] !== '}') {
        const key = str()
        if (keys.has(key))
          fail('JSON 含重复字段')
        keys.add(key)
        ws()
        p++
        visit(depth + 1)
        ws()
        if (raw[p] === ',') {
          p++
          ws()
        }
        else { break }
      }
      p++
    }
    else if (raw[p] === '[') {
      p++
      ws()
      while (raw[p] !== ']') {
        visit(depth + 1)
        ws()
        if (raw[p] === ',') {
          p++
          ws()
        }
        else { break }
      }
      p++
    }
    else if (raw[p] === '"') {
      str()
    }
    else {
      while (p < raw.length && !/[\s,}\]]/.test(raw[p]))
        p++
    }
  }
  visit(0)
}
function validateExpression(v: Json, depth = 0): void {
  if (depth > 32)
    fail('条件嵌套过深')
  if (typeof v === 'boolean')
    return
  if (!isRecord(v) || Object.keys(v).length !== 1)
    fail('条件必须为布尔值或单一算子')
  const [op, arg] = Object.entries(v)[0]
  if (op === 'all' || op === 'any') {
    if (!Array.isArray(arg))
      fail('all / any 必须为数组')
    arg.forEach(x => validateExpression(x, depth + 1))
    return
  }
  if (op === 'is_unknown' || op === 'is_empty') {
    if (typeof arg !== 'string')
      fail('条件字段必须为字符串')
    return
  }
  if (op === 'constraint_set') {
    if (!isRecord(arg) || Object.keys(arg).sort().join(',') !== 'mode,record' || typeof arg.record !== 'string' || !['satisfied', 'violated'].includes(String(arg.mode)))
      fail('constraint_set 需要 record 与合法 mode')
    return
  }
  if (![...binary, ...tolerance].includes(op))
    fail(`不支持的条件算子：${op}`)
  if (!Array.isArray(arg) || arg.length !== (tolerance.includes(op) ? 3 : 2) || typeof arg[0] !== 'string')
    fail('条件算子参数结构错误')
  if (isRecord(arg[1]) && own(arg[1], 'ref')) {
    if (Object.keys(arg[1]).length !== 1 || typeof arg[1].ref !== 'string' || op === 'all_values')
      fail('变量引用结构错误')
  }
}
export function parseTable(value: unknown): {
  kind: 'empty' | 'error';
  message: string;
} | {
  kind: 'ready';
  matrix: Matrix;
} {
  if (value === undefined || value === null || value === '')
    return { kind: 'empty', message: '尚未配置决策表。在下方原生配置中填写 table_json 后，这里会自动显示矩阵。' }
  try {
    if (typeof value !== 'string')
      fail('table_json 必须是 JSON 字符串')
    if (!value.trim())
      return { kind: 'empty', message: '尚未配置决策表' }
    if (new TextEncoder().encode(value).length > 512 * 1024)
      fail('表格 JSON 超过 512 KiB')
    const t: unknown = JSON.parse(value)
    uniqueKeys(value)
    let count = 0
    function walk(v: unknown) {
      if (++count > 20000)
        fail('JSON 值节点超过 20,000')
      if (typeof v === 'number' && (!Number.isFinite(v) || (Number.isInteger(v) && !Number.isSafeInteger(v))))
        fail('数值超出安全范围')
      if (typeof v === 'string')
        validString(v)
      if (v && typeof v === 'object') {
        if (!Array.isArray(v))
          Object.keys(v).forEach(validString)
        Object.values(v).forEach(walk)
      }
    }
    walk(t)
    if (!isRecord(t) || typeof t.id !== 'string' || !t.id.trim() || !Array.isArray(t.rules))
      fail('需要 id、hit_policy 和 rules 数组')
    if (t.hit_policy !== 'FIRST' && t.hit_policy !== 'COLLECT' && t.hit_policy !== 'UNIQUE')
      fail('仅支持 FIRST / COLLECT / UNIQUE 命中策略')
    if (own(t, 'unknown_policy') && t.unknown_policy !== 'strict' && t.unknown_policy !== 'compatible')
      fail('未知值策略必须为 strict / compatible')
    if (t.rules.length > 1000)
      fail('规则数超过 1,000')
    const ids = new Set<string>()
    t.rules.forEach((r) => {
      if (!isRecord(r) || typeof r.id !== 'string' || !r.id.trim() || !own(r, 'when'))
        fail('每条规则需要唯一 id 和 when')
      if (ids.has(r.id))
        fail('规则 id 重复')
      ids.add(r.id)
      validateExpression(r.when)
    })
    return { kind: 'ready', matrix: buildMatrix(t as unknown as Table) }
  }
  catch (e) {
    if (e instanceof SyntaxError)
      return { kind: 'error', message: 'JSON 格式错误，请检查原生配置' }
    return { kind: 'error', message: e instanceof Error ? e.message : '无法读取决策表' }
  }
}
function operand(v: Json) {
  return isRecord(v) && own(v, 'ref') ? `引用(${literal(v.ref)})` : literal(v)
}
function describe(op: string, arg: Json): {
  field: string;
  label: string;
} {
  if (op === 'constraint_set') {
    const a = arg as Record<string, Json>
    return { field: a.record as string, label: `约束集 ${a.mode === 'satisfied' ? '满足' : '违反'}` }
  }
  if (op === 'is_unknown' || op === 'is_empty')
    return { field: arg as string, label: op === 'is_unknown' ? '未知 / null' : '为空' }
  const a = arg as Json[]
  const toleranceLabel = tolerance.includes(op) ? `（容差 ${literal(a[2])}）` : ''
  return { field: a[0] as string, label: `${symbols[op]} ${operand(a[1])}${toleranceLabel}` }
}
export function buildMatrix(table: Table): Matrix {
  const fields: string[] = []
  const outputs: OutputColumn[] = []
  const outputKeys = new Set<string>()
  const addOutput = (parent: string, child?: string) => {
    const key = JSON.stringify([parent, child ?? null])
    if (!outputKeys.has(key)) {
      outputKeys.add(key)
      outputs.push({ key, parent, child, label: child !== undefined ? `$[${JSON.stringify(parent)}][${JSON.stringify(child)}]` : `$[${JSON.stringify(parent)}]` })
    }
  }
  const rows = table.rules.map((rule) => {
    const atoms: Atom[] = []
    const visit = (v: Json, full: boolean): string => {
      if (typeof v === 'boolean')
        return v ? '始终成立' : '始终不成立'
      const [op, arg] = Object.entries(v as Record<string, Json>)[0]
      if (op === 'all' || op === 'any') {
        const a = arg as Json[]
        if (!a.length)
          return op === 'all' ? '始终成立' : '始终不成立'
        return `(${a.map(x => visit(x, full)).join(op === 'all' ? ' 且 ' : ' 或 ')})`
      }
      const d = describe(op, arg)
      if (full)
        return `${literal(d.field)} ${d.label}`
      const id = String.fromCharCode(65 + atoms.length % 26) + (atoms.length >= 26 ? String(Math.floor(atoms.length / 26)) : '')
      atoms.push({ id, ...d })
      if (!fields.includes(d.field))
        fields.push(d.field)
      return id
    }
    const logic = visit(rule.when, false)
    const fullLogic = visit(rule.when, true)
    Object.entries(rule).forEach(([parent, value]) => {
      if (parent === 'id' || parent === 'when')
        return
      if (isRecord(value) && Object.keys(value).length)
        Object.keys(value).forEach(child => addOutput(parent, child))
      else
        addOutput(parent)
    })
    return { rule, atoms, logic, fullLogic }
  })
  return { table, fields, outputs, rows }
}
export function outputValue(rule: Rule, column: OutputColumn): {
  present: boolean;
  value?: Json;
  expanded?: boolean;
} {
  if (!own(rule, column.parent))
    return { present: false }
  const v = rule[column.parent]
  if (column.child === undefined) {
    if (isRecord(v) && Object.keys(v).length)
      return { present: true, expanded: true }
    return { present: true, value: v }
  }
  return isRecord(v) && own(v, column.child) ? { present: true, value: v[column.child] } : { present: false }
}
