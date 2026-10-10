# Dify DMN 0.7.0 + Chrome 扩展 0.1.0

推荐路线：**原版 Dify + Chrome 扩展，不用前端补丁**。

DMN 插件负责决策工具执行；浏览器扩展负责工作流编辑页的只读决策表结构预览。预览不执行决策、不编辑或保存表，也不判断规则命中。

## 安装

1. 按实例的签名与安装策略安装本 Release 的 DMN 0.7.0 `.difypkg`。附件是已验收的原始未签名包。
2. 解压 `dmn-browser-preview-0.1.0.zip`，在 `chrome://extensions` 按允许的开发者模式流程加载包含 `manifest.json` 的目录。
3. 在 Dify 工作流编辑页点击扩展启用，再选择受支持的 DMN 节点。刷新、切换页面或重启浏览器后需重新启用，每个标签页单独授权。

详细步骤见 [中文安装说明](docs/INSTALL-0.7.0.zh-CN.md)。扩展源码、测试和说明位于 `browser-extension/`。

## 精确范围与验证

只支持 `provider_id=liangquanzhou/dmn_decision/dmn`、`provider_type=builtin`、`type=tool`、`tool_name=evaluate`，读取页面内存的 `data.tool_configurations.table_json`。非法、空白或未解析变量会清空旧表，不推测结果。依赖 React 私有 `__reactProps$…` 属性，版本升级需重新验证。

官方未修改 Dify 1.11.1 ARM64 + Chrome for Testing 155.0.8059.39 已通过真实 MV3 30 项检查，以及 4 组共 8 次扩展开/关节点执行对照。模拟页另有 37 项检查。启用使用官方 `Extensions.triggerAction`，不是物理鼠标点击证明。公司定制环境与升级版本尚未验证。

旧前端补丁仅为可选路线，不是本安装流程的前置条件；其历史文档中的版本与限制仍适用。

## 插件能力与边界

0.7.0 提供显式 JSON 表、typed decision、受控只读查询、advisory plan 和结构查看器；不是 DMN XML/FEEL 引擎。默认查询连接未配置并明确阻断；真实公司 API、控制器执行、持久等待及恢复不在本次验收范围内。详情见 [0.7.0 契约](docs/JSON-SUITE-0.7.0.md)。

候选阶段文档按历史记录保留；本次发布不重新构建插件或扩展运行文件。[发布说明](docs/RELEASE-0.7.0.md) 记录来源、资产与最终验收。
