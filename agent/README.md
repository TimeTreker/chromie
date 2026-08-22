# Chromie Agent Cognitive Service

`chromie-agent` is Chromie's single model-facing cognitive service. It exposes
separately testable Goal Interpretation, Goal Association, Planner fast/deep passes,
Reflection, Social Attention, capability-catalog, and WorkDAG diagnostic
surfaces. These are module/contract boundaries inside one FastAPI service, not a
microservice per cognitive role. The Cognitive Gateway itself remains Host-owned.

The service is **not** a second orchestration runtime. The retired `AgentRuntime`,
`InteractionRuntime`, specialized semantic Agent pipeline, `/run`, `/interaction`,
`/agents`, independent response-authoring stage, and Tool Result Interpreter
surfaces have been removed. One Planner authority owns Communicative Activities; its
fast/deep passes receive bounded Responsibility/Goal/Work/Evidence state on initial and
event-driven re-entry. The Host Orchestrator owns turn coordination
and the trusted asynchronous `CapabilityRuntime`; Soridormi remains an execution
provider behind the Capability boundary.

## Authority boundary

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
Planner                  0..N Activity changes or none
```

Social Attention is an optional Activity-scoped auxiliary cognition path. It may select only eligible live social-expression capabilities supplied by the bounded catalog context; it cannot create Goals, replace primary work, alter completion, author response text, or select provider/backend mechanics.

Goal Association keeps one semantic authority while separating implementation concerns: `app/goal_association_contract.py` owns only the model-facing typed DTO/schema and local normalization rules, while `app/goal_association.py` owns the resolver/inference transaction that decides canonical Goal continuity. The contract module has no model client, runtime state, Goal commit, or tracing authority.

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
- `POST /social-attention/plan`
- Agent Skill selection/disclosure endpoints
- WorkDAG validate/dry-run/guarded execution/trace diagnostics

See [`../docs/API_REFERENCE.md`](../docs/API_REFERENCE.md) for the exact maintained API surface.

## Social Attention configuration

The maintained policy is `AGENT_SOCIAL_ATTENTION_MODE=on`. Valid values are `off`, `report_only`, and `on`. Social Attention is detached from primary-response completion: there is no compatibility wait-after-response setting.

Provider-owned body calibration, backend identity, joint targets, and low-level controller parameters are excluded from model-facing Social Attention context. Soridormi resolves semantic body requests for its active embodiment.

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
