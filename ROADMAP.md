# Chromie Roadmap

This document is the authority for delivery order and milestone exit criteria.
The stable mission is defined in
[Project Charter](docs/PROJECT_CHARTER.md). Current implementation and evidence
are tracked in [Status](docs/STATUS.md).

## Planning model

Chromie uses a small number of outcome milestones. Historical implementation
increments are not maintained as separate planning units.

- Only one delivery milestone is active at a time.
- A milestone closes only when its implementation and required evidence exist.
- Default-off experimental work is not release support.
- Older evidence tools retain legacy names such as M3, M5, or M13 for
  compatibility; those names do not create additional active milestones.
- Future work must preserve the ownership and safety boundaries in the charter.

## Completed foundations

Earlier work previously labeled M0-M12 is now represented by two completed
capability foundations:

| Foundation | Included outcomes | State |
|---|---|---|
| Realtime interaction foundation | Five-service runtime, host audio/VAD/playback, deterministic routing, contracts, generated configuration, GPU and target tooling | Implemented and automatically verified; some target evidence remains open |
| Structured embodiment foundation | Native interaction, Skill Runtime, Soridormi named skills, TaskGraphs, confirmation, cancellation, bounded scheduling, traces, and MuJoCo integration | Implemented and automatically verified locally and in simulation |

The old M0-M12 numbering remains visible only in historical commits, tool names,
and evidence references. It should not drive new scope.

## Completed phase - Text-to-MuJoCo interaction closure

### Objective

Close the historical M13 interaction milestone by proving the deterministic
text-input path through Router, native `/interaction`, trusted Skill Runtime,
Soridormi named skills, MuJoCo execution, and safe-idle recovery.

This phase is complete. The retained `text-mujoco` evidence proves a compound
text request is routed into ordered walking, nodding, and turning skills, all
executed by Soridormi in MuJoCo, with the simulator returning to safe idle. The
automatic synthetic and virtual-microphone matrices remain retained regression
evidence for the broader voice pipeline.

Physical microphone recognition and speaker quality are deliberately excluded
from M13 closure. They remain an audio-device validation track for any future
release claim that includes real voice input/output support.

### Exit criteria

- `./scripts/run_tests.sh` passes from the candidate revision;
- automatic `synthetic` and `virtual-mic` matrices pass all seven cases;
- the deployed text-to-MuJoCo check passes against live Soridormi MCP and MuJoCo;
- retained text evidence shows ordered `walk_velocity`, `nod_yes`, and
  `turn_in_place` execution plus safe idle;
- exact Chromie and Soridormi revisions are retained;

This closure does not claim robust human ASR, physical microphone/speaker
quality, production robot support, verified Jetson packaging, or unattended
operation.

The voice acceptance scripts and evidence directories still use the historical
`m13` name. That identifier is retained for compatibility only.

## Open evidence track - Physical audio validation

Physical voice validation is no longer a blocker for M13 text interaction
closure. Before publishing a release that claims support for real microphone and
speaker operation, retain a clean supervised bundle, operator review, and
release evidence that cover microphone choice, room noise, ASR recognition,
audible output, barge-in, request-bound approval and denial, cancellation, stop,
and simulator recovery.

## Open evidence track - SenseVoice ASR hardening

The supported ASR path is sherpa-onnx SenseVoice final-utterance
transcription with `ASR_MODE=final`. The Orchestrator continues to own
microphone capture, VAD, utterance boundaries, timeout handling, and barge-in.
The ASR service owns only complete-utterance transcription.

The objective is reliable local realtime speech operation for Chromie, not
unbounded ASR scope growth. The maintained architecture and evidence plan are
documented in [SenseVoice ASR](docs/SENSEVOICE_ASR.md).

Exit criteria before widening voice-device or profile support:

- the pinned SenseVoice dependency and model have immutable provenance and
  maintained-profile coverage;
- English, Chinese, mixed-command, noisy-room, and physical-microphone
  benchmarks show acceptable recognition quality and latency for the intended
  deployment profile;
- stop, cancel, emergency, silence, unusable-audio, confirmation, timeout, and
  barge-in semantics remain unchanged;
- CPU fallback and maintained CUDA profiles fail clearly when model files or
  providers are unavailable;
- retained evidence uses the four-axis status vocabulary and does not turn a
  benchmark into release readiness.

## Open architecture track - Orchestrator task proposal merge

Router, quick intent, and deepthinking stages may all propose tasks, but
effectful work must become an Orchestrator commitment before execution. The
detailed design and implementation sequence are maintained in
[Orchestrator Task Proposal Merge](docs/ORCHESTRATOR_TASK_PROPOSAL_MERGE.md).

Exit criteria before treating this as a complete smart merge layer:

- Router, Agent, and deepthinking task proposals use one shared schema; the
  shared `TaskProposalLedger` contract exists and Router emits shared
  `task_proposals`, the Agent deepthinking path emits shared
  `deepthinking_task_proposals`, and final Agent speech/skills emit shared
  `agent_task_proposals`;
- the Orchestrator can accept, reject, revise, supersede, or commit proposals
  with deterministic audit metadata;
- static host preflight records schema/provider/availability/confirmation
  status without pretending to prove real-world feasibility;
- effectful proposals never execute until committed and authorized through the
  trusted Skill Runtime;
- later-stage corrections can produce concise user-facing repair speech without
  claiming unverified execution;
- retained traces and experience summaries expose proposal, commit, execution,
  and correction causes without injecting raw history into prompts;
- `python scripts/check_docs.py` and `./scripts/run_tests.sh` pass.

## Open architecture track - Semantic task continuity and situational planning

Chromie should preserve open semantic user goals across turns, associate later
utterances with active tasks through model-based meaning understanding, and
select concrete skills only during capability planning. The detailed design and
staged implementation sequence are maintained in
[Semantic Task Continuity and Situational Planning](docs/SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md).

This track complements the proposal ledger. Semantic models propose task
creation, modification, clarification, correction, cancellation, and response
composition. The Orchestrator remains the deterministic authority for task IDs,
versions, lifecycle transitions, authorization, confirmation validity,
commitment, scheduling, and execution evidence.

Exit criteria before treating semantic task continuity as a maintained runtime
capability:

- goals are retained as versioned open semantic descriptions rather than fixed
  action or intent enums;
- one independent user responsibility maps to one RouteItem, while implementation
  steps remain TaskGraph or provider-plan nodes;
- later turns can semantically modify, clarify, confirm, cancel, or query active
  tasks without regex, phrase-table, or lexical-score decisions;
- missing user parameters retain the original task in a waiting-for-user state,
  while missing world facts request observation or trusted lookup;
- capability planning returns a direct skill, valid composition, context request,
  clarification request, or honest unavailable result;
- goal changes supersede stale plans and confirmations before any effectful work
  can execute;
- natural multi-goal feedback is model-composed, while speech claims and
  commitments are checked against trusted task state;
- simple chat and explicit direct-skill latency remain bounded;
- generalization-oriented Level A and retained live-text evidence pass;
- `python scripts/check_docs.py` and `./scripts/run_tests.sh` pass.

## Current checkpoint - Cognitive authority and evidence validation

The active milestone is to validate the implemented Goal-driven Runtime as the
single semantic authority on the intended live-text and MuJoCo target, and to
make retained evidence provenance strong enough that an older run cannot be
mistaken for validation of newer source.

The common safe base enables structured interaction and authoritative `apply`
for `chat` while leaving Soridormi off. The maintained Soridormi launcher
enables that trusted provider and widens authority to `chat,robot_action`. Both
fail closed after the Goal-driven Runtime acquires a turn. Exact Router actions
are adapter-only; the old CapabilityAgent semantic planner is emergency-only
behind both service gates and a non-empty matching-turn authority claim. That
internal claim is exact turn binding, not caller authentication or a consumed
replay nonce.

This checkpoint does not claim physical microphone/speaker quality, Jetson
packaging, real hardware support, navigation autonomy, manipulation,
unattended operation, target validation of the new cognitive path, or release
readiness.

Exit criteria:

- status, architecture, rollout, configuration, acceptance, and component docs
  describe the same authoritative lanes and fallback boundary as source;
- empty or cross-turn legacy-planner authority claims fail closed before model
  planning;
- cognitive simulator evidence contains an applied cognitive result, completed
  Soridormi `sim` execution, explicit safe idle, an exact matching Chromie
  source, manifest, clean declared paired Soridormi checkout, and a matching
  endpoint-reported Soridormi revision;
- release preparation rejects evidence, capability-manifest, compatibility,
  source-revision, or version provenance drift;
- running Chromie images and loaded models are bound to the candidate revision,
  and publishable image references are immutable;
- `python scripts/check_docs.py`, `./scripts/run_tests.sh`, cognitive scenarios,
  and General Ability Level A pass from the candidate revision;
- retained live-text and MuJoCo runs pass through the authoritative path before
  target behavior or release readiness is claimed.

## Open architecture track - General ability acceptance reconstruction

The behavior test framework is being reconstructed so Chromie is evaluated by
general robot abilities, not by one pasted user sentence at a time.

The detailed design and staged implementation plan are maintained in
[General Ability Test Reconstruction](docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md).

Exit criteria before using this track as the default behavior-quality gate:

- the general ability manifest groups representative Level A and live text
  probes by reusable ability class;
- `python scripts/general_ability_acceptance.py --mode check` validates the
  manifest and all referenced deterministic scenarios;
- `--mode level-a` reports ability-class coverage and evidence level without
  overstating live behavior;
- live text preview and simulator execution runs retain partial summaries,
  per-case progress, and useful failure causes instead of hanging silently;
- failures require a root-cause report that names the earliest wrong boundary;
- status, acceptance, release, and coding-agent reports cite exact evidence
  levels rather than saying only that the project was "tested";
- `python scripts/check_docs.py` and the relevant focused test groups pass.

## Implemented tooling track - Developer usability tools

### Objective

Make the existing Chromie stack easier to inspect, diagnose, and support before
adding new control-plane architecture or physical capability scope.

The first implementation focus is a dependency-light CLI that can report the
configured deployment mode, validate generated configuration, inspect risky
feature gates, probe required services, verify capability manifests, inspect
retained trace artifacts, and prepare evidence metadata without overstating
release claims.

The detailed plan is maintained in
[Developer Usability Tools Plan](docs/DEVELOPER_USABILITY_TOOLS.md).

### Sequence

1. document the milestone and command contract before implementation;
2. add a standard-library CLI skeleton exposed first as
   `python -m tools.chromie_cli`;
3. implement `status`, `config show`, and `config validate`;
4. implement `doctor` for environment, files, service reachability, optional
   Soridormi, and host audio checks;
5. implement `capability check` for manifest provenance, duplicates, feature
   gate consistency, and forbidden low-level controls;
6. add evidence-bundle preflight that labels automated, simulator, target GPU,
   physical audio, and hardware evidence separately;
7. document the trace schema and implement retained-artifact `trace view`;
8. defer `trace explain` until causal explanation semantics are stable.

### Exit criteria

- the CLI runs without package installation as
  `python -m tools.chromie_cli`;
- Level A tests cover command parsing, exit codes, configuration validation,
  doctor result classification, manifest safety checks, retained-trace
  filtering, and evidence preflight;
- `doctor` reports skipped, warning, failure, and pass states deterministically;
- service and provider failures include clear causes instead of being hidden by
  fallback behavior;
- evidence tooling preserves the four-axis status vocabulary and does not turn
  automated, dry-run, or no-motion output into target validation or release
  readiness;
- `python scripts/check_docs.py` and `./scripts/run_tests.sh` pass.

### Selective ecosystem alignment

Chromie will absorb external Agent-framework ideas only when they solve a concrete
project problem. The current plan does not add capability-package scanning,
`SKILL.md` execution, arbitrary script plugins, automatic provider registration, or
a package-install command. Optional descriptive conventions may be documented next
to existing manifests, but the manifest/provider contract and trusted execution
path remain authoritative. Revisit packaging or installation only after a real
interoperability use case demonstrates value that cannot be achieved with the
current registry and MCP/provider model.

## Completed phase - Robust simulation and provider readiness

This milestone is complete for the high-level provider contract. The historical
provider-readiness evidence used Soridormi revision
`4afb4bc6411db4a4194e97349d9466a62efd2f24`, which supplied live no-motion
`sim`, `hardware_shadow`, and `hardware_dry_run` profiles plus test-only fault
injection. All three profiles pass conformance and parity, and the live
16-scenario fault matrix passes its terminal-state, latency, and safe-idle
checks.

The provider-readiness run used a local macOS ARM64 MCP endpoint and did not
command MuJoCo actuators or physical hardware. Separate Linux RTX 5090
Voice-to-MuJoCo automated evidence now passes; supervised physical audio and
real-hardware evidence remain separate release tracks.

### Objective

Prove that the system fails safely under non-ideal conditions and that a
physical provider can replace the simulator provider without changing
Chromie's model-facing semantics.

This combines the former “robust simulation” and “hardware-neutral
commissioning contract” proposals because fault behavior and provider
conformance must be designed and verified together.

### Work

- add Soridormi-owned fault injection for latency, jitter, dropped status,
  timeout, unavailable skills, blocked paths, partial execution, restart, and
  monitor failure;
- add Chromie integration cases for provider timeout, disconnect, malformed
  result, cancellation races, and safe user-facing fallback;
- define repeatable scenario batches and thresholds for success, timeout,
  cancellation latency, and safe idle;
- stabilize versioned named-skill request, progress, terminal status, and error
  semantics;
- define provider conformance tests shared by simulator and physical backends;
- add shadow and dry-run commissioning modes;
- define calibration, timing, health, stop, recovery, and evidence requirements;
- keep device drivers and physical safety implementation in Soridormi.

### Exit criteria

- every versioned fault scenario ends in its expected terminal state;
- no injected failure bypasses confirmation, cancellation, stop, or emergency
  policy;
- simulator providers pass the provider conformance suite;
- a no-motion physical-provider skeleton passes the same contract tests;
- shadow and dry-run modes produce comparable, replayable traces;
- no model-facing contract contains device-specific low-level controls;
- a commissioning checklist is sufficient to select the first reference robot.

## Future phase - Physical pilot preparation

### Objective

Select and prepare one explicitly supported robot configuration for a
progressive, supervised rollout. Until the candidate identity, independent
emergency stop, and no-motion prerequisites are reviewed, development remains
in preparation and does not authorize physical motion.

This phase has two coordinated tracks:

1. **Brain/body task boundary.** Chromie prepares global, user-facing
   TaskGraphs that submit structured embodied goals to Soridormi and monitor
   Soridormi's task events. This keeps navigation, approach, gesture,
   recovery, and future manipulation goals above the low-level robot boundary.
   It does not authorize physical motion.
2. **Soridormi high-level task and skill enrichment.** Soridormi should declare
   and implement the next safe body-side task types first, in no-motion or
   simulator-backed form, before Chromie broadens routing or any motion-control
   model training begins. Near-term task types are `navigate_to_location`,
   `approach_target`, `look_at_target`, `perform_gesture`, and
   `recover_safe_idle`, with preview, submit, event, cancellation, refusal, and
   safe-idle semantics.
3. **Reference robot candidate gate.** The versioned, machine-readable
   candidate manifest pins hardware and software identity, defines one bounded
   low-risk skill, records exclusions, and fails closed on missing safety or
   calibration evidence.

The task-agent boundary exists to keep the project on target: Chromie remains
the local-first voice and decision control plane, while Soridormi remains the
embodied planner/executor. Rich embodied requests should be represented as
structured Soridormi goals, not translated by Chromie into raw or low-level
body controls.

Model-assisted routing supports this boundary but does not own it. The small
Router model may propose routes for normal requests, but deterministic controls,
catalog constraints, schema validation, runtime authorization, and Soridormi
provider checks remain the authority.

### Sequence

1. keep the Chromie/Soridormi task contract aligned with Soridormi's
   authoritative manifest;
2. enrich Soridormi's high-level task and skill surface in no-motion or
   simulator-backed mode before training motion-control models or adding real
   physical execution;
3. validate task-capability inspection, preview, submit, event monitoring,
   refusal, blocked-subsystem reporting, timeout, and cancellation semantics
   without claiming motion, including a no-motion bridge acceptance gate that
   checks capabilities before preview or submit;
4. add Chromie routing and TaskGraph tests for the enriched Soridormi task
   types while preserving explicit named-skill routing for simple bounded
   commands;
5. no-motion health and state inspection for the selected candidate;
6. shadow recommendations;
7. dry-run with operator approval;
8. one low-risk skill at limited speed and workspace;
9. supervised cancellation, stop, emergency stop, and recovery;
10. bounded multi-skill TaskGraphs;
11. narrowly scoped physical prerelease.

### Exit criteria

- exact hardware, firmware, sensors, drivers, and Soridormi revision are pinned;
- Chromie can submit structured Soridormi task goals with stable idempotency
  keys, monitor terminal task events, and fail closed on Soridormi refusal,
  failure, timeout, cancellation, blocked subsystems, or unsafe
  recommendations;
- model-assisted routing remains advisory and cannot bypass deterministic
  controls, capability availability, confirmation, runtime policy, provider
  refusal, or physical-motion gates;
- the enriched Soridormi task surface has retained no-motion or simulator
  evidence before Chromie treats it as routable for rich embodied requests;
- the candidate verifier reports `selected_for_pilot=true` while continuing to
  report `physical_motion_authorized=false`;
- referenced safety, procedure, provider-manifest, and calibration evidence
  files stay inside the evidence root, the provider manifest revision matches
  the candidate, and calibration hashes match;
- calibration and latency measurements are retained;
- physical stop and recovery evidence is reviewed;
- communication loss and stale-command cases fail closed;
- the release names one supported configuration and all exclusions.

Motion-control model training is explicitly later work. It requires a selected
target body or simulator, retained calibration and telemetry, task-level
acceptance metrics, and Soridormi-owned safety envelopes.

## Later work

Perception providers, privacy-controlled durable memory, longer recovery-aware
tasks, distributed observability, verified Jetson packaging, additional robot
platforms, and broader autonomy are candidates only after the physical pilot.

## Anti-drift checks

Before accepting major work, ask:

1. Does it close the active milestone or a documented release blocker?
2. Is the behavior owned by Chromie or Soridormi according to the charter?
3. Does it preserve deterministic controls and fail-closed authorization?
4. Is the required evidence level explicit?
5. Does it avoid binding the model-facing contract to one robot?

If the answer is no, defer the work or revise its scope.

## Implemented architecture track - Goal-driven cognitive runtime

### Objective

Maintain [Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
as the cognitive constitution for current and future Router, Agent, planning,
continuity, response, and social-interaction work.

The architecture changes the primary planning question from “which skill matches
this utterance?” to “what existing or new user goals are present, and what
verifiable plan completely satisfies them?”

This track is implemented through PR8 with dependency-light automated evidence.
The unified runtime is authoritative in lane-gated `apply`: the common safe
base owns `chat`, and the maintained Soridormi launcher widens ownership to
`chat,robot_action`. Both fail closed after ownership acquisition and preserve
explicit rollback controls. Retained live-text and MuJoCo target evidence
remain open.

### Delivery sequence

1. **Implemented (Level A):** Goal contracts and bounded active-goal projection.
2. **Implemented in the unified apply pipeline (Level A):** Goal association before new-goal segmentation.
3. **Implemented in the unified apply pipeline (Level A):** Canonical plans and complete-coverage Fast Planner.
4. **Implemented in the unified apply pipeline (Level A):** Full-registry Deep Planner with bounded same-tier replanning.
5. **Implemented in the unified apply pipeline (Level A):** Consequence-aware parameter resolution and goal satisfaction reporting.
6. **Implemented in the unified apply pipeline (Level A):** Multi-goal response composition and model-driven social attention.
7. **Implemented with Level A evidence; target evidence open:** Unified runtime
   migration, per-lane apply/rollback, atomic Goal-state commit, bounded host
   replan, evidence tooling, and cognitive text-to-MuJoCo entry point.
8. **Implemented with Level A evidence; target evidence open:** Single semantic
   authority, adapter-only exact Router actions, emergency-only legacy planner
   with non-empty matching-turn claims, exact Goal Association schema, and strict
   source/evidence provenance checks.
9. **Implemented with Level A evidence; live qualification open:** Fast Planner
   multi-goal terminal contract with decoder-compatible empty escalation versus
   complete outcome-map semantics, simple common-catalog mixed planning,
   explicit recovery diagnostics, pending-action claim discipline, and retained
   latency qualification. See
   [Fast Planner Multi-Goal Contract Path](docs/FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md).

10. **Implemented with Level A evidence; target evidence open:** User-outcome
    acceptance with stable observable behavior events and hard LLM integrity
    gates, plus a model-authored Social Attention behavior domain that can
    coordinate contextual language and auxiliary body expression. See
    [User-Outcome Acceptance Framework](docs/USER_OUTCOME_ACCEPTANCE.md) and
    [Social Attention Behavior Domain](docs/SOCIAL_ATTENTION_BEHAVIOR_DOMAIN.md).

The Deep Planner does not return semantic work to the Fast Planner. Both tiers
share capability and validation primitives and output the same canonical plan
contract.

### Required development method

Each behavioral implementation must follow
[Scenario-Driven Development](docs/SCENARIO_DRIVEN_DEVELOPMENT.md): retain the
interaction or requirement as a scenario, demonstrate the failing boundary,
implement the architectural correction, pass the retained scenario and full
regression gates, and state the evidence level.

### Exit criteria

- goal association occurs before creation of new goals;
- one turn can modify existing goals and create independent new goals;
- Fast Planner executes only complete high-confidence coverage or escalates;
- simple common-catalog multi-goal execute, respond, and mixed requests terminate
  at Fast Planner from a complete model-authored semantic plan, while the host
  adds only canonical identity and validation; semantic escalation remains valid
  and distinct from contract failure;
- Deep Planner produces a final canonical plan without returning to Fast Planner;
- partial or unconfirmed alternatives never execute;
- information gaps remain attached to the original goal across turns;
- explicit user tasks remain authoritative while response language and auxiliary Social Attention expression are coherently coordinated;
- all execution passes the same deterministic validator;
- retained Level A scenario coverage and user-outcome observation checks pass;
- critical LLM timeout or truncation cannot be hidden by fallback;
- live-text and MuJoCo evidence are retained before target behavior is claimed.

This track does not replace the current physical pilot or audio evidence tracks.
It must preserve existing deterministic stop, authorization, provider, evidence,
and release boundaries.

## Planned architecture track - Runtime observability

### Objective

Establish [Runtime Observability Architecture](docs/RUNTIME_OBSERVABILITY_ARCHITECTURE.md)
as the common contract for architecture-independent execution timing, incident
scene reconstruction, and data-loop evidence correlation.

Runtime Trace must describe the modules that actually participated in an
interaction rather than encoding a fixed Router/Planner/Execution pipeline.
Each module declares stable metadata and emits generic trace items through a
shared framework. Completed traces retain raw timing evidence and reproducible
summaries for critical-path, inclusive/exclusive-time, parallelism, and
user-observable latency analysis.

### Delivery sequence

1. **Implemented:** Common Runtime Trace envelope, module descriptor, item
   lifecycle, timing, hierarchy, links, modes, privacy, and summary contracts.
2. **Implemented with focused automated evidence:** Shared tracing library with
   monotonic timing, wall-clock correlation, `contextvars` propagation,
   sync/async spans, bounded attributes, distributed carriers/fragments, and
   immutable finalization.
3. **Implemented with partial coverage:** Goal-driven coordinator, canonical
   plan adapter, Orchestrator-to-Agent cognitive calls, Goal Association, Fast
   and Deep Planning, Response Composer, and Ollama model calls emit generic
   module-owned trace items without changing semantic behavior.
4. **Implemented with focused automated evidence:** Execution, action-provider,
   VAD/ASR, TTS/playback, queue/resource, session lifecycle, first audible, and
   optional provider-reported first-motion instrumentation.
5. **Implemented for the initial cognitive path:** Topology-aware summaries,
   inclusive/exclusive module time, parallelism, optional interaction-trace
   Runtime Events, and active trace attachment to cognitive-integrity incidents.
   Critical-path output is an explicitly versioned interval/topology
   approximation until broader dependency instrumentation exists.
6. **Implemented:** Deterministic normal-path
   sampling, latency-threshold escalation, detached session summaries, idle and
   process-restart abandonment recovery, cross-artifact correlation, and
   non-blocking accelerator resource observations.
7. **Implemented; environment evidence open:** Reproducible retained-trace
   latency distributions and explicit baseline-versus-candidate regression
   gates with evidence-class, environment, revision-cleanliness, and sample-count
   qualification. Real simulator/hardware baselines and approved thresholds must
   still be collected on the claimed target.

Exit criteria require the trace schema to remain independent of the current
module graph, disabled tracing to preserve behavior with negligible overhead,
critical failures to retain correlated timing evidence, and data-loop status to
remain truthful about local capture versus cloud delivery.

### Goal-driven runtime checkpoint

PR1 through PR6 define and automatically verify Goal contracts, continuity-before-creation association, Canonical Plans, complete-coverage Fast Planning, terminal Deep Planning, bounded same-tier revision, parameter resolution, Goal Satisfaction, response composition, and independent Social Attention.

PR7 unifies those stages under one host runtime with `off`, `report_only`, and
lane-gated `apply`. PR8 makes the unified runtime the single semantic authority
for applied lanes, constrains Goal Association at the model boundary, and
reduces the old CapabilityAgent planner to a gated emergency path requiring a
non-empty matching-turn claim. All applied plans still pass existing trusted
preparation, confirmation, Skill Runtime, and provider boundaries. Goal-state
updates are atomic, and technical failures after authority acquisition fail
closed rather than becoming hidden success or a second semantic plan.
Operational details and evidence commands are maintained in
[Goal-Driven Cognitive Runtime Rollout](docs/COGNITIVE_RUNTIME_ROLLOUT.md).

This checkpoint is implemented and automatically verified only. Retained live-text and MuJoCo evidence must still be collected before target validation is claimed.
