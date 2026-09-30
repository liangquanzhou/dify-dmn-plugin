# v0.3.0 本地运行时对齐规范

本文件给后续本地实现者一个可执行的对齐目标：同一张 JSON 表、同一份变量，在本地方案与 Dify Tool 中得到相同条件结果、最终选择、等待状态和模型指纹。本次规范、插件与向量均独立构建，示例全部为合成数据；不包含、也不要求上传公司源码或真实规则。

现有方案中的 `phases / steps / rules / when / output` 不需要重构。保留原有编排及存储结构，在实际执行单表的位置增加薄适配层即可。Dify 仍是一个 Tool 节点评估一张表，不是完整流程解释器。本规范不把阶段顺序、步骤之间的数据合并、业务动作或输出执行交给插件。

## 1. 冻结条件协议，新增决策层

[CONTRACT.md](CONTRACT.md) 保留 v0.2.0 的条件算子语义，`plugin/evaluator.py` 保留其原实现。布尔条件、算子结构、三值逻辑、严格类型、原始键/ref、金额转换、constraint_set、追溯和资源边界均不变。v0.3.0 在完整条件求值之后增加选择策略与结果封装；本文件补充新选择/状态语义，不重新定义条件语言。

本地适配层向 Tool 传入：

```json
{
  "table_json": "一张完整表的 JSON 文本",
  "values_json": "扁平变量对象的 JSON 文本",
  "expected_sha256": "可选的已批准模型指纹"
}
```

表对象至少包括非空 `id`、`hit_policy` 与 `rules`；每条规则有唯一非空 `id` 和 `when`。`output`、`载荷`、注释、metadata 和其他扩展字段保持数据语义。可以在表对象内增加：

```json
{"unknown_policy":"strict"}
```

`unknown_policy` 只允许 `compatible`、`strict` 两个大小写敏感字符串；缺省为 `compatible`。显式 `null`、空字符串及其他类型不是缺省，返回 `INVALID_UNKNOWN_POLICY`，路径为 `$.table_json.unknown_policy`。它属于表内容，参与模型指纹；不是独立 Tool 参数，也不能从外部参数覆盖。

## 2. 三值条件与最终选择

每条规则的最终条件只有 `true / false / null`。`null` 表示 UNKNOWN。规则内部出现未知叶子，不代表整条规则一定 UNKNOWN；例如 `all(false, unknown)` 为 false，`any(true, unknown)` 为 true。

先完整校验所有规则，再完整求值所有规则和所有 `all / any` 子条件。FIRST 只限制最终选择数量，不跳过后续规则的校验、求值、错误或追溯。出错时整个调用失败，不输出部分成功，不返回等待或无命中来掩盖错误。

所有规则 ID 数组均保持原始 `rules` 数组顺序，不排序、不去掉仍需诊断的后续规则：

- `condition_matched_rule_ids`：所有最终 condition=true 的规则
- `unknown_rule_ids`：所有最终 condition=null 的规则
- `selected_rule_ids`：本次允许交给后续业务步骤的最终选中规则
- `blocking_unknown_rule_ids`：本次 `decision_status=waiting_input` 的实际未决原因；其他状态为空数组

| 策略 | 已求得条件 | selected_rule_ids | decision_status | blocking_unknown_rule_ids |
|---|---|---|---|---|
| compatible + FIRST | 至少一个 true | 第一条 true | matched | [] |
| compatible + COLLECT | 至少一个 true | 全部 true | matched | [] |
| compatible，任意 hit policy | 没有 true，但有 UNKNOWN | [] | waiting_input | 全部 UNKNOWN |
| strict + FIRST | 第一条 true 前存在 UNKNOWN | [] | waiting_input | 第一条 true 前的全部 UNKNOWN |
| strict + FIRST | 第一条 true 前没有 UNKNOWN | 第一条 true | matched | [] |
| strict + FIRST | 没有 true，但有 UNKNOWN | [] | waiting_input | 全部 UNKNOWN |
| strict + COLLECT | 任意位置存在 UNKNOWN | [] | waiting_input | 全部 UNKNOWN |
| strict + COLLECT | 没有 UNKNOWN，存在 true | 全部 true | matched | [] |
| 任意策略 | 全部 false，或 rules=[] | [] | no_match | [] |

FIRST 中，第一条 true 后面的 UNKNOWN 仍出现在 `unknown_rule_ids` 和 `evaluations`，但不会使 strict 等待。COLLECT 的任何 UNKNOWN 都可能改变最终集合，因此 strict 不输出部分选择。

“等待”表示当前信息不足以完成相应策略的决定。UNKNOWN 也可能来自非法业务金额、未完成的约束集合等情况；不能把每个 UNKNOWN 都自动解释成“仅缺一个变量”。`blocking_unknown_rule_ids` 是规则列表，不是补充变量清单。

### 必须区分的三个例子

1. FIRST `[UNKNOWN, true]`：compatible 选第二条；strict 等待，选中为空，第一条是阻塞原因
2. FIRST `[true, UNKNOWN]`：两种策略均选第一条；第二条的未知保留供诊断
3. COLLECT `[true, UNKNOWN]`：compatible 选第一条；strict 等待，所有 true 仍保留在条件命中字段

## 3. 输出和旧字段兼容

| 字段 | v0.3.0 含义 |
|---|---|
| `result` | 仍严格保持 `{matched, evaluations}` 两键结构；matched 是最终选中的完整原始规则 |
| `result_json` | 上述 result 的 JSON 字符串 |
| `matched` | 与 result.matched 相同的最终选中规则列表 |
| `matched_rule_ids` | 与 selected_rule_ids 相同；不会改成“所有 true” |
| `outputs` | 按选中顺序取每条原规则的 output；缺 output 对应 null，不执行也不合并 |
| `evaluations` | 所有规则的完整 v0.2.0 追溯，含最终 condition |
| `selected_rule_ids` | 最终选择的规则 ID |
| `condition_matched_rule_ids` | 所有最终 condition=true 的规则 ID |
| `all_matches` | 所有最终 condition=true 的完整原始规则，包含 when、output 与扩展字段 |
| `unknown_rule_ids` | 所有最终 condition=null 的规则 ID |
| `blocking_unknown_rule_ids` | 本次等待的实际未决规则 ID |
| `decision_status` | matched / no_match / waiting_input，推荐新工作流以此分支 |
| `status` | 旧字段；compatible 下继续仅有 matched / no_match，strict 显式启用 waiting_input 扩展 |
| `table_version` | 对原始 table_json 文本 UTF-8 字节求 SHA-256；维持旧语义 |
| `model_sha256` | 对完整表的 RFC 8785 规范化 UTF-8 字节求 SHA-256 |
| `decision_result` | 下述固定版本的简洁决策对象 |

compatible 没有 true 但有 UNKNOWN 时：旧 `status=no_match`，新 `decision_status=waiting_input`，选中为空，阻塞 ID 为全部 UNKNOWN。这个差异有意保留旧工作流行为；希望把 UNKNOWN 分流处理的新工作流应读取 `decision_status`。

strict 等待时：`status` 与 `decision_status` 均为 `waiting_input`，`matched / result.matched / outputs / matched_rule_ids / selected_rule_ids` 全部为空；`all_matches / condition_matched_rule_ids` 仍保留已经算出的 true，供解释使用，不表示批准执行。

`decision_result` 严格使用以下字段，不复制完整 raw rules 或 evaluations：

```json
{
  "schema_version": "0.3.0",
  "unknown_policy": "strict",
  "decision_status": "waiting_input",
  "selected_rule_ids": [],
  "condition_matched_rule_ids": ["r2"],
  "unknown_rule_ids": ["r1"],
  "blocking_unknown_rule_ids": ["r1"],
  "model_sha256": "64 个小写十六进制字符"
}
```

结果比较采用 JSON 数据等价，不要求各运行时输出对象的属性顺序相同；数组顺序必须相同。对象的金额标签、ref 形状或 `${...}` 文本在 output 中一律是原始数据。不要把 `all_matches` 当成 FIRST 的最终选择，也不要对输出作自动折扣计算、引用替换、字段合并或去重。

Dify Tool 输出 17 个可绑定变量。末尾标准 JSON 消息保持 v0.2.0 的 9 字段聚合结构（result、result_json、matched、outputs、evaluations、matched_rule_ids、status、table_id、table_version），不重复新诊断字段；读取新字段请绑定独立变量或 `decision_result`。每条完整 SDK 帧仍限 4 MiB，全部帧检查通过后才输出，绝不截断规则或追溯。

## 4. 模型指纹与可选校验

`model_sha256 = lowercase_hex(SHA256(UTF8(JCS(parsed_table))))`。规范化遵循 [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html)：对象键递归按 UTF-16 码元排序，数字按 ECMAScript/IEEE 754 格式化，字符串使用规定的转义，省去多余空白；数组原有顺序保留。字符串不做 Unicode 归一化。

哈希输入是收到并解析的**整个表对象**，包括规则顺序、when、output、载荷、扩展字段、metadata，以及显式提供的 unknown_policy。不插入缺省策略、不丢掉未知扩展字段、不把表压缩成条件集合。values_json 和 Tool 的 expected_sha256 不参与模型哈希。

- 对象键顺序、空白、等价 Unicode 转义与等价数值写法不同，可以产生相同 model_sha256
- 规则数组或任何输出/metadata 数组换序会改变 model_sha256
- 修改输出或 metadata 会改变 model_sha256，即使本次选择结果没有变
- 未写 unknown_policy 与显式写 compatible 的行为相同，但完整模型内容不同，model_sha256 不同
- `é` 和 `e` 加组合重音的字符串不会被合并，模型指纹不同
- table_version 仍哈希原始文本，因此空白与键顺序调整通常会改变 table_version

仍先遵守 v0.2.0 JSON 输入边界：禁止重复键、无效 Unicode、非有限数和超出安全整数范围的整数值。JCS 能表达的其他数据不意味着本 Tool 放宽接收范围；例如 `1e30` 在这里因整数值超出安全范围被拒绝。精确长编号应使用字符串。

独立 Tool 参数 `expected_sha256` 原始文本限 256 字符，可用于锁定批准的表：省略、null 或去掉首尾空白后为空的字符串表示不检查；否则必须是恰好 64 个十六进制字符，接受大小写并忽略首尾空白。格式错误报 `INVALID_INPUT`；与 model_sha256 不匹配报 `HASH_MISMATCH`。二者路径均为 `$.expected_sha256`，失败时无成功输出。

不要把用于锁定的 expected_sha256 写进表 JSON：那只会成为普通模型内容，并参与自身哈希，不会启用 Tool 的独立校验。不要为规避自引用而从表内容中选择性剔除字段。已批准哈希应由调用配置保管；哈希一致证明模型内容一致，不证明模型可信、业务事实正确或具备数字签名。

## 5. 在现有 phases / steps 方案中的接入位置

1. 沿用现有阶段、步骤、规则的存储和执行顺序，在需要决策表的那一步选出对应表。阶段/步骤标识可以保留在本地编排中，也可以作为表 metadata；一旦放入表对象就参与 model_sha256
2. 保留该表的规则 ID、顺序、when、output 与所有扩展字段。Tool 的单表输入不要求公司顶层方案改成新的 schema；适配层负责产生这一个表对象，两个运行时必须使用同一个对象范围
3. 从既有变量环境得到同一份扁平 values 对象。点号是完整键的一部分；不要在本地把 `a.b` 额外解释成嵌套路径，也不要把字符串、布尔值、缺失值或 null 自动转换
4. 按既有条件协议完成全部校验与三值求值，再应用本规范的未知策略。不得通过跳过后续规则来实现 FIRST
5. 用 decision_status 作新分支：matched 执行本地原有 output 消费步骤；waiting_input 进入已有补充输入/校验流程；no_match 进入已有无命中处理。不能因 all_matches 非空而越过 strict 等待
6. 校验模型哈希与固定向量，再在公司授权的本地环境做实际业务验证。此交付没有验证公司部署、真实业务表或当地既有实现；不应据此声称两套生产系统已等价

本地实现不必使用 Python，也不要求复制插件内部架构；需要匹配的是公开输入/输出行为与约束。对未来任何“更自然”的业务修正，应单独版本化条件协议，而不是在对齐时悄悄改变 bool、ref、金额、约束或 UNKNOWN 语义。

### 自动编译模型指纹

已提供独立编译工具，用批准的 Python 3.12 和本项目依赖运行：

```bash
python scripts/compile_table.py examples/table.json --output /tmp/table-node-config.json
```

输出只含两个静态 Tool 参数 `table_json` 与 `expected_sha256`，保留原始表文本且自动计算 JCS 指纹，不执行规则。这不是完整 Dify DSL；现有编译器把这两项映射到原有 Tool 静态配置，`values_json` 继续由上游绑定。本地 JS 编译器可独立实现同样逻辑，先通过固定规范化向量，不能用普通 `JSON.stringify` 加字母排序代替 JCS。

内容锁不是签名：有权限同时修改表和预期 hash 的人仍能更新两者。批准、版本控制和部署权限继续由原系统负责。

## 6. 跨运行时固定向量

[tests/vectors/v030-conformance.json](../tests/vectors/v030-conformance.json) 是纯 JSON，无公司信息。每个 expected 由规则语义手工推导；哈希向量先固定 expected_canonical_json，再对该固定 UTF-8 文本计算 SHA-256。不得使用待测实现重新生成 expected 来“修复”失败。

数据集约定：

- `decision_cases`：table/values 为结构化对象；适配器将它们序列化为 Tool 所需 JSON 文本。expected.conditions 对应每条规则的最终条件，其他 ID/status 字段逐项比较；可选 read_variables、evaluations、selected_rules、all_matches、outputs 也须比较
- `error_cases`：table/values 同上，必须整个调用失败，比较 expected_error.code 与 path，不能有成功消息
- `hash_cases`：table_json 是精确输入字符串，不得先格式化；expected_canonical_json 是精确规范化字符串，expected_sha256 与 expected_table_version 分别对应规范内容与原始文本
- 相同 `equivalence_group` 的哈希必须相同；`hash_inequality_pairs` 指定必须不同的 ID 对
- `pin_cases`：按 table_json、values_json 与 expected_sha256 原样调用，比较 expected 中的输出；涵盖大小写、首尾空白、空值禁用
- `input_error_cases`：parameters 是完整 Tool 参数对象，比较 expected_error.code/path，并确认没有部分成功

除各 case 显式 expected 外，每个成功向量还必须满足：

1. `result` 仅含 matched/evaluations，解析 result_json 后等于 result
2. matched_rule_ids=selected_rule_ids；result.matched=matched；所有 ID 均能对应到原始表内的完整原规则
3. all_matches 恰好对应 condition_matched_rule_ids，matched 恰好对应 selected_rule_ids；outputs 恰好为 selected 原规则的 output，缺字段为 null
4. evaluations 数量及顺序与全部原始规则一致；不改变输入 table、values 或任何原始 payload
5. decision_result 的 schema_version 恰好为 0.3.0，unknown_policy 等于表的有效策略，状态、各 ID 数组与 model_sha256 与对应顶层字段一致，不增加隐式字段
6. model_sha256 是 64 位小写十六进制；table_version 是原始 table_json 文本的 SHA-256。决策 case 的文本序列化可因适配器而异，因此不要跨运行时直接比较其 table_version；hash_cases 已指定精确文本，必须比较

覆盖重点包括：缺失/显式 null 前置规则与兜底、true 后 UNKNOWN、FIRST 优先级、COLLECT 完整性、全部 false/UNKNOWN 与空表、输出原样、bool/ref/discount_share/constraint_set 旧语义、无短路错误，以及 UTF-16 键排序、Unicode 转义/不归一化、数值格式与数组顺序。它们是可复用的最小回归集合，不能替代 CONTRACT.md 的完整条件边界测试或真实环境验证。
