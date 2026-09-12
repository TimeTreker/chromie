# Chromie Agent Cognitive Service

`chromie-agent` is Chromie's single model-facing cognitive service. It exposes
separately testable Goal Interpretation, Goal Association, Planner fast/deep passes,
restricted Goal-free Situation planning, Reflection, capability-catalog, and WorkDAG diagnostic
surfaces. These are module/contract boundaries inside one FastAPI service, not a
microservice per cognitive role. The Cognitive Gateway itself remains Host-owned.

The service is **not** a second orchestration runtime. The retired `AgentRuntime`,
`InteractionRuntime`, specialized semantic Agent pipeline, `/run`, `/interaction`,
`/agents`, independent response-authoring stage, and Tool Result Interpreter
surfaces have been removed. One Planner authority owns Communicative Activities; its
fast/deep passes receive bounded Responsibility/Goal/Work/Evidence state on initial and
event-driven re-entry. Re-entry includes one immutable exact affected-Goal scope;
unrelated sibling Work remains outside the Planner transaction; relevant sibling speech
is read-only delivery context. Planner owns
Capability/argument/step semantics, while the shared validation kernel projects only
uniquely derivable duplicate parameter provenance. The Host Orchestrator owns turn coordination
and the trusted asynchronous `CapabilityRuntime`; Soridormi remains an execution
provider behind the Capability boundary.

GI-triggered and GA/Evidence-triggered Planner calls have independent task identities. Canonical Fast/Deep results can reuse a subset of `existing_work_activities`, add steps, and explicitly cancel named Activities with `cancel_activity_ids`. Omission preserves existing Work. The role Memory projection uses already filtered entries; Runtime owns commit and dispatch validation. See [Cognitive Turn Loop](../docs/COGNITIVE_TURN_LOOP.md) and [Memory Extraction](../docs/MEMORY_EXTRACTION.md).

Required Planner projections preserve complete admitted Goals, bindings, Work,
Evidence, source Plans, delivery context and capability applicability contracts.
Existing per-section character budgets reject oversized required inputs before
inference instead of omitting fields or entries. Streaming applies the same rule
before any presentation commit. Budget rejection retains the full Goal scope,
records zero model attempts, and cannot trigger semantic Deep delegation or
partial execution. Optional Situation relevance and auxiliary decoration remain
separate background projections; their omission cannot establish Goal truth.
The existing provider preflight still checks the complete request's model budget.

## Authority boundary

GI, GA, execution events and trusted Situation can trigger independent Planner tasks.
Goal-free Situation supplies no Responsibility, Goal or Capability Work permission,
including safe reads. `SituationalPlannerResolver` keeps the existing endpoint/DTO
surface and configured Fast/Deep clients; it shares the ordinary communication
contract and Activity identity checks with Goal-bound planning. Only an unresolved
Fast decision with no Activity/Memory result may delegate once; direct Deep readiness
has the same restricted scope. A complete decision has no second model reviewer.
Runtime validates all returned provenance, identity, delivered repair references and
Memory candidates before committing Memory or preserving exact speech for delivery.

Primary and Deep GI reject a speed binding with invalid source or dimension
provenance; Host does not delete the binding to accept the rest of the result.
No speed requirement is invented when the user supplies none. Planner may select
execution defaults only under the existing Capability and safety contracts.

GA inherits new Goal WHAT directly from accepted GI references. Existing Goals use
source-bound `requirement_changes`, without model-authored descriptions. Host validates
the original Goal snapshot and commits the selected requirements, typed fields and
provenance atomically; Planner retains Work decisions. See
[Goal meaning inheritance](../docs/COGNITIVE_TURN_LOOP.md#goal-meaning-inheritance).

```text
Perception
  ↓
Cognitive Gateway
  ↓
Goal Interpretation     WHAT only
  ├───────────────┐
  ↓               ↓
Planner           Goal Association
fast/deep passes  canonical Goal continuity
  ↓               │
Plan / Activities │
  └───────┬───────┘
          ↓
CapabilityRuntime       trusted execution lifecycle
          ↓
Provider events         what happened
          ↓
Evidence                what is true
          ↓
CognitiveOpportunity    ephemeral readiness trigger when useful
          ↓
Planner                  0..N Activity changes or none (Goal-bound)

Goal-free trusted Situation
          ↓
/situational-cognition   Planner, communication-only; silence or one Activity; no Work
```

Optional Social Attention decoration is emitted as `auxiliary_activities[]` in the
same Fast `PresentationCommit`, terminal result, or canonical Fast/Deep Planner result
as its Main Activity. It has no Goal-completion authority and there is no second social
model call.

Goal Association keeps one semantic authority while separating implementation concerns: `app/goal_association_contract.py` owns only the model-facing typed DTO/schema and local normalization rules, while `app/goal_association.py` owns the resolver/inference transaction that decides canonical Goal continuity. The contract module has no model client, runtime state, Goal commit, or tracing authority.

GA may regenerate one unambiguously malformed object/array container only after
the complete original claims pass deterministic preflight. Acceptance compares
every authored field/value with that lossless projection. Unknown fields, invalid
optional meaning, conflicting decisions and any semantic change reject; preprocessing
cannot delete them to salvage the result. See the [turn-loop contract](../docs/COGNITIVE_TURN_LOOP.md#30-fastdeep-escalation-is-cognition-depth-not-repair).

WorkDAG endpoints are deterministic validation/execution infrastructure. The retired LLM `WorkDAGPlanner` bridge has been removed; WorkDAG infrastructure does not own cognitive planning.

## Current HTTP surface

Important endpoints include:

- `GET /health`
- `GET /semantic-authority`
- `GET /capabilities`
- `GET /capabilities/catalog`
- `POST /capabilities/search`
- Goal Interpretation / cognitive-core endpoints
- `POST /goal-association`
- `POST /fast-advance`
- `POST /fast-plan`
- `POST /deep-plan`
- `POST /situational-cognition` (restricted Planner Situation contract)
- Agent Skill selection/disclosure endpoints
- WorkDAG validate/dry-run/guarded execution/trace diagnostics

See [`../docs/API_REFERENCE.md`](../docs/API_REFERENCE.md) for the exact maintained API surface.

## Auxiliary social decoration

Planner schemas receive only exact eligible catalog candidates; provider-owned body
calibration, backend identity, joint targets, and low-level controller parameters are
excluded. Runtime validates or suppresses the exact Planner proposal and Soridormi
resolves an accepted semantic target for its active embodiment. No independent
social-decoration model configuration surface exists.

## Capability and Agent Skill distinction

Executable provider functionality is a **Capability**. Reusable model-facing knowledge/procedure packages are **Agent Skills**. Do not use executable `SkillRuntime`/`SkillRequest` vocabulary inside Chromie's canonical runtime. Soridormi may still use provider-local wire `skill_id`, translated at its adapter boundary.

The built-in `chromie.clock.local` Capability is the trusted read-only source for
current local date/time and UTC offset. It takes no arguments, returns immutable
Evidence through the ordinary tool-result path, and does not permit a Planner to
guess or announce the current time before that Evidence returns.

## WorkDAG diagnostics

WorkDAG validation and explicitly gated execution remain available for engineering/control-plane diagnostics. Read-only, planning, guarded, and physical execution retain their separate authorization gates. These endpoints do not replace the canonical Fast/Deep Planner.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r agent/requirements.txt
PYTHONPATH=agent uvicorn app.main:app --host 0.0.0.0 --port 8092
```

The service can run with `AGENT_USE_LLM=0` for dependency-light control-plane tests where the individual current components support it.

For project architecture and current status, see:

- [Goal-Driven Cognitive Architecture](../docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
- [Semantic Authority](../docs/SEMANTIC_AUTHORITY.md)
- [Social Attention Behavior Domain](../docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md)
- [Agent Skills Architecture](../docs/AGENT_SKILLS_ARCHITECTURE.md)
- [Status](../docs/STATUS.md)

Additional owned mechanical contracts:

- [Capability Result Evidence Re-entry](../docs/CAPABILITY_RESULT_EVIDENCE_REENTRY.md)
- [WorkDAG mechanics](../docs/work_dag.md)
- [WorkDAG concurrency decision](../docs/dag_engine_concurrency.md)
