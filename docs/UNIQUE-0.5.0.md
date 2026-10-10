# UNIQUE 命中策略：0.5.0 候选扩展

本候选版本在已发布 0.4.1 的单表插件上独立增加 `hit_policy: "UNIQUE"`。未发布到 GitHub，未部署公司环境，不声称已完成其他产品的功能超集。FIRST/COLLECT 的条件语义、未知策略和输出完全保留；不是查询语言、流程引擎或 FEEL/DMN XML 实现。

## 输入不变，增加一种可选策略

```json
{
  "id": "synthetic-unique",
  "hit_policy": "UNIQUE",
  "rules": [
    {"id":"small","when":{"lt":["size",10]},"output":{"route":"small"}},
    {"id":"large","when":{"gte":["size",10]},"output":{"route":"large"}}
  ]
}
```

仍只接受静态 `table_json`、上游 `values_json`，以及可选的独立 `expected_sha256`。`unknown_policy` 仍只允许省略、`compatible` 或 `strict`，非法显式值仍报错。没有新的必填字段、输入格式或算子。

UNIQUE 的含义是**能够确认恰好一条规则为 true 时才允许选中**。不同规则即使输出相同也构成冲突；这不是允许同值多命中的 ANY 策略。不按规则顺序挑第一条，不合并结果，不执行 output。

## 四种结果

先完成全部规则校验与条件求值，再按以下优先级决定：

| 确定 true 数量 | 最终条件为 UNKNOWN 的规则 | decision_status / status | 最终选中 |
|---|---|---|---|
| 至少 2 条 | 任意 | `conflict` | 空 |
| 0 或 1 条 | 至少 1 条 | `waiting_input` | 空 |
| 恰好 1 条 | 无 | `matched` | 唯一 true 规则 |
| 0 条 | 无 | `no_match` | 空 |

UNIQUE 对 `compatible`、`strict` 及省略策略均采用这一保守语义。`unknown_policy` 控制的 FIRST/COLLECT 历史行为不变，但不能用 `compatible` 绕过 UNIQUE 的唯一性保证。

- `[true, UNKNOWN]` 和 `[UNKNOWN, true]` 都等待：另一条可能在补齐输入后也命中
- `[true, true, UNKNOWN]` 已经确定冲突，补齐未知无法消除两个现有 true；无需等待，阻塞未知列表为空，但未知规则仍保留供诊断
- 空表或全 false 为 `no_match`
- 按整条规则的最终条件判断 UNKNOWN。`all(false, unknown)` 是 false，不阻塞；`any(true, unknown)` 是 true
- 不做规则之间的逻辑求解或互斥证明；只要有未决规则，就保守等待。UNKNOWN 可能来自缺值、非法业务金额或不完整约束，不必然能靠“补一个变量”解决
- 所有规则及 all/any 子表达式仍完整求值。确定冲突或等待后，后续的结构/类型错误仍使整个 Tool 调用失败，不返回部分成功

## 输出与调用方迁移

保留原来的 **17 个独立变量、末尾 9 字段 JSON 聚合消息**。`result` 仍仅包含 `matched` 和 `evaluations`；没有增加结构字段。

- `conflict`、`waiting_input` 时：`matched`、`result.matched`、`outputs`、`matched_rule_ids`、`selected_rule_ids` 全部为空
- `all_matches`、`condition_matched_rule_ids` 保留所有已确定为 true 的原始规则；这是诊断信息，不能当作可执行结果
- `evaluations` 保留全部规则与追溯；`unknown_rule_ids` 保留全部最终 UNKNOWN 规则
- 仅 `waiting_input` 的 `blocking_unknown_rule_ids` 等于全部 UNKNOWN ID；其余状态为空
- UNIQUE 的 `status` 与 `decision_status` 始终一致，二者增加 `conflict`
- `decision_result` 的字段集合不变。FIRST/COLLECT 继续 `schema_version: "0.3.0"`；UNIQUE 使用 `"0.5.0"` 标识新增状态语义。该版本号是结果能力版本，不是输入结构切换
- hash 仍覆盖完整表。更改 FIRST 为 UNIQUE 会改变 `model_sha256`，必须重新审批/生成预期 hash；不自动解除版本锁

接入 UNIQUE 的调用方必须显式处理四种状态：`matched` 才消费选中输出；`waiting_input` 补充/校验信息；`no_match` 进入原无命中分支；`conflict` 进入规则冲突处理或人工复核。不能把未知的新状态默认为成功，也不能退化到 FIRST。原有 FIRST/COLLECT 消费者无需改动；启用 UNIQUE 才需要增加冲突分支。

`plugin/evaluator.py` 的底层 `evaluate_table` 也不会输出临时或任意 UNIQUE 胜者；完整冲突/等待诊断由 `io_contract.invoke_table` 返回。新集成应使用该公开 Tool 边界。

## 可复用验证材料

- `tests/vectors/v050-unique-conformance.json`：23 个手工推导结果向量、4 个错误向量，覆盖相同输出仍冲突、未知前后位置、未知消解、规则内三值逻辑、原始输出与错误不短路
- `tests/test_unique_policy.py`：0–5 条规则的全部 364 种 true/false/UNKNOWN 排列，在默认/compatible/strict 三种配置下测试；并验证 SDK 17变量/9字段消息与内容锁
- `tests/vectors/v041-output-baseline.json`：从已发布提交 `3e3eca1157f713380a678478bfe218d31ec3056a` 捕获的 12 组 FIRST/COLLECT 完整17字段 golden，包含 result_json 原文；不使用待测实现更新预期
- 原 `v020-default-baseline.json` 和 `v030-conformance.json` 保持不变
- 前端只读预览接受并显示 UNIQUE 与四分支说明，不在浏览器执行规则

当前验证结果与候选产物记录在 [VALIDATION-0.5.0-CANDIDATE.md](VALIDATION-0.5.0-CANDIDATE.md)。0.4.1 的真实 Docker 工作流验收仅属于旧版本，不能算作本候选的真实安装或公司部署验证。
