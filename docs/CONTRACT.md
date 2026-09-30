# 单表 JSON 协议 v0.2.0

本协议是自定义决策表条件协议，不是 DMN、FEEL 或 JavaScript。求值器没有 `eval`、脚本、通用 `not`、模板展开、外部引用、任意函数或 IO。示例全部为合成数据。

## 表和变量

`table_json` 必须为一个对象的 JSON 字符串，含：

```json
{"id":"example","hit_policy":"FIRST","rules":[{"id":"r1","when":{"eq":["kind","demo"]},"output":{"selected":true}}]}
```

- `id` 与每条规则的 `id` 必须为非空字符串；规则 id 在表内唯一
- `hit_policy` 只允许 `FIRST` 和 `COLLECT`。`RULE_ORDER` 明确报错，不隐式映射
- `rules` 必须是数组，允许空数组；每条规则必须有 `when`
- 每个条件为布尔值，或**恰好一个**已知算子的对象；多算子、未知算子、错误元数和错误引用结构一律报错
- 所有规则先完整校验、再按数组顺序求值；`all` / `any` 的所有子条件也都求值，不以真假短路跳过后续错误
- FIRST 选第一条 condition 为 true 的规则，COLLECT 选全部 true 规则，顺序不变
- 无命中返回空 matched，保留全部 evaluations；错误不转成无命中
- `output`、`载荷` 及其他规则字段只是数据，完整保留，不执行、不替换引用、不自动合并

`values_json` 必须为扁平键对象的 JSON 字符串。键可含点号或为空字符串，均按完整键精确读取，不解析嵌套对象。`{"ref":"another.key"}` 仅在支持引用的右操作数位置读取另一个变量。引用对象必须仅有 `ref` 一个字段且值为字符串。

## 三值逻辑与严格类型

缺失键和 `null` 通常表示 unknown，结果使用 JSON `null`，不同于 false。布尔 true 不等于数字 1；字符串 "1" 不等于数字 1。数字与数字按 JavaScript Number 语义比较；不把字符串转数字，不深比较数组/对象。两个不同对象即使内容相同也不严格相等；同一个值被左右引用时可按对象身份相等。

`all`：有 false 即 false；否则有 unknown 即 unknown；其余为 true。空数组为 true。

`any`：有 true 即 true；否则有 unknown 即 unknown；其余为 false。空数组为 false。

## 条件算子

| 结构 | 语义 |
|---|---|
| `true` / `false` | 常量 |
| `{"all":[条件,...]}` / `{"any":[条件,...]}` | 上述三值逻辑，所有子条件均求值 |
| `{"eq":[键,值或ref]}` / `ne` | 双方先作金额操作数转换；缺失/null 优先返回 unknown；否则严格相等/不等 |
| `{"gt":[键,值或ref]}` / `gte` / `lt` / `lte` | 同样先转换并检查缺失/null；其余必须为数字，错误类型报错 |
| `{"is_unknown":键}` | 缺失或 null 为 true，其他为 false；不转换金额对象 |
| `{"is_empty":键}` | 缺失/null 为 unknown；空数组/空字符串为 true，非空为 false；其他类型报错 |
| `{"contains":[键,值或ref]}` / `not_contains` | 缺失/null 优先 unknown；左值必须为数组，否则报错。转换元素和目标中的金额对象，再严格比较；不深比较。不丢弃 null 元素。空数组分别为 false/true |
| `{"all_values":[键,原始字面量]}` | 左非数组或空数组为 unknown；否则所有项与右字面量严格相等。不转换金额，不解释引用。`[null]` 对 null 为 true |
| `{"is_minimum":[键,数组或ref]}` | 转换左右金额操作数及数组元素；左必须数字，右为非空数字数组，任意非法/未知项使整个条件 unknown；严格判断左等于最小值 |
| `{"within":[键,值或ref,容差]}` | `abs(左-右) <= 容差` |
| `{"below":[键,值或ref,容差]}` | `左 < 右-容差`，严格边界 |
| `{"above":[键,值或ref,容差]}` | `左 > 右+容差`，严格边界 |

后三项先转换左右金额操作数。容差必须为有限非负数值字面量，不能省略、没有默认值、不解析 ref。操作数或容差的业务类型/数值非法时为 unknown。结构元数错误仍为错误。

**明确收紧**：旧 `all_values` 对右 ref 的执行和追溯存在不一致，本版直接拒绝 ref 对象，不臆造新引用语义。其他原始 JSON 字面量按严格相等处理。

## discount_share 金额操作数

仅识别带 `operator:"discount_share"` 的对象，其他对象保持原样。这是某些算子的金额操作数转换器，不是 `when` 的独立算子。

```json
{"operator":"discount_share","base_fen":125,"pay_percent":50,"rounding":"half_up_fen"}
```

- `base_fen` 是 0 至 2^53−1 的安全整数分，`pay_percent` 是 0 至 100 的整数
- 计算**减免分** `base_fen * (100 - pay_percent) / 100`，不是实际支付分
- 若结果本来为整数分直接返回，无须 rounding
- 若有小数分，仅显式 `rounding:"half_up_fen"` 时按分四舍五入，否则 unknown
- 缺字段、类型或范围错误均 unknown；实现使用整数运算避免浮点中间值偏差
- `all_values`、`constraint_set` 行、`is_unknown`、`is_empty` 及输出数据不执行该转换

## constraint_set 记录

条件结构：

```json
{"constraint_set":{"record":"constraints","mode":"satisfied"}}
```

mode 只允许 `satisfied` / `violated`，追溯只记录 `constraints` 键。记录从 values 读取，为：

```json
{
  "scope_bound":true,
  "logical_role":"necessary_conjunction",
  "applicable_condition_set_complete":true,
  "explicitly_unrestricted":false,
  "conditions":[{"status":"known","left":5,"operator":"gte","right":3}]
}
```

- 缺记录、不是对象、scope_bound 不为 true 或 logical_role 不符时 unknown
- conditions 非数组按空数组；explicitly_unrestricted 为 true 却有条件时 unknown
- platform_asserted_violation 为 true 仅在 conditions 为空时有效：violated=true、satisfied=false，不要求 complete
- 行 status 若是 JS 真值且不等于 "known"，该行 unknown；left/right 缺失或 null 也 unknown
- 行 `eq/ne` 要求同类 string/number/bool，严格比较；序比较要求有限数
- 行 `in/not_in` 要求左为上述标量、右为非空且所有成员与左同类的数组
- 行 `between` 要求左及右两项为有限数，`lower_inclusive` / `upper_inclusive` 必须显式布尔
- 行的非法算子/类型返回 unknown，不抛顶层语法错误；行不解释 ref，不转换 discount_share
- 任意行 false：satisfied=false、violated=true
- 非空全 true 且 complete=true：satisfied=true、violated=false
- 无 false 但存在 unknown，或 complete 不为 true：两种模式均 unknown
- 空数组且 complete=true、explicitly_unrestricted=true：satisfied=true，violated=unknown；其余空记录 unknown

## 结果和追溯

`result` 的形状：

```json
{
  "matched":[],
  "evaluations":[{
    "rule_id":"r1",
    "condition":null,
    "read_variables":["kind"],
    "supporting_variables":[],
    "supporting_alternatives":[],
    "refuting_variables":[],
    "trace_compressed":false
  }]
}
```

- read_variables 按表达式声明遍历顺序收集去重，含适用的右 ref；真假未知均保留
- supporting_variables/alternatives 仅条件 true 时产生；refuting_variables 仅 false 时产生；unknown 时三者均为空
- true 常量支撑路径为 `[[]]`；没有额外变量依赖
- all=true：子支撑路径笛卡尔积；any=true：连接全部 true 子路径
- all=false：连接 false 子反证路径；any=false：子反证路径笛卡尔积
- 每条路径内去重，变量并集保持首次声明/路径出现顺序
- 保留旧协议的压缩：某个笛卡尔步骤的中间路径超过 32 时，合为一条变量并集路径；不将所有 alternatives 统一限制成 32 条
- 新增固定 `trace_compressed` 布尔字段，明确标识该规则内部是否发生上述压缩。压缩后不是完整的最小充分路径集合

例如 `any(eq[a,1], all(eq[b,2],eq[c,3]))` 都为真时，read/support 为 `[a,b,c]`，alternatives 为 `[[a],[b,c]]`。

这些字段是表达式依赖解释，**不是对输入来源、平台断言或业务事实的外部证据验证**。

## 安全边界和错误

为稳定运行，本版额外设定：table_json 512 KiB、values_json 256 KiB；单个 JSON 对象深度 32、值节点 20,000；表最多 1,000 条规则；表达式自身深度 32；一个连接步骤累计 alternatives 最多 256；结果 JSON 最多 4 MiB；每一条完整 SDK 输出帧（包含所有绑定值的聚合消息及转义/封装）也必须不超过 4 MiB，为旧 daemon 的默认 5 MiB 扫描上限留余量。所有消息在首次输出前完成检查，超限不返回部分成功。超限明确报 `LIMIT_EXCEEDED`，不截断结果成“无命中”。

JSON 禁止重复键、非有限数、无效 Unicode 和超过 ±(2^53−1) 的整数数值（包括呈整数值的浮点数）；长编号请使用字符串。普通非整数数值使用 IEEE754 双精度，不是 Decimal 金融精度，极小数可能按 Number 精度舍入。安全范围限制及 all_values/ref 的拒绝是本版公开的边界，不宣称接受所有旧内核可能接收的输入。

错误经 SDK 作为失败的 Tool 调用返回，错误文本为 `{code,path,message}` JSON，只含结构位置和固定描述，不含实际输入值。没有 silent no_match 回退。
