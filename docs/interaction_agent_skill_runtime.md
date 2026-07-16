# Interaction Agent and Skill Runtime

## Current status

The structured interaction architecture is part of the completed structured
embodiment foundation and is exercised by the current simulator acceptance
work.

Implemented now:

- strict shared interaction contracts;
- native `POST /interaction` output plus explicit compatibility rollback;
- host Interaction Coordinator;
- trusted Skill Registry and providers;
- local speech as a named runtime skill;
- Soridormi named-skill discovery and execution;
- host dispatch for native `chromie.task_graph.execute` requests into the
  Agent planning TaskGraph executor;
- bounded scheduling and exclusive groups;
- timeouts, traces, cancellation, and barge-in propagation;
- host-owned spoken request-bound confirmation with expiry and denial;
- simulation-only auto-confirm exemptions;
- deterministic text-driven live Soridormi acceptance.

Open release-support gates:

- physical microphone/speaker validation if a release claims real voice-device
  support;
- physical pilot commissioning evidence before any real robot motion claim.

## Design goal

The language model may propose speech and validated named skills. It must not
emit or authorize raw robot controls.

```text
user speech
  -> deterministic operational controls
  -> structured interaction reasoning
  -> strict InteractionResponse
  -> trusted host Skill Runtime
      -> speech provider
      -> Soridormi named-skill provider
      -> planning TaskGraph provider
```

The execution boundary—not the model—owns validation, availability,
confirmation, resource policy, timeout, cancellation, and provider calls.

Before execution, the host also attaches a static preflight audit to the
`InteractionResponse`. This audit can identify unknown skills, missing
providers, version mismatches, unavailable definitions, schema-invalid
arguments, pending confirmation, pending safety-monitor requirements, and
Soridormi catalog checks that must be deferred. It is diagnostic and
fail-closed input for the trusted runtime; it does not prove that the physical
world will allow the action.

Deep-thinking output follows the same boundary. When `deepthinking_agent` needs
to act as the slow semantic brain, it returns a unified ordered list of robot
skill tasks. Speech is represented as the `chromie.speak` skill, and embodied or
tool work is represented as schema-validated candidate `SkillRequest` objects
from the supplied capability catalog. If deep-thinking proposes an effectful
task but no valid runtime skill survives validation, the host coordinator
replaces any optimistic task speech with a deterministic correction before TTS
playback.
The same deep-thinking tasks are also retained as shared-schema
`deepthinking_task_proposals` metadata so the Orchestrator can audit proposed,
committed, rejected, and not-committed work in one `TaskProposalLedger`.
The final Agent response also emits shared-schema `agent_task_proposals` for
every committed speech and skill item; speech is represented as the local
`chromie.speak` skill rather than as a separate privileged lane.
The deep-thinking prompt includes an explicit output contract block: top-level
JSON keys are `tasks` and `reason`, each task contains `skill_id`, `args`,
`timing`, `timeout_ms`, `cancellable`, `requires_confirmation`, and `reason`,
and non-speech task IDs must come from the supplied capability catalog. The
slow-path prompt and spoken-response reviewer use extracted task/session
context rather than raw transcript history.

## Multi-Agent Boundary

Chromie and Soridormi are both agent-like systems, but they operate at different
scopes. Chromie owns the global, human-facing task DAG: understanding the user,
using memory/search/speech, asking clarifying questions, collecting
confirmation, and deciding which capability provider should handle each node.

Soridormi owns the embodied robot DAG or state machine: robot state, body
capability checks, sensing/localization hooks, route or local motion planning,
gait and skill selection, safety monitoring, stop/cancel behavior, recovery,
MuJoCo execution, and future hardware execution.

Chromie should send structured embodied goals to Soridormi, not movement
recipes, for rich requests. For example, "bring me water" should become a
capability-level request such as `deliver_object` and then fail closed today
because the current robot has no manipulator/carry/handoff capability.
"Walk forward to the house" should not become plain `walk_velocity`; it
requires target resolution, localization, route planning, local obstacle checks,
and bounded local trajectory planning inside Soridormi.

Soridormi exposes both atomic skill APIs and a contract-first task API:

```text
soridormi.skill.*  atomic body skills and simple explicit requests
soridormi.task.*   structured embodied goals, currently no-motion contract,
                   preview, skill-dry-run, and skill-sequence-dry-run tools
```

Chromie may orchestrate when to call Soridormi, what to ask the user, and what
to say next. Soridormi remains authoritative for whether and how the robot body
acts. If Soridormi returns `plan_steps` or `blocked_subsystems`, Chromie can use
them for explanation, clarification, and global TaskGraph state, but not as a
recipe to bypass Soridormi's body-runtime boundary.
If Soridormi returns `task_graph`, Chromie may use it as a body-runtime progress
view. It is not Chromie's global TaskGraph and must not be converted into raw
low-level robot control.
`soridormi.task.preview` is specifically for this explanatory/pre-confirmation
path; it uses `preview_id` and does not create a persistent task record.
When Chromie submits a persistent Soridormi task, it should include a stable
`client_task_ref` from Chromie's global TaskGraph node. Soridormi uses that
reference as a retry key: identical duplicate submissions return the original
`task_id` with `idempotent_replay=true`, while conflicting payloads are
rejected.
If Soridormi returns `recommended_next_actions`, Chromie may use them to choose
the next global graph step, such as reporting a blocked capability or calling a
dedicated stop tool, but the hints are not user-facing speech and not execution
receipts.
`soridormi.task.events` returns the monitor cursor
`soridormi.task_events.v1`, including `latest_sequence`,
`next_after_sequence`, `terminal`, `safe_idle`, `deadline_at`, `expired`, and
`poll_recommendation`. Chromie should poll with the returned cursor until the
task is terminal or until Soridormi recommends cancellation/reporting.
The runtime helper `SoridormiTaskClient` keeps this provider lifecycle out of
speech-generation code: it attaches the global graph/node `client_task_ref`,
returns Soridormi's submit/status/event payloads unchanged, advances
`after_sequence`, and routes cancellation through explicit safety-control
authorization.
Chromie's planning TaskGraph executor uses a Soridormi task-monitoring invoker
for `soridormi.task.submit` nodes. The node is not treated as successful merely
because submit returned; Chromie waits for terminal task events when needed, and
Soridormi refusal/failure/cancellation becomes a failed graph node for the
global orchestrator to report or route from.
When the native Agent returns a planned graph, it is emitted as a
`chromie.task_graph.execute` skill request. The host Skill Runtime can dispatch
that request back to the Agent's planning executor. The Agent-side planning
execution flag remains the gate, and failed graph traces become failed skill
results so completion speech is not played after a blocked or refused embodied
task.
`soridormi.task.get_capabilities` is the read-only way to ask Soridormi what
its embodied task runtime can currently dry-run, hold, redirect, or refuse.
Chromie should treat that readiness as Soridormi-owned state.

Near-term enrichment should happen on the Soridormi side first. Add or harden
no-motion/simulator task types for `navigate_to_location`, `approach_target`,
`look_at_target`, `perform_gesture`, and `recover_safe_idle`; then add Chromie
routing and Skill Runtime tests for the declared contracts. Until a task type
is declared, Chromie should clarify or refuse rich embodied requests instead of
falling back to raw motion or low-level named skills. Motion-control model
training waits for Soridormi-owned task metrics, calibration, telemetry, and
safety envelopes.

For the staged Chromie-side implementation plan, see
`docs/CHROMIE_SORIDORMI_TASK_AGENT_IMPLEMENTATION_PLAN.md`.

## Shared contracts

`InteractionResponse` contains:

- `interaction_id`;
- status: `ok`, `clarify`, `refused`, `ignored`, or `error`;
- zero or more `InteractionSpeech` items;
- zero or more `SkillRequest` items;
- aggregate confirmation requirement;
- bounded metadata and reason information.

Speech timing supports `immediate`, `parallel`, `sequential`, and
`after_skills`. Skill timing supports `parallel` and `sequential`.

The models use strict schemas and recursively reject known low-level fields such
as raw joint targets, motor commands, actuator controls, and torque commands,
including when nested in metadata or arguments.

A valid contract is still only a request. The runtime resolves each skill
against a trusted definition and provider before execution.

## Current Agent implementation

`POST /interaction` accepts the same `AgentRunRequest` as `POST /run`:

1. run the specialized-agent pipeline with `InteractionDraft`;
2. create `InteractionSpeech` and `SkillRequest` objects as agents add speech,
   actions, or TaskGraphs;
3. add shared-schema `agent_task_proposals` for the final speech and skills;
4. serialize and revalidate the complete `InteractionResponse` contract;
5. return native output with `interaction_output_mode=native` metadata.

`POST /run` continues to use `AgentResult`. The old
`AgentResultInteractionAdapter` is retained only for explicit rollback mode or
opt-in native-validation fallback. Native validation failures are fail-closed by
default.

The native path preserves:

- deterministic interrupt, stop, and emergency handling outside model control;
- registry-filtered named skills only;
- schema validation and low-level-field rejection;
- deterministic fallback when model output is invalid;
- no direct TTS, MCP, or hardware call from the Agent.

## Host Interaction Coordinator

The coordinator:

- registers `chromie.speak` locally;
- loads the Soridormi named-skill catalog when the provider is enabled;
- attaches session metadata;
- translates speech items into Skill Runtime requests;
- computes applicable simulation confirmation exemptions;
- executes the complete response through one runtime;
- exposes interaction-scoped cancellation.

The coordinator does not invent an unregistered skill when catalog loading
fails. Body requests fail closed.

## Skill Registry and definitions

Each trusted `SkillDefinition` describes:

- stable skill ID and version;
- provider ID;
- input schema;
- availability and reason when unavailable;
- confirmation and monitor requirements;
- timeout, interruptibility, idempotency, and parallelism;
- exclusive resource group;
- provider-specific metadata.

The host registry is distinct from the Agent capability registry. The former
controls runtime provider execution; the latter controls TaskGraph planning and
MCP policy. The native Agent path and host runtime keep these registries separate;
provider resolution and execution authorization remain host-owned.

## Local speech provider

`InteractionSpeech` is converted to a `chromie.speak` request. The provider
calls the Orchestrator's speech scheduler, which coordinates TTS streaming and
playback. Interruptible speech is cancellable during barge-in.

Speech participates in the same timing model as other skills:

- immediate/parallel speech may overlap eligible work;
- sequential speech waits in order;
- `after_skills` speech runs after body/tool requests.

## Soridormi provider

The provider discovers named skills from the live Soridormi catalog and
registers host definitions. A body-skill execution uses Soridormi's managed
sequence rather than sending low-level controls:

1. create a plan for the named skill;
2. establish or verify required safety monitoring;
3. execute the plan;
4. propagate result and trace data;
5. on cancellation, call Soridormi's motion-cancel boundary and preserve
   stop/emergency behavior.

Robot skills share an exclusive resource group so conflicting motion is not run
concurrently. Soridormi remains authoritative when requests arrive from
multiple Chromie processes.

## Runtime scheduling

`SkillRuntime` validates the full scheduled sequence before dispatch and then:

- groups eligible parallel requests;
- respects `can_run_parallel` and exclusive groups;
- bounds work with `ORCH_SKILL_MAX_CONCURRENCY`;
- applies effective timeouts;
- records one trace per request;
- keeps result order deterministic;
- scopes cancellation to the interaction.

Runtime state is in memory. It is not a durable job queue.

## Confirmation

Implemented behavior:

- per-request and per-definition confirmation flags;
- authorization by exact request ID;
- simulation-mode catalog exemptions;
- rejection when required confirmation is absent;
- TaskGraph graph-bound confirmation grants on the Agent side.
- an explicit host-generated, action-specific spoken prompt;
- bounded affirmative and negative phrase matching before Router or Agent use;
- SHA-256 binding to the exact interaction, request IDs, versions, arguments,
  timing, timeout, and metadata;
- short-lived, single-use approval with changed-request and replay rejection;
- fail-closed denial for ambiguity, expiry, or negative replies;
- operational stop, cancel, and emergency phrases cancel the pending approval
  and pass through to the deterministic Router control path;
- correlated `confirmation_requested`, `confirmation_reply`,
  `confirmation_authorized`, and `confirmation_rejected` evidence events.

Only one confirmation is pending in the host process at a time. Its default
expiry is 20 seconds and is configurable with `ORCH_CONFIRMATION_TTL_SEC`.
No hardware motion uses simulation auto-confirm behavior.

## Failure and fallback behavior

- Invalid interaction contracts fail before execution.
- Unknown, unavailable, or version-mismatched skills fail closed.
- Disabled Soridormi support does not fall back to the legacy hardware daemon.
- Provider timeout or cancellation is reflected in `SkillResult` and trace.
- A failed, refused, or timed-out Soridormi skill suppresses its pending
  `after_skills` completion speech and schedules one deterministic,
  language-matched host warning. The warning never retries or substitutes an
  action.
- Speech-only fallback may continue when safe, but never claims a failed action
  completed.
- Interruption must stop playback and cancel the owning interaction without
  cancelling unrelated work.

## Feature gates

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=0
ORCH_AUTO_CONFIRM_SIM_SKILLS=0
ORCH_CONFIRMATION_TTL_SEC=20
ORCH_SKILL_MAX_CONCURRENCY=8
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat
AGENT_INTERACTION_OUTPUT_MODE=native
AGENT_NATIVE_INTERACTION_FALLBACK=0
```

The common safe base owns the `chat` lane through the unified cognitive runtime
while leaving Soridormi skills and simulation auto-confirm off. The maintained
Soridormi launcher widens authority to `chat,robot_action`; simulator acceptance
must still close before any supervised hardware work.

## Acceptance

The behavior-quality text-driven live Soridormi preview is exercised by:

```bash
python scripts/general_ability_acceptance.py --mode live-text \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

It covers Router, goal-driven Agent planning/composition output, strict
contracts, live Soridormi preflight, and representative ability-class
assertions. Use
`scripts/interaction_text_mujoco_check.py --no-speaker` for retained
text-to-simulator evidence. These paths deliberately do not prove microphone
capture, real TTS playback, or hardware motion.

The deployed text-to-MuJoCo check exercises the Router service, goal-driven
association/planning/composition endpoints, trusted Skill Runtime, live
Soridormi MCP, and optional real speaker output while skipping microphone and
ASR. The old Agent `/interaction` path is available only with
`--no-cognitive-runtime` for labelled compatibility diagnosis:

```bash
python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --no-speaker
```

This natural rehearsal sends only the text request into Chromie. The
`--expect-*` flags below are optional regression assertions checked after
Router, Agent, and Soridormi have produced their outputs:

```bash
python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --expect-skill soridormi.walk_velocity \
  --expect-skill soridormi.nod_yes \
  --expect-skill soridormi.turn_in_place \
  --expect-arg 0:vx_mps=0.2 \
  --expect-arg 0:duration_s=10 \
  --expect-arg 1:count=2 \
  --expect-arg 2:yaw_radps=-0.12
```

This command creates a text-MuJoCo evidence directory and fails closed on route,
interaction, execution, or safe-idle mismatch. It uses a 120s per Soridormi
skill diagnostic timeout by default; pass `--skill-timeout-s 0` to use
catalog/default timeouts unchanged. Generated TTS-audio injection is covered by
`scripts/voice_acceptance.py --mode synthetic`; that mode skips the physical
microphone but intentionally keeps VAD and ASR in the path.

The retained `20260617T081411Z` bundle closes the historical M13 text
interaction scope. Physical microphone and ASR behavior are intentionally
separate from that closure.

For broader text-input behavior coverage without executing robot motion, use
the general ability live-text preview:

```bash
python scripts/general_ability_acceptance.py \
  --mode live-text \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

This validates representative text probes against ability-class expectations
and writes `.chromie/acceptance/general-ability/<id>/`. Use `--execute` only
for supervised simulator execution. The older standalone text skill sweep has
been removed because it was not a trustworthy behavior-claim gate.

The physical voice-device matrix and evidence requirements are maintained in
[`ACCEPTANCE.md`](ACCEPTANCE.md). Run and verify it only when a release claim
includes real microphone and speaker operation:

```bash
python scripts/voice_acceptance.py \
  --mode supervised \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
python scripts/verify_voice_evidence.py --require-clean \
  .chromie/acceptance/voice/<acceptance-id>
```

The runner records correlated JSONL session events through
`ORCH_EVENT_LOG_PATH`, redacted runtime configuration, audio devices, logs,
recordings, automated checks, and operator notes. Tooling existence is not
reference-host evidence.
