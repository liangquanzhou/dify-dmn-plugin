export const first = {
  id: '订单履约路由', hit_policy: 'FIRST', unknown_policy: 'compatible',
  rules: [
    { id: '华北 · 优先配送', when: { all: [{ eq: ['地区', '华北'] }, { gte: ['订单金额', 500] }, { eq: ['会员', true] }] }, output: { 配送方式: '次日达', 运费: 0, 人工审核: false } },
    { id: '华北 · 标准配送', when: { eq: ['地区', '华北'] }, output: { 配送方式: '标准配送', 运费: 12, 人工审核: false } },
    { id: '高额订单 · 审核', when: { gte: ['订单金额', 2000] }, output: { 配送方式: '待审核', 运费: null, 人工审核: true } },
    { id: '其他订单', when: true, output: { 配送方式: '标准配送', 运费: 18, 人工审核: false } },
  ],
}
export const collect = {
  id: '复合条件审查', hit_policy: 'COLLECT', unknown_policy: 'strict',
  rules: [
    { id: '区域或高分合规', when: { any: [{ eq: ['region', 'north'] }, { all: [{ gte: ['score', 80] }, { constraint_set: { record: 'checks', mode: 'satisfied' } }] }] }, output: { route: 'review', priority: 0, audit: false } },
    { id: '分数范围', when: { all: [{ gte: ['score', 60] }, { lt: ['score', 90] }] }, output: { route: 'quality', audit: true } },
    { id: '未知分数', when: { is_unknown: 'score' }, output: { route: null, note: '' } },
    { id: '总是保留审计', when: true, output: { audit: true } },
    { id: '已停用', when: { any: [] }, output: false },
  ],
}
export const edge = {
  id: '空值与原始输出', hit_policy: 'COLLECT',
  rules: [
    { id: '未提供输出', when: true }, { id: '空对象', when: { all: [] }, output: {} },
    { id: 'null', when: true, output: null }, { id: 'false', when: true, output: false },
    { id: 'zero', when: true, output: 0 }, { id: 'empty string', when: true, output: '' },
    { id: 'literal keys', when: { eq: ['a.b', 0] }, output: { 'a.b': 0, a: { b: false } }, 载荷: { retained: true } },
  ],
}
export const unique = {
  id: '唯一配送方式', hit_policy: 'UNIQUE', unknown_policy: 'compatible',
  rules: [
    { id: '免运费', when: { gte: ['订单金额', 500] }, output: { 配送方式: '快递', 运费: 0 } },
    { id: '标准运费', when: { lt: ['订单金额', 500] }, output: { 配送方式: '快递', 运费: 12 } },
    { id: '门店自提', when: { eq: ['自提', true] }, output: { 配送方式: '自提', 运费: 0 } },
  ],
}
