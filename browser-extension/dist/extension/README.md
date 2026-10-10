# Dify DMN Matrix Browser Preview 0.1.0

Read-only MV3 extension for Dify 1.11.1 and the exact `liangquanzhou/dmn_decision/dmn` / `evaluate` tool. Real extension acceptance on official unmodified Dify completed on 2026-10-10: 30/30 checks and 4/4 plugin regression groups (8 node invocations).

Chrome's official `Extensions.triggerAction` simulated toolbar activation through the genuine worker, activeTab and chrome.scripting paths. Physical mouse clicks and OS shortcuts were not independently verified. No company instance was accessed.

See [Chinese installation guide](README.zh-CN.md), [validation](docs/VALIDATION.md), and [runtime equality](docs/RUNTIME-INTEGRITY.json). Load the extracted final extension ZIP directory containing manifest.json from chrome://extensions using the organization's approved method. No Dify frontend patch or replacement web image is required. The Dify tool plugin .difypkg and this browser extension ZIP serve different purposes.

Activate explicitly on each page/tab. React private DOM props are a compatibility risk; refresh, application navigation and browser restart require reactivation. Reads current `tool_configurations.table_json`; no workflow writes, execution, credential reads, telemetry or network implementation. Invalid, empty, dynamic or unsupported values clear stale output. Only activeTab+scripting permissions.

This final packaging changes documentation only. Runtime files and source/tests are byte-identical to the accepted candidate. Source build: npm ci, npm run typecheck, npm run build, npm test. Historical SCRIPT-ONLY evidence must not be confused with real MV3 evidence.
