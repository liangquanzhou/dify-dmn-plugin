# Single JSON Decision Table for Dify

**v0.3.0: one Tool node evaluates one custom JSON table entirely inside the plugin.** No external engine, credentials or XML. Target: Dify **1.11.1**.

[中文安装和使用指南](README.zh-CN.md) · [Condition contract](docs/CONTRACT.md) · [0.3.0 migration](docs/MIGRATION-0.3.0.md) · [Validation scope](docs/VALIDATION.md)

Configure `table_json` as a static JSON string and bind upstream `values_json`. The supported hit policies are `FIRST` and `COLLECT`. Every rule is evaluated; missing/unknown is distinct from false. Rule outputs are data, never code. The package retains the previous plugin/provider identity; 0.1.x XML workflows require migration, while 0.2.0 tables retain their default selection behavior; the manifest's `dmn_decision` name does not mean v0.3.0 implements DMN or FEEL.

The `.difypkg` installs a standard Tool only. It does **not** add a visual table editor. The old v0.1.x XML/KIE frontend patches are incompatible with this version and must not be applied.

## Additive v0.3.0 contract

Existing tables default to `unknown_policy: "compatible"` behavior. Set `unknown_policy: "strict"` **inside the table** to wait when unknown rules can alter FIRST selection or the COLLECT set. Bind `decision_status` (`matched`, `no_match`, `waiting_input`) for new workflows. Legacy matched fields still mean selected rules; `all_matches` and `condition_matched_rule_ids` report every true condition.

`model_sha256` hashes the full table using RFC 8785. Optional `expected_sha256` is a separate Tool parameter that rejects a content-version mismatch before evaluation. `table_version` retains the original-text hash. `scripts/compile_table.py` generates the static table/pin pair automatically.

All 17 outputs are separate bindable variables. The final standard JSON message retains the old nine-field aggregation to avoid duplicating new diagnostics; bind `decision_result` for the versioned new metadata. See [migration](docs/MIGRATION-0.3.0.md), [local runtime alignment](docs/LOCAL_ALIGNMENT.md), and [synthetic cross-runtime vectors](tests/vectors/v030-conformance.json).

## Install from GitHub

1. In a test Workspace, open **Plugins → Install from GitHub**
2. Enter `https://github.com/liangquanzhou/dify-dmn-plugin`
3. Select **v0.3.0**, then its only `.difypkg` asset: `liangquanzhou-dmn_decision-0.3.0-unsigned.difypkg`. Do not select an older release or a source ZIP
4. Add **Evaluate JSON Table** to your workflow. Set `table_json` and bind `values_json`; no engine address or provider credentials are required

The release asset is unsigned. If company policy rejects it, ask the administrator to review and use the approved signing/distribution process; keep signature verification enabled. Local-file installation is an administrator fallback **only if that option is available in your Dify deployment**.

## Source layout

- `plugin/`: pure Python evaluator, bounded JSON boundary, standard Dify provider/tool
- `examples/`: synthetic single-table fixtures
- `tests/`: evaluator, boundary and actual SDK/legacy Dify protocol checks
- `docs/`: condition contract, migration, installation/verification evidence
- `scripts/`: verification and reproducible packaging

No engine service, Java/Maven, container or frontend build is required for this Tool. The unsigned package requires the company's normal review/signature policy. Never disable signature verification to install it.
