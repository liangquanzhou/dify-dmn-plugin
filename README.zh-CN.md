# Dify 单张 JSON 决策表插件 v0.2.0

一个 Dify Tool 节点执行一张自定义 JSON 决策表。全部求值在插件内部完成，**不需要引擎地址、访问令牌、Java 服务或 XML**。适配目标是 Dify **1.11.1**。

本版只提供标准 Tool 和原生参数配置；**不自带可视化表格编辑器**。内嵌可视化编辑仍需要单独的 Dify 前端扩展。本版不包含旧的 dmn-js/XML 补丁。若此前部署过旧补丁，请先按[迁移说明](docs/MIGRATION-0.2.0.md)撤回。

## 安装

1. 在测试 Workspace 安装 `liangquanzhou-dmn_decision-0.2.0-unsigned.difypkg`。本交付未签名，若企业开启签名要求，先由管理员审查并使用公司批准的签名密钥签名；保持签名校验开启
2. 使用 Dify 的 Plugins → Install Plugin → Via Local File 选择经管理员批准的包。若随后通过 GitHub 发布，需要选择 **v0.2.0** Release 中同版本的 `.difypkg` asset；仅提交源码不能用于 GitHub 插件安装
3. 插件列表应显示“JSON 决策表”，无需填写提供方凭据
4. 工作流添加“执行 JSON 决策表”Tool。参数只有 `table_json`（静态 JSON 表）和 `values_json`（绑定上游 JSON 字符串）

插件技术身份仍为 `liangquanzhou/dmn_decision` / provider `dmn` / tool `evaluate`。这用于有意识地升级现有插件，并不表示 v0.2.0 支持标准 DMN。升级旧 0.1.x 是破坏性变更，先备份并新建测试节点，不能让生产旧 XML 工作流直接使用新版。

## 五分钟合成测试

将 `examples/table.json` 全部复制到 `table_json`。它是单张表，不是含多表的方案。

将以下内容以字符串传给 `values_json`：

```json
{"customer.level":"gold","item_count":4}
```

预期：
- `status` 为 `matched`
- `matched_rule_ids` 为 `["priority"]`
- `outputs` 为 `[{"route":"priority"}]`
- `evaluations` 包含两条规则，条件都是 `true`。FIRST 只选择第一条，但不会跳过第二条求值

把 `hit_policy` 改为 `COLLECT`，则两条规则均入选，保持原数组顺序。`output` 只作为数据返回，既不执行其中的表达式，也不自动合并。

上游 Code 节点可以把对象序列化成字符串：

```python
import json

def main(level: str, item_count: int) -> dict:
    return {"values_json": json.dumps({"customer.level": level, "item_count": item_count}, ensure_ascii=False)}
```

在 Tool 的 `values_json` 中绑定该输出。`"customer.level"` 是完整变量名，不会读取 `{"customer":{"level":...}}`。没有值就缺省该键或使用 `null`，不要用空字符串、0 或 false 代替未知。

## 输入和输出

完整定义见 [条件协议](docs/CONTRACT.md)。

- 表结构：`{id, hit_policy: "FIRST" | "COLLECT", rules: [{id, when, output?, 载荷?, ...}]}`
- 必须是单张表，表 id 和规则 id 非空，规则 id 唯一
- 条件 `true` / `false` / `null` 表示真 / 假 / 未知，只有 `true` 才命中
- `FIRST`、`COLLECT` 都对全部规则求值；无命中是正常结果，错误会使节点失败
- `result` 与 `result_json` 表示原始决策结果 `{matched,evaluations}`
- `matched` 原样保留选中规则，含 `output`、`载荷` 和其他数据
- `outputs` 按选中顺序取 `output`；该字段缺失时放 `null`，可从 `matched` 分辨缺失和显式 null
- `matched_rule_ids`、`status`、`table_id`、`table_version` 可直接绑定
- `evaluations` 为每条规则提供条件结果和变量依赖追溯。这些字段不是已验证外部证据

Dify 1.11.1 对任意类型混合 `outputs` 数组可能显示 `Array[Unknown]`，这是其类型展示。需要稳定字符串接口时使用 `result_json` 并在后续 Code 节点显式解析。

## 签名和依赖

运行环境 Python 3.12，官方 SDK 固定为 `dify-plugin==0.10.2`。完整依赖锁定在 `plugin/requirements.txt`，安装时 Dify plugin-daemon 需要访问公司批准的 Python 包源。正常决策执行不请求外部网络。

若管理员已持有批准的签名密钥，可用官方 CLI：

```bash
/path/to/dify signature sign ./liangquanzhou-dmn_decision-0.2.0-unsigned.difypkg \
  -p /secure/path/company.private.pem
/path/to/dify signature verify ./liangquanzhou-dmn_decision-0.2.0-unsigned.signed.difypkg \
  -p /approved/path/company.public.pem
```

管理员须按公司的 Dify/plugin-daemon 信任策略配置受信公钥。Dify 1.11.1 默认 Compose 不会自动转发第三方签名相关变量；需要启用企业第三方签名时，由管理员审查并显式配置 daemon 环境和公钥挂载。不要关闭 `FORCE_VERIFYING_SIGNATURE`。本交付没有生成密钥、建立信任、配置公司服务器或安装软件到公司环境。

## 开发验证和打包

在已获批准的 Python 3.12 开发环境：

```bash
python -m pip install -r plugin/requirements.txt -r requirements-dev.txt
PYTHON=python bash scripts/verify.sh
DIFY_CLI=/path/to/dify bash scripts/package_plugin.sh
python scripts/package_source.py
```

实际检查和未验证范围见 [验证记录](docs/VALIDATION.md)。不把源码模型/SDK协议验证表述为公司环境安装成功。生产采用前仍需依赖审查、签名、公司 Dify 安装和真实工作流验收。

## 官方参考

- [Dify 1.11.1](https://github.com/langgenius/dify/releases/tag/1.11.1)
- [Dify Tool 插件开发](https://docs.dify.ai/en/develop-plugin/dev-guides-and-walkthroughs/tool-plugin)
- [通过 GitHub Release 分发](https://docs.dify.ai/en/develop-plugin/publishing/marketplace-listing/release-to-individual-github-repo)
- [第三方签名验证](https://docs.dify.ai/en/develop-plugin/publishing/standards/third-party-signature-verification)
- [官方 Dify plugin SDK](https://github.com/langgenius/dify-plugin-sdks)
