# 验证记录 · 2026-09-30

## 已通过

- Python 3.12.14 / Dify Plugin SDK 0.10.2：83 项插件单元/契约测试
- 真实 SDK 公共 `Tool.invoke()` → HTTP → Java 21 / Apache KIE 10.2.0 standalone JAR：8 项端到端联调测试
- Java 服务真实 HTTP/KIE 集成：15 项，失败 0、错误 0、跳过 0
- SDK `PluginRegistration` 实际加载 manifest、provider 和 evaluate Tool 成功
- 官方 Dify CLI 0.6.10 打包成功，生成真实 `.difypkg`，检查含 15 个预期文件；不含私钥、真实 `.env`、缓存、Java 二进制或 node_modules
- Python compileall 与 pip dependency check 通过
- Maven shaded JAR 打包、独立进程 `/health` 和 `/evaluate` smoke 通过
- 服务生产模式未配置令牌时退出并拒绝启动；本地开发模式仅为隔离测试

## 覆盖范围

成功命中、无命中、缺少/null 输入、输入类型错误、UNIQUE 多规则冲突、FIRST/COLLECT 引擎语义、FEEL 列表表达式、非法 XML、未知决策、DTD/XXE/外部引用/脚本/扩展拒绝、认证失败、HTTP 方法与 Content-Type、JSON 重复键/尾随内容、输入结构/尺寸/数值边界、超时、重定向、压缩响应拒绝、响应尺寸、错误脱敏、精确高精度数字传输、Dify 可安全序列化输出、准确 XML SHA-256。

插件精度回归在传输层不会先转 float；实际 FEEL 计算仍遵循上游 KIE Decimal128 语义。未声称无限精度或运行了完整 DMN TCK。

## 可复现命令

```bash
python -m pytest -q tests/test_plugin.py tests/test_integration.py
python scripts/check_plugin.py
mvn -f engine/pom.xml test package
```

运行 Python 真实联调测试前先构建 Java JAR；缺少 JAR 时该测试会明确 skip，不能把 skip 当通过。此次交付前已构建 JAR，以上 8 项实际执行且全部通过。

此次 pytest 输出有 2 项来自 SDK/依赖的告警：gevent 导入顺序的 MonkeyPatchWarning、Pydantic 类 Config 弃用告警。它们未导致本套测试失败，但不能据此推断公司并发生产环境已获验证。

## 尚未验证/不作承诺

- 目标部署的 Dify 版本、插件 daemon 配置、私有签名信任、网络权限与部署方式需由部署者核实
- 此记录不包含部署者自己的 Dify 中安装、发布、执行或保存真实工作流的验收
- 未运行完整 Dify Web 构建、完整 API/worker/database 栈或正式 DSL 导入导出验收
- 未构建/运行 Docker 镜像：本环境没有 Docker daemon
- 没有签名私钥；`.difypkg` 未签名、未获得 Marketplace 审核
- 未做生产容量/渗透测试、完整依赖漏洞审计、许可证法务审批
- HTTP 超时/连接限制不等于中断 FEEL 求值的硬执行超时；模型应来自可信编辑者。针对不可信模型的进程隔离/硬超时属于进一步生产加固

前端验证见后续记录与 `frontend/README.md`。编辑器 harness 使用真实 dmn-js 与实际适配组件，但不代替完整 Dify 持久化验收。

## 前端当前结果

- TypeScript 检查通过
- 5 项契约测试通过：精确身份匹配、配置封装与 JSON/DSL 形态 roundtrip、大小/不安全 XML 拒绝、草稿作用域、前后端示例模型一致性
- Vite 生产 harness 构建通过（真实 dmn-js 依赖与编辑器组件）
- 另外 6 项真实 dmn-js DOM 模拟测试通过：XML 导入/导出/显式保存、非法 XML 保留、只读模式、未保存草稿重开/重置、外部变更冲突保护
- Dify 1.17.1 精确 Git checkout 的补丁 dry-run / apply / 所有输出 hash / 重复执行幂等 / reverse / 回滚后干净工作区 / 修改文件拒绝 / 错误 commit 拒绝均通过
- 实际 Chromium 验收未完成：此环境浏览器进程无法创建所需进程 socket；云浏览器也拒绝访问本地开发地址。未生成或伪造浏览器截图
- 完整公司 Dify 的真实浏览器操作、发布/刷新/持久化、DSL 导入导出仍必须验收

## GitHub 发布命名空间回归

发布目标 liangquanzhou/dify-dmn-plugin，插件 author、provider 与前端精确匹配均同步到 liangquanzhou。重新执行 83 项插件测试、11 项前端测试、SDK 注册、前端 typecheck/build、补丁 apply/幂等/reverse/干净树检查，全部通过。插件已用 CLI 0.6.10 重新打包；仍未签名。
