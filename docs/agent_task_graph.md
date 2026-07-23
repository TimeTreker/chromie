# Agent TaskGraph

## Status

Implemented as part of the structured embodiment foundation and used by the
current simulator platform. Validation, dry-run, read-only execution, planning
execution, guarded execution, confirmation grants, cancellation, bounded
concurrency, traces, and scheduler inspection are present and automatically
tested.

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

## Global and Embodied Graphs

Chromie's TaskGraph is the global orchestration graph. It is appropriate for
user-facing and cross-capability work such as:

```text
understand request
  -> search or recall candidates
  -> ask the user to choose
  -> wait for confirmation
  -> inspect Soridormi task capabilities if support is uncertain
  -> preview Soridormi embodied task if clarification or refusal explanation is useful
  -> submit a Soridormi embodied task
  -> monitor Soridormi progress/events
  -> report completion or failure
```

Soridormi may run its own internal embodied graph or state machine after a
Soridormi task node is submitted. That body-facing graph owns sensing,
localization, target/route validation, local trajectory planning, gait/skill
selection, safety monitoring, recovery, and safe-idle reporting.

Chromie's graph should not expand rich embodied goals into low-level body
controls. `walk_velocity(vx_mps=0.2, duration_s=10)` is a concrete body skill
request and remains useful for explicit tests or simple motion commands, but
requests such as "go to the grocery", "bring me water", "dance",
"inspect the door", or "approach that person" should be routed as
capability-level Soridormi tasks when supported. Unsupported or unsafe tasks
should fail closed with a reason.

When the shared capability catalog finds only Soridormi task-level planning
tools for a rich embodied request and a TaskGraph planner is enabled, Chromie
routes the request to the tool-planning lane rather than the direct named-skill
lane. Explicit bounded commands still prefer interaction-executable named
skills such as `soridormi.walk_velocity` when the live catalog exposes them.
This keeps "walk forward for one second" concrete, while "bring me water" stays
a structured Soridormi task goal.

When available, `soridormi.task.preview` is the planning-only way to inspect
Soridormi's embodied interpretation before submitting a persistent task. Preview
outputs are useful for clarification and reporting, but they are not execution
receipts and cannot be monitored with `soridormi.task.status`.
`soridormi.task.get_capabilities` is even earlier in the flow: it reports
Soridormi-owned task readiness and missing body subsystems without constructing
a preview or task record.
Persistent task submission should use a Chromie-owned `client_task_ref`, usually
derived from the global TaskGraph node id. Soridormi treats that reference as
an idempotency key: retrying the same payload returns the original task with
`idempotent_replay=true`; reusing the key for a different payload fails.
Soridormi task outputs may also include `recommended_next_actions`. Chromie's
graph may use those hints to choose a safe next node, but must still validate
every provider call through the active Capability Registry.
For monitoring, `soridormi.task.events` returns
`soridormi.task_events.v1` with `latest_sequence`, `next_after_sequence`,
`terminal`, `safe_idle`, `deadline_at`, `expired`, and
`poll_recommendation`. Chromie's graph should keep the cursor with the global
node state and stop polling once Soridormi reports a terminal state.
Chromie's `agent.app.soridormi_task_client.SoridormiTaskClient` is the current
provider-facing helper for that lifecycle. It derives bounded
`client_task_ref` values from global graph/node ids, submits
`soridormi.task.submit`, polls `soridormi.task.events` by cursor until terminal
state, and invokes `soridormi.task.cancel` only with safety-control
authorization.
`execute-planning` wraps its invoker with the Soridormi task monitor. A
`soridormi.task.submit` node without an explicit `client_task_ref` receives one
from the graph/node id, terminal event state is merged back into the node output
under `monitoring`, and terminal `reason`, `reason_code`,
`blocked_subsystems`, and `recommended_next_actions` fields are promoted to the
node output for deterministic reporting. Soridormi refused/failed/cancelled or
expired tasks become failed TaskGraph nodes instead of successful planning
nodes; their node error preserves the refusal code, blocked subsystems, and
machine-readable next-action hints without inventing a motion workaround.
Every execution trace also carries `outcome_summary`, a deterministic one-line
result summary derived from node results. It is the source that future report
or speech nodes should use when explaining completion, refusal, timeout,
cancellation, or blocked Soridormi subsystems without asking an LLM to infer the
failure. Failed and aborted traces additionally carry `residual_replan` context
that preserves the original goal, completed steps, failed step, failure code,
current physical state, irreversible effects, Soridormi recommended next
actions, and a residual-only replan scope. This context is advisory: it is not
a retry authorization, and any follow-up plan must be newly validated and pass
the usual confirmation, SkillRuntime, and Soridormi gates.
Planning execution may run `chromie.report` nodes through a local trace-only
adapter, primarily as failure-policy fallback nodes. This records a report in
the execution trace without invoking TTS or audio playback. `chromie.speak`
remains outside planning execution; audible speech still belongs to the native
InteractionResponse and host Skill Runtime path.
Native `POST /interaction` emits planned graphs as
`chromie.task_graph.execute` Skill Runtime requests. The host Orchestrator wires
that skill to the Agent's planning executor, which still requires
`AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1`; if the planning executor is
disabled or returns a failed trace, the skill result is failed and completion
speech is suppressed.
The LLM TaskGraph planner normalizes Soridormi `soridormi.task.submit` nodes
that lack an explicit failure fallback by adding a `chromie.report` trace-only
fallback that reports the submit node's `error` field. Existing explicit
fallbacks are preserved.
When Soridormi returns `task_graph`, treat it as Soridormi's body-runtime DAG:
Chromie may display, monitor, or route from it, but must not translate it into
raw motor, joint, torque, or policy outputs. Chromie's own TaskGraph remains the
global user/task graph above that body DAG.

For the staged Chromie-side implementation plan, see
`docs/CHROMIE_SORIDORMI_TASK_AGENT_IMPLEMENTATION_PLAN.md`.

## Next Routing Targets

Soridormi's current no-motion task surface is declared in the authoritative
manifest. Chromie should add routing only for those declared task types and
preserve Soridormi refusal metadata for future-blocked goals.

Near-term task targets:

- `move_forward`, `move_velocity`, and `turn_to_heading` for bounded explicit locomotion;
- `look_at_target` and `perform_gesture` for attention and social cues;
- `skill_sequence` for ordered named-skill requests;
- `recover_safe_idle` and `stop_now` for safe-idle and stop semantics;
- `navigate_to_location`, `approach_target`, and `deliver_object` only as
  structured refusals until Soridormi proves the required simulator pipelines.

For each target, Chromie tests should assert the global graph shape,
confirmation behavior, provider-call arguments, refusal handling,
`blocked_subsystems`, `recommended_next_actions`, terminal events, and
`outcome_summary`. Missing or unsupported task types should remain structured
refusals or clarifications, not fallback velocity recipes.

Motion-control model training is intentionally outside this graph layer until
Soridormi has retained task metrics, calibration, telemetry, and safety
envelopes for a selected target.

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

References are resolved by the executor's reference mechanism; they do not
allow arbitrary code execution. Supported forms are
`<node>.output[.<field>]`, `<node>.error`, and `<node>.status`. Fallback report
nodes may reference the failed node named by the source node's failure policy
without adding a normal dependency edge.

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

- requires the TaskGraph diagnostics bearer token;
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
- the store is capacity-bounded and purges expired entries;
- issuance requires the execution bearer token.

The API proves TaskGraph control-plane binding. The separate host Orchestrator
implements the spoken request-bound confirmation dialogue used by the
InteractionResponse and Skill Runtime path.

## Cancellation and traces

- `POST /task-graphs/{graph_id}/cancel` cancels an active graph or records a
  bounded cancel-before-start tombstone when the execute request has not yet
  registered, and requires the execution bearer token. A later matching
  execute returns a cancelled trace without invoking a tool. A retained
  terminal trace returns `cancellation_requested=false`, and an execution
  retry with that retained `graph_id`, exact graph fingerprint, and execution
  lane returns the retained trace without invoking tools. Guarded retry also
  requires a fresh valid graph-bound grant.
- `GET /task-graphs/{graph_id}/trace` returns the latest non-expired retained
  trace or 404 and requires the diagnostics bearer token.
- `GET /task-graphs/scheduler/status` reports active/waiting counts and graph IDs
  and requires the diagnostics bearer token.

TaskGraph traces keep the planner-provided `summary` and add an
`outcome_summary` after execution. `outcome_summary` is deterministic and
reports the first non-success node with any available `reason_code`,
`blocked_subsystems`, and `recommended_next_actions`; successful traces report a
plain completion result.

Active executions, traces, grants, and pending cancel-before-start tombstones
live only in the Agent process; restarting the service removes them. Traces and
tombstones default to a 900-second TTL and a 128-entry bound. Grants default to
a 128-entry capacity. Configure these with
`AGENT_TASK_GRAPH_TRACE_TTL_SEC`, `AGENT_TASK_GRAPH_TRACE_MAX_ENTRIES`, and
`AGENT_TASK_GRAPH_GRANT_MAX_ENTRIES`.

`graph_id` is a cancel-route identity and must contain 1–128 URL-path-safe
letters, digits, periods, underscores, colons, or hyphens. It is also the
execution idempotency identity and must not be reused for a different graph
or successful execution lane until its retained trace expires. Dry-run traces
remain diagnostics-only and cannot satisfy or block real execution/cancellation.

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
- Dry-run, trace, and scheduler diagnostics require
  `AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN`. A blank value falls back to the execution
  token; if neither token is configured, diagnostics return 503.
- Validation and capability inspection remain unauthenticated; keep the Agent
  on a trusted network or place it behind an authenticated proxy.
- No TaskGraph API should expose raw motor, torque, joint, or actuator fields.

## Acceptance

Automated coverage includes graph validation, planning, read-only/planning
execution, guarded grants, cancellation, MCP invocation policy, resource
arbitration, retries/timeouts, deterministic traces, Soridormi manifest
compatibility, and guarded dry-run/runtime-cancellation paths.

Current evidence and commands are maintained in
[`ACCEPTANCE.md`](ACCEPTANCE.md), not inferred from milestone labels alone.
