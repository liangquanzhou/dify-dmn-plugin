# JSON suite 0.7.0 candidate

Six independently implemented Tools and a static read-only Endpoint. Existing evaluate retains its 17-output contract. New tools have explicit profiles and status envelopes. The default production query has no deployment and fails closed. The viewer only serves bundled assets; imported JSON stays in browser memory.

This unpublished candidate is bounded to four areas: JSON decisions with UNIQUE and typed source-quality/freshness checks; configured read-only queries; bindings, advisory stage plans and static validation that reuse the existing controller boundary; and read-only matrix/Phase-Step-Node views. Query observations must remain fresh through final authorization and publication. No XML/FEEL engine, durable-wait runtime, business writes, company API connection, visual editor or production deployment is included. It does not claim complete target parity. See the source package docs/JSON-SUITE-0.7.0.md and docs/VALIDATION-0.7.0-CANDIDATE.md. Historical text below applies to earlier versions.

# JSON Decision Table 0.5.0 candidate

0.5.0 候选新增 UNIQUE；FIRST/COLLECT 条件、未知策略与输出保留0.3.0契约。配套源码的 Dify 1.11.1 只读矩阵 web 接入需单独构建部署，标准插件包不能自动注入界面。本候选尚未发布或部署公司环境。

UNIQUE：确定至少两条 true 时 status/decision_status=conflict；否则只要还有 UNKNOWN 就 waiting_input；恰好一条 true 且无未知时 matched；全 false/空表 no_match。compatible、strict 和省略策略均不能绕过唯一性保证。同值多命中也冲突。冲突/等待时 matched、outputs、selected_rule_ids 均为空，all_matches 只作诊断；调用方必须显式处理全部四个状态，不能退化为 FIRST。

Dify 1.11.1 单张自定义 JSON 决策表，插件内部求值，无引擎服务、凭据、XML 或可视化编辑器。

必填输入不变：静态 `table_json`、上游绑定 `values_json`。可选 `expected_sha256` 是独立静态版本锁，不能嵌入表中代替校验。

表内可选 `unknown_policy`；FIRST/COLLECT 的既有含义：
- 未填写或 `compatible`：保留 v0.2.0 的选择行为
- `strict`：FIRST 的首个 true 前存在 UNKNOWN 时等待，首个 true 之后的未知不阻塞；COLLECT 任意 UNKNOWN 都等待

全部规则和 all/any 子条件仍完整求值，错误使 Tool 失败，不伪装成等待。when 的既有严格类型、null/ref、金额与 constraint_set 语义不变。output/载荷只作数据，不执行、不自动合并。

旧 `result={matched,evaluations}`、`matched` 和 `matched_rule_ids` 仍表示最终选中，绝不改成“全部 true”。新增 `selected_rule_ids`、`condition_matched_rule_ids`、`all_matches`、`unknown_rule_ids`、`blocking_unknown_rule_ids` 和 `decision_status`。新消费者用 decision_status 分支；compatible 无 true 但有未知时，旧 status 为 no_match、新 decision_status 为 waiting_input；strict 等待时两个状态均 waiting_input。

`model_sha256` 是完整表的 RFC 8785 规范化 SHA-256，包括显式 policy、规则顺序和输出数据；空白和对象键序不影响它。`table_version` 保留原始文本 hash。可选 expected_sha256 不匹配时报 HASH_MISMATCH，校验在规则求值之前，错误不返回部分成功。内容版本锁不是签名或权限验证。

17 个独立变量可绑定，末尾标准 JSON 消息保留旧 9 字段；绑定 `decision_result` 获得简洁决策信息，字段集合不变：FIRST/COLLECT 为 schema_version=0.3.0，UNIQUE 为0.5.0（新增状态能力版本，不是另一种输入结构）。完整 SDK 帧仍限 4 MiB，全部消息预检后才开始输出。

源码分发包含完整条件协议、迁移文档、本地运行时对齐清单、合成向量，以及自动生成静态 table_json/expected_sha256 的 `scripts/compile_table.py`。本地 phases/steps/rules/when/output 无需重构，但运行时和编译器应按这些规范同步；不代表公司真实环境已经验证。

未签名交付；遵守公司审查与签名策略，保持签名校验开启。v0.1.x XML/KIE 工作流仍不兼容；旧发布版本保留，不能自动迁移其 XML 参数。
