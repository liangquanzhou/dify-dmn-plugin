# Single JSON Decision Table for Dify

**v0.2.0: one Tool node evaluates one custom JSON table entirely inside the plugin.** No external engine, credentials or XML. Target: Dify **1.11.1**.

[中文安装和使用指南](README.zh-CN.md) · [Condition contract](docs/CONTRACT.md) · [Breaking migration](docs/MIGRATION-0.2.0.md) · [Validation scope](docs/VALIDATION.md)

Configure `table_json` as a static JSON string and bind upstream `values_json`. The supported hit policies are `FIRST` and `COLLECT`. Every rule is evaluated; missing/unknown is distinct from false. Rule outputs are data, never code. The package retains the previous plugin/provider identity for a deliberate breaking upgrade; the manifest's `dmn_decision` name does not mean v0.2.0 implements DMN or FEEL.

The `.difypkg` installs a standard Tool only. It does **not** add a visual table editor. The old v0.1.x XML/KIE frontend patches are incompatible with this version and must not be applied.

## Source layout

- `plugin/`: pure Python evaluator, bounded JSON boundary, standard Dify provider/tool
- `examples/`: synthetic single-table fixtures
- `tests/`: evaluator, boundary and actual SDK/legacy Dify protocol checks
- `docs/`: condition contract, migration, installation/verification evidence
- `scripts/`: verification and reproducible packaging

No engine service, Java/Maven, container or frontend build is required for this Tool. The unsigned package requires the company's normal review/signature policy. Never disable signature verification to install it.
