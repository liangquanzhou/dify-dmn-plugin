# v0.4.1 交付与验收

本版交付字段级只读决策矩阵：条件字段为列、输出字段为列、规则为行。FIRST/COLLECT、规则顺序和原始 all/any/constraint_set 逻辑保持不变；矩阵展示原始 JSON，不执行或保存配置。

## 发布附件怎么用

1. `dmn-decision-matrix-0.4.1-offline.html`：下载后用浏览器打开即可看实际矩阵、切换示例和展开大表，不需要安装 Node。它是同一 React 组件的自包含查看器，没有 Python 运行时，不能离线执行规则。
2. `liangquanzhou-dmn_decision-0.4.1-unsigned.difypkg`：标准 Dify Tool 插件包。经公司管理员审查、签名和批准的分发流程安装；不要关闭签名校验。
3. `dify-dmn-integration-0.4.1-source.zip`：完整插件源码、前端组件、Dify 1.11.1 补丁/安装器、测试及公开验证摘要。解压后先读 `docs/INSTALL-0.4.1.md`。原始验收记录、运行标识和环境数据不随公开源码分发。
4. `dify-1.11.1-decision-matrix.patch`：单独提供的前端差异，便于审查；应用时仍需要源码 ZIP 中的完整组件和安装器，不能只套用补丁。
5. `SHA256SUMS.txt`：上述四份附件的 SHA-256 清单。

`.difypkg` 本身不能给工作流节点添加 React 界面。公司 Dify 内显示矩阵，需要管理员在固定 Dify 1.11.1 源码副本应用 web 补丁、构建并部署 web；本次发布未部署公司系统。验证分别覆盖同组件演示页面和真实云端 Docker Dify；两者都不代表公司环境。

## 实际完成的验证

- Python：877 项测试通过；核心求值与协议的 7 个 Python 文件与基础版本逐字节一致
- 插件包：官方 CLI 0.6.10 打包；18 个归档文件与源码逐字节一致，归档完整性检查通过
- SDK stdio：源码及最终插件包均通过 13 个成功调用、21 个错误调用及无凭据校验
- 独立前端：33 项测试通过（21 模型、7 组件、5 Dify 身份与参数包装），TypeScript 与 Vite 生产构建通过
- 补丁安装器：6 项回归通过，包括只检查、实际应用、幂等及拒绝错误版本/修改文件/符号链接
- 真实浏览器：20 项通过，覆盖 FIRST/COLLECT、同份 JSON 调用 Python、strict 等待、440px 内部横滚、弹窗、只读、错误 JSON、节点切换
- 独立界面审查：12 项通过，包含 1000 规则/1000 字段的有界分页、输出路径消歧义、XSS 文本化和零页面横向溢出
- 最终离线 HTML：6 项真实浏览器检查通过，零独立资源请求和零 JavaScript 错误

所有浏览器检查均启用 Chromium 沙箱，未传禁用沙箱参数。可复跑测试位于 `tests/`、`frontend/tests/` 与 `frontend/integration/`；公开摘要见 [验证记录](VALIDATION-0.4.1.md)。

## Dify 原生检查

固定官方提交：`2058186f22b4e4d4e155f380c130f4e8f21622fa`。原生检查独立于 demo；可复跑命令见 [安装说明](INSTALL-0.4.1.md)，Panel 回归夹具为 `frontend/integration/dify-panel.spec.tsx.template`。

- pnpm 10.25.0 冻结 lockfile 安装成功；未修改上游依赖与 Next 配置
- 全项目 `pnpm type-check:tsgo` 通过
- 实际 Dify Panel Jest：4/4 通过，覆盖原生表单透传、其他工具不受影响、动态值拒绝静态预览、只读与节点切换
- 本次接入的 7 个文件 oxlint：0 错误/0 警告
- 本次接入文件 ESLint：0 错误；新增组件零警告，3 项上游 TODO/文件行数警告已用原版源码确认
- 实际应用、重复应用与补丁后字节校验通过
- 完整 Dify `pnpm build`：退出码 0，生产编译、35/35 静态页、页面优化及 build traces 均完成（2026-10-08 18:31 UTC）

原生检查曾发现矩阵和设置使用相同 React key 的接入缺陷；已改为不同前缀，避免切节点遗留弹窗。修复后的源码、补丁、组件、离线 HTML 与验证结果已重新对齐。Jest mock 了 Dify 服务和原生表单，因此不是公司实例端到端验收。

Dify 上游构建配置会跳过构建内的 lint/type-check，因此上述 ESLint、oxlint、全项目 tsgo 都是另行真实执行，并非从 build 成功推断。构建有上游 Browserslist 数据过旧等非阻塞提示，未为消除提示更改依赖或锁文件。

## 真实 Docker Dify 验收（2026-10-09）

- 云端隔离实例运行真实 Docker Engine 与 Dify 1.11.1，安装插件 0.4.1
- 原版 web 仅有原生 JSON 控件；替换为配套构建后，同一 Tool 节点显示两行只读矩阵，可展开查看条件、组合逻辑及输出列
- 持久化合成 Start → DMN → End 工作流并从真实 UI 点击 Test Run：成功，3 个节点，2.136330 秒，0 异常
- 输入 `customer.level=gold`、`item_count=4`；`decision_status=matched`，选中 `priority`，`priority` 与 `standard` 的条件均为 true
- 预览展开、关闭与运行后，持久化 `table_json` 原文字节不变

详见 [公开 Docker 验收摘要](DOCKER-VALIDATION-0.4.1.md)。该测试使用了仅针对隔离实例、明确批准的未签名包校验例外；公司签名与信任要求不变。测试环境在证据采集后停止，不提供持续托管入口。

## 未验证的范围

- 公司登录态、API、现有工作流、正式容器及公司部署
- 全部 Dify 后端、全部 Dify 测试套件和生产业务数据
- 公司或其他私有本地执行器的协议对齐

矩阵内部当前采用中文说明；Dify 外层标题与动态提示有 en-US/zh-Hans。它是配置预览，不是新增可视化规则编辑器。离线 HTML 不提供在线托管服务；此次没有部署公司环境。

## 插件包校验

SHA-256：`790baba6bac2950cc99be22a8defc8ad4ea694fd80822737fbf3b414e357ccaf`

包版本为 0.4.1；既有决策结果协议仍为 0.3.0，保留旧 JSON 和 Python 执行语义。详细协议见 `CONTRACT.md`。
