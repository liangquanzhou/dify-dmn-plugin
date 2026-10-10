# Install the unpublished 0.7.0 candidate

This is an unsigned test candidate, not a published release. Its exact package SHA, test status and remaining gates are in [candidate validation](VALIDATION-0.7.0-CANDIDATE.md). Do not substitute evidence from 0.4.1 or 0.6.0.

## Standard plugin

1. Have an administrator review the source, pinned dependencies, unsigned package and deployment policy. Keep company signature verification enabled; use your approved signing/distribution process if the unsigned package is not permitted
2. In an authorized Dify 1.11.1 test environment, install `liangquanzhou-dmn_decision-0.7.0-candidate-unsigned.difypkg` through the plugin package installation flow. The source ZIP is not an installable plugin
3. Preserve existing `evaluate` nodes and their 17 variable bindings. FIRST/COLLECT retain 0.3.0 contract semantics; UNIQUE retains the conservative 0.5.0 contract and requires explicit matched/no_match/waiting_input/conflict branching
4. Choose added tools explicitly. `evaluate_json_table` uses `json-table-v1`, `evaluate_decision` uses a fixed typed architecture node, and `execute_query` uses either its fixed five-field node envelope or the original registered-capability request. Switching tool names alone is not a lossless profile migration
5. Branch on the authoritative status before consuming outputs. Typed/query failures clear business outputs; a null `results.outputs` may project as `{}` in the convenience Dify variable because Dify 1.11.1 forbids top-level null variables

No provider credential or external engine is required. Default `execute_query` has no trusted deployment and must return `QUERY_CONNECTION_NOT_CONFIGURED`; it must not silently use fixture responses. `query_local` and `execute_json_plan` are explicitly SYNTHETIC/ADVISORY_ONLY. Real registered APIs, source authentication, online authorization and company GoldenCases require a separately approved host integration, not dynamic URL/header/credential fields in tool JSON.

## Read-only Dify field matrix

The plugin package cannot inject React into Dify. Apply the separate source integration to exactly Dify commit `2058186f22b4e4d4e155f380c130f4e8f21622fa`:

```sh
python frontend/integration/apply.py /path/to/dify --check
python frontend/integration/apply.py /path/to/dify
```

Then run the target Dify web checks and a production build using your deployment process. The installer rejects modified baselines, partial patches, symlink destinations and differing existing component files. Preserve your previous approved build for rollback. This is a read-only preview of the original table JSON, not a visual rule editor.

The generated `dmn-decision-matrix-0.7.0-candidate-offline.html` previews the same matrix without installing Node or Python. It does not execute decisions.

## Read-only structure viewer

The separate Endpoint serves only bundled assets. Create an Endpoint instance in the authorized host and use the host-issued instance URL with its trailing `/`; ordinary workflow/share URLs are not this viewer. For local viewing, open the source package's `plugin/viewer_static/offline.html`, or the separately named `dmn-structure-viewer-0.7.0-candidate-offline.html` copy.

Importing a local architecture/structure JSON file is browser-memory-only. No upload, persistence, action execution or company connection occurs. The Endpoint viewer does not replace the web patch needed for the original in-panel matrix. See [viewer contract](STRUCTURE-VIEWER.md) for accepted envelopes and limits.

## Upgrade, rollback and production boundaries

The existing plugin/provider identity is retained, but full production upgrade/downgrade acceptance and rollback are not established by synthetic candidate checks. Back up the approved plugin/configuration and test your actual workflows before changing a shared deployment. v0.1.x XML/KIE workflows remain incompatible and are not automatically migrated.

Do not interpret a valid static graph, content digest, source reference or successful synthetic workflow as production authorization, live source truth, durable waiting/recovery, or alignment with an unavailable company controller. No company deployment is included in this delivery.
