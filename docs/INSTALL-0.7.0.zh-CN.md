# Dify DMN 只读决策表扩展 0.1.0

2026-10-10 已在独立 Chrome for Testing 155.0.8059.39、官方未修改 Dify 1.11.1 ARM64 和 DMN 0.7.0 上通过真实 MV3 联调：30/30 扩展检查，4/4 插件回归组（8 次实际节点执行）。触发使用 Chrome 官方 Extensions.triggerAction 工具栏模拟，经过真实 worker、activeTab 和 chrome.scripting；未单独验证物理鼠标点击或系统快捷键。公司实例未测试。

## 安装和使用

1. **Dify 端**：若已有 DMN 0.7.0 的 `liangquanzhou/dmn_decision/dmn` → `evaluate`（Evaluate JSON Table）工具，无需为预览重装。若没有，需要的是 DMN 插件 `.difypkg`，不是本扩展 ZIP。本次验证的包为 `liangquanzhou-dmn_decision-0.7.0-candidate-unsigned.difypkg`，SHA256 `5fb7f29ed5e2472815d9db93aa12f0502a35bc7f024bd6ac9304cadc5b770a90`；它是未签名候选，公司部署须按公司插件签名/审批流程处理，本次隔离测试的签名例外不适用于公司环境。
2. **浏览器端**：解压 `dmn-browser-preview-0.1.0.zip` 到固定目录。公司允许开发者模式安装时，打开 `chrome://extensions`，启用“开发者模式”，点击“加载已解压的扩展程序”，选择直接包含 `manifest.json` 的目录。源码 ZIP 不用于直接安装。若管理策略限制加载，交由管理员按批准方式分发，不绕过策略。
3. 打开 Dify 1.11.1 的工作流编辑页 `/app/:id/workflow`，在 Chrome 扩展菜单中点击 **DMN Matrix Preview for Dify 1.11.1**（可固定到工具栏），再点击受支持的 DMN 节点，左下角显示只读表，右侧保留原生编辑器。
4. 本次页面启用后，节点 A/B 切换及原生 JSON 修改会更新预览。关闭面板后需再次点击扩展；刷新、页面/应用切换或浏览器重启后也需再次启用。每个标签页分别启用，不会给其他标签自动授权。

## 与旧前端补丁路线的区别

这条路线只安装浏览器扩展，**不用 Dify 前端补丁，不替换 web 镜像，不重新构建服务器前端**。DMN `.difypkg` 负责原来的决策工具执行；浏览器 ZIP 负责结构展示。旧的前端补丁文件不属于本路线，不要作为本扩展的安装步骤。

## 精确支持范围

节点必须同时满足 `type=tool`、`provider_type=builtin`、`provider_id=liangquanzhou/dmn_decision/dmn`、`tool_name=evaluate`。
读取的是当前页面内存中 `data.tool_configurations.table_json`：JSON 字符串，或 constant/mixed 包装的字符串值；mixed 中不能有未解析变量。不是 `values_json`、运行结果或服务器已保存版本的证明。
不支持其他同名工具、`evaluate_json_table`、`evaluate_decision`、查询工具或 DMN XML/FEEL。该插件自有 JSON 表可展示 FIRST/COLLECT/UNIQUE 结构。
非法 JSON、空值、变量绑定、非 DMN 节点或不可读页面结构都会清空旧表并显示说明，不推测结果。

## 只读与兼容性边界

只显示条件、规则、逻辑和输出结构；不判断命中、不执行决策/工作流、不编辑或保存表、不读账号凭据、不调用 Dify API。修改仍由右侧 Dify 原生编辑器完成。扩展无网络请求或遥测实现；实际测试网络结论限于记录窗口。
权限只有 activeTab 和 scripting，无持久 host_permissions、无自动 content_scripts。activeTab 在浏览器层授予当前页面临时访问能力，并非只授予某个字段；关闭面板停止读取但不主动撤销浏览器同源临时授权。
适配器读取当前 ReactFlow DOM 上的私有 `__reactProps$…`，不是 Dify 稳定官方 API；Dify、React 或页面结构升级可能失效，届时需重新验证。公司定制前端未在本次范围内。
限制：JSON 512 KiB、1000 条规则、32 层、20000 个值节点、128 展示列；每页50条。超限报错，不伪装完整。

## 验证和交付

本最终包只更新 README/安装说明/验证文档；manifest、background/content/reader、CSS、源代码和测试与已验收候选逐字节一致，见 `docs/RUNTIME-INTEGRITY.json` 与 `docs/VALIDATION.md`。
公开验收摘要随扩展源码包提供，见 `docs/PUBLIC-ACCEPTANCE.md`。原始证据包不公开分发。
开发构建：源码目录运行 `npm ci`、`npm run typecheck`、`npm run build`、`npm test`。发布时不需要 npm；本次文档更新没有重新构建运行文件。
