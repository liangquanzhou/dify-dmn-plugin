# Controlled query capability conformance

This is an independently implemented, unpublished capability delta. The reference is the public interface at `binhuhu/dify_dmn_plugin@561a15efa2a086c93373dc7fbd3fbf88e46a48c4`. No reference implementation, tests, or schema files were copied into this project or executed. The frozen 0.6 candidate is unchanged.

## What is now implemented

| Area | Implemented behavior | Independent evidence |
|---|---|---|
| Declared API arguments | Literal, invocation `inputs`, host `context`, and prior `api` bindings; API paths start at `{data: <operation aggregate>}` | Chain, fan-in, transitive dependency, literal/null/context tests |
| Dependency validation | Unique operation IDs, stable topological execution, missing/cyclic dependency rejection; every API source must be an explicit transitive dependency | Invalid source and dependency tests fail before first transport |
| Output projection | Capability `output_bindings` selects only declared complete operation results; internal API fields need not appear in the public output schema | Multi-API join and public-plan compiler tests |
| Batching | Bind once, split a declared array, send only the current slice; validate each actual API-call input; empty batch performs zero calls | Per-batch payload, empty collection, per-call `maxItems` tests |
| Pagination | Each batch begins with a fresh cursor and fresh cycle detector; global page/call/byte/deadline budgets remain shared | Reused cursor token across separate batches succeeds; repeated cursor within a batch fails |
| Local truncation | Per-batch page and per-operation batch limits mark that operation incomplete; incomplete results cannot supply dependencies; independent operations continue while global budget remains | Both independent declaration orders, optional/required outputs, blocked dependents, coincident local/global exhaustion |
| Collections | Explicit ordered JSON sets or record-identity sets, stable first-seen order; identical records deduplicate, same identity/different record fails | Cross-page/batch merge, numeric versus boolean identity, missing/null key, conflict tests |
| Schemas | General Draft 2020-12 validation within the bounds below, replacing the old types/properties-only subset | Boolean schemas, missing type, union, const/enum, numeric/string/array/object constraints, combinators, conditionals, local refs, recursive data, evaluated-property/item tests |
| Public technical plan | Pure `compile_query_plan` converts registered query-plan.v2 and operation-registry.v2 into the same bounded engine | Raw-byte versus canonical-lock distinction; actual compiled chain invocation; invalid plan tests |
| Fixed QUERY node | The five architecture-v2 tool fields, fixed node registration, shared complete-definition validation, independent NodeIO rebinding, current context/intent checks, NodeResult projection | `tests/test_json_query_node.py` and `examples/json-suite/query-node-request.json` |
| HTTP reads | Host-registered fixed-IP GET or explicitly reviewed read-only POST; bounded typed JSON POST body; static pinned headers | Actual synthetic loopback GET/POST, redirect/status/no-retry, source/size/deadline/cancellation tests |
| Existing protection | No configuration through tool JSON; every source/subject/asset check and online authorization gate remains; hardened endpoint/TLS/watchdog behavior retained | All original 115 query regressions remain enabled |

## Registered technical plan contract

`QueryOperation.input_bindings` is optional only for backwards compatibility. When present, the operation must have registered `input_schema` and `output_schema`. Only mapped arguments reach `payload.inputs`; the full invocation input object is not implicitly forwarded. A binding is one `literal` or one `from` object, with optional `source_format=VALUE|PARAMETER`. The latter preserves the selected JSON value or record without coercion or quality promotion. Paths are explicit key/index arrays, not dotted expressions. There is no evaluator, URL resolver, code importer, or implicit source lookup.

`api` references name `node_id` and select paths under `data`. `inputs` and `context` select their own roots. Direct and transitive dependency references are permitted after static proof. Full source values remain absent from trace. A declared API binding missing at execution blocks that operation rather than substituting null; independent operations can still supply other outputs.

`QueryCapability.output_bindings` declares final projection. Required output gaps yield `UNKNOWN` and `outputs=null`. Optional gaps are omitted and listed in `trace.unknown_outputs`; a successful available subset is explicitly partial in the node envelope. Incomplete API aggregates never become downstream facts. Legacy capabilities without output projection retain their all-or-nothing flat-fact semantics.

Schemas apply to the complete API result aggregate, so an array's `minItems` can be met by multiple pages. Actual batched request slices are checked against the API input schema immediately before their respective calls. Capability input validation and static schema/dependency/source registration are completed before any call. A later dependency's value cannot be type-validated until the earlier API has returned, but is checked before the dependent call.

### Collection identity

`QueryCollection(path, identity_paths=())` is a trusted, digest-bound declaration. Collection paths must be distinct and nonoverlapping. The default identity is the complete JSON value, giving ordered-set semantics. With identity paths, every record must provide each scalar non-null identity component. Compound identities are supported. Numeric `1` and `1.0` have the same canonical identity; boolean `true` is different. Equal records deduplicate. Different records under the same declared identity return `QUERY_FACT_CONFLICT`; missing/invalid identity returns `QUERY_COLLECTION_IDENTITY`. No first/last-wins update or field-level conflict resolution occurs.

Whole-value identity cannot infer that two records with different fields denote the same business object. The host must register business identity paths when that distinction matters. Other fields retain exact-fact conflict checks. Collection declarations, including identities and limits, are covered by the native query-plan digest.

### Public plan compilation is trusted setup, not a new tool

`compile_query_plan` accepts the public query-plan.v2 core: schema/version identity, read-only marker, example marker, technical budget, nodes with operation references/dependencies/input bindings, outputs, and registry reference. It also accepts operation metadata `pagination={parameter,items_key,max_pages}` and `batch={parameter,max_items,max_batches}`. These set local limits in the same engine. Paged items default to explicit whole-value ordered-set collection semantics; reviewed `operation_options.collections` can declare record identities. Options cannot contradict the locked batch or pagination policy.

The registry contains static read-only operation declarations, backend labels, and input/output schemas. Trusted Python registration supplies actual transport objects and authenticated source identities; labels and file paths do not load implementations. `max_concurrency` is a ceiling: execution is serial and does not promise parallel throughput. Only `inputs`, `context`, and `api` roots are available within technical plans. The broader shared binding schema also enumerates node/event/decision/parameters roots; this compiler does not implicitly load those roots. They must be resolved by the host's fixed-node input binding step. This is a documented acceptance boundary, not complete shared-schema parity.

For file locks, supply original UTF-8 bytes. `SHA256_BYTES` is computed from exactly those bytes, including whitespace. A native object is explicitly encoded with RFC8785 because it has no original file-byte representation. These raw asset hashes are distinct from native capability/registry canonical hashes. Neither type grants authority.

## Fixed architecture-v2 node boundary

The SDK accepts exactly one of:

1. Legacy `request_json` with its capability/context/three canonical locks
2. `definition_bundle_json`, `node_ref`, `expected_definition_sha256`, `inputs_json`, `execution_context_json`

Mixing the routes fails. The five-field route uses `QueryNodeDeployment` and `QueryNodeRegistration`, registered in trusted Python only. It validates the whole architecture with the shared validator and selects exactly the configured QUERY node for validation; it never follows control edges or executes another node. Before I/O, the selected QUERY must declare all executor exits: `ok`, `blocked`, `error`, `unknown`, and `cancelled`. The registered capability, definition digest, declared capability schemas, original query-plan and operation-registry byte locks, normalized operation metadata/source identities, and fixed transport assets are compared before I/O.

`verify_node(prepared)` must return `VerifiedQueryNode` after authenticating the caller, subject, current run/node/attempt/activation, permissions, source identities, source quality/freshness and revocation. Independent trusted roots are rebound through the node's declared input bindings and compared to submitted parameters. Submitted `source_refs` and the complete context must match host evidence. When `requires_intent=true`, the actual selected QUERY intent must name this node and identical parameters. The adapter cannot synthesize this evidence from a request, hash or signature. Both node verification and the underlying `QueryDeployment.authorize` are rechecked before/after each call and before publication.

Some capabilities identify subjects directly in a parameter; those use `subject_input` and retain the direct equality check. For capabilities whose ticket/order parameter differs from the host's broader subject scope, trusted registration can set `subject_input=None`: independent NodeIO rebinding, online host scope authorization, and response-envelope subject matching remain mandatory. This is not a way for a caller to disable scope checks.

A success projects `outputs.query={outcome,data,completeness,provenance}`. Failures project `outputs.query=null`. There is no generic truthiness-based absence inference. A successful `{}` and a successful `{tickets: []}` both mean `FOUND` unless trusted registration declares the exact `not_found_when` output shape. That declaration is schema-checked and covered by the native capability-plan digest; matching it produces `NOT_FOUND` only when no incomplete operations or optional unknown outputs remain. Public interface documents enumerate the outcomes but do not establish a generic nested-collection emptiness rule, so this explicit adapter policy is not claimed as full target outcome parity. Timeout/incomplete results cannot become `NOT_FOUND`. Multiple source observations are listed independently with `atomic_snapshot=false`. No transport callback or timestamp list establishes an atomic snapshot.

The SDK's six convenience variables and JSON result come from the same result object. Existing legacy `results.outputs=null` still projects `{}` into the top-level Dify `outputs` VARIABLE. The node route keeps an object `outputs={query:null}`, which also avoids an illegal top-level null VARIABLE. A successful invocation followed by a failed one never retains prior data.

Every response observation is checked when received and retained for freshness checks after each online authorization guard, including the final guard after output schema and response-size validation. Earlier pages or operations cannot become stale while a fresh last response masks them. A clock rollback making an observation future-dated also fails closed with `UNKNOWN/QUERY_STALE_RESPONSE` and null outputs. Locked operation schemas are compared by canonical JSON digest, preserving the difference between JSON booleans and numbers.

## Schema acceptance and resource bounds

Pinned `jsonschema==4.25.1` supplies Draft 2020-12 validation. This is not a claim that installing a library proves complete reference compatibility; the reference dependency pin is different and full differential conformance has not been run.

- Native object and boolean schemas, `{}`, omitted `type`, unions, const/enum, standard numeric/string/array/object constraints, applicators and local references are accepted within budgets
- Only Draft 2020-12 is selected. `$ref`/`$dynamicRef` are local fragments; referenced schemas are resolved during preflight. Missing references and remote/file references fail before I/O, including unused declared schema branches
- A deny-all `referencing.Registry` prevents implicit retrieval even if a reference escapes ordinary preflight
- Product JSON bounds remain 256 KiB per schema/asset object, 64 JSON nesting levels and 100,000 values; schema nesting/reference traversal is at most 32
- Wrapped keyword/search validation is bounded to 100,000 steps, depth 128 and one second per value-validation pass; regex searches have a separate maximum 50 ms timeout. Draft annotation helpers that recurse outside those wrappers also remain subject to Python's finite recursion guard, mapped to `QUERY_SCHEMA_BUDGET_EXCEEDED`. Unproductive recursion and combinator expansion fail closed. Some valid but expensive schemas therefore exceed this supported profile
- Nested explicit same-draft `$schema` declarations retain the invocation's bounded validator class and shared deadline/work/depth state; they cannot switch to an unbounded stock validator. Recursive local schemas that descend through bounded data are tested. Unproductive reference cycles and pathological regexes return `QUERY_SCHEMA_BUDGET_EXCEEDED`; no schema worker or background computation continues
- Regex evaluation uses the already-pinned `regex` module for pattern, pattern-property and extra-property matching. This is a Python-regex profile, not proof of every ECMAScript regex edge case
- `format`, including date-time, URI and UUID, is an annotation in the standard default vocabulary; it is not silently advertised as an assertion. Node context and response observation timestamps are separately checked by timezone-aware parsers and source-age policy. No optional format packages or network format checks are installed
- Unknown schema keywords remain annotations per JSON Schema. The legacy `nullable` extension is retained for existing registered capabilities; it is separate from standard type unions

Remote schemas, other schema drafts, unrestricted recursive/combinator cost, full ECMAScript regex parity, and asserted optional format vocabularies remain explicit acceptance gaps. Invalid schema, invalid data, and budget exhaustion are distinct; none produces usable query outputs.

## Transport boundary

`FixedHttpReadTransport` remains a direct literal-IP adapter. Real destinations require verified HTTPS and a globally routable unicast address. Only explicitly synthetic loopback permits HTTP. Multicast, unspecified/reserved/private/link-local/metadata destinations, DNS, proxies, URL credentials/query/fragment, redirect following and retries remain forbidden.

GET remains the default and retains its previous transport-asset digest when unused extensions are absent. POST requires trusted `method='POST', post_read_only=True`; this declaration records a host review requirement, not proof that an arbitrary server method is safe. Its bounded UTF-8 JSON body includes only statically selected input, cursor and batch fields. Protocol/connection/proxy headers cannot be overridden. Other headers must be immutable host registration; only a digest of their values appears in the transport asset. No credential is read from tool parameters, environment variables, cookies or ambient stores. Secret provisioning and authenticated endpoint behavior remain unimplemented/unverified integration work; tests use only synthetic non-secret headers.

The existing watchdog, numeric socket connection, redirect refusal, TLS verification, TLS-wrapper ownership before handshake, response byte accounting and cancellation behavior are shared by GET and POST. Arbitrary custom transport and online-policy callbacks must still enforce bounded I/O themselves; the engine cannot interrupt a callback that never returns.

## Evidence and remaining work

Focused local command:

```sh
PYTHONPATH=plugin .venv/bin/python -m pytest -q tests/test_json_query.py tests/test_json_query_node.py
```

At the implementation checkpoint: **213 passed**, no skips. This count includes the original 115 query tests; it is not additive to later whole-suite totals. Tests contact only synthetic loopback servers or controlled mocks. No real company endpoint, authentication, native Dify branching/cancellation, durable WAIT/resume/recovery, company GoldenCase acceptance, deployment, release, upgrade or rollback is established by these tests. `execute_json_plan`, controllers, action dispatchers and existing business rules are not replaced.

Public sources used as interface descriptions:

- [Query plan schema](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/schemas/query-plan.schema.json)
- [Node invocation schema](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/schemas/node-invocation.schema.json)
- [Node result schema](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/schemas/node-result.schema.json)
- [Node and binding contracts](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/docs/03_contracts.md)
- [RC5 pagination behavior and licensing boundary](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/docs/releases/v0.4.0-rc5.md)
