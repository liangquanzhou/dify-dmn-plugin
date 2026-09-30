# JSON Decision Table 0.3.0

Dify 1.11.1 单张自定义 JSON 决策表，插件内部求值，无引擎服务、凭据、XML 或可视化编辑器。

必填输入不变：静态 `table_json`、上游绑定 `values_json`。可选 `expected_sha256` 是独立静态版本锁，不能嵌入表中代替校验。

表内新增可选 `unknown_policy`：
- 未填写或 `compatible`：保留 v0.2.0 的选择行为
- `strict`：FIRST 的首个 true 前存在 UNKNOWN 时等待，首个 true 之后的未知不阻塞；COLLECT 任意 UNKNOWN 都等待

全部规则和 all/any 子条件仍完整求值，错误使 Tool 失败，不伪装成等待。when 的既有严格类型、null/ref、金额与 constraint_set 语义不变。output/载荷只作数据，不执行、不自动合并。

旧 `result={matched,evaluations}`、`matched` 和 `matched_rule_ids` 仍表示最终选中，绝不改成“全部 true”。新增 `selected_rule_ids`、`condition_matched_rule_ids`、`all_matches`、`unknown_rule_ids`、`blocking_unknown_rule_ids` 和 `decision_status`。新消费者用 decision_status 分支；compatible 无 true 但有未知时，旧 status 为 no_match、新 decision_status 为 waiting_input；strict 等待时两个状态均 waiting_input。

`model_sha256` 是完整表的 RFC 8785 规范化 SHA-256，包括显式 policy、规则顺序和输出数据；空白和对象键序不影响它。`table_version` 保留原始文本 hash。可选 expected_sha256 不匹配时报 HASH_MISMATCH，校验在规则求值之前，错误不返回部分成功。内容版本锁不是签名或权限验证。

17 个独立变量可绑定，末尾标准 JSON 消息保留旧 9 字段；绑定 `decision_result` 获得 schema_version=0.3.0 的简洁决策信息。完整 SDK 帧仍限 4 MiB，全部消息预检后才开始输出。

源码分发包含完整条件协议、迁移文档、本地运行时对齐清单、合成向量，以及自动生成静态 table_json/expected_sha256 的 `scripts/compile_table.py`。本地 phases/steps/rules/when/output 无需重构，但运行时和编译器应按这些规范同步；不代表公司真实环境已经验证。

未签名交付；遵守公司审查与签名策略，保持签名校验开启。v0.1.x XML/KIE 工作流仍不兼容；旧发布版本保留，不能自动迁移其 XML 参数。
