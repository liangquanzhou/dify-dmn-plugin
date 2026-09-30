# Apache KIE DMN companion service

This service executes actual DMN models with **Apache KIE Drools DMN 10.2.0**, pinned in `engine/pom.xml`. The Java adapter does input admission, HTTP/authentication, and output normalization. It does not implement its own FEEL parser, hit policies, rule matching, or decision evaluator.

## Why this engine

Apache KIE is an Apache-2.0 licensed, actively maintained DMN implementation. Version 10.2.0 is a released Maven Central artifact. The upstream engine supports DMN conformance level 3; that upstream statement must not be confused with the narrower security and serialization scope of this adapter.

Primary sources (verified 2026-09-30):

- [Apache KIE DMN overview, versions, and TCK coverage](https://kie.apache.org/drools/dmn/)
- [Apache KIE 10.2.0 release](https://github.com/apache/incubator-kie/releases/tag/10.2.0)
- [Published artifact version metadata](https://repo.maven.apache.org/maven2/org/kie/kie-dmn-core/maven-metadata.xml)
- [Pinned engine POM](https://repo.maven.apache.org/maven2/org/kie/kie-dmn-core/10.2.0/kie-dmn-core-10.2.0.pom)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)

## Exposed scope

- A single inline DMN **1.3 or 1.4** XML document, with the standard OMG `MODEL` namespace
- Selection by exact decision **ID**, not label/name; dependencies within that same document are evaluated by KIE
- Standard FEEL expressions, contexts, lists, functions, boxed expressions, and engine-supported decision-table hit policies
- JSON input data; numbers are parsed as decimal values, not coerced from strings
- JSON-compatible output (object, array, number, string, boolean, null); native FEEL date/time/duration outputs are serialized to their ISO-style string representation
- Declared required inputs must exist and be non-null; KIE runtime type checking is enabled
- No imports, external model/resource references, Java/PMML/script function definitions, executable extension elements, non-FEEL expression languages, DTDs, entities, XInclude, or processing instructions
- FEEL `external` function syntax is rejected conservatively: the word `external` anywhere in a DMN `<text>` element, even in a string/comment, is disallowed
- DMN 1.1, 1.2, 1.5, and 1.6 are intentionally not admitted by this adapter, although the upstream engine supports more versions
- No model repository, remote deployment, KJAR loading, model import resolution, persistence, rule editing, or unauthenticated public API

The KIE strict runtime builder is an internal utility API, not a long-term compatibility promise. Its use is version-pinned and covered by the real integration suite; rerun that suite when upgrading KIE.

## API contract

### GET `/health`

The bearer-token requirement is identical to `/evaluate`.

```json
{"status":"ok","engine":"Apache KIE","version":"10.2.0"}
```

### POST `/evaluate`

Use `Content-Type: application/json` and, when configured, `Authorization: Bearer <DMN_API_TOKEN>`.

```json
{
  "model_xml": "<definitions ...>...</definitions>",
  "decision_id": "eligibility",
  "facts": {"age": 32, "risk_score": 25}
}
```

A successful HTTP 200 response:

```json
{
  "status": "matched",
  "result": {"eligible": true, "reason": "low_risk_adult"},
  "matched_rule_ids": ["rule_eligible"],
  "model_version": "64-lowercase-hex-characters"
}
```

`model_version` is SHA-256 of the **exact decoded XML string encoded as UTF-8**. Whitespace or other textual changes produce a new hash, even if semantics are unchanged. It is a content identifier, not an engine version or human release number.

`matched_rule_ids` contains the real KIE event-reported IDs of all matching rules from tables evaluated in the requested decision, deduplicated in evaluation order. Dependency-decision rows are excluded. Under FIRST, matching rows and selected output are different concepts: this field includes every matching row; KIE selects the first result. Models should give every rule a stable XML ID. Blank/missing IDs cannot be recovered and are omitted.

`no_match` means a decision table in the requested decision was evaluated but no rule matched. The result remains the **actual engine output**: ordinarily null; a COLLECT table may return an empty list, and a table with a default output may return that default. A non-table decision that evaluates successfully has status `matched` and may have an empty rule-ID list. Business rejection (`eligible: false`) is still `matched` if a rule matched.

All application errors use HTTP 4xx/5xx and a fixed, non-sensitive envelope:

```json
{"error":{"code":"MISSING_FACTS","message":"A declared required input is missing or null."}}
```

Important codes:

| HTTP | Code | Meaning |
|---|---|---|
| 400 | INVALID_JSON / INVALID_REQUEST | Invalid or duplicate-key JSON, wrong fields/types, or missing request data |
| 400 | INVALID_XML | XML parse failure |
| 400 | INVALID_NUMBER | Numeric exponent/scale outside allowed range |
| 401 | UNAUTHORIZED | Missing/incorrect bearer token |
| 404 | UNKNOWN_DECISION | ID is absent from model |
| 413 | REQUEST_TOO_LARGE / MODEL_TOO_LARGE / FACTS_TOO_LARGE | Size limit exceeded |
| 413 | MODEL_TOO_COMPLEX / FACTS_TOO_COMPLEX | Depth/node limit exceeded |
| 422 | UNSUPPORTED_MODEL / UNSAFE_MODEL | Model outside admitted version/security scope |
| 422 | INVALID_MODEL | KIE model compilation failed |
| 422 | MISSING_FACTS | Missing or null declared required input |
| 422 | EVALUATION_ERROR | Type mismatch, failed FEEL expression, UNIQUE overlap, or other KIE evaluation error |
| 422 | UNSUPPORTED_RESULT / RESULT_TOO_COMPLEX / RESULT_TOO_LARGE | Output cannot safely fit the JSON contract |
| 429 | BUSY | Four evaluations are already active; retry later |
| 500 | INTERNAL_ERROR | Unexpected adapter failure |

Engine diagnostics, input values, XML, stack traces, credentials, and filesystem paths are not returned. Application logging contains only startup information; the included SLF4J no-op backend suppresses engine logs that could include model/fact data. Network disconnects or HTTP framing errors handled by the JDK server can occur before the application response handler.

## Numeric precision

The adapter preserves JSON decimal inputs with Java `BigDecimal` and serializes decimal output directly as JSON numbers, without an intermediate binary float. This does **not** promise unlimited-precision DMN arithmetic: FEEL uses Decimal128 semantics with 34 significant digits, as documented in the [KIE FEEL handbook](https://kiegroup.github.io/dmn-feel-handbook/#number). More-than-34-digit values can round during literal parsing or calculation; comparisons to such literals can therefore differ from an untouched input value. Keep decision quantities within the FEEL precision contract, and represent identifiers as strings.

## Resource and trust boundary

This is an **internal service for trusted, reviewed model authors**, not a sandbox for anonymous or hostile multi-tenant model uploads. FEEL can express expensive computations or recursion even without Java/script access. Admission limits do not create a hard CPU or memory bound on a model's evaluation. There is deliberately no claim that interrupting a Java thread can safely kill arbitrary evaluation.

- Request: 2 MiB; XML: 512 KiB UTF-8; canonical JSON facts: 128 KiB
- Numeric input tokens: at most 256 characters; lexical exponent, decimal scale, and adjusted exponent are bounded to ±10,000
- JSON parser depth: 64; facts/output depth: 32; facts/output nodes: 10,000
- XML traversal depth: 64; total XML DOM nodes (including whitespace text): 10,000
- Response: 1 MiB; four simultaneous evaluations; JDK connection limit: 64
- The JDK HTTP request/response time settings address transport, **not** a hard evaluation deadline
- No cache of compiled models or facts; every call is freshly compiled/evaluated

In production:

1. Set `DMN_API_TOKEN` to a high-entropy secret of at least 32 characters. Startup defaults to production and refuses a shorter/missing token. Do not put its value in source control, Dify tool inputs, models, logs, or shared examples
2. Keep the engine on an internal/private network. Do not publish an unauthenticated port. The container listens on `0.0.0.0` so other containers on the same private network can reach it; the plain Java default is loopback only
3. Use TLS at the internal ingress or service mesh whenever traffic crosses a trust boundary; bearer auth alone does not encrypt transport
4. Add ingress body/read/time limits and rate limits. Run containers with an explicit memory limit, CPU limit, non-root user, read-only filesystem, and no outbound network access where feasible
5. Deploy separate processes/containers per trust domain. For untrusted model authors, add a proper per-evaluation isolated worker/process with OS-level resource limits before exposing this service
6. Pin production base images to reviewed digests and scan the resolved dependency tree/images as part of your own release process. The supplied Dockerfile uses readable version tags, which are not immutable digests

`DMN_ENV=development` explicitly permits a missing token for loopback development. It must not be used for public or shared deployments. If a token is supplied in development, it is still enforced.

## Build and run

Requires Java 21 and Maven 3.9+.

```sh
cd engine
mvn --batch-mode --no-transfer-progress test
mvn --batch-mode --no-transfer-progress package
DMN_ENV=development java -jar target/dmn-engine-service.jar
```

Production defaults:

```sh
# Supply DMN_API_TOKEN through your deployment's secret mechanism first.
DMN_BIND_HOST=127.0.0.1 PORT=8080 java -jar target/dmn-engine-service.jar
```

Environment variables: `DMN_API_TOKEN`, `DMN_ENV` (`production` by default), `DMN_BIND_HOST` (`127.0.0.1` by default outside Docker), and `PORT` (`8080`). No third-party account or credentials are needed to evaluate models.

From the repository root, prepare the request without hand-escaping XML:

```sh
python - <<'PY' > /tmp/dmn-request.json
import json
from pathlib import Path
print(json.dumps({"model_xml": Path("examples/eligibility.dmn").read_text(),
                  "decision_id": "eligibility", "facts": {"age": 32, "risk_score": 25}}))
PY
curl --fail-with-body http://127.0.0.1:8080/evaluate \
  -H 'Content-Type: application/json' --data-binary @/tmp/dmn-request.json
```

For an authenticated server, also supply the bearer header through your normal secret-safe client configuration. Avoid copying actual tokens into shell history.

Build the container from its own context:

```sh
docker build -t dmn-engine-service:0.1.0 ./engine
```

The Dockerfile builds the self-contained JAR and runs as UID/GID 10001. Its build skips tests because the cross-project examples are outside the engine Docker build context; run the Maven tests from the full repository before building an image.

## Verification

`engine/src/test/java/org/example/dmn/EngineIntegrationTest.java` sends real HTTP requests to an in-process server backed by the actual KIE engine. It covers authentication/health, successful DMN 1.3 decision tables, missing/null inputs, no match, UNIQUE overlap rejection, FIRST and COLLECT behavior, type errors, malformed XML, unknown decisions, DTD/XXE/external references/scripts/extensions, a DMN 1.4 FEEL list comprehension and scalar output, exact long-decimal FEEL equality and raw numeric serialization, numeric exponent/token bounds, malformed/duplicate/trailing JSON, methods/media types, and size/depth limits.

This is an adapter regression suite, not a rerun of the entire upstream DMN TCK.
