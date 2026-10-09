# v0.4.1 云端验证记录

这是配置矩阵和 Dify 1.11.1 前端接入迭代，不改变 v0.3.0 单表 Python 执行协议。验证包括独立组件、Dify 原生构建和真实 Docker 合成工作流三个层次。
基础源码：`liangquanzhou/dify-dmn-plugin`，提交 `bacdfc66303cc7044e18cfe5ada1e7b05a1441d0`。
Dify 接入目标：`2058186f22b4e4d4e155f380c130f4e8f21622fa`（1.11.1）。

## 已验证范围

- 实际 React 组件由 demo 直接导入，安装器复制同一组件到 Dify，不维护第二套展示实现
- 输入条件列、输出字段列、规则行、输入/输出分组表头与清晰网格；原始配置默认折叠
- 字段路径明确区分空键、带引号键、扁平点号键与嵌套输出；缺失、null、false、0、空字符串保留不同文本
- 条件先转换成仅供显示的原子编号，逻辑列保持原始括号、且/或与常量；constraint_set 保持为单独条件，不展开或改写业务规则
- FIRST/COLLECT、strict/compatible、规则顺序均来自原 table_json；展示不执行条件，不保存或修改配置
- 非法/重复键/过大/过深 JSON、空输入以及节点切换不会保留旧表格
- 大表按 50 规则、12 输入字段、12 输出字段分页，显示范围与总数；不删除规则或列；关闭大表时不挂载重复矩阵
- 440px 节点面板下保留网格和固定规则列，横向滚动查看输出；展开大表使用同一组件，Escape/关闭均可回到面板
- 实际浏览器点击执行按钮，将当前展示的原始 table_json 发送到本地测试桥接，调用 `plugin/io_contract.py` 的 invoke_table；没有 JavaScript 替代执行器

## 真实 Docker 合成工作流

2026-10-09 在隔离云端真实 Docker Dify 1.11.1 中安装 0.4.1 插件，持久化并运行 Start → DMN → End：

- 原版 web 显示原生 JSON 参数控件，不含矩阵；配套构建显示两行只读矩阵，展开功能可用
- 实际 UI Test Run 成功：3 个节点、2.136330 秒、0 异常
- 合成输入 `customer.level=gold`、`item_count=4`；`decision_status=matched`，选中 `priority`，`priority` 与 `standard` 的条件均为 true
- 展开/关闭与运行后，持久化 `table_json` 的原文字节不变
- 浏览器页面无 JavaScript 异常；记录到的 Next.js 路由预取取消不影响实际编辑器和工作流请求

此层验证使用真实 Dify API、已安装插件和配套 web，不是 demo 或 mock。其范围仅为上述合成工作流。原始记录和环境数据不随公开源码分发；见 [公开 Docker 验收摘要](DOCKER-VALIDATION-0.4.1.md)。

未签名包在该隔离实例使用了明确批准、仅限本次测试的签名校验例外。公司部署仍须经审查、签名、信任配置和独立验收，不应关闭签名校验。

## 可复跑组件与安装器检查

```
.venv/bin/python -m pytest -q tests
.venv/bin/python scripts/check_plugin.py
cd frontend
npm ci
npm test
npm run build
cd ..
DIFY_111_SOURCE=/path/to/official-dify-1.11.1 python3 frontend/integration/test_apply.py
CHROMIUM_EXECUTABLE=/path/to/official/headless_shell node frontend/tests/browser-check.cjs
python3 scripts/build_offline_viewer.py
CHROMIUM_EXECUTABLE=/path/to/official/headless_shell node frontend/tests/offline-check.cjs
```

浏览器脚本启动配置为 `{headless:true, chromiumSandbox:true, executablePath}`，未设置禁用沙箱参数。测试脚本同时启动本地 HTTP 服务与浏览器。需要本地安装官方 Playwright 浏览器，路径可用 `CHROMIUM_EXECUTABLE` 覆盖。Python 测试环境及 demo 桥接使用仓库内的 `.venv`。

测试源码为 `frontend/tests/browser-check.cjs`、`frontend/tests/independent-audit.cjs`、`frontend/tests/offline-check.cjs`；运行时生成本地检查结果。最终通过数量与 Dify 原生校验结果见 [交付验收](DELIVERY-0.4.1.md)，包括全项目类型检查、4 项 Panel Jest 回归和完整 Next 生产构建。

离线产物还通过独立浏览器检查：FIRST/COLLECT 矩阵、展开/关闭、无 JavaScript 错误；除 HTML 自身外没有请求任何脚本、样式或外部资源。此检查使用只提供单个 HTML 的本地 HTTP 服务，独立于真实 Docker 工作流验收；不能据此推断公司安装成功。

## 边界

- 组件/demo、原生构建、真实 Docker 合成工作流分别验证；demo 结果不能代替 Docker 验收，Docker 合成成功也不代表公司部署或全部 Dify 功能验收
- `.difypkg` 只含标准 Tool；工作流内矩阵需要同时应用 Dify web 补丁并重新构建部署 web
- 配置预览的结构检查不能替代执行器最终校验；金额转换、约束记录完整性和三值运行结果仍由 Python 负责
- 离线 HTML 是自包含配置查看器，不包含 Python 运行时，不能在离线页面执行规则
- 未部署公司环境、未验证公司既有工作流或生产数据；测试环境已停止，不是持续在线服务
