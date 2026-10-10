# 0.6.0 candidate validation

Date: 2026-10-09. Unpublished candidate based on local UNIQUE commit `fce19ace723836b1832286de1a5533b0e27156d0`. No production data, company connection, remote push or release.

## Verified candidate scope

| Area | Result | Evidence |
|---|---|---|
| Python backend and installer | PASS: 2,439 tests including 7 exact-baseline installer cases | `tests/`, `frontend/integration/test_apply.py` |
| Explicit JSON table | PASS: 111 independent cases, including exhaustive T/F/U selections | `tests/test_json_profiles.py` |
| Typed decision | PASS: 44 independent cases | `tests/test_json_decision.py` |
| Query/plan | PASS: 164 independent cases; real loopback synthetic HTTP included | `tests/test_json_query.py`, `tests/test_json_plan.py` |
| Endpoint | PASS: 71 cases including generated assets through real SDK GET/HEAD | `tests/test_structure_endpoint.py` |
| Frontend | PASS: 95 tests, including 48 existing matrix and 47 viewer | `frontend/tests/`, `frontend/integration/identity.test.ts` |
| Browser viewer | PASS: 42 real sandboxed Chromium checks | `frontend/tests/structure-browser.cjs` |
| Existing matrix browser/offline | PASS: 30 browser and 11 offline checks rerun | Existing browser/offline scripts |
| Frontend TypeScript/builds | PASS: matrix and standalone viewer builds | Locked React/Vite/TypeScript toolchain |
| Official SDK registration | PASS: six Tools and Endpoint load under SDK 0.10.2 / Python 3.12 | `scripts/check_plugin.py` |
| Official package | PASS: CLI 0.6.10 produced an unsigned `.difypkg` | `scripts/package_plugin.sh` |
| Exact packaged legacy stdio | PASS: 20 success + 21 explicit-error calls; unchanged 17 output variables | `tests/compatibility/stdio_smoke.py` |
| Exact packaged new-tool stdio | PASS: 14 calls covering all five added tools and blocked/failed outcomes | `tests/compatibility/json_suite_stdio.py` |
| Official unmodified Dify 1.11.1 API models | PASS: six-tool declaration and 431 messages / 397 variable messages | `tests/compatibility/dify_v060_models.py` |
| Fresh installed Dify 1.11.1 workflows | NOT_RUN at this freeze point | Separate isolated Docker validation in progress |
| Production APIs, authorization, company rules/controller | NOT_RUN | Unavailable business environment; fixture checks do not substitute |
| Full target JSON capability superset / direct five-tool wire parity | NOT_ESTABLISHED | See explicit remaining gaps in `JSON-SUITE-0.6.0.md` |

Counts overlap: focused suites and stdio cases are not additive to the full Python suite. Package hashes and exact build metadata are in `BUILD_INFO-0.6.0.json`. The full Python+installer run reports 45 warnings; warnings are not silently counted as failures or omitted. They are two SDK import/deprecation warnings plus 43 gevent fork warnings when installer subprocess cases share the already-patched test process. The separate installer run passes seven cases without warnings.

## Independent review fixes

A read-only reviewer supplied independent reproductions. Each was fixed and retested before this freeze:

1. Typed DECISION must declare and map `ok`, `blocked`, `error`; it cannot return a successful unmapped port
2. Nested plan model tables are explicitly object-only; encoded strings/non-objects return a technical failure envelope rather than raising an uncaught exception
3. Fixed HTTP transport explicitly rejects multicast/non-unicast destinations and explicit port zero before socket creation
4. Malformed optional viewer names are inert data; importing them and searching no longer crashes the viewer
5. QUERY_PLAN capabilities require a registered asset lock of the correct kind, including unused capabilities when accepting a bundle

Integration review also found that Dify 1.11.1 rejects null top-level VARIABLE values. Query/plan convenience `outputs` now emits `{}` when unavailable; the authoritative `results` and JSON envelopes retain null. Status branching is mandatory, and failure cannot reuse successful business outputs.

The reviewer confirmed that the original evaluator, JSON boundary, model identity, original Tool, and existing matrix implementation files are unchanged from `fce19ac`. No code or tests from the unlicensed reference repository were copied or executed.

## Limits

Pure SDK/API-model checks do not prove installed-host execution, Endpoint reverse-proxy behavior, signing acceptance, company business equivalence or host recovery. New candidate Docker evidence must be tied to the final exact package. Historical 0.4.1 Docker results are not evidence for 0.6.0.

The Next production build is separate from the standalone viewer build. A first fresh build compiled successfully but was killed during unbounded page-data worker fanout; a resource-bounded retry is in progress at this freeze point. Upstream Next skips lint/type checks during production build, so independent TypeScript and focused checks remain necessary.
