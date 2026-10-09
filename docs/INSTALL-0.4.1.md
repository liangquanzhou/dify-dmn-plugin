# 0.4.1 决策矩阵前端接入（Dify 1.11.1）

本交付增加 **只读决策矩阵预览**。执行仍使用插件内的原始 JSON 求值器；矩阵不写配置、不计算命中、不调用外部规则服务。`table_json` 与可选 `expected_sha256` 仍由 Dify 原生表单编辑，默认收起在「原始 JSON 与模型版本锁」内。`values_json` 及输出变量区域不变。

这是 Dify **前端源码补丁**，不能通过安装 `.difypkg` 自动加载。需要管理员按已有审批流程重建并替换自托管 Dify 的 web 前端；本次发布不包含公司系统部署。发布的 `.difypkg` 未签名，公司安装前必须完成管理员审查、签名与批准的分发流程，不应关闭签名验证。

## 发布附件与标准 Tool 安装

发布附件清单见 [发布说明](RELEASE-0.4.1.md)，各附件校验值以 `SHA256SUMS.txt` 为准。插件包 SHA-256 为 `790baba6bac2950cc99be22a8defc8ad4ea694fd80822737fbf3b414e357ccaf`。

在经批准的测试部署中，使用 **Plugins → Install from GitHub**，仓库填写 `https://github.com/liangquanzhou/dify-dmn-plugin`，选择 **v0.4.1** 和 `liangquanzhou-dmn_decision-0.4.1-unsigned.difypkg`。公司策略拒绝未签名附件时，改用管理员审查签名后的批准分发版本；本地文件安装仅在该部署实际提供入口时使用。不要为了安装此包关闭签名校验。

安装后添加“执行 JSON 决策表”Tool，设置静态 `table_json`，绑定 `values_json`，按需配置 `expected_sha256`。这一步提供规则执行；下面的独立 web 接入才提供矩阵显示。离线 HTML 仅用于查看配置，不能作为插件安装，也不能执行 Python 规则。

## 固定基线与身份

- Dify 版本：1.11.1
- 必须精确为 commit：`2058186f22b4e4d4e155f380c130f4e8f21622fa`
- 上游源码：[Tool panel](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/workflow/nodes/tool/panel.tsx)、[use-config](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/workflow/nodes/tool/use-config.ts)、[provider ID 合成](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/api/core/plugin/impl/tool.py)
- 必须同时精确匹配 `provider_type=builtin`、`provider_id=liangquanzhou/dmn_decision/dmn`、`tool_name=evaluate`
- 身份来自本仓库 `plugin/manifest.yaml`、`plugin/provider/dmn.yaml`、`plugin/tools/evaluate.yaml`。不按显示名称、子串或宽泛 `dmn` 标签匹配，不对其他工具启用

本补丁可显示既有 0.3.0 JSON 表；不支持旧 XML/KIE 补丁。执行语义及输出合约仍以 `CONTRACT.md` 和 `LOCAL_ALIGNMENT.md` 为准。

## 应用步骤

准备一份独立的 Dify 1.11.1 Git 工作副本；不要先在公司运行目录试装。安装器需要 Python 3.10+、Git，以及本仓库完整 `frontend/` 目录。单独的 `.patch` 附件仅供审查补丁差异，不能替代源码 ZIP 内的四个组件文件和安装器；只应用 `.patch` 会缺少组件。

```bash
# /path/to/dify 必须为 Git 仓库根目录，而非 web 目录
# 先确认当前提交；如不是固定基线，在独立工作副本选择正确提交
# 不要使用 checkout/reset 丢弃已有本地修改
git -C /path/to/dify rev-parse HEAD

# 从本交付仓库根目录运行；只检查，不修改
python frontend/integration/apply.py /path/to/dify --check

# 应用并逐字节验证，重复运行相同版本为幂等操作
python frontend/integration/apply.py /path/to/dify
```

安装器会：

1. 校验 Git HEAD 与三个补丁目标的 SHA-256，拒绝版本不符、局部应用或自定义修改
2. 执行 `git apply --check`，应用 `frontend/patches/dify-1.11.1-decision-matrix.patch`
3. 将 `frontend/src/decision-table.tsx`、`model.ts`、`decision-table.module.css` 及 `frontend/integration/identity.ts` 拷贝到 `web/app/components/workflow/nodes/tool/components/dmn-decision-table/`
4. 复核补丁后的三个文件 hash 和四个拷贝文件的字节

补丁仅修改 Tool panel、en-US/zh-Hans workflow 两份文案。已有不同的组件文件会触发拒绝，避免覆盖定制内容。升级候选版本时应在新的干净 Dify 工作副本重试；不要直接强制覆盖。脚本没有 push、容器重启、安装依赖或部署步骤。

## Dify 完整校验与构建

固定上游 `web/package.json` 要求 Node >=22.11.0，并指定 pnpm 10.25.0、React 19.2.3、Next ~15.5.9、TypeScript ^5.9.3。按组织批准的工具链安装，不要因为全局 pnpm 版本不同而重写 lockfile。

```bash
cd /path/to/dify/web
pnpm install --frozen-lockfile
pnpm exec oxlint --config .oxlintrc.json app/components/workflow/nodes/tool/panel.tsx app/components/workflow/nodes/tool/components/dmn-decision-table
pnpm exec eslint app/components/workflow/nodes/tool/panel.tsx app/components/workflow/nodes/tool/components/dmn-decision-table i18n/en-US/workflow.ts i18n/zh-Hans/workflow.ts
# 在这个独立工作副本中复制本交付的原生 Panel 回归夹具
cp /path/to/dify-dmn-integration/frontend/integration/dify-panel.spec.tsx.template \
  app/components/workflow/nodes/tool/dmn-integration.spec.tsx
pnpm type-check:tsgo
pnpm test --runInBand app/components/workflow/nodes/tool/dmn-integration.spec.tsx --coverage=false
pnpm build
```

`/path/to/dify-dmn-integration` 是源码 ZIP 解压目录。以上命令分别验证依赖、接入文件、全项目类型、Panel 和构建；不代替组织的完整 CI。实际执行结果见 [交付验收](DELIVERY-0.4.1.md)，不要把清单本身当作通过证明。前端矩阵当前为中文界面，新增外层标题/动态提示提供 en-US、zh-Hans；完整矩阵国际化尚未完成。

## 配置、只读与切换行为

- `use-config.ts` 原样保留。预览读取 `toolSettingValue.table_json`，不调用 `setToolSettingValue`、节点更新或 effect 保存
- 兼容直接保存的 JSON 文本，以及 Dify 原生 `{type: 'constant'|'mixed', value: 'JSON文本'}` 包装；不对 JSON 做重新序列化
- `type: 'variable'`、未知包装类型，或 mixed 文本中含 `{{#...#}}` 运行时引用时，明确显示「无法静态预览」，不会把运行时值或模板猜成静态规则
- constant 包装里的相同字符是原文，照常保留；是否能显示由 JSON 合约校验决定
- 仍把原生完整 `toolSettingSchema`、`toolSettingValue`、`setToolSettingValue` 交给 Dify ToolForm，所以编辑表 JSON 不会丢失版本锁或其他原生设置
- 矩阵与收起的原生设置分别以 `matrix:${id}` 和 `settings:${id}` 为 key；切换节点时重建预览/展开状态，避免 key 冲突导致上一节点弹窗残留
- `readOnly` 原样传给预览和 ToolForm。预览无编辑/保存接口；表格弹窗、滚动及详情展开属于浏览
- 未配置、错误 JSON、超限或不支持条件会显示空状态/错误。它们不改变已保存值，也不代替执行端报错

## 已验证范围与复现

2026-10-08 在独立云工作目录读取并克隆官方固定提交，实际运行过：

- `apply.py --check`、实际应用、相同候选重复应用：通过；三个修改文件和四个组件逐字节校验通过
- 5 项 Vitest identity/原生包装测试：通过（精确身份正反例、constant/mixed 静态值、动态拒绝、无修改、空/非法值透传）
- 6 项安装器回归：通过（只检查不修改、幂等、拒绝修改基线、拒绝不同组件、拒绝局部补丁、拒绝符号链接及错误提交）
- 官方应用后 `git diff --check`：通过
- Dify 原生全项目 `tsgo --noEmit`：通过；4 项 Panel Jest 回归：通过
- Dify 原生接入文件 oxlint：0 错误/0 警告；ESLint：0 错误，仅固定上游已存在的 3 项 TODO/文件行数警告（已对原版源码复核）

```bash
cd frontend
npm ci
npm test -- integration/identity.test.ts
cd ..
DIFY_111_SOURCE=/path/to/official-dify-1.11.1 \
  python -m unittest discover -s frontend/integration -p 'test_apply.py' -v
```

独立组件/demo 的测试、构建与界面检查见 [验证记录](VALIDATION-0.4.1.md)。Panel Jest 使用真实 Panel/矩阵组件，但 mock 了 Dify 服务与原生表单，其结果本身不等于端到端验收。完整 Next 构建已通过，见 [交付验收](DELIVERY-0.4.1.md)。

2026-10-09 另在真实 Docker Dify 1.11.1 完成隔离云端验收：插件 0.4.1 已安装；原版 web 无矩阵，配套 web 显示同节点矩阵；真实 UI 的 Start → DMN → End 运行成功（3 节点，2.136330 秒，0 异常），选中 `priority`，`priority` 与 `standard` 条件均为 true，持久化 `table_json` 字节保持不变。见 [公开合成测试摘要](DOCKER-VALIDATION-0.4.1.md)。

该 Docker 测试对未签名包使用了仅限隔离实例、明确批准的签名校验例外；这不是公司安装步骤。公司登录态、API、既有业务工作流及部署环境仍未验收，不能据此宣称公司 Dify 已安装或上线。
