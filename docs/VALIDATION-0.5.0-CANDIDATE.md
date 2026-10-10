# 0.5.0 UNIQUE 候选验证

日期：2026-10-09。基于已发布提交 `3e3eca1157f713380a678478bfe218d31ec3056a`，在独立云目录开发与测试，没有修改旧发布产物、推送 GitHub、发布 Release、操作用户电脑或公司环境。

## 已通过

| 检查 | 本候选结果 |
|---|---|
| Python 全部测试 | 2042 项通过；原877项保留，新增1153项 UNIQUE 与12项完整旧输出 golden |
| UNIQUE 穷举 | 0–5条规则的364种三值排列 × 默认/compatible/strict；共1092项 |
| 独立兼容复核 | 从真实0.4.1提交重新验证12个golden；额外6558组FIRST/COLLECT完整17字段逐项相同；UNIQUE1000规则边界通过 |
| 固定跨运行时向量 | UNIQUE 23个成功结果、4个技术错误；原v020/v030向量未改 |
| SDK 注册 | manifest/provider/Tool 均通过真实 SDK 0.10.2 加载 |
| 真实 SDK stdio | Python3.12，20个成功调用、21个明确失败；340个变量消息、20个9字段JSON、42个session end |
| 精确候选包 | 官方CLI0.6.10打包；对该.difypkg解包后再次通过同一 stdio 验证 |
| 前端组件 | 48个单元测试，TypeScript与Vite生产构建通过 |
| 安装器 | 7项测试，精确Dify基线、组件复制和拒绝覆盖行为通过 |
| 浏览器 | 30项检查，含UNIQUE四种结果、双未知策略、只读不触发执行、原JSON不变、440px与展开视图 |
| 离线查看器 | 11项检查，仅加载本地HTML，无额外资源/执行请求 |
| 独立界面回归 | 原审计通过：1000规则/字段、分页、sticky、XSS、只读、节点切换 |
| Dify原生面板 | 新的干净候选checkout中5个Panel Jest测试通过 |
| Dify静态检查 | 全部受跟踪源码TypeScript检查、修改组件focused ESLint通过 |

Dify前端固定提交为 `2058186f22b4e4d4e155f380c130f4e8f21622fa`。Chromium启用沙箱。前端仅预览原始JSON，不在浏览器实现执行内核。

pytest有两条依赖库既有告警（gevent的SSL导入时机与Pydantic类式配置弃用）；Vite有依赖中的既有 `use client` 指令告警。检查均以成功退出，不隐去告警或关闭检查。

## 尚未运行，不构成验收结论

- 本候选完整 Dify Next 生产构建、真实 Docker 安装及 Start → UNIQUE → 四状态分支 → End 的宿主验收
- 本候选官方 daemon0.5.1 Go包解码测试；已运行的是当前SDK的真实stdio消息与官方CLI打包
- 公司部署、真实业务规则、本地业务执行器等价性、公司签名或信任策略验收
- 查询、类型化节点、流程运行、完整查看器等后续能力；参见未完成的[覆盖计划](JSON-CAPABILITY-PLAN.md)

0.4.1的Docker和完整Next构建成功仅属于旧版本，不能挪用于0.5.0。

## 候选交付

- 插件：`liangquanzhou-dmn_decision-0.5.0-candidate-unsigned.difypkg`，manifest版本 `0.5.0`
- 源码：`dify-dmn-integration-0.5.0-candidate-source.zip`
- 离线预览：`dmn-decision-matrix-0.5.0-candidate-offline.html`，不包含Python或规则执行能力
- 校验：`SHA256SUMS-0.5.0-candidate.txt`

实际插件摘要、字节数和检查范围记录在 `BUILD_INFO.json`。候选未签名；安装前必须按管理员批准的审查、签名与分发流程，保持签名校验开启。

### 前端接入与升级边界

`.difypkg` 不会注入React，必须另行构建对应web。候选安装器只接受精确Dify基线或与本候选逐字节相同的组件；旧0.4.1组件会被拒绝覆盖。安全做法是在新的干净 `2058186...` checkout 应用本候选，再由管理员审查差异和独立构建。现有修改需要先备份并人工审查替换，不能把拒绝覆盖当作可忽略告警，也不能宣称原地升级幂等。不要把旧0.4.1离线文件当作UNIQUE预览。

新增工作流须按[UNIQUE契约](UNIQUE-0.5.0.md)显式绑定 `decision_status` 并处理 `conflict`。当前测试证明插件消息和面板兼容，尚未证明Dify宿主中四个分支都实际运行成功。

## 重现

使用Python3.12及 `plugin/requirements.lock.txt`，运行 `PYTHON=python3 bash scripts/verify.sh`。使用固定前端依赖运行 `npm ci && npm test && npm run build`。浏览器脚本分别为 `frontend/tests/browser-check.cjs`、`offline-check.cjs`、`independent-audit.cjs`；离线文件由 `scripts/build_offline_viewer.py` 从同一Vite产物生成。

使用官方CLI0.6.10执行 `DIFY_CLI=/path/to/dify bash scripts/package_plugin.sh`；随后执行 `python tests/compatibility/stdio_smoke.py --package dist/liangquanzhou-dmn_decision-0.5.0-candidate-unsigned.difypkg`。最后由 `scripts/package_source.py` 按明确allowlist打包，源代码ZIP不包含虚拟环境、node_modules、登录状态或本地验证原始日志。
