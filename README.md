# Dify DMN 0.7.0 + Chrome preview 0.1.0

Use **stock Dify + the Chrome extension; no frontend patch is required**.

The Dify plugin executes JSON decision tools. The separate MV3 extension displays a read-only decision-table structure in the workflow editor. It does not edit/save tables, execute workflows, or calculate rule matches.

[中文指南](README.zh-CN.md) · [Installation](docs/INSTALL-0.7.0.zh-CN.md) · [Release notes](docs/RELEASE-0.7.0.md) · [Plugin contracts](docs/JSON-SUITE-0.7.0.md)

## Install

1. Install the original 0.7.0 `.difypkg` from the v0.7.0 Release using your deployment's approved signature and installation policy. The accepted package remains unsigned; its original candidate filename is retained to identify the exact tested bytes.
2. Extract `dmn-browser-preview-0.1.0.zip`. In Chrome's extensions page, load the directory containing `manifest.json` through your approved developer-mode distribution process.
3. Open a Dify workflow editor and explicitly activate the extension, then select a supported DMN node. Reactivate after refresh, application navigation, or browser restart. Each tab requires its own activation.

The extension only accepts `type=tool`, `provider_type=builtin`, `provider_id=liangquanzhou/dmn_decision/dmn`, and `tool_name=evaluate`. It reads the current page's `data.tool_configurations.table_json`; empty, invalid, dynamic, or unsupported data clears the old preview. Other tools in the suite are not supported by this extension.

## Evidence and compatibility

Official unmodified Dify 1.11.1 ARM64 + Chrome for Testing 155.0.8059.39 passed 30 real-MV3 checks and four plugin regression groups (eight real node executions with extension off/on). Another 37 checks used a simulated host and are separate evidence. Activation used official `Extensions.triggerAction` through the real worker, activeTab, and chrome.scripting; physical mouse input was not independently verified.

The reader depends on private React `__reactProps$…` properties. Company-customized environments and upgraded versions remain unverified. See the [public acceptance summary](browser-extension/docs/PUBLIC-ACCEPTANCE.md). Synthetic acceptance is not a production authorization or an exhaustive security audit.

## Plugin scope

The 0.7.0 suite includes explicit JSON-table profiles, typed decisions, bounded registered read-only queries, advisory plans, and a read-only structure viewer. It is not a DMN XML/FEEL engine. Existing `evaluate` FIRST/COLLECT/UNIQUE contracts and all 17 outputs are preserved. Default query connections are unconfigured and fail closed; company API integration, durable waiting/recovery, and runtime parallel orchestration are not established by this release. See [suite contracts and limits](docs/JSON-SUITE-0.7.0.md).

## Source layout

- `plugin/`: frozen 0.7.0 Python tools and viewer assets; all 40 packaged files match the accepted `.difypkg`.
- `browser-extension/`: separate 0.1.0 extension source, tests, prebuilt extension, and public documentation.
- `frontend/`: optional historical frontend integration and structure-viewer source. The frontend patch is not required for the recommended extension route.
- `tests/`, `examples/`, `scripts/`, `docs/`: synthetic fixtures, tests, packaging, contracts, and validation records.

Candidate-era documents and embedded package documentation are retained as historical records. Release packaging changes public documentation and source packaging only; plugin and extension runtime bytes are unchanged. The v0.4.1 patch route remains optional and has its own exact-baseline restrictions.
