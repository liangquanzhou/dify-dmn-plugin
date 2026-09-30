# 从 0.1.x 迁移至 0.2.0

这是破坏性协议变更，不能用原工作流参数直接运行。保留插件身份 `liangquanzhou/dmn_decision`、提供方 `dmn`、Tool `evaluate`；显示名称改为“JSON 决策表”。同一身份升级可能影响所有引用它的工作流，先在隔离测试 Workspace 操作，保留旧版包、源码、Web 镜像和已导出的工作流。

## 变化

| 0.1.x | 0.2.0 |
|---|---|
| DMN XML / `model_xml`、`decision_id` | 自定义单表 JSON / `table_json` |
| `facts_json` | `values_json`，扁平键精确匹配 |
| 远程 KIE engine / `engine_url`、`api_token` | 插件进程内计算，无提供方凭据 |
| `result.value` / `model_version` | `result={matched,evaluations}` / `table_version` |
| 标准 DMN/FEEL | 本包列明的自定义 JSON 条件协议 |
| dmn-js XML 前端补丁 | 本版没有可视化编辑器补丁，使用原生 Tool JSON 配置 |

不要自动转换旧 XML、整份方案或旧执行结果。本包没有这样的迁移器。新的表必须已经符合 `docs/CONTRACT.md`。

## 步骤

1. 导出并备份旧工作流及旧包，在测试 Workspace 安装 v0.2.0（需要签名时由管理员签名）
2. 创建新的“执行 JSON 决策表”Tool 节点，粘贴单张表到 `table_json`，把上游 JSON 字符串绑定到 `values_json`
3. 原 `engine_url`、`api_token` 不再声明或使用。若旧凭据仍存在于 Dify 的历史配置，应由管理员按公司政策清理；本包不删除平台数据
4. 更新后续节点的绑定：常用 `result_json`、`outputs`、`matched_rule_ids`；不要继续读取 `result.value` 或 `model_version`
5. 用合成示例验收，再由你在公司受控环境验证真实表。检查 false/unknown、FIRST/COLLECT、无命中和错误路径
6. 验收后再按公司发布流程迁移生产工作流。回滚需要恢复旧插件版本、旧工作流及与之匹配的 Web 镜像，不能只降插件版本而保留新参数

## 如果以前部署过 XML 前端补丁

旧补丁依据 provider/tool 身份匹配，即使插件已升级仍可能显示 XML 界面。必须先撤回旧补丁并重建部署 Web，才能使用原生新参数。

使用原 v0.1.1 源码中的安装器，对当时准确且未被修改过的 Dify 1.11.1 checkout：

```bash
python3 /path/to/v0.1.1/frontend/scripts/apply-patch.py /path/to/dify --version 1.11.1 --reverse --check
python3 /path/to/v0.1.1/frontend/scripts/apply-patch.py /path/to/dify --version 1.11.1 --reverse
```

安装器会校验实际 commit、tag 及文件 hash。如果已有公司改动导致拒绝，停止并人工审阅差异，不能强制套补丁。随后按公司的 Dify Web 构建/镜像部署流程重建，并处理补丁安装时产生的锁文件变化。该过程不会由 `.difypkg` 自动完成。

若此前从未安装前端补丁，则不需要修改 Dify 前端，也不需要 Java、Maven、KIE 或额外服务。
