# Current Implementation Status

**Status authority:** this file describes what is present in the repository snapshot.
**Current committed base revision:** `53bd882`; retained target evidence below
records the exact revision that produced each bundle
**Status refresh date:** 2026-06-27
**Current focus:** **Simulation-demo release audit across the
Chromie/Soridormi boundary; physical pilot preparation and physical audio
validation remain separate release-support tracks**
**Version candidate:** `0.1.0-alpha.1` (prepared, not published)
**Soridormi capability snapshot:** generated from the paired Soridormi checkout; see `capabilities/soridormi.json` metadata for provenance

`ROADMAP.md` describes milestone intent. This file is the source of truth for
current implementation, automated evidence, target evidence, and release
readiness.

The temporary `demo-sim-2026-06-27` tag was withdrawn during the paired
Chromie/Soridormi documentation and evidence audit. Recreate any demo tag only
from a revision whose docs, automated checks, and retained simulator evidence
match the release claim.

The stable project goal and ownership boundaries are defined in
[Project Charter](PROJECT_CHARTER.md).

The provider-readiness milestone is complete. A live local Soridormi MCP
endpoint passed the `sim`, recommendation-only `hardware_shadow`, and no-motion
`hardware_dry_run` conformance profiles, profile parity, and all 16 injected
fault scenarios. This is no-motion provider-contract evidence from macOS ARM64;
it is not Linux/GPU MuJoCo, audio-device, or physical-robot evidence.

The current top-level development layer is the Chromie/Soridormi task-agent
boundary. Chromie now consumes a richer Soridormi task API snapshot with
`soridormi.task.get_capabilities`, `preview`, `submit`, `status`, `events`, and
`cancel`. Chromie's global TaskGraph can submit a structured embodied goal with
a stable `client_task_ref`, monitor Soridormi task events to terminal state,
and treat refused, failed, cancelled, or timed-out task states as failed graph
nodes with deterministic `reason_code`, `blocked_subsystems`, and
`recommended_next_actions` reporting plus a trace-level `outcome_summary` for
future report/speech nodes. Planning execution can also run `chromie.report`
as a trace-only local fallback while leaving audible `chromie.speak` in the
host Skill Runtime path; LLM-planned Soridormi task-submit nodes get that
fallback automatically when no explicit failure fallback is present. Native
`/interaction` graph requests are now wired through the host Skill Runtime as
`chromie.task_graph.execute` and can dispatch to the Agent planning executor
when its feature gate is enabled; failed graph traces suppress completion
speech. A no-motion task-agent bridge acceptance mode now probes Soridormi,
requires `task_api_no_motion=true` before preview or submit, submits with a
Chromie-owned `client_task_ref`, and monitors terminal task events. A local
Soridormi dry-run MCP endpoint passed this bridge acceptance on June 20, 2026
with graph `soridormi-task-agent-acceptance-115cc864fd04`, backend
`local_tool_dry_run`, `no_motion=true`, `safe_idle=true`, and explicit
`capabilities`, `preview`, `submit`, and `events` nodes. This
prepares richer user-facing goals such as navigation, approach, and
object-delivery requests without lowering them into velocity recipes. The task
surface remains a no-motion contract unless later Soridormi evidence proves
execution.

Soridormi's no-motion task and skill surface is now declared in the
authoritative capability snapshot. The current non-hardware implementation
section is Chromie routing into those declared task types: bounded locomotion,
attention, gesture, sequence, stop, safe-idle, and planning-hold tasks may be
represented as structured goals, while navigation, approach, and delivery must
remain structured refusals until Soridormi proves the required simulator
pipelines. Training or tuning motion-control models waits until a selected
target body or simulator, calibration artifacts, telemetry, safety envelopes,
and task-level acceptance metrics exist.

The current small Router model is not a single source of truth for routing or
safety. `qwen3:0.6b` may propose routes for normal requests, but deterministic
operational controls, capability-catalog constraints, low-confidence
deepthought delegation, schema validation, host Skill Runtime authorization,
and Soridormi provider checks remain authoritative. Deterministic semantic
action parsing is now a rules-only or explicit compatibility fallback rather
than the normal hybrid brain path. Router decisions now retain staged
task/action proposals in `metadata.route_stage_outputs` and a merged
`metadata.task_list`, while execution still requires Agent and provider
validation. See
[Model-Assisted Routing Guardrails](MODEL_ASSISTED_ROUTING_GUARDRAILS.md).

Chromie now has a structured mind context layer for owner-approved identity,
core principles, long-term goals, reflex policy, deliberation policy, and
experience tuning boundaries. The default identity names the robot Chromie,
marks her as a female AI robot with she/her pronouns, and describes her as
6 years old in her robot identity. It also defines her as a companion robot who
can keep people company and do simple helpful things, while explicitly treating
backend LLM/model-provider identity as implementation detail rather than
self-identity. The Orchestrator attaches a bounded `mind` snapshot to Router and
Agent context so conversation and deepthinking prompts can answer identity
questions from that owner-approved profile. An append-only
experience journal records
interaction outcomes, and failed or uncertain outcomes can create
human-review-only update proposals. Experience is not allowed to auto-apply core
principle or physical safety changes. See
[`chromie_mind.md`](chromie_mind.md).

On June 14, 2026, the Linux x86_64 reference host with an NVIDIA GeForce RTX
5090 retained:

- GPU smoke `20260614T130944Z`: 21 passed, 0 failed, including ASR/TTS GPU
  visibility, non-empty TTS PCM, and `gemma4:26b` loaded 100% on GPU;
- synthetic M13 `20260614T132934Z`: all seven cases passed at Chromie revision
  `f0e22ba`;
- virtual-microphone M13 `20260614T133155Z`: all seven cases passed through
  PipeWire at the same revision.

Both M13 bundles pass `verify_voice_evidence.py --allow-automated --require-clean`
with no errors or warnings. They are retained automated target-host evidence,
not release-closing physical microphone/speaker evidence.

On June 17, 2026, the same development line retained:

- synthetic M13 `20260617T075825Z`: all seven cases passed at Chromie revision
  `4604a03`, including the live Soridormi catalog and host confirmation path;
- text-to-MuJoCo `20260617T081411Z`: the text request “walk ahead at 0.2 speed
  for 10 seconds and then nod your head twice, then turn left” routed to ordered
  `soridormi.walk_velocity`, `soridormi.nod_yes`, and
  `soridormi.turn_in_place`; all three completed in MuJoCo `sim` mode and the
  status check ended standing, with no active task and no emergency stop.

That text-to-MuJoCo evidence closes the historical M13 text interaction scope.
It intentionally skips microphone and ASR. Physical microphone/speaker
validation remains open only for future voice-device release claims.

## Status vocabulary

Chromie tracks four independent states. Do not collapse them into one word such
as “done.”

| State | Meaning |
|---|---|
| Implemented | The code path exists in this repository. |
| Automatically verified | A repeatable test covers the behavior without requiring the target GPU, microphone, or robot. |
| Target validated | The behavior has retained evidence from the intended GPU, audio device, simulator, or hardware environment. |
| Release ready | The behavior is supported, documented, packaged, and included in a published release scope. |

A feature can be implemented and automatically verified while still lacking
Target validation or Release readiness.

## Current capability matrix

| Capability | Implementation | Automated evidence | Target or live evidence | Default deployment state |
|---|---|---|---|---|
| Five Docker services plus host Orchestrator | Implemented | Compose and control-plane tests | RTX 5090 GPU smoke passed 21/21; all services healthy | Main runtime |
| Realtime microphone/VAD/ASR/TTS/playback loop | Implemented; ASR inference runs off the WebSocket event loop; TTS playback stays ordered while complete speech can be chunked across bounded restartable service workers | Component concurrency/cancellation, TTS worker-pool, TTS alignment, plus automatic TTS-generated stdin and virtual-microphone acceptance modes | Synthetic and PipeWire virtual-mic matrices passed 7/7; physical microphone/speaker validation remains open for voice-device release claims | Enabled after host audio setup |
| Deterministic Router operational controls plus quick LLM route classifier | Implemented; interrupt/ignore controls remain deterministic while normal requests use catalog search, the small Router model, validators, or fallback behavior | Router rule, capability-routing, LLM-prompt, and regression tests | Exercised by deployed smoke test | Enabled by `.env.common` |
| Multi-agent `POST /run` compatibility path | Implemented | Contract and integration tests | Used by the current voice loop | Enabled by `.env.common` |
| Structured `POST /interaction` API | Native `InteractionRuntime` is the default; compatibility adapter remains selectable | Native output, strict validation, fallback, and end-to-end named-skill tests | Text-to-live-MuJoCo evidence `20260617T081411Z` passed with ordered walk, nod, turn execution and safe idle | Host rollout flag off |
| Native structured Interaction Agent | Implemented with direct `InteractionSpeech`/`SkillRequest` accumulation, simulator-bounded expressive body cues, and safe defaults for underspecified walking requests | Native route, TaskGraph, validation, fail-closed, fallback, expressive chat attention/nod cues, and compatibility-mode tests | Text-input MuJoCo closure evidence retained; physical microphone retention remains separate | Agent default |
| Trusted host Skill Runtime | Implemented | Scheduling, confirmation, timeout, cancellation, and isolation tests | Text-to-live-MuJoCo closure evidence passed | Used only by structured path |
| Spoken request-bound confirmation | Implemented with host-owned prompt, exact request fingerprint, expiry, single-use approval, and denial | Approval, denial, ambiguity, replay, mutation, expiry, and authorization tests | Clean synthetic and virtual-mic approval/denial evidence passed; text-to-MuJoCo uses the same trusted runtime authorization boundary | Structured path; simulator exemption configurable |
| Local speech skill provider | Implemented | Skill Runtime tests | Exercised by text acceptance; physical speaker validation remains separate | Available in structured path |
| Soridormi named-skill provider | Implemented | Provider and interaction-coordinator tests | Live MCP/MuJoCo planning, execution, and cancellation paths exist | Provider flag off |
| Provider failure normalization | Strict catalog/availability/plan/monitor/completion validation, stable timeout/cancellation terminal states, deterministic language-matched speech fallback, and a versioned 16-scenario replayable fault matrix with configurable latency thresholds, status snapshots, and safe-idle enforcement | Matrix, threshold and safe-idle evaluation, provider restart, unavailable skill, deterministic jitter, dropped monitor status, malformed completion, mismatched identity, disconnect-during-cancel, timeout, fallback, and completion-suppression tests | Live Soridormi-owned injection passed 16/16 scenarios; all ended safe-idle with no threshold violations | Used by Soridormi named skills |
| Provider conformance | Shared versioned checks and replayable high-level traces for simulator, recommendation-only hardware shadow, and no-motion hardware dry-run profiles, plus manifest preflight and strict retained-evidence verification | Local three-profile parity, trace-drift detection, opaque-identity normalization, profile-specific no-motion proofs, unsafe-output rejection, manifest preflight, and complete/unsafe bundle tests | Live no-motion `sim`, `hardware_shadow`, and `hardware_dry_run` profiles passed with parity; real hardware mode remains refused | Test tooling; real hardware mode refused |
| Conversation state across VAD utterances | Implemented in host memory with optional local recoverable task-context store | Boundary, follow-up, task-context, restart-restore, and limit tests | Available in the host Orchestrator | Conversation state enabled by `.env.common`; task-context store opt-in |
| High-level Chromie ability self-model | Implemented as a host ability registry above concrete skills plus owner-approved mind identity for self-description questions, with stable cognition, speech, memory, social, body, task, safety, and state ability IDs; deep-thinking acknowledgement and simulator-only thinking pose now resolve through this registry | Ability-registry, mind-profile, conversation-identity, and Orchestrator TTS-alignment tests | No broad target-validation claim; only existing text/simulator interaction paths exercise fulfilled abilities | Registry enabled in host Orchestrator; most social/body abilities remain honest stubs |
| Structured acceptance evidence capture | Readiness preflight plus JSONL events, generated/captured audio, redacted runtime snapshot, case checks, and three explicit voice modes implemented; text-MuJoCo evidence writes route, interaction, execution, status, events, and summary artifacts | Preflight, synthetic/virtual-mic framing, isolation, text-MuJoCo, and bundle-verification tests | Clean synthetic, virtual-mic, and text-MuJoCo evidence retained; physical supervised mode remains optional release-support evidence for real audio claims | Acceptance-only |
| Developer usability CLI | `python -m tools.chromie_cli` implements `status`, `config show`, `config validate`, `doctor`, `capability check`, `trace view`, and `evidence bundle` with plain/JSON output; `trace explain` remains future work | CLI command, output, validation, doctor, manifest-safety, retained-trace, and evidence-preflight unit tests plus full Level A gate | Local doctor can report service reachability, trace view can summarize retained local artifacts, and evidence preflight can label retained bundle pointers, but none create target evidence or release readiness | Tooling |
| Capability registry and deployment probe | Implemented | Registry, manifest, pagination, and schema tests | Checked-in Soridormi manifest is pinned to an upstream commit | Manifest loading opt-in |
| LLM TaskGraph planning | Implemented | Planner validation and fallback tests | No automatic dispatch by design | Flag off |
| Read-only TaskGraph execution | Implemented | Preflight, references, parallelism, retry, timeout, fallback, and cancellation tests | Live MCP acceptance can exercise it | Flag off |
| Stateful planning-only TaskGraph execution | Implemented; `soridormi.task.submit` nodes get stable `client_task_ref` values, are monitored through `soridormi.task.events`, preserve refused/blocked metadata, populate deterministic trace outcome summaries, can activate trace-only `chromie.report` fallbacks before graph success is reported, and can be invoked from native `chromie.task_graph.execute` Skill Runtime requests | Planning policy, concurrency, task-submit monitoring, idempotency-key, terminal-event, refusal, timeout, blocked-subsystem reporting, outcome-summary, trace-only report, error/status refs, rich-goal routing, host Skill Runtime dispatch, and completion-speech suppression tests | Safe Soridormi plan creation acceptance exists; task API dry-run bridge acceptance passed locally; physical task execution evidence remains future work | Flag off |
| Soridormi task-agent bridge | Implemented for contract/no-motion task goals, including capability inspection, preview/submit/status/events/cancel schemas, event-cursor monitoring, deterministic refusal/blocked-subsystem reporting and trace summaries, trace-only report fallbacks, safety-control authorization for task cancellation, routing from rich embodied requests to task planning, and a fail-closed no-motion bridge acceptance mode | Manifest materialization, capability registry, task client, planning TaskGraph, dry-run task contract tests, and no-motion bridge acceptance tests | Local Soridormi dry-run MCP bridge acceptance passed against the paired Soridormi task API snapshot with `local_tool_dry_run`, explicit task events, `no_motion=true`, and `safe_idle=true`; no physical task execution claim | Planning/tooling only; physical motion gates off |
| Guarded side-effect execution | Implemented; diagnostics are bearer-protected and trace/grant retention is bounded | Authorization, one-time grant, retention, confirmation, monitor, fallback, and cancellation tests | Soridormi dry-run and runtime-cancellation tooling exists | Flag off; bearer token required |
| Physical TaskGraph execution | Policy path implemented | Safety and sequential-execution tests | Supervised hardware acceptance remains open | Separate flag off |
| Reference robot candidate gate | Versioned schema, intentionally incomplete template, fail-closed semantic verifier, and optional self-contained evidence-package verification implemented | Identity, revision, timestamp, emergency-stop, calibration, referenced evidence file, evidence-root containment, provider-manifest revision match, calibration hash, exclusion, low-level-field, and no-motion authorization tests | No real candidate has been recorded or selected | Preparation only; cannot authorize motion |
| Shared bounded scheduling and resource arbitration | Implemented | Agent and Orchestrator concurrency tests | MuJoCo interaction path exercises the policy | Parallel flags off |
| Hardware profile detection and generated `.env.runtime` | Implemented | Profile-detection tests | RTX 5090 profile and CUDA arch 120 validated; Jetson packaging evidence is incomplete | Automatic |
| Host hardware daemon | Legacy mock compatibility implementation | Hardware/control-plane tests | No production hardware claim | Optional; mock driver only |
| Alpha release packaging | Candidate version, notes, compatibility file, archive/checksum generator, and strict release gate implemented | Packaging/evidence unit tests and full suite | M13 text scope is closed; publishable voice-device scope still requires its declared physical audio evidence or a narrowed compatibility claim | Candidate only |

## Verified automated evidence

The repository test command is:

```bash
./scripts/run_tests.sh
```

For focused Level A development checks, `python scripts/test_matrix.py --list`
shows roadmap-aligned module groups and declared combinations. These checks are
convenience slices over the existing automated tests and do not replace the
canonical full-suite gate above.

At the current working revision the Level A suite is expected to run:

- **453** current `unittest` cases under `tests/`;
- **20** dependency-light legacy Agent test functions under `agent/tests/`;
- documentation consistency checks after this documentation refresh.

The file-backed behavior scenario runner is implemented for Router and
InteractionRuntime module checks. It loads one deterministic JSON scenario per
file from `scenarios/`, evaluates route, speech, skill, confirmation, task, and
forbidden-output expectations, writes timestamped comparison reports under
`.chromie/reports/behavior-scenarios/`, and can compare against a previous
`summary.json` to list regressions and improvements. This is Level A automated
evidence only and does not create a target, simulator, microphone, speaker, or
release-readiness claim. Scenario authoring templates and
`scripts/scenario_author.py` can create draft files, validate the scenario
library, and print constrained prompts for LLM-assisted candidate generation;
committed scenarios remain deterministic files reviewed by a human.

The developer-usability CLI through PR6 passed focused CLI tests, documentation
checks, and the full Level A gate. It currently exposes
`python -m tools.chromie_cli status`, `config show`, `config validate`, and
`doctor`, `capability check`, `trace view`, and `evidence bundle`. `doctor`
performs local reachability checks only, `trace view` summarizes retained local
artifacts according to `docs/TRACE_SCHEMA.md`, and `evidence bundle` labels
retained evidence pointers without creating target evidence or release
readiness.

The current task-agent routing, refusal-reporting, host graph-dispatch,
no-motion bridge-acceptance, and reference-candidate verifier refresh after
committed base `f4bbb2f` passed `python scripts/check_docs.py`,
`python scripts/test_matrix.py taskgraph soridormi`, local dry-run
`--task-agent-bridge` acceptance against Soridormi MCP on `127.0.0.1:8011`,
focused
interaction/catalog task-agent tests, focused host Skill Runtime graph dispatch
tests, focused Soridormi acceptance tests, focused robot-candidate verifier
tests, and dependency-complete Orchestrator AgentClient coverage. The latest
local `INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh` attempt on 2026-06-28
installed the declared host test dependencies, passed
`python scripts/check_docs.py`, ran 453 current `unittest` cases with `OK`, and
then passed 20 dependency-light legacy Agent test functions.

The tests alone do not prove GPU performance, microphone quality, speaker
quality, or real robot safety. The retained RTX evidence above separately
validates the target GPU and automated host audio paths.

`scripts/interaction_text_mujoco_check.py` is available for text-input,
speaker-output, live-MuJoCo checks that skip microphone and ASR. The retained
`20260617T081411Z` bundle is the historical M13 text interaction closure
evidence. It does not prove physical microphone recognition or speaker quality.

`scripts/interaction_text_skill_sweep.py` is available for text-input
preview sweeps across maintained Soridormi skill prompts. It reports live
available skills without text cases and executes motion only when explicitly
run with `--execute` against a supervised simulator endpoint.

## Open release-support gates

M13 text interaction is closed. A release that continues to claim physical
voice-device support is not publishable until all of the following are complete:

1. Run `scripts/voice_acceptance.py --mode supervised` on the reference
   host for all seven cases and ensure
   `scripts/verify_voice_evidence.py --require-clean` passes.
2. The retained bundle is reviewed for audible quality, simulator safe idle,
   cancellation/recovery behavior, correlated IDs, and absence of secrets.
3. The candidate compatibility file has no remaining release blockers and
   a clean release bundle is generated from the accepted revision.

## Open target-evidence tracks

These legacy evidence tracks do not define the current delivery:

- **Target GPU:** complete on the RTX 5090 reference host with a retained 21/21
  smoke pass; repeat on any hardware claimed by a release.
- **Combined target runner:** run
  `scripts/run_supervised_target_acceptance.sh` with a supervised, runtime-backed Soridormi
  endpoint and complete the documented recovery step.
- **Audio:** automatic synthetic and virtual-microphone modes passed; real
  microphone/speaker device information, timing logs, and pass/fail notes are
  still needed only for a physical voice-device release claim.
- **Hardware:** real motion remains experimental until Soridormi commissioning,
  confirmation, monitor, cancellation, stop, and recovery evidence are all
  retained for the exact hardware configuration.

## Known limitations

- The default structured interaction feature flags are off.
- Native interaction output is the Agent default, but the host structured
  rollout remains default-off until alpha acceptance evidence is retained.
- `AGENT_NATIVE_INTERACTION_FALLBACK` is default-off so malformed native output
  fails closed unless an operator explicitly enables adapter fallback.
- The checked-in Soridormi manifest is a pinned contract snapshot; the live
  endpoint must be probed before execution is enabled.
- Provider-readiness preflight passes for the pinned Soridormi snapshot.
  Physical motion still requires an exact robot selection and supervised
  commissioning evidence.
- The Soridormi task API is currently a contract/no-motion surface. Chromie may
  submit and monitor structured embodied goals, but must not report physical
  completion unless Soridormi later returns retained execution evidence from a
  validated simulator or commissioned robot path.
- Motion-control model training is deferred until Soridormi has stable
  high-level task semantics, retained simulator or robot telemetry, calibration
  evidence, and safety envelopes for the selected target body.
- Jetson profiles select model/runtime values, but this repository does not yet
  include verified Jetson-specific Dockerfiles or Compose overrides.
- The host hardware daemon currently constructs `MockRobotDriver` regardless of
  serial-related modules or environment variables. It is not a production
  hardware backend.
- TaskGraph and Skill Runtime schedulers are process-local. Cross-process robot
  exclusivity remains Soridormi’s responsibility.
- Candidate release notes, compatibility metadata, archive generation, and
  checksums exist, but there is no published GitHub release or support promise
  in this snapshot.

## Release classification

Treat this revision as a **completed M13 text-to-MuJoCo candidate, a
simulation-demo candidate, and a prepared voice alpha candidate**, not as a
published or production release. The release generator refuses a publishable
voice-device bundle while tracked release blockers remain. See
[Release and Packaging](RELEASE.md).
