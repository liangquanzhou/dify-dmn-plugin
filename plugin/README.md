# JSON Decision Table 0.2.0

执行一张自定义 JSON 决策表，兼容 Dify 1.11.1。求值在插件进程内完成，不需要引擎服务、账号、API token 或 XML。

两个输入：
- `table_json`：节点静态配置，单个 `{id,hit_policy,rules}` 对象的 JSON 字符串
- `values_json`：运行时输入，将上游输出绑定为 JSON 对象字符串。变量名按完整键精确匹配，点号不代表嵌套路径

支持 `FIRST` / `COLLECT`。所有规则均求值，选择命中的第一条/全部。未知条件为 `null`，不等同于 `false`；非法语法/不支持策略/明确类型错误会让 Tool 失败。`output`、`载荷` 和其他规则数据均不执行、不自动合并。

输出包含 `result`（原契约 `matched` / `evaluations`）、`result_json`、`matched`、`outputs`、`evaluations`、`matched_rule_ids`、`status`、`table_id` 和 `table_version`。

这是自定义条件协议，不是标准 DMN/FEEL 执行器。包只提供 Dify 标准 Tool；可视化表格编辑器需要单独的 Dify 前端扩展，本版没有该扩展。

**破坏性升级**：0.1.x 的 XML/KIE 参数和前端补丁不兼容。先在测试 Workspace 备份工作流，再新建节点按新契约配置。不要直接升级仍在执行旧 XML 的生产工作流。若已部署旧 XML 前端补丁，先由管理员按原版本的补丁卸载器撤回并重建 Web，否则它仍可能拦截此 Tool 的面板。

完整条件协议、合成示例、迁移步骤及测试范围见源代码包 `README.zh-CN.md`、`docs/CONTRACT.md`、`docs/MIGRATION-0.2.0.md` 和 `docs/VALIDATION.md`。

未签名交付；按企业政策审查和签名，保持签名验证开启。
