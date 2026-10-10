# 0.7.0 JSON suite candidate

This is an unpublished, independently implemented follow-on to the frozen 0.6.0 candidate, targeting the latest builtin JSON capabilities. It is **not yet a verified functional superset** and is not a full DMN/FEEL implementation. No remote push, release, company connection or production deployment is part of this candidate.

The accepted scope is fixed to four blocks: JSON decisions/UNIQUE/typed source quality and freshness; configured read-only queries with bounded batch/pagination/timeout/missing handling; bindings/advisory stage plans/static validation behind the existing controller boundary; and read-only Dify field matrices plus Phase → Step → Node overview. Remaining work closes defects, regression evidence and artifacts within those blocks. It does not add new product modules or expand toward unrestricted reference parity.

## Tools and explicit profiles

| Tool | Contract | Purpose |
|---|---|---|
| `evaluate` | Existing flat-key table, FIRST/COLLECT/UNIQUE | Unchanged existing semantics and 17 bindable outputs |
| `evaluate_json_table` | Explicit `json-table-v1` | Object paths, missing versus known null, JSON deep/type-sensitive equality, string ordering, nine operators and conservative UNKNOWN |
| `evaluate_decision` | Typed `service-decision-table-v1` within architecture.v2 | One fixed typed decision, result templates, state/data/intent reduction and NodeResult |
| `query_local` | Two fixed fixture capabilities | Clearly marked SYNTHETIC ticket/order test responses |
| `execute_query` | Fixed architecture.v2 QUERY NodeResult or explicit original capability request | Static registered read-only operations, declared dependency bindings/collection merge and online trusted-host policy; fails closed without deployment |
| `execute_json_plan` | Explicit `json-plan-v1` advisory adapter | LOCATE or P1–P5 deterministic dependency plan over fixture queries and JSON-table models |

The separate Endpoint serves a read-only Phase → Step → Node viewer. It does not run workflows or mutate imported definitions. See [viewer guide](STRUCTURE-VIEWER.md).

Existing FIRST/COLLECT defaults, flat dotted keys, missing/null-as-UNKNOWN, expression syntax and all 17 old outputs are retained. Choosing a new tool is an explicit profile change. Do not convert between the profiles by changing the tool name alone.

### JSON table profile

`table_json` and `inputs_json` accept a native object or a single JSON object string. Double encoding is rejected. Table and input budgets are each 256 KiB, depth 64, 128 rules and 32 conditions per rule. Paths contain 1–16 object keys. Array indexes are not object paths, and dots have no special meaning. Duplicate/dangerous keys, nonfinite/unsafe numbers, cycles and invalid Unicode fail.

The exact table fields are `format`, `id`, `version`, `hit_policy`, `rules`. Each rule has `id`, `when` (a conjunctive condition array) and `output`. Each condition has `path`, `op`, `value`. Operators are `eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`, `exists`, `is_null`.

FIRST blocks only on unknown rules before its first true rule. COLLECT blocks on any unknown. Added UNIQUE reports `FAILED/UNIQUE_HIT_CONFLICT` for multiple true rules, even with the same output; zero or one true plus unknown waits. Conflict takes priority over unknown. This projection intentionally differs from the original `evaluate` tool's branchable `conflict` status.

Read `results.status` first: `SUCCEEDED`, `WAITING_INPUT`, `FAILED`. `outcome` distinguishes `MATCHED`, `NO_MATCH`, `UNKNOWN`. A matched null output still has matched/selected rule IDs. No-match FIRST returns null; no-match COLLECT returns an empty array. Technical failure clears selected output. `trace` covers every rule and condition without copying input values. Optional expected digest binds canonical RFC8785 content only.

### Typed decision and trusted sources

Static fields: definition bundle, fixed node reference, required expected definition digest. Dynamic fields: typed `parameter_snapshot`, `runtime_snapshot` and run/subject/activation/authorization-reference/as-of context. `runtime_snapshot` is currently accepted as an opaque object; it is not authenticated or used as execution evidence. See the complete [synthetic invocation](../examples/json-suite/typed-decision-request.json).

The evaluator validates declared parameter types, required records, nullable known values and allowed qualities. A non-known record must carry null; it is never a known null or a confirmed false. Wrong types cannot hide behind UNKNOWN. Value predicates on non-known records remain unknown; quality predicates may explicitly inspect quality. Records require source references, but references alone are not authentication.

Snapshots must match the fixed node, subject, definition and explicit reference time. Future observations and stale/type-error diagnostics are rejected. Old-snapshot reuse requires trusted evidence. The default credential-free SDK mode is `CONTENT_ONLY_NOT_AUTHORIZATION`; it cannot establish online activation, tenant access, source truth or maximum age. It never dispatches an intent.

A trusted Python host may pass a policy returning `VerifiedDecisionSources`. The callback must authenticate sources and recheck current activation/permissions before returning. The evaluator then compares the verified context and records, rebinds every fixed source and enforces maximum observation age. `PARAMETER` bindings forward full records; `VALUE` binds a known value whose record/provenance was independently checked by the host. JSON cannot select or instantiate this policy. No credentials or grants are created by this candidate.

FIRST/COLLECT/UNIQUE share conservative selection. Explicit no-match templates are required for a successful empty outcome. Reduction rejects conflicting states, data facts, route choices and intent targets/parameters; equal facts/intents deduplicate. Data is reduced before action input bindings are resolved. Selected intents must match the selected control path; an unselected template cannot supply a missing action. Any failure returns a null decision and empty convenience state/data/actions.

### Host boundaries

The query adapter's default Dify installation has no registered deployment and performs no IO. A digest pins content, never online permission. Its fixed host transport is optional; generic host callbacks remain responsible for their own transport safety. See [query and plan contract](JSON-QUERY-PLAN.md) for precise limits, loopback evidence and transport restrictions.

The plan tool is SYNTHETIC / ADVISORY_ONLY. It is a compatibility boundary for testing and mapping existing flows, not a replacement runtime. Existing local P1–P7 business truth and Dify/controller mappings remain authoritative and unchanged. A local successful plan does not establish equivalence to unavailable business repositories.

## Static graph and query additions

The typed boundary now validates paired and nested PARALLEL/ALL_SUCCESS regions, technical failure convergence, definite sources, cross-Step destinations, bounded reentry declarations and WAIT outcome/correlation declarations. It still evaluates only the fixed invoked node. A valid graph does not dispatch nodes or authenticate an activation. See [typed graph conformance](TYPED-GRAPH-CONFORMANCE.md).

The registered query adapter supports declared literal/input/context/prior-API bindings, transitive dependency proof, batch-local pagination, explicit collection identity/conflict handling, and offline bounded Draft 2020-12 validation. A trusted Python host can compile reviewed query-plan/operation-registry assets, register the fixed QUERY node and authenticate sources/selected intents for every online authorization check. The default SDK installation still has no connection and fails closed. See [query conformance](QUERY-CONFORMANCE.md) for the exact supported profile and schema/transport limits.

The fixed HTTP transport can perform literal-IP HTTPS GET or explicitly host-registered read-only POST. Endpoint, method and permitted static headers are deployment configuration, never dynamic Tool input. Declaring POST read-only is a trusted deployment assertion, not something this plugin can independently prove about a remote service. No retry or redirect is performed.

## Remaining acceptance gates and scope limits

- Complete target-schema acceptance is not established. Resource bounds, conservative definite-source/path analysis and the documented offline schema safety profile can reject inputs accepted by a broader target. These restrictions are not counted as covered behavior
- Exact five-tool envelope/name compatibility is distinct from functional coverage. The explicit architecture QUERY entry is implemented; all adapter fields and result projections still require acceptance against the chosen caller contract
- Production Dify/controller registration, company API schemas and live authorization are unavailable. The default has no deployment and performs no IO; SYNTHETIC fixtures are not a substitute
- Existing local P1–P7 business rules and their GoldenCase corpus are unavailable in this cloud checkout. The advisory plan does not establish equivalence to that repository
- Fresh exact-package 0.7.0 SDK, browser and isolated real Dify acceptance are recorded separately in [candidate validation](VALIDATION-0.7.0-CANDIDATE.md). The preserved 0.6.0 freeze and all earlier evidence remain version-specific
- The viewer is display-only. Its separate Endpoint does not remove the Dify web-patch installation needed for our original in-panel matrix
- No reference-repository code/tests/schemas were copied or executed. Independent acceptance vectors do not imply an exhaustive cross-implementation certificate

No independent XML/FEEL engine or reference workflow runtime is included. Durable waiting, callback identity/deduplication, business state, action dispatch, recovery and reentry execution belong to the existing host/controller integration. A later valid callback may start a new Dify run from verified business state; that is not native continuation of an old Dify checkpoint. This candidate makes no durable-resume claim for Dify 1.11.1.

## Reference provenance

The public interface target is `binhuhu/dify_dmn_plugin` at `561a15efa2a086c93373dc7fbd3fbf88e46a48c4`: [builtin three-tool contracts](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/builtin-0.3.0.md), [typed node design](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/dsl-v0.4.md), [viewer contract](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/structure-viewer.md). No license was present in the pinned reference checkout. This implementation uses public interface names and behaviors, with original implementation and independently designed synthetic tests.
