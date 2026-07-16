# Single Semantic Planning Authority

## Purpose

Chromie permits exactly one semantic planning authority for one routed turn.
Routing, observation, schema validation, skill adaptation, confirmation, and
execution may involve multiple components, but they must not independently
reinterpret the same user goal after an authoritative planner has started.

This boundary is separate from robot validation. It can be automatically
verified without a GPU, Ollama, Soridormi, MuJoCo, a microphone, or physical
hardware. Live services are still required to validate model quality and robot
behavior.

## Maintained invariant

A turn carries one `context.semantic_authority` claim. The claim records an
owner and one of three roles:

- `authoritative`: may resolve user goals and produce the semantic plan;
- `observer`: may produce comparison evidence but cannot commit or execute;
- `adapter`: may validate and materialize an already-selected exact action but
  cannot reinterpret the utterance.

After the Goal-driven Runtime acquires authoritative ownership, any planning,
composition, host-validation, or state-commit failure is fail-closed. The same
turn cannot re-enter the legacy CapabilityAgent planner.

## Entrypoint ownership

| Entrypoint | Semantic owner | Role | Planner path | Failure behavior |
|---|---|---|---|---|
| Orchestrator turn in `apply`; mapped route lane is allowlisted and apply preconditions pass | Goal-driven Runtime | authoritative | Goal Association → Fast Planner → terminal Deep Planner when required → Response Composer → trusted adapter | Fail closed after ownership is acquired. |
| Orchestrator turn in `apply`; mapped route lane is excluded | Existing routed Agent path | authoritative | The compatibility path selected before Goal-driven ownership; exact Router actions remain adapter-only | Goal-driven Runtime never acquires this turn. |
| Orchestrator turn in `report_only` | Goal-driven Runtime | observer | Same stages, evidence only | The existing routed Agent path remains the only authority. |
| Agent `/interaction` or `/run` with exact Router `actions[]` | No new semantic planner; Router-action materializer | adapter | Schema validation and `SkillRequest` materialization only | Invalid actions are blocked or clarified; no LLM reinterpretation. |
| Explicit compatibility emergency | Legacy CapabilityAgent | authoritative | Legacy capability semantic planner | Requires both service gates and a per-turn emergency claim. |
| Post-interrupt correction in `apply`; corrected mapped lane is allowlisted | Goal-driven Runtime | authoritative | Same apply coordinator as a normal turn | Fail closed after ownership is acquired. |
| Post-interrupt correction in `apply`; corrected mapped lane is excluded | Existing post-interrupt Agent path | authoritative | Compatibility handling selected before Goal-driven ownership; exact actions remain adapter-only and physical resume stays locked | Goal-driven Runtime never acquires this correction. |

`GET /semantic-authority` exposes the same machine-readable route matrix from
the Agent service.

## Legacy CapabilityAgent status

The CapabilityAgent remains in the repository for compatibility evidence and
emergency operation. In normal operation it is an adapter:

1. Exact Router `actions[]` are validated and converted to `SkillRequest`
   objects without calling the CapabilityAgent LLM.
2. A robot-action request without exact actions cannot invoke the old semantic
   planner by default.
3. The old planner runs only when all three conditions are true:
   - the Orchestrator has `ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=1`;
   - the Agent has `AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=1`;
   - the Orchestrator attaches a valid per-turn
     `legacy_capability_fallback` claim with `emergency_fallback=true` and a
     non-empty `turn_id` exactly matching the Agent request `sid`.

The two environment variables alone are not enough. The claim's exact turn
binding rejects an empty or cross-turn claim from silently widening authority.
This internal routing claim is not caller authentication and is not stored as a
single-use nonce: replaying the same valid claim with the same `sid` is not
independently prevented here. Keep the endpoint on its trusted network boundary
and keep both emergency gates off during normal operation.

The maintained launcher and common profiles set both gates to `0`.

## Disabled lanes versus failed authoritative turns

The Orchestrator first maps Router routes to semantic lanes: `chat`, `clarify`,
and `deep_thought` map to `chat`; `robot_action`, `tool`, and `memory` retain
their lane names; everything else maps to `unsupported`. A mapped lane excluded
by `ORCH_COGNITIVE_APPLY_LANES` stays on the existing routed Agent path before
the Goal-driven Runtime starts. Exact Router actions on that path are still
adapter-only, and the old CapabilityAgent semantic planner still needs its
explicit emergency gates and turn claim.

Once Goal Association begins under authoritative `apply`, there is no
same-turn compatibility fallback. Technical failure, terminal-lane mismatch,
response-composition failure, trusted runtime rejection, or Goal-state commit
failure produces truthful no-action output and an `error` resolution.

## Offline equivalence and regression evidence

The migration keeps old planner behavior covered as explicitly labelled
emergency-fallback tests while adding boundary tests that establish:

- exact Router actions produce the same validated skill requests with the LLM
  available or unavailable;
- the CapabilityAgent LLM call count remains zero on adapter-only requests;
- neither a service gate nor a per-turn claim alone can enable the old planner;
- empty and mismatched turn claims are rejected before any LLM call;
- both gates plus the emergency claim enable the retained compatibility planner;
- Goal-driven failures never emit a `legacy_fallback` status;
- allowlisted mapped lanes at apply and post-interrupt entrypoints name
  Goal-driven Runtime as their only authority after acquisition, while
  excluded mapped lanes retain the pre-acquisition Agent path;
- maintained profiles use `apply`, `fail_closed`, and disabled legacy gates.

Run the dependency-light audit with:

```bash
python scripts/semantic_authority_audit.py --check
```

Run the relevant regression tests with:

```bash
PYTHONPATH=agent:. python -m unittest -v tests.test_semantic_authority
```

These checks establish code-path ownership and deterministic adapter
compatibility. They do not establish live-model semantic quality or robot
execution correctness.

## Live validation still required

On the NVIDIA workstation, retain evidence for:

- real Goal Association and Planner outputs across common and ambiguous turns;
- execute-plus-clarify multi-goal continuation;
- post-interrupt correction without duplicate execution;
- Soridormi/MuJoCo skill execution and safe-idle closure;
- voice ASR/TTS behavior.

A live failure does not reopen the old planner during the same turn. Recovery
must start a new turn or use an explicitly initiated emergency compatibility
operation.
