# 0.7.0 candidate validation

Date: 2026-10-09. Unpublished candidate based on preserved 0.6.0 source `fce633b118fa27f362b2c2ccc0279960c3e8e29e`. Implementation is frozen after independent review at local commit `30d94a9eda9b2735d82372b1f7bd189eb7d477ef`. Fresh isolated-host synthetic acceptance passed on the exact package below. This record uses fresh candidate checks, not historical host results.

## Fixed scope

Four blocks only: JSON decisions with UNIQUE and typed source quality/freshness; configured read-only queries with bounded pagination/batches/timeouts/missing handling; bindings/advisory stage plans/static validation behind the existing controller boundary; and read-only Dify matrices plus Phase → Step → Node overview. No additional product modules, XML/FEEL engine, durable WAIT runtime, business writes, company API connection, editor, remote push, release or production deployment.

## Exact package

- File: `liangquanzhou-dmn_decision-0.7.0-candidate-unsigned.difypkg`
- Size: 237,045 bytes
- SHA-256: `5fb7f29ed5e2472815d9db93aa12f0502a35bc7f024bd6ac9304cadc5b770a90`
- Official packaging CLI: 0.6.10; SDK 0.10.2; Python 3.12.14
- Unsigned candidate. Company review, trust and signing requirements are unchanged

## Fresh checks

| Area | Result | Evidence / limit |
|---|---|---|
| Complete Python suite | PASS: 2,609 tests, five warnings, no skips | `tests/`; warnings are two SDK import/deprecation notices and three gevent subprocess notices |
| Exact Dify-baseline installer | PASS: seven cases | `frontend/integration/test_apply.py`; exact official Dify commit |
| Frontend unit/interaction tests | PASS: 103 tests | Six files; matrix/identity and 55 structure model/viewer checks |
| TypeScript and Vite builds | PASS: matrix and structure viewer | Locked frontend toolchain; regenerated Endpoint/offline assets |
| Real viewer browser | PASS: 42 checks | Official Playwright headless Chromium 134, browser sandbox enabled, synthetic local server |
| Existing matrix browser | PASS: 30 checks | FIRST/COLLECT/UNIQUE, 440px UI, no stale configuration, same JSON→Python execution |
| Single-file matrix browser | PASS: 11 checks | Current 0.7-named HTML, no secondary asset requests |
| SDK registration | PASS: six Tools and Endpoint loaded | No provider credentials required |
| Exact packaged legacy stdio | PASS: 20 success + 21 explicit-error calls | All 17 existing bindable outputs preserved |
| Exact packaged new-tool stdio | PASS: 15 calls | Five added tools, including fixed QUERY node fail-closed route |
| Unmodified Dify 1.11.1 API models | PASS: six-tool declaration; 438 messages / 403 variables | Exact-package stdio evidence; Dify commit `2058186f22b4e4d4e155f380c130f4e8f21622fa` |
| Native in-panel patch identity | PASS | All four component files match candidate bytes in exact Dify build checkout; installer check passes |
| Independent scoped review | PASS after three additional findings fixed | Custom reproductions and targeted Python/frontend reruns; see fixes below |
| Extracted source archive | PASS: 2,609 backend + seven installer cases; SDK registration | Explicit 157-file manifest; no private/raw evidence included |
| Package integrity / credential-pattern scan | PASS | All 40 archive entries match source; no unsafe paths, private state, or common credential-pattern findings; not an exhaustive security audit |
| Fresh full Dify Next production build | PASS: 35 pages, self-contained standalone | Two workers, 6 GiB heap, VM stopped and no concurrent checks; final run 123 seconds, about 7.0 GiB peak RSS |
| Fresh native Dify type/lint/panel checks | PASS: full web typecheck and five panel tests; focused oxlint zero warnings/errors; ESLint zero errors | Three ESLint warnings were independently reproduced against unmodified Dify HEAD; upstream build skips are not used as proof |
| Actual Dify 1.11.1 package installation | PASS | Fresh install on isolated Docker host; package SHA above matches uploaded and installed candidate |
| Actual six-tool host contracts | PASS: 19 synthetic workflow cases | UNIQUE four states, simple/typed decisions, local query outcomes, both unconfigured QUERY entry routes, plan success/pin failure |
| Query → decision status gates | PASS: five synthetic cases | Successful known inputs reach decisions; unknown/timeout/error queries do not execute downstream decision |
| Actual hosted Endpoint | PASS | GET/HEAD, static assets, CSP, local import, asset allowlist and query rejection |
| Stock-versus-patched Dify UI | PASS on same plugin/app/database | Read-only matrix and expanded dialog; actual Test Run succeeded; persisted table_json bytes unchanged |
| Company production authorization, APIs and business GoldenCases | NOT_RUN / unavailable | Synthetic checks cannot substitute for trusted company deployment/controller integration |
| Exhaustive target parity | NOT_ESTABLISHED | Supported-profile limits remain explicit in suite/conformance docs |

Counts overlap; focused suites and stdio cases are not additive to the full Python total. Two earlier portable-build attempts were unusable because a validation-only dependency symlink escaped the standalone output or polluted source discovery; the final isolated rebuild with an identical project-local locked dependency tree passed, with no broken/escaping symlinks. No product code or type checks were weakened. Browser startup with full desktop Chromium failed at its local IPC socket under the execution sandbox; the supported official Playwright headless shell passed with Chromium sandbox still enabled. Browser security was not disabled.

## Installed-host acceptance details

The test host installed this exact unsigned candidate under a previously approved isolated signature-verification exception. This exception applies only to that synthetic test fixture; it does not change company signature policy or recommend bypassing verification. No company environment was contacted. The host sandbox capabilities remained zero with NoNewPrivs enabled.

The 19 contract cases intentionally return typed `FAILED`, `BLOCKED` or waiting envelopes inside successful Dify workflow calls where appropriate. Those results are not silently counted as business success. The five query→decision flows separately verify that failure/unknown query results stop before the decision node. Synthetic timeout/error fixtures are not proof of native durable waiting, cancellation or restart recovery.

The original browser phase recorded zero JavaScript page errors. Twenty aborted Next RSC prefetch requests occurred during navigation, with no recorded HTTP error responses. An initial branch-editor screenshot was taken before `/tools/builtin` metadata finished loading and showed six temporary Invalid variable warnings. After the actual six-tool metadata response and render settled, the warnings cleared without changing the graph or package. The main native three-node UI run succeeded with no validation badge.

One inherited harness assertion incorrectly required `trace.calls=0` on the fixed QUERY node's early unconfigured return, which deliberately has no `calls` field. It was corrected to assert `BLOCKED`, `QUERY_CONNECTION_NOT_CONFIGURED`, `outputs.query=null` and authorization `NONE`; the legacy path retains its zero-call assertion. The complete host case set was rerun. No plugin change was needed.

## Review fixes

Previously reported 0.7 defects were independently reproduced and retested:

1. Selected parallel branches must prove ALL_SUCCESS completion after business-route selection. An unselected globally possible success cannot authorize downstream selected intents
2. Explicit nested same-draft `$schema` declarations retain the bounded validator class and shared deadline/work/depth budget
3. Viewer import commits only after a separate candidate tree renders successfully; stale read/error/cleanup callbacks cannot replace a newer view or destroy the prior DOM, focus and navigation state

The final independent review found and verified three further fixes:

4. Every retained query observation is rechecked after authorization and before publication. Fresh later pages/operations cannot hide expired earlier evidence; clock rollback also fails closed
5. Registered operation schemas use canonical JSON equality. JSON `true`/`false` cannot compare equal to numeric `1`/`0` and bypass the locked asset before IO
6. Recursion exhaustion in Draft annotation helpers returns `QUERY_SCHEMA_BUDGET_EXCEEDED` with unusable outputs, rather than mislabeling resource exhaustion as an invalid schema

No high/medium fail-open issue remained in the scoped independent review. This is not an exhaustive security certificate or reference-implementation parity proof.

## Compatibility and limits

The original evaluator, JSON boundary, model identity, evaluate Tool and existing field-matrix implementation remain byte-identical to the UNIQUE baseline `fce19ac`. FIRST/COLLECT keep contract version 0.3.0; UNIQUE keeps 0.5.0. Package version 0.7.0 does not change those semantics.

Typed graph acceptance is static validation, not execution. Query IO requires a trusted registered read-only deployment and online host verification; the standard credential-free installation is deliberately unconfigured and blocked. Runtime parallel dispatch, event delivery, durable waiting/recovery/reentry and business writes remain outside the candidate. No reference-repository code, tests or schemas were copied or executed.
