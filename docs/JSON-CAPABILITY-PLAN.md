# 内置 JSON 能力覆盖实施计划

日期：2026-10-09。目标：独立实现对方最新内置 JSON 路线的能力覆盖，保留我们的表达式、解释追溯和字段矩阵优势。UNIQUE 是第一阶段，不等于已完成超集。

## 固定基线与范围

- 我们：`liangquanzhou/dify-dmn-plugin`，v0.4.1，`3e3eca1157f713380a678478bfe218d31ec3056a`
- 对方：`binhuhu/dify_dmn_plugin`，main `561a15efa2a086c93373dc7fbd3fbf88e46a48c4`，声明 v0.4.0-rc5
- 当前覆盖目标：内置包 `hu8627/dmn_json` 的五个工具及只读 Endpoint 查看器
- 业务规则以接入方批准的既有框架与业务验收用例为准；公开 SYNTHETIC 示例不能替换业务真值
- 优先复用接入方现有的规则生成、阶段映射、测试及薄运行层；本计划不要求另造一套通用流程引擎
- 对方固定 main 无 LICENSE；发布记录说明双许可草案尚未合入。参考公开设计、独立编写实现和测试，不复制源码或直接纳入依赖
- 本计划基于静态源码、schema 和说明核对；没有执行对方代码。下面未勾选的项目均是验收目标，不是完成声明

## 保持原有语义并显式增加新 profile

### 现有单表 profile

必须保留：扁平键精确取值、缺失/null 为 UNKNOWN、JavaScript 风格容器身份相等、数值序比较、嵌套 `all/any`、右侧 `ref`、金额与约束算子、原始规则载荷、完整条件追溯、17 个 Dify 绑定变量。

FIRST/COLLECT 的 `unknown_policy=compatible` 默认行为不变，`strict` 显式阻断影响选择的 UNKNOWN。非法模型/输入仍令 Tool 失败，不伪装成无命中。

现有上限包括模型 512 KiB、输入 256 KiB、JSON 深度 32、1000 条规则、结果/输出帧 4 MiB。新兼容 profile 应单独定义预算，不能因共用解析器而无意拒绝对方契约原本接受的输入。

### UNIQUE 增量契约

UNIQUE 必须检查整张表，不能在第一条 TRUE 后停下，也不能将多条同输出命中当作唯一命中。

| 确定 TRUE 数 | UNKNOWN 数 | 结果 | 可选中业务规则 |
| --- | --- | --- | --- |
| 0 | 0 | `no_match` | 无 |
| 1 | 0 | `matched` | 唯一 TRUE |
| 0 或 1 | 大于 0 | `waiting_input` | 无 |
| 大于等于 2 | 任意 | `conflict` | 无 |

冲突优先于 UNKNOWN；保留全部确定命中与未知证据，清空选中规则和由选中规则派生的业务结果。`compatible` 不能放松 UNIQUE 的唯一性证明要求；旧 FIRST/COLLECT 不因此改变。冲突是可分支的决策状态，语法/类型错误仍是技术失败。该输出映射属于我们的增量契约；对方 typed 契约中的 `FAILED/UNIQUE_HIT_CONFLICT` 由兼容层另行投影。

### 两类新增 profile

1. 简单表兼容 profile：支持 `json-table-v1` 的对象路径、缺失/null 区分、深相等、字符串序比较、9 个比较算子及保守 UNKNOWN。不能用旧默认语义进行无损转换的情况，应由显式 profile 处理；实现前只能明确拒绝，不能悄悄变义，也不能将拒绝计作已覆盖
2. 类型化节点 profile：显式参数类型、quality、来源、时效、绑定与结果模板。已知 null 和 UNKNOWN 分开。执行状态、业务状态与动作意图分开。定义摘要只绑定内容，不能作为授权证明

profile 名称、工具入口和版本号在实现时确认；这里的分类不表示已经有相应公共 API。

## 五工具与查看器覆盖清单

### C1 简单表 evaluate_json_table

- [ ] 输入支持对象和单层 JSON 对象字符串；固定表及可选 RFC8785 摘要
- [ ] `path` 按对象键数组逐层读取，不把点号当路径，不把数组索引当对象路径
- [ ] `eq/ne/lt/lte/gt/gte/in/exists/is_null`；布尔与数字不同，JSON 深相等，字符串按 Unicode 码点排序
- [ ] FIRST/COLLECT、行内 AND、空条件为 TRUE；FALSE 优先于 UNKNOWN
- [ ] FIRST 前置 UNKNOWN 阻断、后置 UNKNOWN 仅追溯；COLLECT 任意 UNKNOWN 阻断
- [ ] 无命中、命中输出 null、失败明确区分；完整规则/条件轨迹与统一结果 envelope
- [ ] 对应 profile 的重复键、危险键、数值、深度、大小及结果上限测试

### C2 类型化决策 evaluate_decision

- [ ] 固定 definition bundle、node_ref、expected digest；动态输入和执行上下文分开
- [ ] type、record_required、nullable、allowed_quality；KNOWN/UNKNOWN/NOT_APPLICABLE/CONFLICT
- [ ] 校验快照的节点、主体、定义摘要、as_of、source_refs 和观察时间；禁止用 UNKNOWN 掩盖错误类型
- [ ] UNIQUE/FIRST/COLLECT、明确无命中模板、完整匹配诊断
- [ ] state/data/actions 归约：相同事实去重，冲突事实/状态/意图参数/控制路线拒绝；先归约 data 再绑定意图
- [ ] 所选意图目标与实际控制路径一致；未命中行不能补足缺失动作
- [ ] NodeResult 技术状态、端口、diagnostics、trace；失败清空便利业务输出，防止沿用上次成功
- [ ] 固定图/引用/端口与模型校验。结构验证不等于激活图；纯决策不联网、不导航、不执行动作
- [ ] 来源认证、在线权限、激活与最大年龄由可信宿主验证；调用者自报 source_refs/hash 不授予权限；旧快照复用必须重新核验

### C3 受控查询 execute_query

- [ ] 单个固定只读 capability，静态部署注册；LLM 参数不能提供 URL、代码、模块、动态 headers 或凭据
- [ ] 输入输出 schema、主体、当前激活和所选 QUERY 意图校验；缺连接/缺授权在 IO 前阻断
- [ ] 定义、查询计划与操作注册表资产锁；禁止签名有效就绕过在线授权
- [ ] 多 API 技术依赖、批量、游标分页；时间、调用数、页数和响应大小共同有界
- [ ] 来源、观察时间/最大年龄、事实冲突、部分结果和可选输出 UNKNOWN；没有模拟成功回退
- [ ] SSRF、代理、重定向、取消与超限防护；默认不自动重试可能产生不明状态的外部调用

对方默认 SDK 配置加载器只放行 literal loopback SYNTHETIC；真实读取需要可信宿主 Python `QueryDeployment`。我们的薄查询适配层应接现有接口，不把演示通道当生产连接，也不强迫业务接口迁就对方的具体传输实现。

### C4 模拟查询 query_local

- [ ] 工单、订单两类固定 fixture，FOUND/NOT_FOUND/UNKNOWN/TIMEOUT/ERROR
- [ ] 明确 SYNTHETIC provenance，与真实查询入口及结果标识隔离
- [ ] 作为现有测试体系的独立适配器，不当作生产数据来源

### C5 轻量计划 execute_json_plan

- [ ] LOCATE 或 P1–P5、依赖排序、跨阶段依赖限制、重复/缺失/循环引用拒绝
- [ ] 固定模型摘要与 hit policy，literal / inputs / 前序步骤结果绑定
- [ ] 缺输入、缺输出、失败和 UNKNOWN 阻断；`terminate_when` 提前结束；后续 SKIPPED/BLOCKED 正确
- [ ] 逐步及逐阶段状态、结果投影、请求摘要和响应预算
- [ ] SYNTHETIC/ADVISORY_ONLY 身份始终可见

先由已有 Dify/controller 映射并验证等效行为。需要原样接收旧 `json-plan-v1` 请求时，再提供薄兼容入口。只有 Dify 等效流程而没有该入口时，不宣称五工具调用契约兼容；也不能将“没有实现入口”写作已经完全覆盖包内功能。

### C6 只读查看器

- [ ] 显式 Phase → Step → Node，目录搜索、控制边/端口、跨 Step 出口、来源/绑定/模板与定位诊断
- [ ] 复用我们的逐字段矩阵作为节点详情；保留 AND/OR 括号和大表展开/分页
- [ ] 明确显示导入源、实际数量、缺模型/模板/策略诊断；无静默省略和隐式推断 Phase/Step
- [ ] 独立 Endpoint 与离线查看；本地导入仅在浏览器内存，不上传、不执行、不持久化
- [ ] 规模限制、无效导入保留原视图、焦点恢复、移动端、CSP/无外联、资源 allowlist

对方查看器接受 architecture.v2 或 display-only structure-view.v1，不直接接受旧 json-plan 或 XML。展示合法不能证明执行合法。我们节点内字段矩阵仍需 Dify web 补丁，独立查看入口不会消除该安装要求。

## 模块职责

- 决策内核：纯条件求值、选择策略和诊断；复用安全 JSON、摘要等共用设施，语义差异由显式 profile 隔离
- 节点契约层：类型化快照、固定绑定、结果模板/归约、NodeResult 与既有 17 输出之间的显式投影
- 查询适配层：固定只读能力、schema/预算/来源、可信授权；一次调用只负责一个能力
- 现有 Dify/controller：节点先后、分支、状态传递、动作派发、等待和恢复的宿主职责；逐项验证已有覆盖，不默认 Dify 已提供全部保证
- 可选兼容适配器：旧简单表/plan 输入契约和输出投影；不能把不等价转换隐藏在适配器内
- 查看器：只读定义投影与诊断，既不解释流程也不授予执行权

## 里程碑和验收出口

### M1 UNIQUE 与基线不退化

- 穷举小规模 TRUE/FALSE/UNKNOWN 组合及排列；覆盖空表、零/一/多命中、同输出多命中、TRUE 前后 UNKNOWN、冲突伴随 UNKNOWN
- 验证 compatible/strict 对 UNIQUE 一致保守；冲突/等待无选中业务输出，保留完整证据
- 运行现有本地对齐、GoldenCase、SDK、前端矩阵、独立/离线查看测试；FIRST/COLLECT 与 17 输出回归无变化
- 更新公共契约与使用说明，并验证 Dify 对 `conflict` 的分支绑定；未完成宿主验证时单列未验收

### M2 profile 与类型化合同

- 独立编写简单表公开契约向量：missing/null、true/1、1/1.0、深对象/数组、字符串顺序、路径、空 AND、FIRST 前后 UNKNOWN、COLLECT 未知、命中 null、摘要变更
- 类型化向量：必需记录缺失、nullable/quality 组合、错类型、错主体/节点/摘要/as_of、未来/过期数据、伪来源/未认证复用、无命中模板、归约冲突和路径意图不一致
- 校验成功→失败连续调用不会残留 state/data/actions；旧 profile 的数据仍按旧语义执行
- 兼容性按公开字段、状态、错误码、结果与匹配选择判定，不用展示文案相同冒充行为等价

### M3 查询和已有编排接线

- 模拟查询所有出口；受控查询的无连接/未授权/错资产锁必须在 IO 前拒绝
- 分页耗尽、循环 cursor、批量边界、依赖缺口、超时、取消、部分结果、来源冲突、过期响应与 SSRF 负向用例
- 在隔离 Dify 1.11.1 验证 Start → Query → Decision → 分支 → End，包含所有失败/等待出口；保证状态不被当作成功数据
- 用现有映射完成 LOCATE/P1–P5 计划语义等效测试；需调用契约兼容时补旧请求入口验收
- 真实业务 API 与生产在线授权另有独立验收记录，SYNTHETIC 测试不能代替

### M4 查看器和发布覆盖证明

- 多 workflow、跨 Step 出口、复杂条件矩阵、缺引用、重复 ID、悬空边、超限/损坏导入、大表、缩放/搜索/返回焦点、移动端和无外联验证
- 将 C1–C6 每项关联到实现、测试和证据；明确区分“通过”“失败”“未运行”
- 用真实 SDK/官方包流程和隔离目标宿主验证新版本；保留旧绑定升级回归、可回退产物和包摘要
- 只有 C1–C6 能力验证完整后，才使用“最新内置 JSON 路线功能超集”；“直接兼容原五工具调用”需额外验证输入输出契约，不能互换两种表述
- 对方固定 profile 接受、我们仍拒绝或改变业务结果的用例属于未覆盖项。更丰富的其他功能、更多测试数量或更强安全限制不能抵消这一缺口

## 单列的可选范围

### 包外参考宿主

对方另有 ReferenceRuntime：EXCLUSIVE、成对嵌套 PARALLEL/ALL_SUCCESS、WAIT 先登记再发送、事件/超时/取消单胜者、去重、SQLite 检查点、恢复、REENTER，以及未知 in-flight 交互不自动重发。逻辑并行不等于并行吞吐，也不保证外部 exactly-once。

本计划不声称已覆盖这些保证。若后续要称整个仓库的运行能力超集，先在现有宿主上建立等效验收矩阵：重复/晚到/错主体/旧轮次事件、重启恢复、并行失败收敛、重入次数耗尽、不明发送对账。先补实际缺口，不默认新增一套 runtime。

### 旧外部 XML 和 FEEL

旧 `hu8627/dmn` 是独立外部 Node 服务路线，包含 DMN XML、同文档 DRG、literalExpression、FEEL 类型和 COLLECT 聚合等。本计划不覆盖，不能宣称整个仓库或完整 DMN/FEEL 超集。若未来有真实导入/互操作需要，再作为独立 profile 或服务集成评估。

## 固定证据链接

- [我们的单表契约](https://github.com/liangquanzhou/dify-dmn-plugin/blob/3e3eca1157f713380a678478bfe218d31ec3056a/docs/CONTRACT.md)
- [对方五工具注册](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/builtin/provider.yaml)
- [简单表](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/plugin/dmn_client/json_table.py)
- [类型化决策](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/plugin/dmn_client/decision_executor.py)
- [节点合同](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/plugin/dmn_client/node_contract.py)
- [查询](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/plugin/dmn_client/query_executor.py)
- [模拟查询与计划](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/plugin/dmn_client/local_plan.py)
- [查看器合同](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/structure-viewer.md)
- [包外宿主](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/adapters/host/README.md)
- [旧 XML 和 FEEL 支持范围](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/support-matrix.md)
- [RC5 验收和许可边界](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/releases/v0.4.0-rc5.md)
