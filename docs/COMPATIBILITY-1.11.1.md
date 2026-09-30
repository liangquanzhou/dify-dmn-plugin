# Dify 1.11.1 兼容性验证

验证日期：2026-09-30。插件版本：`liangquanzhou/dmn_decision 0.1.1`。

## 结论与边界

当前基础 Tool 实现可以将 `meta.minimum_dify_version` 从 `1.17.1` 修正为 `1.11.1`，并保留 `dify-plugin==0.10.2`。这个结论来自实际 SDK 子进程协议测试，以及目标版本的真实 Go/Python 解析器验证；不是仅修改版本字段后宣称兼容。

已验证的是插件声明、基础 Tool 协议、凭据校验和输出消息。未在公司的 Dify 实例完成安装、工作流 UI 操作、数据库集成或端到端执行；也没有启动完整 Dify/daemon 服务。SDK 的其他功能（LLM 反向调用、触发器等）不属于这个插件的使用范围，不能据此推断兼容。

## 固定的官方基线

- [Dify 1.11.1](https://github.com/langgenius/dify/tree/2058186f22b4e4d4e155f380c130f4e8f21622fa)，提交 `2058186f22b4e4d4e155f380c130f4e8f21622fa`
- 该版本 [docker-compose.yaml](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/docker/docker-compose.yaml#L909-L910) 使用 `langgenius/dify-plugin-daemon:0.5.1-local`
- [plugin-daemon 0.5.1](https://github.com/langgenius/dify-plugin-daemon/tree/96b51115cb30f008bf4eda7e3787ea27d39c18e2)，提交 `96b51115cb30f008bf4eda7e3787ea27d39c18e2`
- 测试运行环境为 Linux amd64、Python 3.12、Go 1.23.3，插件使用现有锁定依赖和 SDK 0.10.2

公司的 daemon 镜像可能经过单独升级或定制；Dify 的版本号本身不能证明实际运行的 daemon 镜像。上线前请核对。

## 已完成的验证

1. 真实 SDK 子进程启动 `plugin/main.py`，使用本地安装模式，从标准输入接收与 daemon 0.5.1 `Session.Message` / `GetInvokePluginMap` 一致的请求封装
2. 使用本地 HTTP 合约桩测试凭据校验：正确凭据返回 `result: true`；被拒绝的凭据返回 `ToolProviderCredentialValidationError`，会话正常结束
3. 通过真实 SDK 执行 5 次 Tool 调用，覆盖对象、无匹配/null、字符串、列表、超出 JavaScript 安全范围的整数；检查 25 个 variable 消息、5 个 JSON 消息和全部会话结束事件
4. 用 daemon 0.5.1 原始 Go parser/validator 校验候选包的 manifest、provider、tool 声明和 SDK 启动声明；检查 `form`/`llm`、5 项 `output_schema` 和 2 项 provider credentials
5. 用 daemon 0.5.1 原始 Go wire types 校验上一步捕获的 SDK 会话封装、输出块、凭据结果及错误
6. 用 Dify 1.11.1 原始 `ToolProviderEntityWithPlugin` / `ToolInvokeMessage` Python 类解析 daemon 规范化的 provider 声明及全部 30 个输出消息
7. daemon 0.5.1 上游 `pkg/entities/plugin_entities` 单元测试通过；`pkg/entities/tool_entities` 没有自带测试，本项目测试补充了实际消息验证
8. 对下方记录的最终 `.difypkg` 字节运行 daemon 0.5.1 的真实 `NewZipPluginDecoder`、manifest validator 和 `CheckAssetsValid`，全部通过；同时断言 `Verified() == false`，符合 unsigned 状态

HTTP 合约桩只验证插件/SDK/协议链路，不代表 DMN 引擎语义或公司内网连通性。引擎单元测试和真实引擎集成测试属于仓库中的另一组测试。

### 为什么输出在 1.11.1 中有效

[Tool 参数和输出定义](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/api/core/tools/entities/tool_entities.py) 已有 `form`、`llm`、`output_schema` 和 `variable` 消息。`result` 始终包装成对象 `{"value": ...}`，所以无匹配结果为 `{"value": null}`；不会发送 1.11.1 拒绝的顶层 null variable。`matched_rule_ids` 是数组，其余独立输出为字符串。精确数字仍通过 `result_json` 保留。

[Tool 节点](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/api/core/workflow/nodes/tool/tool_node.py#L337-L354) 已处理非流式 variable 输出。这里是源码核对，不是工作流节点全栈运行测试。

[本地包安装 UI](https://github.com/langgenius/dify/blob/2058186f22b4e4d4e155f380c130f4e8f21622fa/web/app/components/plugins/install-plugin/install-from-local-package/steps/install.tsx#L107-L112) 会比较当前 Dify 版本和 `minimum_dify_version`；原来填写 `1.17.1` 会阻止 `1.11.1` 安装。

### SDK 与依赖

保留 SDK 0.10.2，不为消除版本门槛而盲目回退。daemon 0.5.1 的 [Python 环境创建逻辑](https://github.com/langgenius/dify-plugin-daemon/blob/96b51115cb30f008bf4eda7e3787ea27d39c18e2/internal/core/local_runtime/setup_python_environment.go) 同样使用 Python 3.12 和 `requirements.txt`。这不替代公司的依赖镜像、出网策略、CPU 架构、操作系统 wheel 可用性或安全漏洞扫描。安装时仍需取得锁定依赖；本次不声称已完成所有目标平台的依赖安装。

## 复现

先在受控环境中取得上述两个固定提交的官方源码。以下变量分别指向本仓库、Dify 源码和 daemon 源码；`PYTHON` 应指向安装了本插件锁定依赖的 Python 3.12 环境，`go` 应为真正的 Go 编译器。

```bash
export DMN_ROOT=/path/to/dify-dmn
export DIFY_SOURCE=/path/to/dify-1.11.1
export DAEMON_SOURCE=/path/to/dify-plugin-daemon-0.5.1
export PYTHON=/path/to/python3.12-venv/bin/python

"$PYTHON" "$DMN_ROOT/tests/compatibility/stdio_smoke.py" \
  --output /tmp/dmn-stdio-evidence.json

mkdir -p "$DAEMON_SOURCE/tests/dmncompat"
cp "$DMN_ROOT/tests/compatibility/daemon_051_test.go" \
  "$DAEMON_SOURCE/tests/dmncompat/"
cd "$DAEMON_SOURCE"
DMN_PLUGIN_ROOT="$DMN_ROOT/plugin" \
DMN_STDIO_EVIDENCE=/tmp/dmn-stdio-evidence.json \
DMN_DECLARATION_OUTPUT=/tmp/dmn-daemon-declaration.json \
DMN_PACKAGE="$DMN_ROOT/dist/liangquanzhou-dmn_decision-0.1.1-unsigned.difypkg" \
  go test -v ./tests/dmncompat

PYTHONPATH="$DIFY_SOURCE/api" "$PYTHON" \
  "$DMN_ROOT/tests/compatibility/dify_111_api_check.py" \
  --evidence /tmp/dmn-stdio-evidence.json \
  --declaration /tmp/dmn-daemon-declaration.json
```

测试只向下载的 daemon 源码添加独立测试目录，不修改其解析器。临时证据包含合成测试数据，不含公司模型、凭据或业务事实。

## 安装和上线仍需检查

- 这是私有自研插件的 unsigned 包，不是官方市场已验证插件。能被包解析器读取不代表通过可信签名验证，也不保证默认策略允许安装
- 不应为了安装而全局关闭签名验证。daemon 0.5.1 有第三方签名配置项 `THIRD_PARTY_SIGNATURE_VERIFICATION_ENABLED` 和 `THIRD_PARTY_SIGNATURE_VERIFICATION_PUBLIC_KEYS`；由管理员依公司政策管理签名和受信任公钥，保留 `FORCE_VERIFYING_SIGNATURE=true`
- Dify 1.11.1 默认 Compose 没有传入上述两个第三方签名变量；仅编辑 `.env` 不会自动把它们加入容器环境。管理员需要显式配置 daemon 服务环境与只读公钥挂载。本次没有生成签名私钥、签署包或修改公司安全设置
- 核实实际 daemon 镜像、Python 依赖下载源、架构 wheel、插件安装权限，以及 daemon 到 DMN 引擎的网络/TLS/认证连通性
- 在测试工作区安装后保存 provider credentials，新建 Tool 节点，填入 XML/decision id，并绑定前序节点的 JSON 字符串到 `facts_json`
- 分别执行命中、无匹配、非法输入和引擎拒绝认证场景；检查全部 5 项独立输出及后续节点引用。可选内嵌编辑器补丁的 UI 验收应单独完成

## 发布包记录

- 文件：`liangquanzhou-dmn_decision-0.1.1-unsigned.difypkg`
- 大小：12,575 bytes
- SHA-256：`16c5ed36b7610257b75f9ed46f59ada2ee6d9ead4bb7bd912587977b328819c1`
- 目标最低 Dify 版本：`1.11.1`
- 签名状态：unsigned，未验证签名
