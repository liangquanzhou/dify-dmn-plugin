# v0.2.0 验证记录

验证日期：2026-09-30。全部运行在交付开发环境，用合成规则和数据；没有访问公司环境、公司源码或真实业务规则。

## 冻结插件包

- 文件：`liangquanzhou-dmn_decision-0.2.0-unsigned.difypkg`
- 大小：16,414 bytes
- SHA-256：`154c415b5d66ca87bcc284bd2eeb9a8fed42ae7b9aeb615a0cb5733a92f18856`
- 官方 Dify CLI 0.6.10 成功打包；16 个包内文件，ZIP CRC 正常
- 最终包解压后的 Python 源码与冻结源码逐字一致
- 包不含引擎客户端、XML、Java、前端补丁、签名私钥或业务凭据
- 包**未签名**；老 daemon decoder 测试也明确断言 `Verified()==false`

## 已通过

1. **246 项 pytest**：212 项 evaluator + 30 项 JSON 边界 + 4 项实际 SDK Tool 外壳
   - 全部指定条件算子、FIRST/COLLECT 全量求值、三值逻辑、引用和点号完整键、空结构
   - 严格 bool/number/string 类型、对象引用相等、不深比较、缺失优先级、不短路隐藏错误
   - discount_share 分金额/舍入边界、constraint_set 特殊聚合、all_values null
   - 追溯路径生成、笛卡尔超过 32 降级标记、256 alternatives 资源边界
   - 原规则/output/载荷数据不执行不改写，错误不包含实际输入值
   - JSON 重复键/非法 Unicode/非有限/不安全整数/大小/深度/节点/规则上限
   - 完整 SDK 聚合帧超限检查及在首次 yield 前拒绝、转义字符扩张
2. **官方 SDK 注册**：manifest、空凭据 provider、两个参数及 Tool class 成功加载
3. **从上述最终 `.difypkg` 解压后启动真实 SDK 子进程**：Python 3.12 + dify-plugin 0.10.2，以 plugin-daemon 0.5.1 的实际 stdio 信封调用
   - 1 次无凭据 validate 成功
   - 6 次成功调用：FIRST、COLLECT、无命中、missing/null unknown、混合原始 outputs、含点号键
   - 18 次明确错误：坏输入、非法表达式/策略/id、大小深度规则限制及超大输出帧等
   - 共 54 条 variable、6 条 JSON、25 个 session end；每个错误只返回 error/end，**没有部分成功或 no_match 流**
   - 所有实际 stdout 行都检查不超过 4 MiB
4. **实际旧 daemon 源码验证**：3 个本包 Go 兼容测试全部通过、无 skip；38 个官方实体 top-level 测试通过
   - 声明解析、完整 stdio wire、同一 hash 最终包解码与资源检查
   - provider 声明从最终包 decoder 导出，而非以源码目录替代
5. **实际 Dify 1.11.1 API 类验证**：从原始 API 源码导入 `ToolProviderEntityWithPlugin` / `ToolInvokeMessage`，接受上述最终包声明及全部消息，任意混合数组与内部 null 保持原样
6. **独立只读复核**：再次运行 246 pytest、SDK 注册及最终包 stdio；额外 10,000 个确定性随机合成输入无未捕获异常，51,362 项独立 Decimal 金额舍入/三值检查通过
   - 合法 19,000 元素数组 × 1,000 个 contains 规则的单次最坏扫描样例约 6.34 秒，仅为当前开发环境观察，不是吞吐/并发承诺

pytest 有 2 个 SDK/依赖上游警告（gevent 导入顺序和 Pydantic 旧 Config 风格），未形成测试失败。

## 输出帧回归

一个合法 COLLECT 表：1,000 条规则复用同一 400 字符变量名，table 约 441 KB、result JSON 约 1.80 MB，但含全部绑定字段和 result_json 的聚合 JSON 超过 5.45 MB。旧 daemon 默认扫描上限为 5 MiB，仅限制 result 不够。

修复为使用 SDK 的真实 `StreamOutputMessage` / `SessionMessage` / `model_dump_json()` 序列化，对**每条最终消息**按 4 MiB 上限（含 UTF-8、转义、session id、换行）做预检查，全部通过后才开始输出。超限明确 `LIMIT_EXCEEDED`。该案例已在单元、真实 SDK 和独立复核中验证。

## 锁定的官方基线

- [Dify 1.11.1](https://github.com/langgenius/dify/releases/tag/1.11.1)，commit `2058186f22b4e4d4e155f380c130f4e8f21622fa`
- [plugin-daemon 0.5.1](https://github.com/langgenius/dify-plugin-daemon/tree/0.5.1)，commit `96b51115cb30f008bf4eda7e3787ea27d39c18e2`
- Python 3.12、SDK 0.10.2、CLI 0.6.10
- v0.2.0 保留 Dify 1.11.1 minimum，未依赖新版本节点类型或后端改造

## 可重复命令

```bash
python -m pytest -q tests
python scripts/check_plugin.py
python tests/compatibility/stdio_smoke.py \
  --package dist/liangquanzhou-dmn_decision-0.2.0-unsigned.difypkg \
  --output /tmp/dmn-final-stdio-evidence.json
```

Go 和 API 验证需要另行取得**官方准确基线源码**。将本包 `tests/compatibility/daemon_051_test.go` 放入 daemon 的测试目录后，设置源码/证据/最终包路径；详细环境变量见该测试文件。API 检查应将 `PYTHONPATH` 指向官方 Dify 1.11.1 的 `api/`，运行 `tests/compatibility/dify_111_api_check.py --help` 查看证据参数。不能把简化的替代模型当成这一步的通过。

## 尚未验证

- 公司 Dify 的真实安装、签名信任政策、依赖下载/私有包源、管理员权限、数据库和工作流 UI
- 真实业务表及公司定制 plugin-daemon 的差异
- 浏览器中的编辑、发布、导入/导出及生产并发/长期资源表现
- 全量 Dify 前后端部署；本版没有可视化编辑器实现

协议模型、SDK和包解码通过不表示已在公司环境安装成功，也不表示未签名包会通过公司的签名策略。
