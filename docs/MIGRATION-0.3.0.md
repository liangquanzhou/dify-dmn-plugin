# 0.2.0 → 0.3.0：兼容默认选择，显式启用未知策略

现有表的结构不用重写，v0.2.0 的条件语言也不改。旧表缺省使用 compatible：旧 9 个输出字段及末尾标准 JSON 消息保留原含义，matched/matched_rule_ids 始终是“最终选中”，不是全部 true。正常输入下默认新旧结果通过固定基线与独立差分验证；资源限制仍适用，不承诺任意规模均成功。

## 可选择的升级

1. 先在测试 Workspace 安装 0.3.0，保留 0.2.0 包和旧工作流供回滚。无需凭据或额外服务
2. 旧表和输入绑定先不改，用原变量检查默认行为
3. 新分支绑定 `decision_status`，区分 matched/no_match/waiting_input；停止用旧 status 判断“确定无命中”
4. 要阻止缺输入时先走兜底，在表对象中显式加入 `"unknown_policy":"strict"`。FIRST 仅首个 true 前的 UNKNOWN 阻塞；COLLECT 所有 UNKNOWN 阻塞；等待时 selected/outputs 为空
5. 使用 `selected_rule_ids` 消费最终选择；`condition_matched_rule_ids`/`all_matches` 仅解释所有 true，等待时不得把它们送入业务动作
6. 编译器为完整表生成 `model_sha256`，把它放到独立 `expected_sha256` Tool 配置。修改表（包括 policy/output/metadata）后需按批准流程重新编译版本锁

compatible 有 true 同时有 UNKNOWN 时仍会选中，decision_status=matched 不表示所有条件已知，unknown_rule_ids 保留诊断。compatible 没有 true 但有 UNKNOWN 时旧 status=no_match 保留兼容，新 decision_status=waiting_input；显式 strict 等待时旧 status 也扩展为 waiting_input。

## 输出传输

17 个独立变量包括旧 9 个与新 8 个。末尾标准 JSON 消息只保留旧 9 个字段；新诊断通过独立变量和 decision_result 获取。这避免将相同规则/追溯重复塞进聚合 JSON，保留旧大结果的可传输范围。

每条完整 SDK 帧仍受 4 MiB 限制，全部帧通过检查后才首次输出；任何新独立字段自身超限也会报错，不截断、不返回部分成功。JSON结果、输入、规则数和证据路径限制见 CONTRACT.md。

## 两种 hash

- table_version：原始 table_json UTF-8 文本 SHA-256，旧语义不变
- model_sha256：完整解析表的 RFC 8785 规范化字节 SHA-256，空白/对象键顺序不影响，数组/规则顺序保留

unknown_policy 是表内容并参与 hash；缺省不注入字段，所以缺省和显式 compatible 虽行为相同，hash 不同。expected_sha256 只放在 Tool/调用配置中，值允许省略/null/空白禁用，非空必须 64 个十六进制字符（原始文本最多 256 字符）。错误格式报 INVALID_INPUT，内容不同报 HASH_MISMATCH，均在规则求值前失败。

hash 锁只验证内容版本，不验证来源、审批或签名，不能阻止有权限者同时更新表和 hash。Dify 插件签名仍是独立要求。

## 本地方案同步

phases/steps/rules/when/output 不改。新增内容限于单表可选 unknown_policy、运行时新决策结果和编译器自动指纹。按 [LOCAL_ALIGNMENT.md](LOCAL_ALIGNMENT.md) 接入，并在本地 JS/Code 与 Python Tool 上运行同一 [合成向量](../tests/vectors/v030-conformance.json)。本交付没有接触用户 Mac、公司源码或真实表，不能宣称本地实现已同步上线。

独立编译工具：

```bash
python scripts/compile_table.py examples/table.json --output /tmp/table-node-config.json
```

输出静态 table_json/expected_sha256，不是完整工作流 DSL。values_json 仍由上游绑定。
