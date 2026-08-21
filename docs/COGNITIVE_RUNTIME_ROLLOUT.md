# Goal-Driven Cognitive Runtime Rollout

## Status

**Implementation:** present in the repository.

**Automated verification:** dependency-light unit tests and retained cognitive
runtime scenarios cover report-only operation, lane-gated apply, Fast-to-Deep
escalation, trusted terminal host validation, atomic Goal-state application,
Planner response projection, fail-closed disablement, and evidence classification.

**Target validation:** open. No live model-stack or MuJoCo evidence created by
this implementation patch is claimed here.

**Deployment readiness:** not established. This rollout does not widen
simulator, microphone, speaker, or physical-robot support claims.

This document is the operational companion to
[Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md).
The architecture document owns cognitive principles. This document owns the
staged runtime migration, rollback, diagnostics, and evidence procedure.

## 1. Purpose

PR1 through PR6 introduced the Goal-driven pipeline as advisory stages:

```text
Goal Association
→ Fast Planner
→ Deep Planner when Fast coverage is incomplete
```

PR7 connects those stages to the existing trusted host boundary without making
any model an execution authority:

```text
User Turn
→ deterministic emergency and interruption controls
→ Goal Interpretation (contextual WHAT only)
→ concurrent Fast Planner / Goal Association fan-out
→ Fast Planner
   ├─ complete terminal CanonicalPlan
   └─ escalate
       → Deep Planner
→ trusted host CanonicalPlan validation
   ├─ valid
   └─ structured rejection → fail closed
→ mechanical validation/materialization of Planner-owned Communicative Activities
→ trusted runtime adapter
→ atomic Goal-state application
→ existing request-bound confirmation
→ existing Trusted Capability Runtime
→ provider execution and retained evidence
```

The main planning direction is acyclic. Deep planning never returns semantic
work to Fast planning. Deep Planner may make one one mechanical DTO regeneration
inside its own transaction. Trusted Host validation is terminal and does not
invoke another semantic planner after rejecting the terminal plan.

Goal Association uses Ollama schema-constrained generation with state-specific
small model-facing DTOs. When active Goal IDs exist,
`GoalAssociationModelOutput` permits semantic relationships, independent
new-goal descriptions, or a natural clarification. When no association target
exists, `GoalSegmentationModelOutput` omits the association field and its schema
definition entirely, so the model decides only independent new-goal
descriptions or a clarification. This avoids relying on decoder enforcement of
composed `maxItems`/`oneOf` constraints to represent the host-known fact that an
association is impossible.
The host generates turn IDs, association IDs, goal IDs, versions, source text,
default containers, canonical `SemanticGoal` objects, and the final
`GoalAssociationResolution`. If model DTO validation still fails, the same
model receives the original JSON, exact validation errors, and the same compact
state-specific schema for one bounded revision. A second invalid result fails closed. No
lexical alias table, phrase mapping, or local semantic rewrite changes the
model-authored goal descriptions or relationships.

Deep Planning and single-goal Fast Planning use the flat model-facing
`PlannerModelOutput` schema rather than asking the structured decoder to emit
the shared `CanonicalPlan` union directly. Multi-goal Fast Planning uses the
decoder-tight `FastPlannerMultiGoalPlanOutput`. The model authors aggregate
disposition, steps, step IDs, arguments, ordering, ownership, goal outcomes,
responses, escalation judgments, and satisfaction. The host adds only canonical
identity fields and validates the shared CanonicalPlan contract.

Deep Planner complete multi-goal output still uses an exact `goal_outcomes`
object keyed by Goal Association IDs. Satisfaction fields mean how adequately
the proposed plan would satisfy each goal if its response and steps succeed;
pending execution alone is not an unmet planning requirement.

User-facing response transport is outside task planning. `chromie.speak` is
excluded from both planner capability schemas and rejected if a planner emits
it as a step. A direct conversational part of a mixed goal is represented by a
goal-scoped `respond` outcome and exact Planner-owned Communicative Activity.
Executable outcomes may also carry a still-needed prospective communicative
delta. The Host mechanically validates truth stage, evidence provenance,
confirmation, and delivery coordination from the immutable Plan and Interaction
Context; wording never becomes execution evidence.

## 2. Authority boundaries

### Models may

- associate the current turn with active Goals;
- segment independent new Goals;
- estimate complete, partial, or uncertain Goal coverage;
- propose a CanonicalPlan;
- resolve low-consequence parameters or request material information;
- propose exact, adjusted, alternative, clarification, unavailable, or refused
  outcomes;
- compose goal-scoped speech;
- `SocialAttentionPlanner` alone may propose optional Social Attention decoration.

### Models may not

- authorize their own side effects;
- bypass confirmation;
- commit Goal-state mutations directly;
- execute a skill;
- declare provider success without evidence;
- turn an invalid partial plan into partial execution;
- route Deep planning back to Fast planning.

### Trusted host code owns

- deterministic stop, cancellation, interruption, and stale-turn suppression;
- CanonicalPlan contract validation;
- capability identity and availability;
- argument-schema validation;
- provider and version checks;
- exclusive resource and parallel-conflict checks;
- request-bound confirmation;
- Goal and plan version application;
- atomic state commit or rollback;
- Trusted Capability Runtime submission;
- execution evidence and terminal state.

## 3. Runtime modes

`ORCH_COGNITIVE_RUNTIME_MODE` controls the unified path.

### `off`

The PR7 unified pipeline is not called. Existing Goal Interpreter, Agent, and trusted
ordinary cognition fails closed rather than entering another semantic path.

Use this mode only to disable the Goal-driven Runtime for diagnostics or fault isolation.

### `report_only`

The unified pipeline runs as an observer and records Goal associations, Fast/Deep
planning, the terminal `CanonicalPlan`, Planner response projection, failures, and stage
latency. It has no authority to commit user-visible speech, Goal state, confirmation,
or effects. This mode is diagnostic only.

### `apply`

The unified pipeline is authoritative in `apply`. Runtime validates the terminal
`CanonicalPlan` directly against the selected Capability contracts: schema, declared
semantic scope, effects, authorization, safety, confirmation, resources, concurrency,
availability, and provider identity. There is no intermediate semantic lane or route
taxonomy. Failure of any required contract fails closed and cannot enter another
semantic planner.

## 4. Capability-owned execution applicability

Execution applicability comes from the typed Plan and Capability/provider declarations.
The Host does not derive `chat`, `memory`, `tool`, or `robot_action` categories and does
not use such categories to widen or narrow Planner authority. Non-effectful response
Plans remain conversational; executable steps must individually satisfy their declared
Capability and Runtime contracts. Mixed-provider Plans are valid only when every step
is independently authorized and the declared resource/dependency graph permits their
coordination.

## 5. Semantic authority and failure policy

The effective technical failure policy is `fail_closed`. Once Goal-driven semantic
authority has begun, model failure, Planner projection failure, Capability/Runtime
rejection, provider failure, or Goal-state commit failure cannot authorize same-turn
fallback into a retired route/intent or Agent semantic planner. See
[Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md).

## 6. Total and per-stage budgets

The unified path has a total host deadline plus stage-specific Agent deadlines.
The defaults are:

```env
ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS=15000
ORCH_GOAL_ASSOCIATION_TIMEOUT_MS=3500
ORCH_FAST_PLANNER_TIMEOUT_MS=3000
ORCH_DEEP_PLANNER_TIMEOUT_MS=10000
```

The total foreground budget bounds one admitted interactive turn; it does not replace the stricter Charter latency targets for first useful speech. Planner fast pass may escalate once to the deep pass when HOW warrants it. Either planner pass may
regenerate once only for a mechanically malformed DTO. Deep semantic rejection is
terminal, and Host validation cannot spend the remaining runtime budget on another
semantic planning pass.

A timeout produces a structured fallback cause. It never authorizes partial
work.

## 7. Trusted runtime validation

Before a CanonicalPlan can be adapted into `InteractionResponse`, the host
checks every step together.

Validation includes:

- exact capability ID exists;
- capability is available;
- capability is interaction-executable;
- input arguments satisfy the current runtime schema;
- provider registration and version are compatible;
- parallel timing is supported by declared provider/resource evidence;
- exclusive resource claims do not conflict;
- no step references forbidden low-level controls;
- no blocking information gap remains;
- Goal satisfaction and disposition are contract-consistent.

If one step is invalid, no effectful step is committed.

The validator either accepts the terminal plan or rejects it. Deep Planner has already produced its terminal semantic plan; any permitted
same-tier regeneration was mechanical DTO recovery only. A Host rejection therefore
fails closed, commits no Goal state, and starts no
effect.

## 8. Runtime adaptation

A validated CanonicalPlan is converted to the existing strict interaction
contract:

```text
CanonicalPlan
→ InteractionResponse
→ InteractionRuntime.prepare_response()
→ confirmation
→ CapabilityRuntime.execute_response()
```

The adapter assigns:

- stable request IDs and idempotency information;
- current capability versions;
- model-authored sequential or parallel timing;
- current confirmation requirements;
- canonical-plan and Goal provenance;
- response-composition metadata.

Material alternatives and safe adjustments never receive a backend-derived
confirmation exemption. The changed plan must be approved by the user unless an
existing policy explicitly authorizes the adjustment class.

## 9. Goal-state commit

Goal Association remains advisory until the entire cognitive turn has passed:

1. terminal planning;
2. trusted CanonicalPlan validation;
3. Planner response projection validation;
4. trusted `InteractionResponse` preparation.

Only then does the host apply Goal changes.

Goal-state application is atomic for one resolution. If any proposed operation
is rejected, the pre-turn Goal snapshot is restored and no partial Goal update
is retained.

Supported single-Goal relationships include:

```text
new
continue
reference
modify
clarify
confirm
reject
cancel
pause
resume
replace
```

`merge` and `split` remain rejected until a dedicated multi-Goal transactional
contract exists.

Goal-state success does not imply effect execution success. Execution evidence
is retained separately.

## 10. Planner communication and social attention

Fast/Deep Planner receives the versioned Goal snapshot and owns the exact
goal-scoped Communicative Activities in its immutable Canonical Plan. There is
no later model-backed wording owner. The Host may create an internal transport
projection with the Plan fingerprint, but that projection cannot add, omit,
rewrite, or reinterpret an Activity.

Trusted checks ensure:

- all known Goals are covered by the appropriate terminal response;
- pre-execution speech does not claim completion; and
- clarification enters `waiting_for_user` semantics.

Social Attention is a separate background cognition owned by
`SocialAttentionPlanner`. Its valid `none`, malformed output, target/resource
validation, and optional execution never delay or rewrite the attached Main
Activity. Every opportunity names that concrete observable Activity; `none` is
a valid decision and late standalone decoration is suppressed.

## 11. Evidence records

Operational records default to:

```env
ORCH_COGNITIVE_EVIDENCE_PATH=.chromie/evidence/cognitive-runtime/events.jsonl
ORCH_COGNITIVE_EVIDENCE_INCLUDE_TEXT=0
```

With text disabled, each event stores text length and a short SHA-256 digest,
not raw user speech.

A record includes:

- mode, status, and lane;
- Goal Association result;
- Fast and terminal plan summaries;
- Goal satisfaction;
- response-composition status and plan fingerprint;
- trusted interaction skill IDs;
- confirmation requirement;
- Goal-state application results;
- per-stage and total latency;
- fallback reason;
- terminal-plan validation outcome.

An `applied` record is written only after trusted host preparation and atomic
Goal-state application succeed. A technical fallback, state rejection, or
preparation failure is recorded as fallback/error rather than applied.

## 12. Evidence classification tool

Use:

```bash
python scripts/cognitive_runtime_acceptance.py --mode check
python scripts/cognitive_runtime_acceptance.py --mode level-a
```

To summarize retained live events:

```bash
python scripts/cognitive_runtime_acceptance.py \
  --mode evidence \
  --events .chromie/evidence/cognitive-runtime/events.jsonl \
  --require-applied-lane chat \
  --output .chromie/evidence/cognitive-runtime/live-text-summary.json
```

To build a classified bundle with optional text-to-MuJoCo evidence:

```bash
python scripts/cognitive_runtime_acceptance.py \
  --mode bundle \
  --events .chromie/evidence/cognitive-runtime/events.jsonl \
  --text-mujoco-summary .chromie/acceptance/text-mujoco/<run>/summary.json \
  --output .chromie/evidence/cognitive-runtime/bundle.json
```

The tool reports evidence classes independently. It never turns deterministic
scenarios into live evidence, or live text into simulator/physical validation,
or any of those into release readiness. Simulator target validation additionally
requires a clean run whose recorded Chromie and Soridormi revisions match the
expected source. A user-supplied `--soridormi-repo` records only a declared
paired checkout; it does not prove which source the MCP endpoint executes.
Target validation therefore requires the endpoint to report its own revision
and for that revision to match the clean paired checkout and manifest. It also
requires explicit goal-driven `apply` selection, an `applied` cognitive
resolution, completed Soridormi `sim` execution, and explicit safe idle before
and after execution. The current runner records `declared_paired_checkout` with
no endpoint-reported revision, so its new bundles remain diagnostic until that
endpoint binding exists. Bundle-generator identity is kept separate from
retained-run provenance.

## 13. Level A rollout scenarios

The retained `cognitive_runtime` scenario family covers:

### Chat apply

A complete Fast response becomes the authoritative chat interaction without an
effectful skill.

### Compound walk-and-blink runtime replan

The Fast Planner escalates. The first Deep plan conflicts at the trusted runtime
boundary. Structured feedback produces one revised Deep plan. The validated
plan is adapted without partial execution.

### Capability-contract fail-closed boundary

A Plan step is not applied when its Capability is unavailable, unauthorized, schema
invalid, confirmation-incomplete, resource-conflicting, or otherwise rejected by the
trusted Runtime. The failure cannot re-enter another semantic planner.

### Multi-Goal response coverage

One turn creates independent Goals, and the final coordinated response covers
all Goal IDs without inventing or omitting a Goal. The trusted runtime adapter
accepts terminal `mixed` plans when their executable subset is valid, maps them
to a successful interaction, and preserves `source_goal_ids` on every emitted
skill.

### Daily-life multi-goal matrix

Eight additional deterministic cases cover normal Chinese and English compound
requests: look plus nod, blink plus a joke, action plus ambiguous movement,
a supported gesture plus unavailable pickup, walk plus blink plus greeting,
repeated blink steps, look plus blink, and a three-way execute/respond/clarify
turn. Expectations verify per-goal outcome, arguments, timing, skill ownership,
speech coverage, confirmation, and final status.

Run them with:

```bash
python scripts/general_ability_acceptance.py \
  --mode level-a \
  --ability-class multi_goal_daily_life \
  --no-write
```

These scenarios are dependency-light Level A evidence only.

### Fast Planner multi-goal contract optimization

The July 17, 2026 operator-supplied live-text simulator diagnostic passed
the four-case daily-life matrix only after Deep Planner recovery. Every Fast
Planner attempt recorded a model-contract failure rather than a valid
terminal result or semantic escalation. This is successful end-to-end
recovery, not successful Fast Planner operation.

The first implementation used one plan-shaped envelope with an optional inner
terminal map. Five warm runs produced 20/20 Fast contract failures, mandatory
Deep recovery, a 22.87-second median cognitive runtime, and only 3.9 percent
improvement over the 23.79-second baseline. The revised implementation in
[Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
requires a complete model-authored semantic plan with every authoritative goal
outcome, step cross-reference, and satisfaction field decoder-required. The host
no longer compiles semantic plan fields. Automated evidence is green; repeated
warm live-text simulator evidence must be rerun. Rollout must preserve the existing
one-way authority path and shared trusted validator. Existing `report_only`,
lane gates, and `AGENT_FAST_PLANNER_ENABLED` provide observation and rollback;
a new semantic authority or partial-execution fallback is not permitted.

## 14. Live-text rollout procedure

### Phase 0 — baseline

```env
ORCH_COGNITIVE_RUNTIME_MODE=off
```

Retain current compatibility behavior and known scenario results.

### Phase 1 — report-only

```env
ORCH_COGNITIVE_RUNTIME_MODE=report_only
```

Run representative multi-turn text cases:

```text
你好，你是谁？
往前走十五秒。
往前走十五秒，同时眨眼。
那改成先走，再眨眼，可以吗？
咖啡要冰的，顺便查一下天气。
算了，不用了。
```

Review:

- Goal continuity before creation;
- independent Goal segmentation;
- Fast complete versus Deep escalation;
- exact skills and arguments;
- alternative/clarification behavior;
- response Goal coverage;
- latency and fallback causes.

### Phase 2 — apply non-embodied capabilities

```env
ORCH_COGNITIVE_RUNTIME_MODE=apply
```

Retain successful and failure cases while only the non-embodied provider set is enabled.

### Phase 3 — enable trusted Soridormi capabilities in simulator

Keep `ORCH_COGNITIVE_RUNTIME_MODE=apply` and enable the reviewed Soridormi provider
through the maintained simulator operator mode. Do not use this phase as physical
hardware qualification; retain exact Chromie/Soridormi revisions and provider contracts.

## 15. Cognitive text-to-MuJoCo procedure

The text-to-MuJoCo checker uses the unified PR8 authority path by default:

```bash
python scripts/interaction_text_mujoco_check.py \
  "Walk forward for five seconds, then nod." \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --no-speaker \
  --preview-only
```

After preview succeeds against the exact simulator/provider revision, rerun the
approved executable scenario without `--preview-only` under the provider
contract and backend-neutral Host confirmation and safety policy.

The run retains `cognitive_runtime_resolution.json` alongside the existing
summary and provider evidence.

A live text preview is not MuJoCo execution evidence. MuJoCo execution is not
physical-robot evidence.

## 16. Rollback

### Immediate global rollback

```env
ORCH_COGNITIVE_RUNTIME_MODE=off
```

Restart the host Orchestrator. No database migration or capability change is
required.

### Fail-closed disablement

`off` is a diagnostic/fault-isolation state, not an emergency semantic rollback.
When the unified Runtime is disabled, admitted ordinary cognition cannot execute
through a retired planner or direct-LLM path. `report_only` is evidence-only when
explicitly invoked and likewise grants no execution authority.

## 17. Operational review questions

Before widening the enabled provider/capability surface, review:

1. Does Goal Association preserve existing Goals instead of creating duplicates?
2. Do Fast plans apply only with complete high-confidence coverage?
3. Do compound Goals escalate without leaking partial skills?
4. Does Deep avoid same-tier semantic replanning and permit at most one mechanical DTO regeneration before terminal Host validation?
5. Are material alternatives held for request-bound approval?
6. Does speech match the current plan and execution state?
7. Are all applied events recorded only after host preparation and Goal commit?
8. Are failures explicit and prevented from widening semantic authority?
9. Can the lane be disabled without state repair?
10. Is the claimed evidence class supported by retained artifacts?

## 18. Exit criteria

PR7 implementation is automatically verified when:

- the unified pipeline supports `off`, `report_only`, and `apply`;
- apply is lane-gated and rollback-safe;
- Fast escalation reaches Deep once and never returns to Fast;
- Deep performs no same-tier semantic replan; at most one mechanical DTO regeneration is allowed, and trusted runtime rejection fails closed;
- invalid or partial plans commit no effectful skill;
- Goal-state application is atomic;
- the Planner response projection is fingerprint-bound to the terminal Plan;
- evidence distinguishes applied, report-only, skipped, and error outcomes;
- dependency-light cognitive scenarios and the full test suite pass.

Target validation remains open until retained live-text and MuJoCo artifacts
from the intended deployment are reviewed. Use [Cognitive Gateway/Core
Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md) for the
current identity capture, live-service cases, endpoint source binding, and
safe-idle verification. Implementation alone does not make Chromie release
ready.
