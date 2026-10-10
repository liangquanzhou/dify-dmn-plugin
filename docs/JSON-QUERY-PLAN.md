# Read-only query and advisory plan adapters

These are independently written extensions based on public interface descriptions. No reference implementation or reference tests were copied or executed. They preserve the existing `evaluate` profile. They do **not** establish five-tool wire compatibility, equivalence to company P1–P7 rules, or production acceptance.

## Entry points

| Tool | Input | Authority |
|---|---|---|
| `query_local` | `request_json` with `capability_id`, `parameters` | Fixed SYNTHETIC fixtures only |
| `execute_json_plan` | `request_json` with `plan`, `models`, `inputs`; optional complete-request `expected_sha256` | SYNTHETIC / ADVISORY_ONLY |
| `execute_query` | Pinned-capability `request_json` or fixed architecture-v2 five-field route | Trusted Python host registration and online authorization required |

Each request accepts a native object or one JSON object string. Double decoding, duplicate keys, prototype-related keys, invalid Unicode, nonfinite/unsafe integer values, cycles and excessive nesting are rejected. Failures never reuse previous successful outputs. SDK wrappers emit `results` plus status/output variables and a JSON message; each checks actual SDK frame size before yielding anything. Dify 1.11.1 forbids null as a top-level VARIABLE: the convenience `outputs` variable is therefore `{}` when authoritative `results.outputs` is null. The `results` envelope and JSON message preserve the null, and consumers must branch on status before treating convenience outputs as facts.

## Synthetic queries

Only `demo.ticket_lookup` and `demo.order_lookup` exist. Their sole input is `ticket_id` or `order_id` respectively. Each result carries `provenance.environment=SYNTHETIC`, `mock=true`, `advisory_only=true` and `source=bundled-fixture`. There is no network, mutation, sleep or business-system lookup.

- `T-100`, `T-200`, `T-300` return corresponding `O-100`, `O-200`, `O-300`
- `O-100` is `CONFIRMED_ABSENT`, `O-200` is `CONFIRMED_PRESENT`, `O-300` is `UNKNOWN`; their evidence is `KNOWN`, `KNOWN`, `UNKNOWN`
- Other identifiers return `SUCCEEDED / NOT_FOUND`, with `outputs=null`
- Missing/null/empty identifiers return `WAITING_INPUT / UNKNOWN`
- `T-UNKNOWN` / `O-UNKNOWN` return `WAITING_INPUT / UNKNOWN`
- `T-TIMEOUT` / `O-TIMEOUT` and `T-ERROR` / `O-ERROR` return `FAILED / TIMEOUT` and `FAILED / ERROR`

Timeout and error fixtures are simulated outcomes, not measured timeouts. Wrong identifier types and unexpected parameters fail. The canonical response includes `status`, `outcome`, `outputs`, `error`, contract identifiers and explicit provenance. This implementation also exposes `execution_status`, `output_port`, `query_status`, diagnostics and trace; exact equivalence of all rival envelope fields has not been established.

See [`synthetic-query-request.json`](../examples/json-suite/synthetic-query-request.json).

## Trusted query API

The default SDK deployment is `None`. A valid request then returns `BLOCKED / QUERY_CONNECTION_NOT_CONFIGURED`, with no I/O and no synthetic fallback. JSON cannot configure a connection, import code, change credentials or install transports. No environment-file loader, signature-only shortcut or ambient credential lookup exists.

A trusted embedding host constructs `QueryDeployment`, registered `QueryCapability` objects, fixed `QueryOperation` technical DAGs, the operation registry, transport callables and `authorize(request)`. It can call `execute_query(request, deployment=deployment)`. A reviewed SDK host integration could inject `json_query.SDK_DEPLOYMENT` at startup. There is no tool parameter that does so.

The independent request contract is:

```json
{
  "capability_id": "registered.read_only_capability",
  "definition_sha256": "<64 lowercase hexadecimal characters>",
  "query_plan_sha256": "<64 lowercase hexadecimal characters>",
  "operation_registry_sha256": "<64 lowercase hexadecimal characters>",
  "inputs": {"subject_id": "bound-subject"},
  "context": {
    "subject_id": "bound-subject",
    "run_id": "bound-run",
    "activation_id": "current-activation",
    "node_ref": "fixed-host-node-identity",
    "selected_intent": {
      "kind": "QUERY",
      "capability_id": "registered.read_only_capability",
      "inputs_sha256": "<RFC8785 digest of inputs>"
    }
  }
}
```

All three asset locks are mandatory. The plan digest includes schemas, operations, dependencies, pagination/batch settings, optional-output policy and budgets. The registry digest binds registered operation metadata and source identities. `FixedHttpReadTransport` additionally requires the registry's `transport_sha256` to match its actual configured transport asset. Custom callable code identity remains a reviewed host deployment responsibility; a descriptor is not code signing.

The legacy node identifier is an opaque host-bound string. The SDK also accepts the fixed architecture-v2 fields `definition_bundle_json`, object `node_ref`, `expected_definition_sha256`, `inputs_json`, and `execution_context_json` through `json_query_node`. The routes cannot be mixed. The node adapter validates one registered QUERY node and returns NodeResult; it does not navigate the graph. See [query conformance](QUERY-CONFORMANCE.md) for host registration, source rebinding, selected-intent checks, separate asset-byte locks, compiler semantics and explicit remaining boundaries.

### Mandatory host authorization

The host callback must validate the authenticated caller, tenant/subject, currently active run/node/activation, selected QUERY intent, current permission and revocation state against trusted host records. Returning the literal boolean `True` is required. Merely receiving consistent claims, a valid hash or a signature is insufficient. The adapter calls it before the first operation, before every I/O call, after each transport returns and before publishing success. A revoked permission clears outputs.

The adapter validates input schema, subject equality, nonempty context identity, intent capability and input digest, every registered operation and all asset locks before I/O. Schemas now use bounded Draft 2020-12 validation with offline local references, standard unions/constraints/combinators and the retained legacy nullable extension. Additional properties follow the declared schema. Format is an annotation; timestamps used for execution are separately parsed and checked. Recursive/regex/work limits and remaining schema acceptance boundaries are detailed in [query conformance](QUERY-CONFORMANCE.md). Top-level input fields named `url`, `endpoint`, `headers`, `credentials`, `module`, `code` or `proxy` are forbidden.

Each operation registry entry requires `read_only=true` and nonempty `source_refs`. The response must name one registered source, have the same subject, and provide a timezone-aware observation timestamp neither in the future nor older than the capability's maximum age. Source names alone are not evidence authentication: trusted transports must authenticate the endpoint and the host must establish the source's identity and authority.

### Bounds and results

- Default 16 calls, 16 total pages, 2 MiB cumulative returned JSON response, 10 seconds and batches up to 100 items
- Hard maxima: 1,000 calls/pages/batch items, 300 seconds, 2 MiB response body, 64 registered operations
- Dependencies must be acyclic and complete; technical execution is serial
- Every batch starts with a fresh cursor; repeated/unexpected/oversized cursors fail; optional local page/batch limits mark an operation incomplete while independent operations can continue within global budgets
- No automatic retries or cache; an exception never triggers a second call
- Conflicting values for the same fact fail; identical facts deduplicate; explicit ordered collection identities allow safe accumulation across pages and batches
- Incomplete operations never supply dependent inputs. Missing required facts return `UNKNOWN` and `outputs=null`; declared optional gaps may produce an explicitly partial available subset
- Missing optional facts are listed in `trace.unknown_outputs`, never fabricated as known null
- Cancellation, stale observations, timeout, authorization failure, source mismatch or budget failure clear outputs

Declared API input bindings now select literals, invocation inputs, trusted context or explicit prior-operation results. Output bindings project the final capability result. `QueryCollection` explicitly selects whole-value or record-key identity for ordered deduplication; conflicting records under the same key fail. The pure trusted-setup `compile_query_plan` accepts public query-plan.v2 technical declarations. Legacy capabilities without these declarations retain exact flat-fact conflict behavior. These are capability adapters, not a new controller. Cancellation of an arbitrary custom callback cannot be forced by this adapter; its pre/post guards reject late results but do not interrupt a callback that never returns. Such callbacks must enforce their own I/O deadlines, cancellation, byte limits and safe endpoint policy. The online authorization callback must also be bounded by the host; a policy lookup that consumes the deadline is rejected before further I/O. Raw-string transport responses count exact UTF-8 body bytes cumulatively; object responses count serialized returned JSON, so custom transports remain responsible for their actual wire-byte budget.

### Optional fixed HTTP transport

`FixedHttpReadTransport` is a narrow trusted-code adapter, not an arbitrary URL tool:

- Its endpoint and parameter names are constructed in Python and pinned in the registry
- GET or explicitly reviewed read-only POST with bounded JSON body; static host-only pinned headers; no ambient credentials/cookies, caller headers, runtime endpoint substitution or dynamic imports
- Globally routable unicast literal-IP HTTPS with certificate verification for real destinations
- HTTP/HTTPS loopback only when explicitly marked `SYNTHETIC`; such a transport also requires SYNTHETIC deployment provenance
- Hostnames, multicast, unspecified, reserved/private/link-local/metadata addresses, userinfo, zones, URL query/fragment and control characters rejected (explicit synthetic loopback is the only non-public exception)
- Direct numeric socket connection: no DNS resolution and no ambient HTTP proxy use
- Every redirect rejected without following its Location
- Only successful uncompressed `application/json` responses accepted
- Bounded URL and response-body reads, including Content-Length checks
- Watchdog actively shuts down the socket on total deadline or trusted cancellation, covering slow headers and body; no retry

Synthetic loopback tests verify actual GET and read-only POST requests, typed JSON bodies, static header restrictions, proxy ignoring, redirect/no-retry behavior, response size/content checks, total deadline and active cancellation. Watchdog callback failures fail closed; a separate mocked-TLS lifecycle regression verifies the timer owns the wrapper before handshake. Endpoint-policy tests verify negative SSRF destinations without contacting them. Public-IP HTTPS certificate behavior relies on Python's verifying TLS context and is **not** a production/public-network integration test. Company APIs, authenticated endpoints, credential provisioning/storage and production host permission integration remain unimplemented/unverified. No real company data is used.

## Advisory plan contract

A request has exactly `plan`, `models`, `inputs`. The plan has `format=json-plan-v1`, `version=0.3.0`, `id`, `flow`, `phases`, `outputs`.

- `locate_problem`: exactly one `LOCATE` phase
- `solve_problem`: exactly `P1`, `P2`, `P3`, `P4`, `P5` in order
- Each phase is `{id, steps}`; an empty phase needs a nonempty `skip_reason`
- Every nonempty phase contains at least one decision
- Step IDs are globally unique; explicit `depends_on` is mandatory
- Missing/duplicate/cyclic dependencies and later-phase dependencies fail before execution
- Stable topological execution allows a dependency to appear later in the same phase's declaration order
- Step-result bindings must refer to explicit transitive dependencies; a termination condition may also refer to its own decision result

Models are a map from model ID to `{table, sha256}`. Each nested `table` must be a JSON object; encoded table strings are rejected as `INVALID_MODEL`, without nested decoding. Every model, including unused and later-skipped models, is structurally validated and digest-checked before any query or decision runs. Decision policy pins must equal the model. Models use the explicit `json-table-v1` profile; `UNIQUE` is our documented extension. Existing flat-key tables are not silently converted.

Query steps contain `capability_id`, exact `<id>.input.v1` / `<id>.output.v1` pins and `parameters`. They call only `query_local`; plans cannot invoke real `execute_query`. Decision steps contain `model_id`, `hit_policy`, `inputs` and optional `terminate_when`.

Bindings are exactly `{literal: <JSON>}` or `{from: ["inputs", ...]}` / `{from: ["steps", "step-id", ...]}`. Object keys, array decimal indexes and array `length` are supported, with at most 16 path components. There is no expression evaluator. Missing mapped inputs are omitted; explicit null remains null. Missing final output paths wait instead of silently emitting null.

Step `response` preserves the raw local-query or table response. Success/no-match is not technical failure. Missing query inputs, blocking decision UNKNOWN and required output gaps return `WAITING_INPUT`; technical failures return `FAILED`. Subsequent steps are `BLOCKED`, with no response. Fail-fast applies to the whole invocation, including independent later steps.

A successful decision can evaluate `terminate_when: {value: <binding>, equals: <JSON>, outputs: <mapping>}`. Equality is JSON-type-sensitive: boolean true differs from numeric 1, while 1 and 1.0 are equal. A match uses only termination-specific outputs; later steps are `SKIPPED` with `TERMINATED`. Missing termination values/outputs wait and block later steps. A failed decision cannot become a successful termination.

Responses expose request/plan digests, plan identity/flow, step and phase statuses, outputs and `terminated_by`. Content hashes do not authorize execution. Budgets are 1,600,000 bytes per plan request, 256 KiB per input object/model, 64 models, 128 steps, 64 steps per phase, 128 bindings per mapping and 2 MiB response. Oversized accumulated trace is cleared on failure.

See the runnable [`advisory-locate-request.json`](../examples/json-suite/advisory-locate-request.json). These adapters do not implement P6/P7, action dispatch, controller state persistence, parallel execution, checkpoints, WAIT/resume, retries or recovery. The unavailable existing flowmanager/controller has not been replaced or integration-tested. Actual Dify 1.11.1 Start → Query → Decision → branch → End remains separate acceptance work.

## Evidence and remaining acceptance

Run:

```sh
PYTHONPATH=plugin python -m pytest -q tests/test_json_query.py tests/test_json_query_node.py tests/test_json_plan.py
python scripts/check_plugin.py
```

The independent tests cover synthetic exits, pre-I/O failure, actual SDK invocation, pinned asset/identity/permission policy, source/time/schema checks, fact conflict, partial data, technical dependencies, batching/pagination, response bounds, local HTTP policy/deadline/cancellation, stable plan ordering, pins, missing/null bindings, UNKNOWN/failure propagation, P1–P5 phases, termination and response clearing.

Not established by these tests: complete rival request/response/schema parity; real business APIs; production authenticated provenance and online authorization; arbitrary custom-transport safety; native Dify branching or host cancellation; company rule/GoldenCase equivalence; framework persistence/recovery; public release/install/rollback acceptance. More independent tests do not offset these gaps.
