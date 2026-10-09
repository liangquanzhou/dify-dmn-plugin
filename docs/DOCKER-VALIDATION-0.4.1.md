# v0.4.1 Docker Dify 实测摘要

2026-10-09 在独立云端 Debian 12 虚拟机中使用真实 Docker Engine 29.9.0 / Compose 5.6.0 完成验证。Dify API 与原版 web 均为 1.11.1，前端补丁基线为 `2058186f22b4e4d4e155f380c130f4e8f21622fa`。

## 已完成

- 安装 `liangquanzhou/dmn_decision` 0.4.1，安装包 SHA-256 为 `790baba6bac2950cc99be22a8defc8ad4ea694fd80822737fbf3b414e357ccaf`
- 保存同一个 Start → Evaluate JSON Table → End 工作流
- 原版 web 显示原生 JSON 设置，没有矩阵；替换配套补丁 web 后，节点内显示 2 行只读矩阵，可展开完整条件、组合逻辑和输出字段
- 在真实 Dify UI 点击 Test Run：成功，3 个节点，2.136330 秒，0 异常
- 输入 `{"customer.level":"gold","item_count":4}`，使用仓库 `examples/table.json`
- `decision_status=matched`；最终选择 `priority`；条件为 true 的规则为 `priority` 与 `standard`
- 展开、关闭与执行后，持久化 `table_json` 原文字节不变
- 测试浏览器开启 Chromium 沙箱；运行完成后停止专用测试环境

这不是托管服务或公司环境部署。仅验收上述合成工作流、配置持久化、原版/补丁展示与真实执行；未覆盖全部 Dify 功能、LLM/RAG、生产负载、公司登录或实际业务数据。

## 独立复现

1. 在组织批准的隔离 Docker 环境准备官方 Dify 1.11.1，服务端口仅暴露至 localhost，使用全新的测试数据
2. 按管理员批准的插件审查/签名流程安装本版 `.difypkg`；生产和公司环境保持签名校验开启
3. 创建 Start → Evaluate JSON Table → End，Start 提供字符串 `values_json`；Tool 静态 `table_json` 填入 `examples/table.json` 全文，动态 `values_json` 绑定 Start 输出；End 绑定 Tool 的 `decision_status`、`matched_rule_ids` 和 `condition_matched_rule_ids`
4. 以以上合成输入执行并检查结果
5. 按 [安装说明](INSTALL-0.4.1.md) 在独立的固定基线源码应用前端安装器，执行类型检查、测试、构建并重建 web 镜像；只替换测试 web 服务，比较同一已保存节点的配置预览
6. 展开/关闭并再次执行，对比保存前后的原始 `table_json`

本次云端隔离实例曾获得单独批准，仅为测试此未签名包临时关闭该实例的插件签名校验。这不构成公司、共享或生产环境的安装建议；发布资产不包含该测试实例的设置、账号、密码、会话或磁盘。

完整原始测试日志与截图用于验收。公共源码仅保留此结果摘要、测试代码和合成夹具，不附带会话、容器日志或未经审查的运行环境快照。
