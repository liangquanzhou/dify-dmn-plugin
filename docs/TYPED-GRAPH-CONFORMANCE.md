# Typed graph conformance delta

This unpublished delta extends the independently implemented architecture.v2 validator and pure DECISION boundary. It does not execute a graph. The host remains the only owner of activation, fork tokens, interaction delivery, waits, checkpoints, reentry and cross-Step navigation.

## Newly accepted and checked

- Reciprocal PARALLEL SPLIT/JOIN pairs, including nested pairs, with explicit distinct split-edge branch identities
- ALL_SUCCESS joins with CANCEL_REMAINING and mapped `ok`/`error` continuations
- Alternative technical paths within one branch, direct empty branches, EXCLUSIVE technical convergence, and validated optional exclusive-pair references
- WAIT declarations within a parallel branch, including their received, timeout, cancelled and error continuations
- Definite node-source availability after a successful join, including sources inside a nested successful region; exclusive optional branches do not establish that availability
- Registered STEP/PHASE destinations resolved across the whole workflow, and explicit bounded REENTER_STEP declarations with a non-reentry technical exhaustion exit
- Offline validation of capability and WAIT event schemas using the shared Draft 2020-12 validator
- Shared technical NODE_PORT selectors on DECISION success/failure ports, without confusing their technical branches with business routes

The algorithm labels active regions with a stack of `(split, branch)` identities. Ordinary convergence can combine alternative paths of the same branch; it cannot merge sibling obligations. A matching join removes exactly one region. All branches must have a possible resolved completion. Successful join evidence includes definite sources from each successful branch; its failure edge only retains the common pre-fork evidence. Failure and unresolved technical results cannot manufacture successful branch completion. A valid WAIT receipt is a possible resolution in this static analysis, not evidence that an event actually arrived.

## Rejections added or tightened

- Crossed/nonreciprocal pairs, duplicate/missing/mismatched branch identities, orphan joins, premature region escapes and cross-branch ordinary merges
- INCLUSIVE, ALL_SETTLED, arbitrary graph cycles, and implicit cross-Step cycles that would bypass bounded reentry
- Failed parallel paths that start new execution/WAIT work instead of converging to the paired join; nested join failures must converge through technical exclusive plumbing
- Empty nonterminal continuations, unregistered technical result ports, missing WAIT outcomes, malformed or irrelevant node fields
- Node data references that are merely ancestors but are not definite predecessors; sibling parallel reads; target intent bindings depending on future action output
- Undeclared parameter references in any result template, including unselected templates
- WAIT declarations without a valid event schema, a positive integer timeout, run/step/attempt/intent correlation fields, or a definite preceding INTERACTION in the same branch
- Missing exit destinations, mismatched reentry class/destination, and a reentry exhaustion exit that could itself reenter
- Embedded invalid schemas or external schema references; schema validation never fetches a remote resource

Business action declarations still require explicit deployment enablement and produce only intents. This flag is definition content, not authorization to perform the action.

## Selected results and control paths

Reduction still binds all selected Data before resolving selected target-node input bindings. It still rejects conflicting state, data, route and intent facts and deduplicates equal facts/intents.

The intent-path projection follows the current DECISION's successful continuation and the selected business route. It considers successful joins and accepted WAIT receipts, and excludes failure-only action paths. NODE_PORT selectors are narrowed to predecessor ports that can actually reach them. Every required intent target on those potential selected paths must be selected by the current result; unselected templates cannot supply it. Selected targets outside those paths fail. This is a bounded static consistency check and does not dispatch any action, choose an actual future technical result, or prove runtime activation.

## Trust and compatibility

`runtime_snapshot` remains an opaque JSON object. Claims inside it are neither consumed as events nor accepted as activation, completion or authorization evidence. RFC8785 definition digests bind content only. The content-only mode remains `CONTENT_ONLY_NOT_AUTHORIZATION`.

The existing trusted `VerifiedDecisionSources` boundary is unchanged: trusted host code must authenticate the source context and current permissions, independently reproduce parameter records/bindings, and set a maximum observation age. Neither a source reference, an enabled node kind, nor a caller-supplied hash grants that authority. Explicit context, input and event roots remain host-provided evidence; declaring an event root does not register or consume a WAIT receipt.

`validate_definition(bundle)` keeps its public signature and returns the original, unmodified definition. The shared `prepare_node(..., kind=...)` performs the existing envelope, definition-pin and fixed-reference checks for DECISION or QUERY preparation; `prepare_decision(...)` remains a compatible wrapper.

## Independent evidence

`tests/test_json_architecture.py` constructs original small synthetic graph vectors. No reference implementation, test, or schema was copied into this repository or executed. Existing `tests/test_json_decision.py` was retained unchanged, including all prior audit regressions.

Focused checks at this checkpoint:

| Check | Result |
|---|---|
| Original typed decision tests | 44 passed |
| New architecture vectors | 56 passed |
| Combined architecture/decision/query-node/plan/JSON-profile run | 277 passed (focused shared-worktree checkpoint) |
| Runtime parallel dispatch, WAIT persistence, events, restart recovery or controller | Not implemented or run by this delta |
| Real Dify 1.11.1 integration and production authorization | Not run by this delta |
| Exhaustive equivalence against the target implementation | Not run; no full-parity claim |

## Remaining boundaries

Static acceptance is a supported profile, not a universal BPMN/DMN engine or a complete equivalence certificate for every architecture.schema.json instance. It intentionally rejects unsupported gateway/policy combinations and cross-Step active parallelism. Ordinary source analysis is conservative: it does not solve arbitrary correlations among independent technical predicates or prove that every possible JSON field exists within a source result. Trusted host binding and runtime checks remain necessary.

The path projection checks potentially activatable selected work. It is not a host schedule, durable fork ledger, cancellation implementation, event race winner, checkpoint, recovery protocol, source authentication system or exactly-once guarantee. A structurally valid WAIT is not evidence that Dify or another host supports durable wait/resume behavior. P1–P7 business rules and existing host mappings are unchanged.

Resource bounds remain 1 MiB for the definition envelope, 256 declared nodes and 1,024 edges per bundle, plus the existing JSON-profile depth and value limits. Embedded schemas have the shared schema engine's own documented safety limits. These limits and the stricter explicit profile can reject inputs beyond this candidate's supported subset; such rejections are not counted as completed target coverage.

## Public interface references

Target pin: `binhuhu/dify_dmn_plugin` at `561a15efa2a086c93373dc7fbd3fbf88e46a48c4`.

- [Architecture declarations and public design](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/docs/01_architecture.md)
- [Node, binding and result contracts](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/docs/03_contracts.md)
- [Public field/schema declaration](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/specs/service-decision-dsl-v2/schemas/architecture.schema.json)
- [Declared reference-host boundaries](https://github.com/binhuhu/dify_dmn_plugin/blob/561a15efa2a086c93373dc7fbd3fbf88e46a48c4/adapters/host/README.md)

The pinned reference checkout has no license grant. Only its public interface and documented behavior informed this original implementation; no reference source/test/schema is redistributed here.
