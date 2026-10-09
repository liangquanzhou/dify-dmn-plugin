# JSON Decision Matrix for Dify · v0.4.1

A read-only field-column decision matrix for the Dify **1.11.1** Tool configuration panel: conditions and outputs are columns; rules are rows. The standard Python Tool and its v0.3.0 execution contract are unchanged.

[中文指南](README.zh-CN.md) · [Release notes and assets](docs/RELEASE-0.4.1.md) · [Installation](docs/INSTALL-0.4.1.md) · [Validation](docs/VALIDATION-0.4.1.md)

## Install v0.4.1

1. Have your administrator review the unsigned package and complete your organization's approved signing and distribution process. Keep signature verification enabled
2. For a deployment that permits the reviewed GitHub asset, open **Plugins → Install from GitHub**, enter `https://github.com/liangquanzhou/dify-dmn-plugin`, select **v0.4.1**, and choose `liangquanzhou-dmn_decision-0.4.1-unsigned.difypkg`. If policy rejects the unsigned asset, use the administrator-approved signed distribution instead; a source ZIP is not an installable plugin
3. Add **Evaluate JSON Table** to a test workflow. Set `table_json` and bind upstream `values_json`; no engine address or provider credentials are required
4. To show the matrix inside the Tool panel, separately apply and build the matching web integration from the source ZIP, following [the installation guide](docs/INSTALL-0.4.1.md). It targets exactly Dify commit `2058186f22b4e4d4e155f380c130f4e8f21622fa`

The `.difypkg` installs a standard Tool. It cannot inject React into Dify. The separately built web integration adds a read-only configuration preview, not a visual rule editor. The `dmn-decision-matrix-0.4.1-offline.html` release asset previews the same component without Node; it contains no Python runtime and does not execute rules. Old v0.1.x XML/KIE frontend patches are incompatible.

## Verified in real Docker Dify

On 2026-10-09, an isolated cloud Docker Dify 1.11.1 instance installed plugin 0.4.1, displayed the patched matrix, and completed **Start → DMN → End** from the actual UI: **3 nodes, 2.136330 seconds, 0 exceptions**. `priority` was selected; both `priority` and `standard` conditions were true. Persisted `table_json` bytes were unchanged. See the [public synthetic-test summary](docs/DOCKER-VALIDATION-0.4.1.md).

The unsigned package was tested under an explicitly approved signature-check exception in that isolated instance only. Company signing and trust requirements still apply. This verifies the synthetic flow, not a company deployment or general production acceptance.

## Execution contract retained from v0.3.0

One Tool node evaluates one custom JSON table entirely inside the plugin. No external engine, credentials or XML. Configure `table_json` as a static JSON string and bind upstream `values_json`. `FIRST` and `COLLECT` evaluate every rule; missing/unknown is distinct from false. Rule outputs are data, never code.

The package retains the existing plugin/provider identity. v0.1.x XML workflows require migration; v0.2.0 tables retain their default selection behavior. The `dmn_decision` technical name does not imply support for standard DMN or FEEL. See the [condition contract](docs/CONTRACT.md), [v0.3.0 contract migration](docs/MIGRATION-0.3.0.md), and [v0.4.1 validation scope](docs/VALIDATION-0.4.1.md).

## Additive v0.3.0 contract

Existing tables default to `unknown_policy: "compatible"` behavior. Set `unknown_policy: "strict"` **inside the table** to wait when unknown rules can alter FIRST selection or the COLLECT set. Bind `decision_status` (`matched`, `no_match`, `waiting_input`) for new workflows. Legacy matched fields still mean selected rules; `all_matches` and `condition_matched_rule_ids` report every true condition.

`model_sha256` hashes the full table using RFC 8785. Optional `expected_sha256` is a separate Tool parameter that rejects a content-version mismatch before evaluation. `table_version` retains the original-text hash. `scripts/compile_table.py` generates the static table/pin pair automatically.

All 17 outputs are separate bindable variables. The final standard JSON message retains the old nine-field aggregation to avoid duplicating new diagnostics; bind `decision_result` for the versioned new metadata. See [migration](docs/MIGRATION-0.3.0.md), [local runtime alignment](docs/LOCAL_ALIGNMENT.md), and [synthetic cross-runtime vectors](tests/vectors/v030-conformance.json).

## Source layout

- `plugin/`: pure Python evaluator, bounded JSON boundary, standard Dify provider/tool
- `examples/`: synthetic single-table fixtures
- `tests/`: evaluator, boundary and actual SDK/legacy Dify protocol checks
- `docs/`: condition contract, migration, installation/verification evidence
- `scripts/`: verification and reproducible packaging

The standard Tool needs no external engine service, Java/Maven or custom frontend build. The optional in-panel matrix requires the separate Dify web build described above. The unsigned package requires the company's normal review/signature policy. Never disable signature verification to install it.
