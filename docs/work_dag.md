# WorkDAG and DAGEngine

Status: current architecture authority for Chromie-level DAG representation and execution.

## Purpose

A **WorkDAG** is the Planner-authored directed acyclic graph that represents the topology of planned Work. A **DAGEngine** is the deterministic runtime mechanism that validates and advances that graph.

The distinction is intentional:

```text
Goal
  ↓
Planner                         semantic HOW authority
  ↓ authors
WorkDAG                         representation only
  ↓ executed by
DAGEngine                       dependency / readiness / scheduling mechanics
  ↓ dispatches
Activities / Capabilities
  ↓
Capability Runtime
  ↓
Providers
  ↓
Evidence
  ↓
Planner                         meaning / revision / new Work
```

Neither WorkDAG nor DAGEngine is a second Planner.

## Authority boundary

### Planner owns

The Planner authors Chromie-level WorkDAG semantics, including:

- which Work nodes exist;
- which Capability each node invokes;
- node arguments and material Goal bindings;
- dependency topology;
- concurrency relationships;
- bounded retry policy when that retry is already part of the committed plan;
- explicit pre-authored fallback edges or failure policy;
- whether changed Evidence justifies a revised/new WorkDAG;
- user-facing communication.

### WorkDAG owns no decisions

WorkDAG is a typed representation. It stores committed topology and policy but does not reason, schedule, execute, interpret Evidence, or speak.

### DAGEngine owns mechanics only

DAGEngine may:

- validate DAG structure and acyclicity;
- validate that referenced Capabilities exist and arguments satisfy deterministic contracts;
- calculate ready, blocked, pending, running, and terminal nodes;
- dispatch independent ready nodes concurrently when execution contracts permit it;
- enforce already-authored dependency, timeout, retry, and fallback policy;
- propagate cancellation and terminal dependency state;
- retain bounded execution traces;
- report node-level execution facts.

DAGEngine must not:

- infer what the person meant;
- invent a new Work node or Capability;
- rewrite Planner-authored arguments to create a different action;
- choose an alternative Capability after failure;
- create a recovery strategy that was not already committed in the WorkDAG;
- emit `residual_replan` or engine-authored `recommended_next_actions`;
- interpret a terminal result into user-facing meaning;
- author Chromie's speech.

If reality invalidates the current plan, DAGEngine reports execution facts. Evidence/Situation then re-enter the same Planner, which may author a revised or new WorkDAG.

## Why DAG, not a workflow loop

Chromie's canonical Work graph is acyclic. Acyclicity keeps one bounded plan understandable and prevents the execution engine from becoming a hidden cognitive loop.

A retry that is mechanically and explicitly committed may be represented by a bounded retry policy on a node. A semantic retry such as "the obstacle changed the situation; find another way" is not an engine loop:

```text
WorkDAG A
  ↓
DAGEngine
  ↓ failure Evidence
Planner
  ↓
WorkDAG B
```

This is the normal human-like boundary: execution reports reality; cognition decides what reality means.

## Revision and continuity contract

`dag_id` is stable while Planner is revising one coherent body of Work. The first committed revision is `revision=1`; every semantic modification uses the same `dag_id`, increments `revision` exactly once, and sets `parent_revision` to the immediately previous revision.

There are two normal outcomes when Goal Association or new Evidence changes the situation:

```text
Goal / Evidence change
        ↓
      Planner
        ├── current topology still valid
        │       ↓
        │   NO_CHANGE / reuse existing Activity
        │       ↓
        │   DAGEngine continues current revision
        │
        └── future Work must change
                ↓
          WorkDAG revision N+1
                ↓
             DAGEngine
```

Goal Association never edits WorkDAG. GA owns Goal continuity only. A new/updated Goal creates a Planner opportunity; only Planner may decide whether to preserve, extend, merge, replace, or cancel planned Work.

Completed execution history is immutable. When revision `N+1` follows an authoritative trace for revision `N`, DAGEngine mechanically verifies that every already-successful/skipped node still exists with identical committed semantics. Those nodes are inherited as execution facts and are **not dispatched again**. Pending/unstarted topology may change because Planner owns future HOW. DAGEngine enforces revision monotonicity and history integrity but does not decide what the revision should contain.

A WorkDAG is not required to become a session-global mega graph. Planner may keep independent coherent Work in separate DAGs and merge/revise only when Goals have real coordination/dependency needs.

## Node contract

The canonical model is `agent.app.work_dag.models.WorkDAG`.

A WorkDAG has:

- `dag_id`: stable URL-safe identity for one coherent body of planned Work across revisions;
- `revision`: monotonically increasing semantic revision authored by Planner;
- `parent_revision`: exactly the previous revision for revision > 1;
- `version`;
- `summary`: Planner-authored bounded plan summary;
- `goal_ids`: canonical Goals whose Work is represented by this revision;
- `revision_reason`: bounded Planner-authored reason for a semantic revision;
- `authored_by`: `planner` for canonical Chromie Work. `operator`/`system`/`user` are limited to standalone revision-1 diagnostic/control-plane fixtures; semantic revisions after revision 1 are Planner-only;
- optional `max_duration_s`;
- `nodes`;
- graph-level deterministic failure/timeout policy.

A `WorkNode` has:

- `id`;
- `capability_id`;
- `role`: `activity`, `monitor`, `confirmation`, `report`, or `safety`;
- `args`;
- `source_goal_ids`: exact canonical Goal ownership for Planner-authored nodes;
- `depends_on`;
- `during` for monitor sidecars;
- optional timeout/retry/failure policy;
- optional pre-authored event/fallback policy.

`role` is an execution-role hint, not an intent taxonomy. There are no `query`, `plan`, `chat`, `tool`, or Router-style cognitive node types.

## Confirmation and physical safety

Planner-authored WorkDAG does not bypass existing safety boundaries.

Physical work still passes through deterministic validation, confirmation requirements, Capability Runtime authorization, provider preflight, and Soridormi safety/execution contracts. DAGEngine may verify that required confirmation/monitor structure exists; it does not decide that confirmation is unnecessary.

A Planner-created retry or replacement Work after failure goes through the same normal confirmation and safety path again.

## Failure and Evidence

DAGEngine traces contain execution facts such as:

- `dag_id`;
- terminal DAG status;
- Planner-authored summary;
- node status, Capability id, attempts, error, and blockers;
- diagnostic execution events.

The `chromie.work_dag.execute` adapter projects a bounded subset as trusted Capability result Evidence:

- `dag_id`, `dag_revision`, and the Planner-authored `goal_ids`;
- terminal status;
- node results with their original `source_goal_ids`, plus `inherited_from_revision` when completed Work was carried forward without re-execution;
- `pending_node_ids`;
- provider-reported `reason_code` / `blocked_subsystems` where present;
- provider-reported next-action suggestions only under the provenance-explicit name `provider_reported_next_actions`.

Provider suggestions are evidence about what the provider reported. They are not DAGEngine recommendations and do not authorize follow-up Work.

There is deliberately no `outcome_summary` and no `residual_replan` layer. Planner owns post-Evidence meaning and replanning.

## Planner-facing capability boundary

For the current implementation, Planner may choose the Capability:

```text
chromie.work_dag.execute
```

with a fully authored `dag` argument. This is an execution boundary, not delegation of planning to DAGEngine. The Capability accepts a WorkDAG that already contains the Work topology.

A future canonical Plan representation may make WorkDAG first-class rather than nesting it under an execution Capability. That is a representation decision only; it must not change the authority rule above.

## Agent control-plane API

The Agent exposes deterministic WorkDAG/DAGEngine endpoints:

- `POST /work-dags/validate`
- `POST /work-dags/dry-run`
- `POST /work-dags/execute-read-only`
- `POST /work-dags/execute-planning`
- `POST /work-dags/execute-guarded`
- `POST /work-dags/confirmation-grants`
- `POST /work-dags/{dag_id}/cancel`
- `GET /work-dags/{dag_id}/trace`
- `GET /work-dags/engine/status`

The guarded execution and cancellation surfaces require the DAGEngine execution bearer token. Dry-run and diagnostics use the diagnostics token and fail closed when it is not configured.

The execution modes are deterministic qualification/acceptance surfaces. They do not create separate semantic Planners. Direct operator/system/user fixtures may create standalone revision-1 DAGs for diagnostics, but only Planner may author a semantic revision after revision 1.

## Provider-local DAGs

A Provider may expose an atomic Capability whose implementation internally uses its own DAG, state machine, controller, or planner.

For example:

```text
Chromie Planner
  ↓
soridormi.bring_water       one advertised Capability
  ↓
Soridormi-local DAG         provider implementation detail
```

That is not a duplicate Chromie Planner. Chromie owns HOW at the level exposed by current provider affordances; Soridormi owns how it fulfils the capability contract it advertises.

Soridormi payloads may therefore continue to use provider-owned fields such as `task_graph`. Those fields are intentionally not renamed to Chromie `WorkDAG` unless the provider contract itself changes.

## Non-negotiable invariants

1. Planner is the sole ordinary semantic author and modifier of Chromie-level WorkDAG topology.
2. WorkDAG is representation, not cognition.
3. DAGEngine is deterministic execution mechanics, not cognition.
4. WorkDAG remains acyclic.
5. DAGEngine never invents replacement Work or user-facing meaning.
6. Normal node completion returns to DAGEngine for mechanical continuation; it does not require a Planner call.
7. Material failure, Goal change, or other semantic invalidation returns to Planner; DAGEngine never replans.
8. Completed nodes are immutable execution history and are inherited, never re-executed, across a valid next revision.
9. GA changes Goal continuity only; WorkDAG changes always pass through Planner.
10. Provider-local DAGs remain valid behind provider Capability boundaries.
