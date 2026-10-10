import { describe, expect, it } from 'vitest'
import { counts, diagnostics, LIMITS, localTable, matches, parseStructure } from '../src/structure-model'
import { example } from '../src/structure-fixture'
const fixture = () => JSON.parse(JSON.stringify(example))
const parse = (v: unknown) => parseStructure(JSON.stringify(v))
describe('explicit read-only structure projection', () => {
  it('accepts authored display envelope without execution validation', () => {
    const b = parse(fixture()); expect(counts(b)).toEqual({ workflows: 2, phases: 2, steps: 3, nodes: 5, edges: 2 })
    expect(b.workflows[0].phases[0].steps[0].graph.nodes.map(n => n.node_id)).toEqual(['start', 'eligibility', 'finish'])
  })
  it('accepts public architecture root without silently adding fields', () => { const b = fixture(); b.schema_version = 'service-decision-dsl.node-architecture.v2'; expect(parse(b)).toEqual(b) })
  it.each(['json-plan-v1', 'structure-view.v2', '', 'xml'])('rejects unsupported root %s', schema_version => { const b = fixture(); b.schema_version = schema_version; expect(() => parse(b)).toThrow('仅接受') })
  it('never synthesizes Phase or Step', () => { const b = fixture(); delete b.workflows[0].phases; expect(() => parse(b)).toThrow('不推断层级') })
  it.each(['workflow', 'phase', 'step', 'node', 'edge'])('rejects duplicate %s IDs in their own scope', scope => {
    const b = fixture(); const w = b.workflows[0]; const p = w.phases[0]; const s = p.steps[0]
    const array = scope === 'workflow' ? b.workflows : scope === 'phase' ? w.phases : scope === 'step' ? p.steps : scope === 'node' ? s.graph.nodes : s.graph.edges
    array.push(structuredClone(array[0])); expect(() => parse(b)).toThrow('重复')
  })
  it('allows repeated scoped IDs in different explicit parents', () => { const b = fixture(); b.workflows[1].phases[0].steps[0].step_id = 'L1'; b.workflows[1].phases[0].steps[0].graph.nodes[0].node_id = 'start'; expect(() => parse(b)).not.toThrow() })
  it.each(['source', 'target'])('rejects dangling %s edge', field => { const b = fixture(); b.workflows[0].phases[0].steps[0].graph.edges[0][field] = 'absent'; expect(() => parse(b)).toThrow('悬空') })
  it('allows explicit cross-step exits and diagnoses unresolved destinations', () => { const b = fixture(); expect(diagnostics(parse(b)).some(d => d.code === 'MISSING_EXIT_TARGET')).toBe(false); b.workflows[0].phases[0].steps[0].exits.continue.destination.step_id = 'missing'; expect(diagnostics(parse(b)).some(d => d.code === 'MISSING_EXIT_TARGET')).toBe(true) })
  it('diagnoses missing model with complete location', () => { const d = diagnostics(parse(fixture())).find(d => d.code === 'MISSING_MODEL')!; expect(d.location.workflow.workflow_id).toBe('sample.solve'); expect(d.location.node!.node_id).toBe('missing') })
  it('diagnoses absent policies and missing templates without inline fallback', () => { const b = fixture(); delete b.models['typed@1'].hit_policy; b.models['typed@1'].rules[0].output_template_ref = 'absent'; b.models['typed@1'].rules[0].output = { state: 'do-not-use' }; const codes = diagnostics(parse(b)).map(d => d.code); expect(codes).toContain('MISSING_HIT_POLICY'); expect(codes).toContain('MISSING_TEMPLATE') })
  it('diagnoses unknown profiles, malformed bindings, missing binding node and ports', () => {
    const b = fixture(); const n = b.workflows[0].phases[0].steps[0].graph.nodes[1]; b.models['local@1'].profile = 'unknown'
    n.input_bindings = { one: { literal: 1, from: { source: 'node', path: [] } }, two: { from: { source: 'node', path: [], node_id: 'absent' } }, three: { from: { source: 'http', path: 'x' } } }; n.ports = []
    const codes = diagnostics(parse(b)).map(d => d.code); expect(codes).toContain('UNSUPPORTED_PROFILE'); expect(codes).toContain('INVALID_BINDING'); expect(codes).toContain('MISSING_BINDING_NODE'); expect(codes).toContain('UNDECLARED_PORT')
  })
  it('searches referenced rule IDs and declared names', () => { const b = parse(fixture()); const workflow = b.workflows[0]; const phase = workflow.phases[0]; const step = phase.steps[1]; const node = step.graph.nodes[0]; expect(matches(b, { workflow, phase, step, node }, 'ready-route')).toBe(true); expect(matches(b, { workflow, phase, step, node }, 'absent')).toBe(false) })
  it('searches local rule IDs and de-duplicates shared model diagnostics', () => { const b = fixture(); const w = b.workflows[0]; const p = w.phases[0]; const st = p.steps[0]; const node = st.graph.nodes[1]; const parsed = parse(b); expect(matches(parsed, { workflow: w, phase: p, step: st, node }, '会员或合规高额')).toBe(true); b.models['local@1'].profile = 'unsupported'; st.graph.nodes.push({ ...node, node_id: 'duplicate-model-reference' }); expect(diagnostics(parse(b)).filter(d => d.code === 'UNSUPPORTED_PROFILE')).toHaveLength(1) })
  it.each(['workflow', 'phase', 'step', 'node'])('normalizes untrusted optional %s names before search', level => { const b = fixture(); const workflow = b.workflows[0]; const phase = workflow.phases[0]; const step = phase.steps[0]; const node = step.graph.nodes[1]; ({ workflow, phase, step, node }[level] as any).name = { toString: null, valueOf: null }; const parsed = parse(b); const w = parsed.workflows[0]; const p = w.phases[0]; const st = p.steps[0]; const n = st.graph.nodes[1]; expect(matches(parsed, { workflow: w, phase: p, step: st, node: n }, 'eligibility')).toBe(true); expect(matches(parsed, { workflow: w, phase: p, step: st, node: n }, 'not-present-in-this-node')).toBe(false) })
  it('reuses local matrix only with explicit profile', () => { const b = fixture(); expect(localTable(b.models['local@1']).value).toContain('会员或合规高额'); expect(localTable(b.models['typed@1']).value).toBeUndefined() })
  it('keeps unknown fields, inert URLs, and JavaScript object keys as data', () => { const b = fixture(); b.source_refs = ['https://example.invalid/no-request']; b.models = JSON.parse('{"__proto__":{"profile":"other","rules":[]}}'); const parsed = parse(b); expect(Object.hasOwn(parsed.models, '__proto__')).toBe(true); expect(parsed.source_refs).toEqual(b.source_refs) })
  it('uses documented browser JSON.parse duplicate-key behavior', () => { const b = JSON.stringify(fixture()).replace('"example_only":true', '"example_only":false,"example_only":true'); expect(parseStructure(b).example_only).toBe(true) })
  it('enforces the UTF-8 budget', () => { const b = fixture(); b.extra = '汉'.repeat(LIMITS.bytes / 3); expect(() => parse(b)).toThrow('2 MiB') })
  it('rejects depth and value budgets without recursive traversal', () => { const b = fixture(); let x: any = b; for (let n = 0; n < 42; n++) { x.extra = {}; x = x.extra } expect(() => parse(b)).toThrow('深度'); const c = fixture(); c.extra = Array(60001).fill(0); expect(() => parse(c)).toThrow('60,000') })
  it('enforces workflow and node and edge limits', () => {
    const b = fixture(); b.workflows = Array.from({ length: 31 }, (_, i) => ({ ...b.workflows[0], workflow_id: `w${i}` })); expect(() => parse(b)).toThrow('1–30')
    const c = fixture(); c.workflows[0].phases[0].steps[0].graph.nodes = Array.from({ length: 601 }, (_, i) => ({ node_id: `n${i}`, kind: 'START' })); expect(() => parse(c)).toThrow('600 nodes')
    const d = fixture(); d.workflows[0].phases[0].steps[0].graph.edges = Array.from({ length: 1801 }, (_, i) => ({ edge_id: `e${i}`, source: 'start', source_port: 'READY', target: 'finish' })); expect(() => parse(d)).toThrow('1,800 edges')
  })
  it('rejects non-finite numeric parsing', () => { const b = JSON.stringify(fixture()).replace('"example_only":true', '"example_only":true,"number":1e999'); expect(() => parseStructure(b)).toThrow('有限') })
})
