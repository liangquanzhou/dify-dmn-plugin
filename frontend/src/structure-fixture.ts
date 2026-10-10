/** Authored synthetic illustration, never a production workflow. */
export const example = {
  schema_version: 'structure-view.v1', example_only: true,
  source_refs: [{ label: 'Independent synthetic example', uri: 'https://example.invalid/inert-source' }],
  workflows: [
    { workflow_id: 'sample.locate', flow_type: 'LOCATE', scope: 'SYNTHETIC / EXAMPLE_FRAGMENT', phases: [
      { phase_id: 'LOCATE', name: '定位问题', steps: [
        { step_id: 'L1', name: '收集与判断', graph: { nodes: [
          { node_id: 'start', name: '开始', kind: 'START', ports: ['READY'] },
          { node_id: 'eligibility', name: '字段矩阵示例', kind: 'DECISION', ports: ['MATCHED', 'WAITING'], model_ref: 'local@1', input_bindings: { amount: { from: { source: 'inputs', path: ['amount'] } } } },
          { node_id: 'finish', name: '继续处理', kind: 'END', ports: [], exit_ref: 'continue' },
        ], edges: [
          { edge_id: 'entry', source: 'start', source_port: 'READY', target: 'eligibility' },
          { edge_id: 'matched', source: 'eligibility', source_port: 'MATCHED', target: 'finish', condition: { note: 'Declared metadata, not evaluated' } },
        ] }, exits: { continue: { class: 'BUSINESS', destination: { kind: 'STEP', phase_id: 'LOCATE', step_id: 'L2' } } } },
        { step_id: 'L2', name: '类型化结果', graph: { nodes: [
          { node_id: 'route', name: '结果模板示例', kind: 'DECISION', ports: ['MATCHED'], model_ref: 'typed@1', input_bindings: { ready: { from: { source: 'inputs', path: ['ready'] } } } },
        ], edges: [] }, exits: { done: { class: 'BUSINESS', destination: { kind: 'END_WORKFLOW', outcome: 'COMPLETE' } } } },
      ] },
    ] },
    { workflow_id: 'sample.solve', flow_type: 'SOLVE', scope: 'SYNTHETIC / EXAMPLE_FRAGMENT', phases: [
      { phase_id: 'P1', steps: [{ step_id: 'S1', name: '诊断定位示例', graph: { nodes: [
        { node_id: 'missing', name: '缺失模型示例', kind: 'DECISION', model_ref: 'not-present', ports: ['WAITING'] },
      ], edges: [] }, exits: {} }] },
    ] },
  ],
  models: {
    'local@1': { profile: 'dmn-local-table-v1', table: { id: '本地表达式矩阵', hit_policy: 'FIRST', rules: [
      { id: '会员或合规高额', when: { any: [{ eq: ['member', true] }, { all: [{ gte: ['amount', 500] }, { eq: ['compliant', true] }] }] }, output: { route: 'priority', fee: 0 } },
      { id: '常规处理', when: true, output: { route: 'standard', fee: 8 } },
    ] } },
    'typed@1': { profile: 'service-decision-table-v1', version: '1', hit_policy: 'UNIQUE', parameters: { ready: { type: 'boolean', record_required: true, nullable: false, allowed_quality: ['KNOWN', 'UNKNOWN'] } },
      rules: [{ rule_id: 'ready-route', when: [{ path: ['ready'], op: 'eq', value: true }], output_template_ref: 'ready' }],
      result_templates: { ready: { state: 'READY', data: { eligible: { literal: true } }, actions: [] }, empty: { state: 'WAITING', data: {}, actions: [] } },
      on_no_match: 'RESULT_TEMPLATE', empty_template_ref: 'empty' },
  },
}
