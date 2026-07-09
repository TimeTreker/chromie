# Current Implementation Status

**Status authority:** this file describes what is present in the repository snapshot.
**Current release-prep base:** `0.0.1` scope with Soridormi MuJoCo `sim`
execution; retained target evidence below records the exact revision that
produced each bundle
**Status refresh date:** 2026-07-09
**Current focus:** **Freeze the `0.0.1` release across the Chromie/Soridormi
boundary, with Soridormi executing robot work through MuJoCo `sim`; physical
pilot preparation and human voice-device validation remain separate
release-support tracks**
**Version:** `0.0.1` (MuJoCo-executor scope, not yet published)
**Soridormi capability snapshot:** generated from the paired Soridormi checkout; see `capabilities/soridormi.json` metadata for provenance

`ROADMAP.md` describes milestone intent. This file is the source of truth for
current implementation, automated evidence, target evidence, and release
readiness.

The temporary `demo-sim-2026-06-27` tag was withdrawn during the paired
Chromie/Soridormi documentation and evidence audit. Do not recreate that demo
tag; the next release tag is `0.0.1`, and it must come only from a revision
whose docs, automated checks, and retained Soridormi MuJoCo evidence match the
release claim.

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

The current fast Router model is not a single source of truth for routing or
safety. `qwen3:4b` may propose routes for normal requests, but deterministic
operational controls, capability-catalog constraints, low-confidence
deepthought delegation, schema validation, host Skill Runtime authorization,
and Soridormi provider checks remain authoritative. The July 9, 2026 live-text
general-ability failures exposed the earliest wrong boundary in the Router:
the old `qwen3:0.6b` profile could time out on cold model load and misclassify
ordinary catalog-backed body requests even when warm. The fix is architectural:
use the locally available `qwen3:4b` fast-router profile, keep it resident with
`ROUTER_LLM_KEEP_ALIVE`, warm it during Router startup, select primary/review
timeouts by stage rather than model name, bound quick-router output to compact
classification JSON with `ROUTER_LLM_NUM_PREDICT=96`, and convert
schema-invalid or narrowed quick compound `actions[]` into CapabilityAgent
planner handoff instead of executing or narrowing them. Isolated low-information
ASR fragments clarify even if the fast model calls them chat. Weather/tool
queries with semantic weather evidence are normalized back to the tool lane when
the weather lookup affordance is present, even if a stale route item says chat.
This is not evidence of microphone, speaker, simulator execution, or physical
robot behavior until the corresponding live acceptance run is retained.
Deterministic semantic action parsing is now a rules-only or explicit
compatibility fallback rather than the normal hybrid brain path. The
fast Qwen-class Router now receives unlocked
`common_ability_catalog`/`common_ability_ids` as its commonly used ability menu;
per-query catalog matches are not used by the fast Router decision surface, and
rare/full-catalog or `prompt_tier_locked` selections delegate to `deep_thought`
instead of entering the immediate fast action surface. Catalog prompt tiers now
carry `prompt_tier_source` and
`prompt_tier_reason`; the initial preset lives in
`capabilities/prompt_tiers.json`, and an optional experience-derived overlay can
move ordinary unlocked skills between common and rare, while safety-sensitive
locked entries are forced to the full-catalog/deepthinking path. Router
decisions now retain staged
multi-route items in `routes` and `metadata.route_items`, staged task/action
proposals in `metadata.route_stage_outputs`, optional non-executable
`metadata.desired_abilities` for understood but unavailable human-like
abilities, and a merged shared-schema `metadata.task_proposals` list plus
legacy `metadata.task_list` and a `metadata.route_merge` ledger, while
execution still requires Agent and provider validation. The top-level `route`
remains a compatibility primary route; independent route items can split one
utterance into immediate speech, memory, deepthought, tool, and Skill Runtime
lanes with separate `context_profile` values. Safe short chat route items may
feed the host fast-first TTS lane when `direct_to_tts=true`; that local speech
cannot claim memory writes, tool results, physical completion, or execution
authority. Optional post-interrupt review can attach a corrected follow-up
route after deterministic cancellation has already happened, but it does not
authorize automatic physical resume. See
[Model-Assisted Routing Guardrails](MODEL_ASSISTED_ROUTING_GUARDRAILS.md).
The structured host interaction path now copies Router stage proposals into an
internal Orchestrator task-proposal ledger before execution. The ledger marks
effectful Router tasks as `not_committed` unless the final
`InteractionResponse` contains a matching committed skill, and records committed
speech/skills, static preflight status, and rejected deepthinking tasks for
later diagnostics. Later-stage merge corrections can attach
`revised_task_proposals`, which records the replacement proposal and an
automatic `superseded` marker for the earlier proposal without authorizing
execution by itself. The host preflight audit checks only what can be known
before execution, such as skill registry presence, provider registration,
schema validity, availability, confirmation, and safety-monitor requirements;
real world feasibility remains a Skill Runtime and Soridormi evidence question.
The ledger is now validated through the shared `TaskProposalLedger` contract.
Router emits shared `task_proposals`, and the Agent deepthinking path emits
shared `deepthinking_task_proposals` for proposed speech/skills,
missing-ability proposals, and rejected candidate tasks. Final Agent speech and skills now emit shared
`agent_task_proposals`, with speech represented as the local `chromie.speak`
skill.
Experience records now retain proposal/preflight summaries and can create
owner-review-only tuning proposals when a mismatch is detected. This is
implemented and automatically verified; it does not execute proposed tasks,
auto-apply learned rules, or change physical authorization policy. See
[Orchestrator Task Proposal Merge](ORCHESTRATOR_TASK_PROPOSAL_MERGE.md).
The episode evaluator also supports offline good/bad/needs-review case
journaling: `scripts/evaluate_experience_episodes.py` can write
`offline_reviews.jsonl`, owner-review-only proposal output, and scenario
candidates from the same episode evidence. This path is outside realtime audio,
can use optional deepthinking scoring, and keeps raw episode logs out of normal
prompt memory.

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

On July 4, 2026, the same development line retained automated acoustic voice
evidence `20260704T114654Z` at Chromie revision `842a334`: all seven generated
TTS prompt cases passed through host output, configured host input capture,
VAD, ASR, Router, Agent, trusted Skill Runtime, TTS scheduling, and Soridormi
`sim` behavior. This bundle passes `verify_voice_evidence.py
--allow-automated --require-clean` and is valid for the narrowed
`0.0.1` generated-speech and Soridormi MuJoCo-executor claim. It remains
`release_eligible=false` for a human-supervised physical voice-device claim.

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
| Realtime microphone/VAD/ASR/TTS/playback loop | Implemented; ASR inference runs off the WebSocket event loop through an explicit final-utterance backend boundary; `ASR_BACKEND=sherpa_onnx` and `ASR_MODE=final` are the maintained defaults; ASR startup performs a synthetic warm-up decode before accepting WebSocket requests; Faster-Whisper remains selectable for fallback/comparison; TTS playback stays ordered while complete speech can be chunked across bounded restartable service workers; route-level fast-first speech can start after Router returns while the Agent continues | Component concurrency/cancellation, ASR backend-selection, sherpa-onnx normalization, ASR accuracy-evaluator tests, TTS worker-pool, TTS alignment, plus automatic TTS-generated stdin and virtual-microphone acceptance modes | Local sherpa-onnx CPU and warmed CUDA evidence passed health plus English/Chinese final transcripts; clean SenseVoice A/B smoke showed 0 WER/CER for both sherpa-onnx and Faster-Whisper; physical microphone/speaker validation remains open for voice-device release claims | Sherpa-onnx SenseVoice CUDA provider default with startup warm-up; CPU fallback configurable; fast-first speech enabled by `.env.common` |
| Deterministic Router operational controls plus quick LLM route classifier | Implemented; interrupt/ignore controls remain deterministic while normal requests use catalog context, the fast Router model, validators, safe fallback, or deep model handoff; catalog search does not choose ordinary intent by itself; quick routing can emit ordered unlocked common-catalog compound `RouteDecision.actions` including `chromie.speak` speech tasks with per-action confidence, low-confidence `quick_router_review_request`, and deepthinking accept/revise/supersede review metadata | Router rule, capability-routing, LLM-prompt, deepthinking, interaction, and regression-scenario tests | Exercised by deployed smoke test; compound speech/body task path currently has automated evidence only | Enabled by `.env.common` |
| Multi-agent `POST /run` compatibility path | Implemented | Contract and integration tests | Used by the current voice loop | Enabled by `.env.common` |
| Structured `POST /interaction` API | Native `InteractionRuntime` is the default; compatibility adapter remains selectable | Native output, strict validation, fallback, and end-to-end named-skill tests | Text-to-live-MuJoCo evidence `20260617T081411Z` passed with ordered walk, nod, turn execution and safe idle | Host rollout flag off |
| Native structured Interaction Agent | Implemented with direct `InteractionSpeech`/`SkillRequest` accumulation, review-gated robot-action planning, optional simulator-bounded expressive body cues, and safe defaults for underspecified walking requests | Native route, TaskGraph, validation, fail-closed, fallback, expressive cue, exact-intent, and compatibility-mode tests | Text-input MuJoCo closure evidence retained; physical microphone retention remains separate | Agent default; chat body cues off |
| Trusted host Skill Runtime | Implemented | Scheduling, confirmation, timeout, cancellation, and isolation tests | Text-to-live-MuJoCo closure evidence passed | Used only by structured path |
| Spoken request-bound confirmation | Implemented with host-owned prompt, exact request fingerprint, expiry, single-use approval, and denial | Approval, denial, ambiguity, replay, mutation, expiry, and authorization tests | Clean synthetic and virtual-mic approval/denial evidence passed; text-to-MuJoCo uses the same trusted runtime authorization boundary | Structured path; simulator exemption configurable |
| Local speech skill provider | Implemented | Skill Runtime tests | Exercised by text acceptance; physical speaker validation remains separate | Available in structured path |
| Soridormi named-skill provider | Implemented | Provider and interaction-coordinator tests | Live MCP/MuJoCo planning, execution, and cancellation paths exist | Provider flag off |
| Provider failure normalization | Strict catalog/availability/plan/monitor/completion validation, stable timeout/cancellation terminal states, deterministic language-matched speech fallback, and a versioned 16-scenario replayable fault matrix with configurable latency thresholds, status snapshots, and safe-idle enforcement | Matrix, threshold and safe-idle evaluation, provider restart, unavailable skill, deterministic jitter, dropped monitor status, malformed completion, mismatched identity, disconnect-during-cancel, timeout, fallback, and completion-suppression tests | Live Soridormi-owned injection passed 16/16 scenarios; all ended safe-idle with no threshold violations | Used by Soridormi named skills |
| Provider conformance | Shared versioned checks and replayable high-level traces for simulator, recommendation-only hardware shadow, and no-motion hardware dry-run profiles, plus manifest preflight and strict retained-evidence verification | Local three-profile parity, trace-drift detection, opaque-identity normalization, profile-specific no-motion proofs, unsafe-output rejection, manifest preflight, and complete/unsafe bundle tests | Live no-motion `sim`, `hardware_shadow`, and `hardware_dry_run` profiles passed with parity; real hardware mode remains refused | Test tooling; real hardware mode refused |
| Conversation state across VAD utterances | Implemented in host memory with optional local recoverable task-context store; first deterministic extracted-memory/prompt-builder slice implemented for session/task memory, explicit memory-route updates, trusted runtime outcomes, Router prompt sanitization, direct fallback context, ordinary conversation prompts, capability planning/review prompts, and deepthinking prompts | Boundary, follow-up, task-context, restart-restore, extracted-memory, memory-agent, Router prompt-sanitization, conversation prompt, capability prompt, and deepthinking prompt tests | Available in the host Orchestrator | Conversation state enabled by `.env.common`; task-context store opt-in; durable personal memory and LLM-assisted extraction remain open |
| High-level Chromie ability self-model | Implemented as a host ability registry above concrete skills plus owner-approved mind identity for self-description questions, with stable cognition, speech, memory, social, body, manipulation, navigation, environment, task, safety, and state ability IDs; broad human-like missing abilities can be recorded as `known_missing`/`planned` and surfaced as `missing_ability` proposals while deep-thinking acknowledgement and simulator-only thinking pose resolve through this registry | Ability-registry, mind-profile, conversation-identity, Router prompt/proposal, deepthinking proposal, task-ledger, and Orchestrator TTS-alignment tests | No broad target-validation claim; only existing text/simulator interaction paths exercise fulfilled abilities | Registry enabled in host Orchestrator; most body, social, manipulation, navigation, and environment abilities remain honest non-executable roadmap entries |
| Structured acceptance evidence capture | Readiness preflight plus JSONL events, generated/captured audio, redacted runtime snapshot, case checks, and four explicit voice modes implemented; text-MuJoCo evidence writes route, interaction, execution, status, events, and summary artifacts | Preflight, synthetic/virtual-mic/acoustic framing, isolation, text-MuJoCo, and bundle-verification tests | Clean synthetic, virtual-mic, acoustic, and text-MuJoCo evidence retained; physical supervised mode remains optional release-support evidence for human voice-device claims | Acceptance-only |
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
| Release packaging | `0.0.1` version, release notes, compatibility file, archive/checksum generator, and strict release gate implemented | Packaging/evidence unit tests and full suite | M13 text scope is closed; acoustic generated-speech evidence supports the narrowed Soridormi MuJoCo-executor claim; human voice-device scope still requires supervised physical audio evidence | Release prep |

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

- the current `unittest` cases discovered under `tests/`;
- **20** dependency-light legacy Agent test functions under `agent/tests/`;
- documentation consistency checks after this documentation refresh.

The file-backed behavior scenario runner is implemented for Router and
InteractionRuntime module checks. It loads one deterministic JSON scenario per
file from `scenarios/`, evaluates route, speech, skill, confirmation, task, and
forbidden-output expectations, writes timestamped comparison reports under
`.chromie/reports/behavior-scenarios/`, and can compare against a previous
`summary.json` to list regressions and improvements. This is Level A automated
evidence only and does not create a target, simulator, microphone, speaker, or
release-readiness claim.

The general ability acceptance layer is now implemented as a claim-oriented
wrapper over representative behavior scenarios and live text probes. The
manifest at [`../scenarios/general_ability_acceptance.json`](../scenarios/general_ability_acceptance.json)
groups cases by reusable ability class, and
`python scripts/general_ability_acceptance.py --mode check` plus
`--mode level-a` report evidence level, claim scope, per-class coverage, and
whether a root-cause report is required. This is implemented and automatically
verifiable at Level A. It does not create live service, microphone, speaker,
simulator execution, physical robot, or release-readiness evidence by itself.

`scripts/scenario_author.py` can create draft files, validate the scenario
library, and print constrained prompts for LLM-assisted candidate generation;
committed scenarios remain deterministic files reviewed by a human.
Interaction scenarios can optionally run the host `prepare_response()` layer to
verify static preflight, proposal ledger, and deterministic correction metadata.
The `look_out_warning_correction` and
`revise_window_gaze_to_warning_speech` fixtures verify that quick window-gaze
proposals for warning utterances are superseded or revised into warning repair
speech with no Soridormi motion skill.

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
focused interaction/catalog task-agent tests, focused host Skill Runtime graph
dispatch tests, focused Soridormi acceptance tests, focused robot-candidate
verifier tests, and dependency-complete Orchestrator AgentClient coverage. The
retained local `./scripts/run_tests.sh` baseline on 2026-07-04 passed
`python scripts/check_docs.py`, ran 640 current `unittest` cases with `OK`, and
then passed 20 dependency-light legacy Agent test functions. The behavior
scenario runner also passed 353/353 adapter, Router, interaction, and dialogue
scenario files with `--no-write`.

The current 2026-07-09 local gate after the general ability reconstruction and
regression fixes passes the canonical dependency-light suite:
`./scripts/run_tests.sh` completed `python scripts/check_docs.py`, 743
`unittest` cases, and 20 dependency-light legacy Agent tests. Focused
general-ability checks also pass, including
`python scripts/general_ability_acceptance.py --mode check`,
`python scripts/general_ability_acceptance.py --mode level-a` with 35/35 Level
A representative probes, and `python scripts/test_matrix.py general-ability`.
The retained Level A summary is under
`.chromie/acceptance/general-ability/20260709T080845Z-level-a/summary.json`.

The 2026-07-09 live text preview run against local Router, Agent, and
Soridormi MCP is not passing yet. After fixing a headless runner blocker where
`sounddevice` was imported before `ORCH_AUDIO_INPUT_MODE=stdin` and
`ORCH_AUDIO_OUTPUT_MODE=discard` could take effect, the retained live-text
summary at
`.chromie/acceptance/general-ability/20260709T082052Z-live-text/summary.json`
shows 0/6 cases passed. All six live cases reached Router/Agent/MCP but routed
through `deep_thought_router_unavailable` after live Router LLM timeouts instead
of the expected `robot_action`, `clarify`, `tool`, or `chat` routes. This is
live service evidence for a Router/model-latency and fallback-path failure, not
simulator execution or release readiness.

The tests alone do not prove GPU performance, microphone quality, speaker
quality, or real robot safety. The retained RTX evidence above separately
validates the target GPU and automated host audio paths.

`scripts/interaction_text_mujoco_check.py` is available for text-input,
speaker-output, live-MuJoCo checks that skip microphone and ASR. The retained
`20260617T081411Z` bundle is the historical M13 text interaction closure
evidence. It does not prove physical microphone recognition or speaker quality.
On 2026-07-02, local live simulator rehearsals also passed through the current
Router/Agent/Skill Runtime/Soridormi MCP stack: warning text
`Look out, there is a cable in front of you.` emitted no Soridormi skills and
kept sim safe-idle under
`.chromie/acceptance/text-mujoco/20260702T055149Z`, and `Please nod twice.`
executed `soridormi.nod_yes` in MuJoCo `sim` mode and returned safe-idle under
`.chromie/acceptance/text-mujoco/20260702T055207Z`. These are local text-input
simulator evidence, not microphone, speaker-device, or physical-robot evidence.

The older standalone text prompt sweep has been removed as a behavior claim
tool. Add or update live text probes through the general ability manifest
instead, then run
`python scripts/general_ability_acceptance.py --mode live-text` against the
deployed stack.

## Open release-support gates

A release that claims human physical voice-device support is not publishable
until all of the following are complete:

1. Run `scripts/voice_acceptance.py --mode supervised` on the reference
   host for all seven cases and ensure
   `scripts/verify_voice_evidence.py --require-clean` passes.
2. The retained bundle is reviewed for audible quality, simulator safe idle,
   cancellation/recovery behavior, correlated IDs, and absence of secrets.
3. The release compatibility file has no remaining voice-device blockers and
   a clean release bundle is generated from the accepted revision.

## Open target-evidence tracks

These legacy evidence tracks do not define the current delivery:

- **Target GPU:** complete on the RTX 5090 reference host with a retained 21/21
  smoke pass; repeat on any hardware claimed by a release.
- **Combined target runner:** run
  `scripts/run_supervised_target_acceptance.sh` with a supervised, runtime-backed Soridormi
  endpoint and complete the documented recovery step.
- **Audio:** automatic synthetic, virtual-microphone, and acoustic modes passed;
  human microphone/speaker device information, timing logs, and pass/fail notes
  are still needed only for a physical voice-device release claim.
- **Hardware:** real motion remains experimental until Soridormi commissioning,
  confirmation, monitor, cancellation, stop, and recovery evidence are all
  retained for the exact hardware configuration.

## Known limitations

- The default structured interaction feature flags are off.
- Native interaction output is the Agent default, but the host structured
  rollout remains default-off unless the operator selects the `0.0.1` release
  configuration.
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
- Release notes, compatibility metadata, archive generation, and checksums
  exist, but there is no published GitHub release or support promise until the
  `0.0.1` tag and release artifacts are created.

## Release classification

Treat this revision as the **`0.0.1` release-prep snapshot** until it is tagged
and published. It is not a production release, physical-robot release, or human
voice-device release. Robot execution evidence for this release is limited to
Soridormi MuJoCo `sim`. See [Release and Packaging](RELEASE.md).
