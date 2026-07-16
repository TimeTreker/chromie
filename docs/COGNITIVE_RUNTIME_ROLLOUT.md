# Goal-Driven Cognitive Runtime Rollout

## Status

**Implementation:** present in the repository.

**Automated verification:** dependency-light unit tests and retained cognitive
runtime scenarios cover report-only operation, lane-gated apply, trusted host
validation, bounded same-tier replanning, atomic Goal-state application,
response composition, legacy rollback, and evidence classification.

**Target validation:** open. No live model-stack or MuJoCo evidence created by
this implementation patch is claimed here.

**Release readiness:** not established. This rollout does not widen the current
`0.0.1` simulator, microphone, speaker, or physical-robot release scope.

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
→ Response Composer
```

PR7 connects those stages to the existing trusted host boundary without making
any model an execution authority:

```text
User Turn
→ deterministic emergency and interruption controls
→ Goal Association
→ Fast Planner
   ├─ complete terminal CanonicalPlan
   └─ escalate
       → Deep Planner
→ trusted host CanonicalPlan validation
   ├─ valid
   └─ structured rejection
       → one bounded Deep Planner revision
→ Response Composer
→ trusted runtime adapter
→ atomic Goal-state application
→ existing request-bound confirmation
→ existing Skill Runtime
→ provider execution and retained evidence
```

The main planning direction is acyclic. Deep planning never returns semantic
work to Fast planning. The only loop is a bounded same-tier Deep Planner
revision from structured trusted-validator feedback.

Goal Association uses Ollama schema-constrained generation with a small
model-facing `GoalAssociationModelOutput` DTO. The model decides only semantic
relationships, independent new-goal descriptions, or a natural clarification.
The host generates turn IDs, association IDs, goal IDs, versions, source text,
default containers, canonical `SemanticGoal` objects, and the final
`GoalAssociationResolution`. If model DTO validation still fails, the same
model receives the original JSON, exact validation errors, and the same compact
schema for one bounded revision. A second invalid result fails closed. No
lexical alias table, phrase mapping, or local semantic rewrite changes the
model-authored goal descriptions or relationships.

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
- propose optional social attention.

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
- Skill Runtime submission;
- execution evidence and terminal state.

## 3. Runtime modes

`ORCH_COGNITIVE_RUNTIME_MODE` controls the unified path.

### `off`

The PR7 unified pipeline is not called. Existing Router, Agent, and trusted
runtime behavior remains the compatibility path.

Use this mode for immediate rollback.

### `report_only`

The unified pipeline runs in the background and records:

- Goal associations;
- new Goal segmentation;
- Fast coverage;
- Deep escalation and revision;
- terminal CanonicalPlan;
- response composition;
- candidate apply lane;
- failure and fallback causes;
- stage latency.

It does not change user-visible speech, Goal state, confirmation, or execution.
Observer routing is not filtered by the apply-lane allowlist, so tool and memory
routes can be measured without granting them authority. This mode is available
for diagnostics; it is not the maintained default.

### `apply`

The unified pipeline may become authoritative only for mapped semantic lanes
listed in `ORCH_COGNITIVE_APPLY_LANES`. Router routes `chat`, `clarify`, and
`deep_thought` map to the `chat` lane; `robot_action`, `tool`, and `memory`
retain their lane names.

A mapped lane that is not enabled remains on the existing routed Agent path,
selected before Goal-driven authority acquisition. An enabled lane still
applies only after all trusted validation and response-composition gates pass.

Initial recommended lanes:

```env
ORCH_COGNITIVE_APPLY_LANES=chat
```

The common safe base applies only `chat`. The maintained Soridormi launcher
widens the set to `chat,robot_action` after enabling the trusted provider. Tool
and memory lanes remain outside apply until their own retained live scenarios
prove authorization, result truthfulness, and rollback.

## 4. Lane classification

A terminal CanonicalPlan is projected to one runtime lane:

| Plan shape | Lane |
|---|---|
| No effectful steps | `chat` |
| All skills are Soridormi capabilities | `robot_action` |
| All skills are trusted memory capabilities | `memory` |
| All skills are other trusted Chromie capabilities | `tool` |
| Mixed or unsupported provider surface | `unsupported` |

This classification is a runtime dispatch property. It does not infer the
meaning of user language.

## 5. Semantic authority and failure policy

The effective technical failure policy is `fail_closed`.
`ORCH_COGNITIVE_FALLBACK_POLICY` remains accepted as a deprecated compatibility
input, but it cannot authorize same-turn fallback after the Goal-driven Runtime
has acquired semantic authority.

A route whose mapped semantic lane is excluded by
`ORCH_COGNITIVE_APPLY_LANES` remains on the routed Agent path before authority
acquisition. Once Goal Association begins in authoritative `apply`, any model,
composition, terminal-lane, trusted-runtime, or Goal-state commit failure
produces truthful no-action speech and no effectful skill. It does not fall
through to the legacy CapabilityAgent planner.

The legacy CapabilityAgent semantic planner is retained only as an explicit
emergency compatibility path. It requires disabled or non-authoritative
Goal-driven processing, host and Agent opt-in gates, and a per-turn emergency
authority claim. Exact Router `actions[]` use a deterministic adapter and never
call that planner. The Agent rejects an empty claim or a claim whose `turn_id`
does not exactly match the request `sid`, which blocks cross-turn reuse. The
claim is not stored as a consumed nonce, so this boundary does not independently
prevent replay with the same `sid`. See
[Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md).

## 6. Total and per-stage budgets

The unified path has a total host deadline plus stage-specific Agent deadlines.
The defaults are:

```env
ORCH_COGNITIVE_RUNTIME_TIMEOUT_MS=25000
ORCH_COGNITIVE_HOST_REPLAN_BUDGET=1

ORCH_GOAL_ASSOCIATION_TIMEOUT_MS=3500
ORCH_FAST_PLANNER_TIMEOUT_MS=3000
ORCH_DEEP_PLANNER_TIMEOUT_MS=10000
ORCH_RESPONSE_COMPOSER_TIMEOUT_MS=5000
```

The total budget prevents a sequence of individually legal calls from creating
unbounded turn latency. The host replan budget permits at most one Deep Planner
revision after trusted runtime rejection.

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

The validator returns structured feedback to the Deep Planner when the bounded
replan budget remains. The revised plan passes the same validation again.

## 8. Runtime adaptation

A validated CanonicalPlan is converted to the existing strict interaction
contract:

```text
CanonicalPlan
→ InteractionResponse
→ InteractionRuntime.prepare_response()
→ confirmation
→ SkillRuntime.execute_response()
```

The adapter assigns:

- stable request IDs and idempotency information;
- current capability versions;
- model-authored sequential or parallel timing;
- current confirmation requirements;
- canonical-plan and Goal provenance;
- response-composition metadata.

Material alternatives and safe adjustments never receive simulator
confirmation exemption automatically. The changed plan must be approved by the
user unless an existing policy explicitly authorizes the adjustment class.

## 9. Goal-state commit

Goal Association remains advisory until the entire cognitive turn has passed:

1. terminal planning;
2. trusted CanonicalPlan validation;
3. response composition;
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

## 10. Response composition and social attention

The Response Composer receives an immutable fingerprinted terminal
CanonicalPlan. It may organize goal-scoped speech and optional auxiliary social
attention, but it cannot change user-task steps.

Trusted checks ensure:

- all known Goals are covered by the appropriate terminal response;
- pre-execution speech does not claim completion;
- clarification enters `waiting_for_user` semantics;
- optional attention uses exact available capabilities;
- attention has valid target evidence;
- attention does not conflict with the primary plan;
- invalid optional attention is removed without changing the user task.

Social attention is not recorded as a new user Goal.

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
- host replan count.

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

### Per-lane fail-closed boundary

A valid robot plan is not applied when its terminal `robot_action` lane is absent
from the apply allowlist. If the mismatch is discovered after Goal-driven
authority has started, the result is classified as `error` and cannot re-enter
the legacy planner.

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

## 14. Live-text rollout procedure

### Phase 0 — baseline

```env
ORCH_COGNITIVE_RUNTIME_MODE=off
```

Retain current compatibility behavior and known scenario results.

### Phase 1 — report-only

```env
ORCH_COGNITIVE_RUNTIME_MODE=report_only
ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed
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

### Phase 2 — apply chat

```env
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat
ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed
```

Retain successful and failure cases before widening lanes.

### Phase 3 — apply robot action in simulator

```env
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat,robot_action
ORCH_COGNITIVE_FALLBACK_POLICY=fail_closed
```

Do not enable this phase for physical hardware. Use the maintained simulator
profile and retain exact Chromie/Soridormi revisions.

## 15. Cognitive text-to-MuJoCo procedure

The text-to-MuJoCo checker uses the unified PR8 authority path by default:

```bash
python scripts/interaction_text_mujoco_check.py \
  "Walk forward for five seconds, then nod." \
  --cognitive-runtime \
  --cognitive-apply-lanes chat,robot_action \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --no-speaker \
  --preview-only
```

After preview succeeds against the exact simulator/provider revision, rerun the
approved executable scenario without `--preview-only` under the existing
simulator confirmation and safety policy.

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

### Per-lane authority gate

Remove the affected route before rollout:

```env
ORCH_COGNITIVE_APPLY_LANES=chat
```

A routed `robot_action` turn is then excluded before Goal-driven authority
acquisition. If an already-started plan resolves to a disabled lane, it fails
closed rather than entering compatibility planning.

### Explicit emergency compatibility

The maintained profiles keep both legacy gates disabled. Emergency operation
requires all of the following:

```env
ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=1
AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=1
```

The Orchestrator must also attach an emergency authority claim whose non-empty
`turn_id` exactly matches the Agent request `sid`. This internal claim is not a
caller-authentication or single-use replay mechanism.
These settings do not reopen a turn that already entered authoritative
Goal-driven processing.

## 17. Operational review questions

Before widening an apply lane, review:

1. Does Goal Association preserve existing Goals instead of creating duplicates?
2. Do Fast plans apply only with complete high-confidence coverage?
3. Do compound Goals escalate without leaking partial skills?
4. Does one bounded Deep revision resolve trusted-validator feedback?
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
- trusted runtime rejection can trigger one bounded same-tier revision;
- invalid or partial plans commit no effectful skill;
- Goal-state application is atomic;
- response composition is fingerprint-bound to the terminal plan;
- evidence distinguishes applied, report-only, skipped, and error outcomes;
- dependency-light cognitive scenarios and the full test suite pass.

Target validation remains open until retained live-text and MuJoCo artifacts
from the intended deployment are reviewed. PR7 implementation alone does not
make Chromie release ready.
