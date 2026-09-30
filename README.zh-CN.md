# Dify DMN 决策工具：首个可运行交付包

版本：0.1.0 · 构建日期：2026-09-30

这是一个带真实 DMN 执行能力的集成起点，供公司测试环境验证；需要在目标 Dify 版本上验收后才能投入生产。它包含：

1. **标准 Dify Tool 插件**：接收上游 JSON，执行节点内的 DMN XML，向下游返回结构化结果
2. **Dify 前端补丁**：只为这个 Tool 显示 dmn-js 编辑器；工作流运行时仍使用原生 Tool
3. **附带的私有 DMN 引擎服务源码**：Apache KIE DMN 10.2.0，负责真实 FEEL/DMN 求值。无需假定公司已经有规则服务

`.difypkg` 只安装第 1 部分。嵌入编辑器需构建公司自己的 Dify Web 镜像；实际执行需部署第 3 部分。单独安装插件不会自动安装 Java 或修改 Dify 前端。

## 1. 版本与边界

| 部件 | 固定版本 |
|---|---|
| Dify 前端基线 | 1.17.1 |
| Dify commit | `8387590ace4a094de812b7847fc6a4c3a27cd52b` |
| Dify Plugin SDK | 0.10.2 |
| 打包 CLI | 0.6.10 |
| 插件 Python | 3.12 |
| DMN 引擎 | Apache KIE 10.2.0 |
| 引擎 Java | 21 |
| dmn-js | 17.12.2 |

该 Dify 基线的完整前端构建要求 Node 24.20.0+（v24）及 pnpm 12.3.4；此处只运行独立 harness，未完成整个 Dify Web 构建。

部署者必须先确认目标 Dify 的精确版本。前端安装脚本对其他版本拒绝自动套用；先适配再验收。插件 manifest 的 minimum_dify_version 是最低声明，不等于后续所有版本已经测试。

执行服务使用成熟的 Apache KIE 引擎，不包含自制的“DMN 子集解释器”。本适配层有明确的安全范围：单文件 DMN、FEEL、所选 decision；不开放 Java/脚本执行、外部导入等能力。详见 `docs/engine.md`。成熟引擎不代表本 HTTP 适配层支持 DMN 标准的每个构造。

## 2. 文件布局

- `plugin/`：可由官方 CLI 打包的标准 Tool 源码
- `engine/`：Java 引擎适配服务、Maven 测试与 Dockerfile
- `frontend/`：版本锁定的前端适配文件、补丁安装器与浏览器验证环境
- `examples/eligibility.dmn`：标准 DMN XML 示例，仅使用虚构业务数据
- `tests/`：插件契约、异常与真实服务联调测试
- `scripts/`：插件注册检查、验证与打包脚本
- `docs/VALIDATION.md`：此次实际执行过的检查及未验证范围
- `THIRD_PARTY_NOTICES.md`：依赖与许可证说明
- 单独提供的 `liangquanzhou-dmn_decision-0.1.0-unsigned.difypkg`：未签名插件包；重新打包时写入 `dist/`

## 3. 在隔离环境启动引擎

先安装 Java 21 和 Maven 3.9.x，使用公司批准的官方来源。以下命令仅在你选择的测试环境执行：

```bash
cd engine
mvn --batch-mode test package
# 开发模式只监听回环地址，不带令牌。不要暴露到局域网/公网
DMN_ENV=development DMN_BIND_HOST=127.0.0.1 PORT=8080 \
  java -jar target/dmn-engine-service.jar
```

容器入口默认生产模式，要求管理员配置令牌。Dockerfile 是构建配方，本次没有 Docker daemon，未运行镜像构建。服务不自带 TLS：生产中放在公司内部网络与 TLS 网关后，只允许 plugin-daemon 访问。按公司规范配置机密，令牌不要写入源码、XML、工作流 DSL、提交记录或聊天。

Dify 的 plugin-daemon 与引擎必须网络互通。不同容器的 `localhost` 不是同一机器：在同一受控网络下，可给插件填写 `http://dmn-engine:8080`；跨不可信网络必须使用 HTTPS。HTTP 只适用于受控隔离网络，由公司管理员判断。

引擎启动、环境变量、限制和错误码以 `docs/engine.md` 为准。此服务每次编译模型，优先简洁与隔离，没有跨请求模型缓存；大模型/高吞吐需另行压测与容量设计。

## 4. 插件审查、签名、安装

先阅读插件请求的权限与 `plugin/PRIVACY.md`。插件没有申请 LLM、应用调用、工具反向调用、持久化存储或端点注册权限。出站请求只发往管理员配置的引擎；模型和业务事实会发送给该引擎。数值 JSON token 限 256 字符，十进制指数/数量级/scale 限于 ±10,000；facts 层级限 32、值节点总数限 10,000，避免极端输入耗尽资源。

本包是**未签名**的开发交付。由公司管理员审查源码和依赖后，用公司批准的签名机制签名；保持 Dify 的签名校验开启。不要为了安装关闭 `FORCE_VERIFYING_SIGNATURE`。

如需重打包：

```bash
# 使用已从官方发布页验证来源的 CLI 0.6.10
/path/to/dify plugin package ./plugin -o ./dist/liangquanzhou-dmn_decision-0.1.0-unsigned.difypkg
# 下面由管理员用已批准、已存在的签名私钥执行
/path/to/dify signature sign ./dist/liangquanzhou-dmn_decision-0.1.0-unsigned.difypkg \
  -p /secure/path/company.private.pem
/path/to/dify signature verify ./dist/liangquanzhou-dmn_decision-0.1.0-unsigned.signed.difypkg \
  -p /approved/path/company.public.pem
```

管理员在 daemon 中配置受信公钥，签名验证保持开启。生成/配置新签名密钥、建立信任与调整网络都属于公司管理员的上线操作，本交付没有替你执行。

在测试 Workspace：Plugins → Install Plugin → Via Local File，选择管理员签名后的包。配置提供方：

- **企业内部 DMN 引擎地址**：仅 origin，例如 `https://dmn-engine.internal`，不带路径、查询参数、URL 账号密码
- **引擎访问令牌**：通过 Dify 的 secret-input 安全填写，与服务端配置一致

保存凭证会调用 `/health` 验证连通性与授权。健康检查不发送业务模型或事实。插件 HTTP 客户端验证 TLS，不跟随重定向，不使用进程级 HTTP 代理变量；企业代理/私有 CA 需按公司网络规范适配，不能简单关掉 TLS 验证。

## 5. 安装前端编辑器

前端是源码适配，不是另建一种后端节点。遵循 `frontend/README.md`，在公司测试 Dify 源码 checkout 的锁定版本上运行补丁安装器，然后用 Dify 自己的包管理器安装依赖并构建 Web 镜像。

补丁只匹配：

```text
provider_type = builtin
provider_id   = liangquanzhou/dmn_decision/dmn
tool_name     = evaluate
```

其他 Tool 仍显示原生面板。若公司重新命名插件 author/name/provider，必须同步更新身份匹配和相应测试，否则不会显示专用编辑器。

对本基线，XML 实际存到节点 `tool_configurations.model_xml` 的 `{type:'constant', value:XML}` 中；`decision_id` 同样属于静态配置。`facts_json` 使用原生 `tool_parameters` 和变量选择器。编辑器的保存动作调用 Dify 既有配置更新函数，随后仍依赖 Dify 既有草稿保存/发布流程。没有用 localStorage 代替工作流持久化。

保留 dmn-js 的 bpmn.io 标识、链接和许可证，不允许遮挡或去除水印。

## 6. 第一个工作流

无需 LLM 即可测试：Start → Code → DMN Tool → End。

1. Start 提供数字 `age` 和 `risk_score`
2. Code 节点把上游对象变成 JSON 字符串，例如：

```python
import json

def main(age: int, risk_score: int) -> dict:
    return {"facts_json": json.dumps({"age": age, "risk_score": risk_score})}
```

3. 添加 **DMN 决策 → 执行 DMN** Tool
4. 导入 `examples/eligibility.dmn`，显式保存到节点；决策 ID 填 `eligibility`
5. 把 Code 的 `facts_json` 绑定到 Tool 的 **业务输入 JSON**，不要填对象类型
6. 运行 `{age:25, risk_score:30}`，期待 `status=matched`、原生结果 `{eligible:true, reason:"low_risk_adult"}`、规则 `rule_eligible`
7. End 可输出 `result_json`，或读取 `result.value` 中的字段

下游输出：

| 名称 | 类型 | 说明 |
|---|---|---|
| `status` | string | `matched` 或 `no_match` |
| `result` | object | `{value: 可安全传递的DMN结果}`，详见数值精度规则 |
| `result_json` | string | 原生结果的 JSON 字符串，包括数组、标量或 `null` |
| `matched_rule_ids` | array[string] | 引擎匹配事件提供的规则 ID |
| `model_version` | string | 被执行的准确 XML UTF-8 内容 SHA-256 |

**数值精度**：`result_json` 是精确 JSON 结果，保留高精度十进制数。`result.value` 为适应 Dify/浏览器 JSON 处理，将十进制数及超过 JavaScript 安全整数范围的整数转为字符串；普通安全整数、布尔、字符串保持原类型。下游需要金融/精密计算时，从 `result_json` 使用支持 Decimal 的解析器读取，不要经 JavaScript Number 或 Python float 中转。这保证传输不额外舍入；Apache KIE 的 FEEL 字面量/运算仍遵循 Decimal128（34 位有效数字）语义，不承诺无限精度计算。输入 `facts_json` 也应在上游生成时保留精度；插件无法恢复上游已舍入的值。

无命中是成功结果，`status=no_match`，不是基础设施错误。输入缺失、类型错误、UNIQUE 重叠、非法 XML、错误 decision_id、引擎超时会使 Tool 报错，交给 Dify 原生错误处理分支。不要把所有异常兜底成“拒绝/通过”，避免掩盖规则或基础设施故障。

`model_version` 是内容指纹，不是审批版本号。即使 XML 语义不变，只改缩进也会改变它。重开/导出应保留准确快照；编辑器显式保存时序列化可能改变格式。

## 7. 复现验证

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r plugin/requirements.txt -r requirements-dev.txt
python -m pytest -q tests/test_plugin.py
python scripts/check_plugin.py
(cd engine && mvn --batch-mode test package)
(cd frontend && npm ci && npm test && npm run typecheck && npm run build)
# 浏览器检查另需 Playwright 的 Chromium；按 frontend/README.md 执行
```

`plugin/requirements.txt` 固定了此次验证的 Python 依赖版本；前端 harness 附 package-lock，Java 直接依赖固定于 pom。Maven 传递依赖和容器基础镜像仍需公司自己的锁定、扫描与镜像管理，不声称供应链构建完全可复现。

真实联调脚本、浏览器测试命令与实际结果见 `docs/VALIDATION.md`。测试 harness 不是完整 Dify 集成环境：未验收公司 Dify 的数据库持久化、DSL 导入导出、发布后执行、API 调用或多人编辑。

## 8. 公司上线前的验收与回滚

- 确认准确 Dify 版本、部署方式、私有插件安装权限和定制 Web 镜像发布权限
- 保留旧 Web 镜像 digest、现有插件版本、工作流 DSL 与公司正常备份
- 在测试环境验收：编辑 → 显式保存 → 关面板重开 → 刷新 → 发布 → 执行 → DSL 导出/导入；检查 XML hash 与 facts 绑定不变
- 验收成功、无命中、缺少输入、类型错误、多命中冲突、非法 XML、未知决策、凭证失效、网络超时，以及原有其他 Tool 不受影响
- 验收插件凭证不出现在 DSL、节点模型或普通日志中；Dify 自身 trace 可能保存 facts/result，按公司数据政策设置
- 基于实际规则规模做执行时间、并发、内存、超时、恶意/意外复杂 FEEL 模型测试；只授权可信编辑者创建模型
- 审核依赖漏洞、许可证、供应链和签名；生产必须令牌、网络隔离及适当 TLS
- 回滚：恢复旧 Web 镜像与已保留插件版本/工作流，确认执行链路；别直接删除未备份的模型快照
- 后续升级 Dify：重新检查 Tool 配置数据结构与面板钩子，运行全部回归，不自动绕过版本检查

## 9. 官方来源

- [Dify 1.17.1](https://github.com/langgenius/dify/releases/tag/1.17.1)
- [锁定的 Tool 面板](https://github.com/langgenius/dify/blob/8387590ace4a094de812b7847fc6a4c3a27cd52b/web/app/components/workflow/nodes/tool/panel.tsx)
- [Dify Tool 开发](https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/tool-plugin)
- [官方 CLI 0.6.10](https://github.com/langgenius/dify-plugin-daemon/releases/tag/0.6.10)
- [第三方签名](https://docs.dify.ai/en/develop-plugin/publishing/standards/third-party-signature-verification)
- [Apache KIE DMN](https://kie.apache.org/drools/dmn/)
- [Apache KIE 10.2.0](https://github.com/apache/incubator-kie/releases/tag/10.2.0)
- [dmn-js](https://github.com/bpmn-io/dmn-js)
- [bpmn.io 许可证](https://bpmn.io/license/)
