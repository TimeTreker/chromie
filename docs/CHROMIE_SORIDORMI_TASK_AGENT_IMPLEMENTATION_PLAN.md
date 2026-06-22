# Chromie and Soridormi task-agent implementation plan

This is the Chromie-side companion to Soridormi's task-agent implementation
plan. Soridormi owns the embodied robot runtime. Chromie owns the user-facing
brain, global task graph, confirmation loop, provider selection, and progress
reporting.

The matching Soridormi repository doc should define the body-runtime side of
this plan: task-level MCP APIs, embodied task schemas, local planning,
execution, monitoring, recovery, and MuJoCo-first validation.

Related Chromie docs:

- `docs/PROJECT_CHARTER.md`
- `docs/interaction_agent_skill_runtime.md`
- `docs/agent_task_graph.md`
- `docs/agent_capability_registry.md`
- `docs/ACCEPTANCE.md`

Related Soridormi docs:

- `docs/CHROMIE_SORIDORMI_MULTI_AGENT_ARCHITECTURE.md`
- `docs/CHROMIE_SORIDORMI_TASK_AGENT_IMPLEMENTATION_PLAN.md`
- `docs/SORIDORMI_MCP_SERVER.md`
- `docs/SORIDORMI_NAVIGATION_GOAL_CONTRACT.md`

## Current agreement

Chromie owns the human-facing brain layer:

- understand the user request;
- keep conversation, task, memory, and confirmation context;
- ask clarifying questions;
- resolve candidates such as places, people, objects, or named targets;
- build the global task graph;
- select MCP capability providers;
- submit structured embodied goals to Soridormi;
- monitor Soridormi task status and events;
- explain completion, refusal, blocked state, cancellation, or failure to the
  user.

Soridormi owns the embodied robot layer:

- expose robot capabilities through MCP;
- validate embodied goals and atomic body skills;
- maintain robot state, safety state, and active embodied task state;
- run sensing, local planning, gait selection, control, monitoring, and
  recovery;
- decide whether a task is executable, blocked, unsupported, unsafe, cancelled,
  or complete;
- validate motion in MuJoCo before any hardware path.

Both systems may use an orchestrator or DAG engine. Chromie's graph is global
and user-facing. Soridormi's graph or state machine is body-facing and
safety-critical.

## Top-view direction

This plan exists to keep Chromie on its main target: a local-first realtime
voice and decision control plane that can request embodied capability safely.
The task-agent work is not a new low-level robot controller and not a general
autonomy expansion. It is the high-level brain/body contract needed before a
physical pilot:

- Chromie may plan, clarify, confirm, submit, monitor, cancel, and explain a
  structured embodied goal.
- Soridormi decides whether that goal is executable, unsupported, unsafe,
  blocked, cancelled, or complete.
- Physical motion remains Soridormi-owned and default-off until retained
  simulator and commissioning evidence exists for the exact path.

The practical rule is simple: Chromie can say "submit and monitor a navigation
goal"; it must not invent "drive these joints or velocities until you arrive"
when Soridormi has not declared that body capability.

## Next implementation section

Soridormi's high-level no-motion task and skill surface is now declared in the
authoritative capability manifest. The next section is Chromie routing into
that declared surface, before motion-control model training and before any
physical execution claims.

Current priority task types:

- `move_velocity` and `turn_to_heading` for bounded explicit locomotion;
- `look_at_target` for attention, gaze, or facing behavior;
- `perform_gesture` for nod, shake, and expressive body gestures;
- `skill_sequence` for ordered Soridormi named-skill requests;
- `recover_safe_idle` and `stop_now` for recovery and stop semantics;
- `navigate_to_location`, `approach_target`, and `deliver_object` as
  future-blocked structured refusals until Soridormi proves the required
  simulator pipelines.

Chromie should consume these declared contracts through the capability manifest
and route user requests into them. If Soridormi does not declare or enable the
task type, Chromie should clarify or refuse instead of lowering the request
into a velocity or pose workaround.

Motion-control model training is later work. It needs a selected simulator or
robot target, retained calibration and telemetry, task-level success metrics,
and Soridormi-owned safety envelopes.

## Build order

### Step 1 - Freeze the boundary contract

Goal: make the brain/body interface explicit in both repositories.

Chromie deliverables:

- link to the shared Chromie/Soridormi architecture agreement;
- document that Chromie owns global task context and user confirmation;
- document that Soridormi owns embodied planning, execution, and recovery;
- keep raw motor, joint, torque, actuator, controller-array, and low-level
  policy outputs out of model-facing contracts;
- keep concrete body skills separate from rich embodied goals.

Gate:

```text
Chromie docs state that the Agent may propose structured goals or registered
skills, but must not send raw robot controls or bypass Soridormi refusal
```

### Step 2 - Prepare for Soridormi task-level MCP APIs

Goal: keep existing named-skill support while preparing Chromie to consume a
richer Soridormi task API.

Soridormi now declares this contract-only surface:

```text
soridormi.task.get_capabilities
soridormi.task.preview
soridormi.task.submit
soridormi.task.status
soridormi.task.events
soridormi.task.cancel
```

Chromie should treat this as a provider capability, not as a replacement for
all existing skills. Atomic requests can still use `soridormi.skill.*` when the
user intent is already concrete and the skill is enabled. The current task
surface reports `no_motion=true` and `execution_mode=contract_only`, so Chromie
must not report the embodied goal as physically completed unless a later
Soridormi execution status proves it.

Gate:

```text
Chromie can represent a Soridormi task submission as a trusted provider call,
and unavailable task APIs fail closed instead of falling back to unsafe control
```

Current state: the checked-in Soridormi capability snapshot includes
`soridormi.task.get_capabilities`, `soridormi.task.preview`,
`soridormi.task.submit`, `soridormi.task.status`, `soridormi.task.events`, and
`soridormi.task.cancel` as no-motion contract tools.
`task.get_capabilities` is Soridormi's body-runtime readiness declaration: it
reports dry-run-ready tasks, planning holds, safety redirects, future-blocked
tasks, missing Soridormi subsystems, and external dependencies. Preview uses a
non-persistent `preview_id` and is useful before clarification or user
confirmation. Submit creates a task record with `task_id`.
The task status schema also includes `phase`, `terminal`, and
`allowed_next_phases`; Chromie should monitor those fields and Soridormi task
events before speaking completion. Some simple structured tasks may complete as
`execution_mode=skill_dry_run`; Chromie must still treat `no_motion=true` as no
physical execution. Multi-step structured requests may complete as
`execution_mode=skill_sequence_dry_run` and expose `skill_sequence` step
metadata; this proves contract compilation only, not real robot motion through
the task API. Task status may also include `plan_steps` and
`blocked_subsystems`, which explain Soridormi's embodied interpretation and
missing subsystems without exposing raw robot controls.
It may also include `task_graph`, Soridormi's body-runtime DAG view with node
IDs, sequence edges, current phase, terminal state, and raw-control denial.
Chromie may monitor or report from this graph, but Chromie's own TaskGraph
remains the global user/task graph and must not lower Soridormi's body graph
into raw robot controls.
`recommended_next_actions` gives Chromie machine-readable routing hints such as
submit after confirmation, monitor/cancel, call dedicated stop tools, report a
blocked capability, or avoid lowering a missing-capability goal into a velocity
recipe.

### Step 3 - Model structured embodied goals

Goal: define the shape of body goals Chromie may submit after user-facing
planning.

Candidate goal types from Chromie's point of view. The first five are the next
priority for Soridormi-side enrichment:

- `approach_target` for locally bounded approach behavior;
- `navigate_to_location` for resolved destination goals;
- `look_at_target` for attention and gaze behavior;
- `perform_gesture` for nod, shake, and expressive body gestures;
- `recover_safe_idle` for recovery requests;
- `move_velocity` for explicit concrete motion requests;
- `turn_to_heading` for bounded heading changes;
- `skill_sequence` for bounded ordered body-skill sequences;
- `speak_while_moving` for coordinated interaction;
- `stop_now` for deterministic interruption;
- future `deliver_object` only after Soridormi declares manipulation support.

The Agent may keep the original user wording for traceability, but the
provider call must carry structured parameters, constraints, timeout policy,
and context. Natural language is not a low-level control channel. Returned
`plan_steps` can be shown to users or logs as explanation, but Chromie must not
execute them as a substitute for Soridormi-owned control.
Returned `recommended_next_actions` may guide Chromie's graph routing, but it is
not user-facing copy and not proof of physical execution.

Gate:

```text
Chromie validates structured goal payloads before invoking Soridormi and records
why a goal was submitted, refused, cancelled, or completed
```

### Step 4 - Extend Chromie's global TaskGraph patterns

Goal: represent rich embodied work as global graph nodes without expanding them
into body-control recipes.

Example for "let's go to the nearby grocery":

```text
understand request
  -> search or recall candidate groceries
  -> ask the user which one
  -> wait for confirmation
  -> inspect Soridormi task capabilities if needed
  -> preview Soridormi navigate_to_location task if needed
  -> submit Soridormi navigate_to_location task
  -> monitor Soridormi progress/events
  -> report arrival, blocked state, cancellation, or failure
```

The `submit Soridormi task` node is a provider call. The details below that
node belong to Soridormi: target resolution validation, localization, local
route planning, obstacle handling, gait, controller behavior, and recovery.
When Soridormi returns `blocked_subsystems`, Chromie should report or clarify
based on that refusal instead of inventing a velocity workaround.

Gate:

```text
TaskGraph docs and tests show Chromie orchestrating user-facing subtasks while
Soridormi owns embodied substeps
```

### Step 5 - Decide concrete skill versus rich task routing

Goal: make routing predictable.

Use concrete Soridormi skills when:

- the user gives a concrete body command such as "walk forward for 10 seconds";
- the target skill is available, enabled, bounded, and safe;
- confirmation and execution gates are satisfied.

Use Soridormi task submission when:

- the request requires sensing, localization, route planning, recovery, or
  multiple embodied substeps;
- the request depends on environmental context;
- the request should remain a goal rather than a velocity recipe.

Refuse or clarify when:

- the task is unsafe;
- Soridormi does not expose the needed capability;
- the target is ambiguous;
- required confirmation is missing;
- the provider is unavailable or reports unsafe state.

Gate:

```text
Chromie does not translate "walk to the house" into walk_velocity, and does not
translate "bring me water" into unsupported motion
```

### Step 6 - Add acceptance-style tests

Goal: test the user-facing planning boundary before adding more autonomy.

Dry-run scenarios:

- `stop now` routes to deterministic stop/cancel behavior;
- `turn left then nod twice` becomes a bounded `skill_sequence` dry-run when
  supported;
- `come closer slowly` becomes an approach task or a structured refusal;
- `look at me and say hello` combines attention and speech without raw control;
- `walk forward to the house` refuses or blocks with missing navigation support;
- `bring me water` refuses with missing manipulation/carry/handoff support;
- unsafe physical requests refuse without body motion.

Gate:

```text
Chromie tests assert routing, confirmation, provider-call shape, refusal reasons,
and progress reporting without claiming unsupported Soridormi capability
```

Soridormi's companion suite lives at
`task_acceptance_cases/mcp_task_acceptance.yaml` and currently validates these
task-boundary examples through the local no-motion MCP task service.

### Step 7 - Integrate once Soridormi exposes the task API

Goal: connect Chromie's global graph to Soridormi's task API only after the body
runtime exposes the contract.

Integration expectations:

- load task-level capabilities from Soridormi's manifest;
- submit structured goals through trusted runtime/provider code;
- dispatch native `chromie.task_graph.execute` requests through the host Skill
  Runtime into the Agent planning executor when the planning execution gate is
  enabled;
- monitor task events and final status;
- propagate cancel, stop, timeout, and emergency paths;
- suppress success speech after failed, refused, or partial execution;
- retain traces that correlate Chromie graph nodes with Soridormi task ids.

Gate:

```text
Chromie integration tests pass against dry-run Soridormi task APIs, and live
MuJoCo validation is required before claiming executable embodied behavior
```

Current state: Chromie has `agent.app.soridormi_task_client.SoridormiTaskClient`
as the narrow provider helper for this step. It creates bounded
`client_task_ref` values from global graph/node ids, submits
`soridormi.task.submit`, polls the `soridormi.task_events.v1` cursor until
Soridormi reports terminal state or `stop_polling`, preserves the latest events
on monitor exhaustion, and calls `soridormi.task.cancel` with explicit
safety-control authorization.

Planning TaskGraph execution now wraps its invoker with
`SoridormiTaskMonitoringInvoker`. A `soridormi.task.submit` node receives a
graph/node-derived `client_task_ref` when one is absent, terminal event state is
merged into the node output under `monitoring`, and terminal `reason`,
`reason_code`, `blocked_subsystems`, and `recommended_next_actions` values are
promoted to the node output for deterministic reporting. Soridormi refused,
failed, cancelled, or expired task states fail the graph node instead of
becoming false success, and the node error preserves the refusal code, blocked
subsystems, and routing hints. Execution traces also populate deterministic
`outcome_summary` values from node results, giving future report/speech nodes a
stable source for completion, refusal, timeout, cancellation, and blocked-state
messages. Planning execution can activate `chromie.report` fallbacks through a
trace-only local adapter, but audible `chromie.speak` remains outside the
planning lane. The planner normalizes Soridormi task-submit nodes by adding a
trace-only report fallback when the model omits one, using the submit node's
`error` reference as the report message. This still does not claim physical
execution; it only ensures Chromie's global planning graph treats Soridormi's
task contract as the source of truth.

### Step 8 - Next implementation focus

Goal: turn the task-agent bridge into user-facing planning behavior without
leaving the project target.

Next Chromie-side work should stay in this order:

1. keep route/planner tests green for concrete named skills on explicit
   bounded commands, and `soridormi.task.*` planning for rich goals such as
   navigation, approach, inspection, recovery, or object delivery;
2. keep dry-run graph tests green for task capability inspection, preview,
   submit, terminal event monitoring, refusal, timeout, and cancellation;
3. keep the no-motion task-agent bridge acceptance gate green, including the
   rule that `task_api_no_motion=true` and declared task types are required
   before preview or submit is allowed;
4. keep refusal and blocked-subsystem graph reporting deterministic and concise,
   keep trace-only report fallbacks available for planning graphs, and connect
   audible speech only through the host Skill Runtime path without making
   unsupported Soridormi goals sound like completed motion;
5. only after that, connect the same flow to retained live Soridormi task API
   evidence; physical execution still waits for the reference robot gate.

Gate:

```text
Chromie can explain why a rich embodied request was submitted, refused,
blocked, cancelled, or completed by Soridormi without lowering it into raw
robot controls or claiming physical execution from no-motion evidence
```

## Not now

Do not add these to Chromie while building this plan:

- direct robot-controller output;
- raw joint, torque, actuator, bus, controller-array, or `action_14d` fields;
- bypasses around Soridormi refusal;
- claims that navigation, perception, manipulation, carry, or handoff work
  before Soridormi declares and validates them;
- hidden fallbacks that report success after partial execution;
- physical execution defaults.

## Validation expectation

Docs-only changes:

```bash
rg -n "Chromie-side companion|soridormi.task.submit|Step 4" docs
python scripts/check_docs.py
```

Code or contract changes:

```bash
./scripts/run_tests.sh
python scripts/check_docs.py
```

Live Soridormi integration changes must include Soridormi-side validation and
Chromie acceptance evidence. A Chromie green test alone does not prove robot
motion safety.
