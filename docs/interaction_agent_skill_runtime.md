# Interaction Agent and Skill Runtime

## Current status

The structured interaction architecture is part of the completed structured
embodiment foundation and is exercised by the current alpha acceptance work.

Implemented now:

- strict shared interaction contracts;
- native `POST /interaction` output plus explicit compatibility rollback;
- host Interaction Coordinator;
- trusted Skill Registry and providers;
- local speech as a named runtime skill;
- Soridormi named-skill discovery and execution;
- bounded scheduling and exclusive groups;
- timeouts, traces, cancellation, and barge-in propagation;
- host-owned spoken request-bound confirmation with expiry and denial;
- simulation-only auto-confirm exemptions;
- deterministic text-driven live Soridormi acceptance.

Open alpha gates:

- rerun the automatic matrix with spoken approval and denial evidence;
- run and review the implemented seven-case microphone/MuJoCo evidence flow on
  the reference host;
- close applicable target-evidence tracks and publish the prepared alpha
  candidate only after all blockers are removed.

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
```

The execution boundary—not the model—owns validation, availability,
confirmation, resource policy, timeout, cancellation, and provider calls.

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
3. serialize and revalidate the complete `InteractionResponse` contract;
4. return native output with `interaction_output_mode=native` metadata.

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
- Speech-only fallback may continue when safe, but must not claim a failed action
  completed.
- Interruption must stop playback and cancel the owning interaction without
  cancelling unrelated work.

## Feature gates

```env
ORCH_ENABLE_INTERACTION_RESPONSE=0
ORCH_ENABLE_SORIDORMI_SKILLS=0
ORCH_AUTO_CONFIRM_SIM_SKILLS=0
ORCH_CONFIRMATION_TTL_SEC=20
ORCH_SKILL_MAX_CONCURRENCY=8
AGENT_INTERACTION_OUTPUT_MODE=native
AGENT_NATIVE_INTERACTION_FALLBACK=0
```

Defaults remain conservative. Enable structured speech-only rollout before
Soridormi skills, then close simulator acceptance before any supervised hardware
work.

## Acceptance

The deterministic text-driven live Soridormi flow is exercised by:

```bash
./scripts/interaction_text_acceptance.py
```

It covers Router, native Agent interaction output, strict contracts,
trusted Skill Runtime scheduling, live Soridormi MCP, and a test speech
scheduler. It deliberately does not prove microphone capture, real TTS
playback, or hardware motion.

The complete alpha microphone matrix and evidence requirements are maintained in
[`ACCEPTANCE.md`](ACCEPTANCE.md). Run and verify it with:

```bash
python scripts/m13_voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<acceptance-id>
```

The runner records correlated JSONL session events through
`ORCH_EVENT_LOG_PATH`, redacted runtime configuration, audio devices, logs,
recordings, automated checks, and operator notes. Tooling existence is not
reference-host evidence.
