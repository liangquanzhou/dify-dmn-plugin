# 只读 Phase → Step → Node 查看器

候选功能，独立前端入口与 Dify Endpoint。首次展示为自行编写的 SYNTHETIC / EXAMPLE_FRAGMENT；它不是业务规则或生产流程。

## 打开与边界

- 离线：直接打开 `plugin/viewer_static/offline.html`，单文件包含真实 React 字段矩阵及许可证。也可保持 `index.html`、`viewer.js`、`viewer.css` 相邻并直接打开 `index.html`
- Dify：在支持 Endpoint 的宿主安装插件后，创建 Endpoint 实例，打开宿主签发且以 `/` 结尾的实例地址。普通 workflow/share 链接不是该入口
- 本地导入只读取浏览器内存。不上传、不求值、不执行动作、不保存文件、不访问 localStorage/IndexedDB、不注册服务工作线程；刷新恢复内置示例
- 本入口不能替代原 Dify 节点内字段矩阵的 web 补丁安装。原矩阵组件、规则语义、演示执行入口及 Vite 配置没有改动
- 展示校验不等于执行合同验证、来源认证、图激活、权限判断或摘要验证。声明的 URL、来源和摘要都是惰性文本

## 导入形状

接受根 `schema_version`：

1. `service-decision-dsl.node-architecture.v2`
2. `structure-view.v1`，仅用于显式展示的 envelope，不是新的执行 profile 或 Dify 导入格式

两者必须明确提供 workflows → phases → steps → graph.nodes / graph.edges，以及每个 Step 的 exits。示例：

```json
{
  "schema_version": "structure-view.v1",
  "workflows": [{
    "workflow_id": "example.locate",
    "flow_type": "LOCATE",
    "scope": "SYNTHETIC",
    "phases": [{
      "phase_id": "LOCATE",
      "steps": [{
        "step_id": "S1",
        "name": "示例",
        "graph": {
          "nodes": [{"node_id": "D", "kind": "DECISION", "ports": ["MATCHED"], "model_ref": "decision@1"}],
          "edges": []
        },
        "exits": {}
      }]
    }]
  }],
  "models": {
    "decision@1": {
      "profile": "dmn-local-table-v1",
      "table": {
        "id": "local-table",
        "hit_policy": "FIRST",
        "rules": [{"id": "r1", "when": {"eq": ["ready", true]}, "output": {"route": "ready"}}]
      }
    }
  }
}
```

`dmn-local-table-v1` 是本查看器的明确展示包装：提供 `table` 对象，或原样 `table_json` 字符串。只有通过现有矩阵解析器的本地表才复用原矩阵。它没有新增执行语义，不能用来无损转换对象路径、深相等或 typed quality。

模型展示：
- `service-decision-table-v1`：保持完整原始条件数组，按 rule_id、state、data、actions 分列，显示完整参数契约、来源、未命中策略和结果模板
- 明确声明 `profile` 或 `format` 为 `json-table-v1`：原样展示条件与完整 output；null、字符串、数组和对象不假定为 typed state/data/actions
- 未知 profile、冲突的 profile/format 声明或非法本地包装：显示诊断和完整原文，不猜测条件语义，不当作本地矩阵
- 缺失模型、缺失/未知 hit_policy、缺失模板及无效绑定均可定位。找不到 output_template_ref 时，不回退到同一行的 inline output

这是投影检查。architecture 根可以保留完整定义，但查看器不实施其部署/执行约束，不自动合成缺少的 Phase 或 Step，不转换旧 XML 或 json-plan-v1。额外字段保留在完整导入原文中。

## 确定的导入预算

UTF-8 2 MiB；深度 40；60,000 JSON 值；1–30 workflows；最多 600 nodes、1,800 edges。拒绝无效 UTF-8、非有限数、非对象结构、缺少显式层级、相应作用域内重复 ID 和 Step 内悬空边。workflow ID 全局唯一；phase ID 在 workflow 内唯一；step ID 在 phase 内唯一；node/edge ID 在 Step 内唯一。

JSON 对象键与数值采用浏览器 `JSON.parse` 的显示语义（含重复键最后一个值覆盖），建议生产来源始终使用唯一键。本入口不声称执行层的安全 JSON 或数值校验通过。值遍历为迭代式，不因深层 JSON 递归耗尽栈。

非法、损坏或超限导入保留旧视图与旧来源，同时显示失败文件名和原因。超过预算需要提供显式较小展示包；没有自动省略、截断或重排节点。

导入采用独立候选视图：文件读取与解析成功后，先在隐藏、不可交互的容器内完成 React 首次渲染，再替换已提交视图。读取、解析或首次渲染失败时，保留原来的 DOM 节点、事件监听、来源、目录展开状态、选中详情、焦点、搜索、缩放与滚动位置，并显示可读错误。这里不将后续任意交互故障称为导入回滚保证。

每次读取固定捕获 File 与独立修订号。过期成功、失败和清理回调不能替换新视图、覆盖新错误、解除新请求的读取状态或清空新选择；同一文件可连续重新导入。成功替换后，已移除视图的延迟焦点/滚动回调失效。可选的非字符串名称仍作为原始数据保留并安全忽略，不声称与目标 RC5 的所有无效显示字段拒绝规则完全一致。

## 导航与详情

- 选择流程类型，再选实际声明的 workflow；相同类型允许多个 workflow
- 可折叠 Phase / Step 目录按名称、ID、规则 ID 搜索，包含本地表规则。搜索只筛选目录，画布仍显示所有已声明节点；可选 name 非字符串时不参与索引，仍保留原文，不能触发对象强制转换
- 节点位置依 graph.nodes 数组顺序；不把展示顺序称为运行顺序
- Step 内控制边带方向箭头；展开边清单可读完整 edge_id、source_port 和条件。详情中进入边为琥珀色、离开边为紫色
- Step exits 展示完整跨 Step/Phase 目的地，不把跨 Step 控制边改造成新的归属
- 每个节点可查看完整 input/event bindings、ports、来源、模型和 Step 原文
- 拖动空白或正常滚动平移；Ctrl/⌘+滚轮或按钮缩放；100% 复位；Fit Step 至少 65%；Fit All 按实际画布尺寸提供整体概览
- 桌面侧抽屉、手机全屏详情；Escape/关闭恢复到原节点或目录按钮；嵌套大表先关闭内层再关闭详情
- 本地矩阵继续保留 AND/OR 括号、50 行/12 字段分页及展开大表。typed/simple 规则按50行分页；诊断按50项分页，共享模型诊断只生成一次并在每个引用它的节点详情中显示，避免按节点数重复放大

## Endpoint 安全边界

`plugin/endpoints/structure_viewer.yaml` 定义 GET `/` 与 GET `/<path:asset_path>`。SDK 0.10.2 同时路由 HEAD；代码显式去掉 HEAD body（SDK 会直接序列化 Response）。Endpoint 无参数配置。

严格 allowlist 仅 `index.html`、`viewer.js`、`viewer.css`；其他路径、目录、symlink、查询串、请求体均拒绝。它不读取请求中的 JSON、不操作 SDK session、不接收上传、不调内核、不返回仓库文件。

响应包含 `default-src 'none'`、`script-src 'self'`、`connect-src 'none'`、`base-uri 'none'`、`form-action 'none'`、`frame-ancestors 'none'`、no-store、nosniff、no-referrer、DENY 和最小 Permissions-Policy。仅样式允许 inline，以满足 React 布局/缩放；脚本不允许 unsafe-inline/eval。独立 offline.html 的内联脚本以构建时 SHA-256 CSP hash 放行，没有通用内联脚本权限。

注册由 manifest 指向 `endpoints/structure_viewer.yaml`，并启用 `resource.permission.endpoint.enabled`。没有额外 Endpoint provider 类。

## 构建与可复验结果

```sh
cd frontend
npm ci --ignore-scripts
npm test
npm run build:structure
CHROMIUM_EXECUTABLE=/path/to/sandboxed/chromium npm run browser:structure
cd ..
.venv/bin/python -m pytest -q tests/test_structure_endpoint.py
```

`vite.structure.config.ts` 与原演示服务配置隔离，不携带 Python evaluator middleware。`scripts/build_structure_viewer.py` 从源码构建固定文件名资源与单文件离线页，并重算 CSP hash；许可证取自既有 React MIT 通知。发布/打包前必须重建，不手改生成 JS/CSS。

2026-10-09 冻结0.6候选的历史验证（不是0.7导入事务更改后的验收）：
- 47 项独立 schema/DOM 测试通过（32 schema + 15 组件）；连同既有48项共95项前端测试
- 71 项 Python Endpoint/真实 SDK 路由、解析、调用与 HEAD 序列化测试通过
- 历史0.6版本的42项真实 Chromium 检查通过，含直接 file:// index.html 与600节点/1800边预算边界。包括网络观察、CSP 注入连接阻断、桌面/390px布局、焦点、非法导入、121规则/15列大表和离线自包含；0.7最终字节须另行重跑
- 原矩阵 48 项组件/模型测试、30 项真实浏览器检查、11 项原离线检查继续通过；原组件/样式/模型文件无差异
- Chromium 使用沙箱，无 `--no-sandbox`；截图已检查
- 真实目标 Dify 宿主安装、宿主签发 URL、host 中 iframe/代理行为尚未验收。本地静态 HTTP 与 SDK 测试不冒充目标宿主验证；插件打包验收另记

本实现仅根据公开文档/JSON schema 独立编写，没有复制或执行无 LICENSE 对方仓库的实现或测试。示例与所有测试向量均独立编写。

### 0.7 候选导入事务补充验证

依据固定公开目标 `561a15efa2a086c93373dc7fbd3fbf88e46a48c4` 的 [RC5 变更声明](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/releases/v0.4.0-rc5.md) 独立补充导入可靠性，不使用或执行目标实现/测试。

- `npm run test:structure`：55/55 通过，含原32项模型测试、23项交互测试。新增8项覆盖读取/解析/注入渲染错误的真实 DOM 与完整视图状态保留、旧成功/失败乱序、新读取期间的旧清理、同一 File 重复导入和已移除视图的动画回调隔离
- `npm test`：全部103/103前端测试通过，原矩阵和身份绑定回归包含在内
- `npx tsc --noEmit`：通过
- 本轮未启动浏览器服务、未重跑真实 Chromium，也未将已有0.6浏览器证据冒充这些更改的浏览器验收。发布打包前须重新生成静态资源与离线 CSP hash，并对最终字节做浏览器/Endpoint回归
