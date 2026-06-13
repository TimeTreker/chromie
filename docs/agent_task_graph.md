# Agent TaskGraph

## Status

Implemented as part of the structured embodiment foundation and used by the
current alpha
platform. Validation, dry-run, read-only execution, planning execution, guarded
execution, confirmation grants, cancellation, bounded concurrency, traces, and
scheduler inspection are present and automatically tested.

TaskGraph support does not mean every graph may execute. Execution classes are
separately gated, and target-machine or hardware acceptance remains separate
from implementation status.

## Purpose

A TaskGraph is a validated directed acyclic graph of named capabilities. It
allows the Agent to describe dependencies, monitoring, confirmation, timeout,
retry, failure, and fallback behavior without exposing raw hardware controls.

The lifecycle is intentionally split:

```text
model or caller proposes graph
  -> replace/untrust model identity where applicable
  -> validate against active Capability Registry
  -> inspect or dry-run
  -> choose an explicitly enabled execution class
  -> invoke through ToolInvoker policy
  -> retain process-local trace
```

A graph returned by `POST /run` is never automatically executed.

## Graph contract

`TaskGraph` contains:

- `graph_id`, `version`, `created_by`, and the original user request;
- English and optional Chinese summaries;
- graph-level confirmation and duration policy;
- a list of unique `TaskNode` objects;
- default failure and timeout policies.

A node includes:

- `id` and registry `tool` identifier;
- type: `query`, `plan`, `action`, `monitor`, `confirmation`, `report`, or
  `safety`;
- validated arguments;
- `depends_on` and optional `during` relationships;
- timeout and retry policy;
- failure, timeout, and event policy;
- an optional condition.

References to prior outputs are resolved by the executor's reference mechanism;
they do not allow arbitrary code execution.

## Validation

`POST /task-graphs/validate` checks the complete graph before execution,
including:

- unique and valid node identifiers;
- known capabilities and argument schemas;
- dependency and monitoring references;
- acyclic structure;
- node type and capability side-effect compatibility;
- confirmation, safety monitor, and fallback relationships;
- policy constraints required by physical or safety-sensitive capabilities.

Validation answers whether the graph is structurally and policy-compatible. It
does not authorize a side effect.

## Execution classes

### Dry-run

`POST /task-graphs/dry-run`

- always available;
- makes no MCP calls;
- simulates dependency and policy behavior;
- can auto-confirm simulated confirmation nodes when requested;
- stores the resulting trace in process memory.

### Read-only

`POST /task-graphs/execute-read-only`

Requires:

```env
AGENT_ENABLE_READ_ONLY_TASK_GRAPH_EXECUTION=1
```

The executor performs full preflight and accepts only capabilities allowed by
the read-only policy. Any ineligible node rejects the graph before remote calls
begin.

### Planning

`POST /task-graphs/execute-planning`

Requires:

```env
AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1
```

This path permits safe reads and stateful `planning_only` capabilities such as
creating a Soridormi plan. A plan is not motion; later execution remains behind
guarded and physical policy.

### Guarded effects

`POST /task-graphs/execute-guarded`

Requires:

```env
AGENT_ENABLE_GUARDED_TASK_GRAPH_EXECUTION=1
AGENT_TASK_GRAPH_EXECUTION_TOKEN=<non-empty-secret>
```

The request must include `Authorization: Bearer <token>` and a valid, unexpired,
single-use confirmation grant bound to the exact graph content. The executor
enforces capability side-effect, monitor, fallback, and confirmation policy.

### Physical execution

Additionally requires:

```env
AGENT_ENABLE_PHYSICAL_TASK_GRAPH_EXECUTION=1
```

Physical enablement is rejected at startup unless guarded execution is also
enabled. Before a physical node can run, the graph must provide the required
confirmation proof and a covering safety monitor that is active. Cancellation
or safety failure invokes required stop/emergency fallback behavior.

This feature gate is not a hardware commissioning certificate. Use the target
acceptance procedures in [`ACCEPTANCE.md`](ACCEPTANCE.md).

## Confirmation grants

`POST /task-graphs/confirmation-grants` accepts the exact graph, a set of
confirmed confirmation-node IDs, and a TTL from 1 to 300 seconds. It returns a
short-lived token bound to the graph fingerprint.

Properties:

- only confirmation nodes may be named;
- grants expire;
- grants are consumed once;
- modifying the graph invalidates the grant;
- storage is process-local;
- issuance requires the execution bearer token.

The API proves TaskGraph control-plane binding. The separate host Orchestrator
implements the spoken request-bound confirmation dialogue used by the
InteractionResponse and Skill Runtime path.

## Cancellation and traces

- `POST /task-graphs/{graph_id}/cancel` requests cancellation of an active graph
  and requires the execution bearer token.
- `GET /task-graphs/{graph_id}/trace` returns the latest retained trace or 404.
- `GET /task-graphs/scheduler/status` reports active/waiting counts and graph IDs.

Active executions, traces, and grants live only in the Agent process. Restarting
the service removes them.

## Concurrency

Enable eligible parallelism with:

```env
AGENT_ENABLE_PARALLEL_TASK_GRAPH_EXECUTION=1
AGENT_TASK_GRAPH_MAX_CONCURRENCY=4
```

The shared `ResourceArbiter`:

- bounds total work;
- honors capability `can_run_parallel`;
- serializes matching `exclusive_group` values;
- respects graph dependencies;
- returns node results in deterministic graph order;
- scopes cancellation to the owning graph.

Physical work remains sequential. The arbiter is process-local, so Soridormi
continues to enforce cross-process robot exclusivity. See
[`task_graph_concurrency_decision.md`](task_graph_concurrency_decision.md).

## LLM planning

Enable planning with:

```env
AGENT_ENABLE_TASK_GRAPH_PLANNING=1
AGENT_USE_LLM=1
```

For tool routes, the planner supplies filtered capability context to the model,
parses structured output, replaces model-provided graph identity, marks the
graph `created_by="llm"`, and validates it. Invalid output falls back to the
legacy compatibility tool-action proposal.

Planning is not execution. The caller must explicitly submit the validated graph
to an enabled endpoint.

## Security boundary

- Capability manifests are trusted deployment inputs and fail fast at startup.
- Model output is untrusted and revalidated.
- All remote calls cross `ToolInvoker` authorization policy.
- Guarded write endpoints require a bearer token.
- Inspection and trace endpoints are currently unauthenticated; keep the Agent
  on a trusted network or place it behind an authenticated proxy.
- No TaskGraph API should expose raw motor, torque, joint, or actuator fields.

## Acceptance

Automated coverage includes graph validation, planning, read-only/planning
execution, guarded grants, cancellation, MCP invocation policy, resource
arbitration, retries/timeouts, deterministic traces, Soridormi manifest
compatibility, and guarded dry-run/runtime-cancellation paths.

Current evidence and commands are maintained in
[`ACCEPTANCE.md`](ACCEPTANCE.md), not inferred from milestone labels alone.
