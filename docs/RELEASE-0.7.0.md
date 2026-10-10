# v0.7.0：DMN 插件与 Chrome 只读预览扩展

推荐安装路线为 **原版 Dify + Chrome 扩展，不用前端补丁**。本次发布 DMN 插件 0.7.0 和独立 Chrome MV3 扩展 0.1.0；旧前端补丁保留为可选路线。

## 安装与附件

请阅读 [中文安装说明](INSTALL-0.7.0.zh-CN.md)。Release 提供以下附件；在同一目录下载后用 `shasum -a 256 -c SHA256SUMS.txt` 校验。

| 附件 | 用途 |
| --- | --- |
| `liangquanzhou-dmn_decision-0.7.0-candidate-unsigned.difypkg` | 原始已验收 DMN 安装包，保留文件名与未签名状态 |
| `dmn-browser-preview-0.1.0.zip` | 原始最终 Chrome 扩展，解压加载 |
| `dmn-browser-preview-0.1.0-source-public.zip` | 去敏公开版扩展源码、测试、构建产物及说明 |
| `dify-dmn-plugin-0.7.0-source.zip` | 与最终 v0.7.0 tag 文件内容一致的完整项目源码 |
| `INSTALL.zh-CN.md` | 中文安装与兼容性边界 |
| `SHA256SUMS.txt` | 以上五个附件的 SHA256 |

插件安装包 SHA256：`5fb7f29ed5e2472815d9db93aa12f0502a35bc7f024bd6ac9304cadc5b770a90`（237045 字节）。Chrome ZIP SHA256：`8e9419570dfe87f5f473db4efe84a9a374cc57e6e3343986d4c808b20d404a17`。未重新构建或改动插件、扩展运行字节。

## 精确支持范围

扩展只读页面内存中的 `data.tool_configurations.table_json`，节点须精确匹配 `type=tool`、`provider_type=builtin`、`provider_id=liangquanzhou/dmn_decision/dmn`、`tool_name=evaluate`。它不执行决策、不判断命中、不保存或编辑表，不支持其他同名工具或本套件的其他 Tool。非法、空值、变量绑定、非目标节点会清空旧表。

权限为 activeTab 和 scripting；每个标签页显式启用，刷新、页面切换及浏览器重启后需重新启用。依赖 React 私有 `__reactProps$…` 属性，不是 Dify 稳定 API。公司定制环境、升级版本与物理鼠标点工具栏尚未验证。

## 验收证据

- 原版 Dify 1.11.1 ARM64 + Chrome for Testing 155.0.8059.39：30/30 真实 MV3 检查通过。
- 四组插件回归（正常命中、兜底、非法 JSON、UNIQUE conflict），扩展开/关各一次，共 8 次真实节点执行，输出与状态一致。
- 模拟宿主另有 37/37 检查，属于独立证据层。
- 启用使用官方 `Extensions.triggerAction`，经真实 service worker、activeTab 与 chrome.scripting；不声称物理鼠标点击证明。
- 预览阶段配置未改，工作流/节点执行为零；上述执行回归另行进行。公司生产验收未完成。

详情见 [公开扩展验收摘要](../browser-extension/docs/PUBLIC-ACCEPTANCE.md)。插件原有 0.7.0 候选阶段完整验收记录仍保留在 [候选验证](VALIDATION-0.7.0-CANDIDATE.md)，其测试未因本次文档整合而重新运行。各版本历史结果不可互相替代。

当前仓库未配置 GitHub Actions workflow；不宣称 CI 通过。

## 来源与公开审查

完整冻结源码来源为 `312309fb022f93e4b529162837efb7323f77853c`，输入源码 ZIP SHA256 为 `dd4c0b3dc74dee5d800894605588fb263604e499c35b2c1377a4d2b9cccada8a`。插件包内全部 40 个文件与冻结源码一致。

扩展原始最终源码 ZIP SHA256 为 `efca3fa8a213c043e8b9db21764d2fa7e63ae2189e8f342bf3376569103fd344`。其中原始构建证据含内部构建路径，故公开源码另行去敏重包装：去掉原始 evidence 目录、增加公开摘要、整理文档中的私有证据引用。源码、测试、manifest、JS/CSS 共 15 个文件逐字节未变。公开源码 ZIP 哈希见 SHA256SUMS，不能与原始源码 ZIP 哈希混用。

本次不上传浏览器 profile、账户文件、私有部署配置、原始证据包或公司数据。候选阶段文档和插件包内说明作为冻结历史记录保留，安装以本发布说明和中文安装指南为准。
