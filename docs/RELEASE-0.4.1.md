# v0.4.1 发布说明：只读 JSON 决策矩阵

v0.4.1 为 Dify 1.11.1 的 JSON 决策表 Tool 配置面板增加字段列矩阵：条件字段和输出字段为列，规则为行，原有嵌套且/或逻辑显式展示。Python 求值器及 v0.3.0 执行合约保持不变。

## 本版内容

- 标准 `.difypkg` Tool：执行单张 JSON 决策表，支持 FIRST/COLLECT、三值条件与现有 17 个独立输出
- 独立 web 接入：只对精确匹配的 `liangquanzhou/dmn_decision/dmn` / `evaluate` Tool 显示矩阵，原生 JSON 参数与版本锁仍由 Dify 表单编辑
- 只读矩阵：输入/输出分组、组合逻辑、规则顺序、字段路径消歧义、横向滚动、展开大表和有界分页；不保存或重写 `table_json`
- 自包含离线查看器：展示同一 React 组件，可切换示例与展开大表；不包含 Python 运行时，不执行规则

`.difypkg` 不会向 Dify 注入 React。要在工作流节点看到矩阵，必须另行应用、构建并按组织流程部署 web 接入。矩阵是配置预览，不是可视化规则编辑器。

## 配套附件

以下为本版发布附件的用途与文件名；下载时以 Release 的 Assets 列表及 `SHA256SUMS.txt` 为准。

| 附件 | 用途 |
| --- | --- |
| `liangquanzhou-dmn_decision-0.4.1-unsigned.difypkg` | 未签名的标准 Dify Tool 安装包 |
| `dify-dmn-integration-0.4.1-source.zip` | 插件、前端组件、精确基线安装器、补丁、测试与公开文档 |
| `dmn-decision-matrix-0.4.1-offline.html` | 可直接打开的只读矩阵查看器 |
| `dify-1.11.1-decision-matrix.patch` | 便于单独审查的前端差异；应用仍需源码 ZIP 内的组件和安装器 |
| `SHA256SUMS.txt` | 上述四份附件的 SHA-256 校验清单 |

插件包 SHA-256：

```text
790baba6bac2950cc99be22a8defc8ad4ea694fd80822737fbf3b414e357ccaf
```

在同一目录下载全部附件后，可用 `sha256sum -c SHA256SUMS.txt` 校验。源码 ZIP 不包含依赖缓存、原始验收记录、运行标识或私有环境数据。

## 适配与安装

- 精确目标：Dify **1.11.1**，提交 `2058186f22b4e4d4e155f380c130f4e8f21622fa`
- 插件身份保持 `liangquanzhou/dmn_decision` / provider `dmn` / tool `evaluate`
- 现有 v0.3.0 JSON 表继续使用原执行合约；v0.1.x XML/KIE 工作流及旧前端补丁不兼容
- 安装器校验提交及目标文件 hash，拒绝错误基线、局部补丁和冲突组件，不自动部署

完整步骤见 [安装说明](INSTALL-0.4.1.md)。公司采用前必须完成管理员审查、签名、信任配置和批准的分发流程，保持签名校验开启。

## 实际验证结果

- Python：877 项测试通过；核心执行与协议的 7 个 Python 文件与基础版本逐字节一致
- 源码与最终插件包 SDK stdio 检查通过；归档完整性及内容校验通过
- 独立前端：33 项测试；安装器：6 项；组件浏览器检查：20 项；独立界面审查：12 项；最终离线 HTML 检查：6 项
- Dify 原生：全项目类型检查、4 项 Panel Jest 回归、接入文件 lint 与完整 Next 生产构建通过；ESLint 保留 3 项经原版源码复核的上游警告
- 真实 Docker：2026-10-09，在隔离云端 Dify 1.11.1 安装插件 0.4.1，显示配套矩阵，并从真实 UI 跑通 Start → DMN → End：**3 节点，2.136330 秒，0 异常**。选中 `priority`，`priority` 与 `standard` 条件均为 true；持久化 `table_json` 字节不变

详见 [交付验收](DELIVERY-0.4.1.md)、[验证范围](VALIDATION-0.4.1.md) 和 [真实 Docker 合成验收](DOCKER-VALIDATION-0.4.1.md)。

## 使用边界

- 未签名包的 Docker 测试使用了仅限隔离实例、明确批准的签名校验例外；公司环境仍必须遵守签名与信任要求
- 合成工作流通过不代表生产就绪、全部 Dify 功能通过或公司既有业务验收；此次未部署公司环境
- 运行时条件与结果仍由 Python 执行器负责；矩阵结构预览不能代替执行端校验
- 矩阵内部说明当前为中文；新增 Dify 外层标题和动态提示提供 en-US/zh-Hans，完整矩阵国际化尚未完成
- 验收环境已停止，离线 HTML 是文件附件，不是持续托管的在线服务
