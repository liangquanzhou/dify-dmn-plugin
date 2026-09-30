# v0.3.0 验证记录

验证日期 2026-09-30，全部使用合成数据，在交付开发环境运行。未访问用户 Mac、公司源码或真实规则；未复制所比较的无 LICENSE 插件代码，也未发布本候选。

## 最终插件包

- `liangquanzhou-dmn_decision-0.3.0-unsigned.difypkg`
- 19,395 bytes，18 个文件，ZIP CRC 通过
- SHA-256：`30dde6e77640789d8dcb9fe5055a3b07309e18bfaf7a262631703f420e8750f2`
- 官方 CLI 0.6.10 打包；包内文件与冻结源码逐字一致
- 未签名；旧 daemon decoder 明确验证 `Verified()==false`
- 条件核心 `plugin/evaluator.py` 与 v0.2.0 逐字一致，v0.3.0 的 policy/hash 为外层新增逻辑

## 877 项 pytest 通过

| 范围 | 用例数 |
|---|---:|
| 原条件 evaluator | 212 |
| 原 JSON 边界 | 30 |
| SDK Tool/完整帧 | 5 |
| v0.3.0 policy（含 484 个 FIRST/COLLECT 三值排列组合） | 499 |
| RFC8785 identity/版本锁 | 17 |
| 自动 hash 编译器 | 4 |
| 跨运行时固定向量 runner | 74 |
| 固定 v0.2.0 旧 9 输出基线 | 36 |

固定对齐文件有 **73 个向量**：36 决策、11 错误、16 canonical/hash、6 pin、4 输入错误，另有 6 对 hash 不等关系。runner 74 项含一项分组/不等关系总检查。决策 expected 手工推导，canonical 文本先固定再求 hash；不由 v0.3.0 求值器重生成期望。

旧 9 输出基线来自冻结 v0.2.0，用相同合成表移除可选 policy 后捕获，带来源 hash。新默认行为逐字段比较，包括 result_json 和 table_version。独立只读审查额外运行 2,186 个默认模式差分，旧 9 字段全部相等。

Pytest 有两个上游依赖警告（gevent 导入顺序、Pydantic 旧 Config），未产生失败。

## 精确最终包与官方旧运行时

从上述 hash 的 `.difypkg` 解压后，启动真实 Python 3.12.14 / dify-plugin 0.10.2 `main.py`，使用官方 daemon 0.5.1 的 stdio 信封：

- 无凭据 validate 通过
- 13 个成功调用：旧成功路径、缺输入兜底、strict FIRST 等待/不阻塞、strict COLLECT、兼容模式，以及两种格式的同模型/版本锁
- 21 个显式错误：原 18 个坏输入/类型/语法/策略/资源限制，加非法 unknown_policy、hash 格式、hash 错配
- 221 条独立 variable、13 条旧 9 字段 JSON 聚合、35 个 session end
- 每个错误仅 error/end，无部分成功/伪 no_match；全部实际输出行小于 4 MiB
- 官方 daemon 源码：3 个本包 Go 兼容测试与 38 个官方实体 top-level 测试通过，无跳过
- 官方 Dify 1.11.1 原始 API 类接受最终包 provider（两个必填字符串+一个可选字符串、零凭据）、17 个输出和全部消息

包声明由同一个最终包 decoder 导出，stdio 证据 hash 与包字节一致，不把源码目录检查当作最终包验证。

## JCS 与传输独立复核

RFC8785 使用官方 PyPI 的 `rfc8785==0.1.4`（Trail of Bits / Apache-2.0），没有把简单的 sorted JSON 冒称 JCS。独立复核将其与 Node ECMAScript 数字序列化对比，150,000 个随机/边界 float 无差异；嵌套 UTF-16 键排序、控制字符、数值属性名、Unicode 与 hash 对照也通过。这是本次覆盖，不宣称数学证明所有浮点值。

一次兼容性审查发现：把新增字段重复放进聚合 JSON 会让旧约 4.01 MB 可发送结果增长到 4.34 MB。修复为新字段独立 variable 输出，末尾聚合仍只包含旧 9 字段。

1,000 条 COLLECT 规则复用 280 字符键的回归，18 条消息全部发送，最大真实 SDK 帧约 4,005,626 bytes，低于 4 MiB。较大的 400 字符键用例仍正确报 LIMIT_EXCEEDED，且没有任何先行成功消息。

每个新独立帧也受同样 4 MiB 限制；不能因其他帧较小而绕过。全部帧预检查，拒绝时不截断规则、输出或追溯。

## 锁定基线与复现

- [Dify 1.11.1](https://github.com/langgenius/dify/releases/tag/1.11.1)：commit `2058186f22b4e4d4e155f380c130f4e8f21622fa`
- [plugin-daemon 0.5.1](https://github.com/langgenius/dify-plugin-daemon/tree/0.5.1)：commit `96b51115cb30f008bf4eda7e3787ea27d39c18e2`
- Python 3.12.14、SDK 0.10.2、CLI 0.6.10、rfc8785 0.1.4
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785) 与 [PyPI 包/发布 hash](https://pypi.org/project/rfc8785/)

```bash
python -m pytest -q tests
python scripts/check_plugin.py
python tests/compatibility/stdio_smoke.py \
  --package dist/liangquanzhou-dmn_decision-0.3.0-unsigned.difypkg \
  --output /tmp/dmn-final-stdio-evidence.json
```

Go/API 验证需要另行取得官方准确基线源码；本包 `tests/compatibility/daemon_051_test.go` 列出环境变量，API 检查应把 `PYTHONPATH` 指向官方 `api/` 并使用从同一包导出的 provider。详细 stdout 摘要见 validation-evidence.txt。

## 尚未验证

- 公司 Dify 实际安装、签名信任、包源、管理员权限、UI 与数据库工作流
- 公司本地 JS/Code 执行器已实现本协议或已上线；本地需用同一向量验证
- 真实业务规则/输入、公司定制 daemon、并发和长期资源行为
- 可视化编辑器；本版仍仅标准 Tool，无前端扩展

内容 hash 校验不是签名或权限证明；插件仍须按公司签名策略安装。候选包可审阅与测试，不代表公司环境已验证或自动迁移完成。
