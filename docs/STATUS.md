# Current Implementation Status

**Status authority:** this file describes what is present in the repository snapshot.
**Current release-prep base:** `0.0.1` scope with Soridormi MuJoCo `sim`
execution; retained target evidence below records the exact revision that
produced each bundle
**Status refresh date:** 2026-07-21
**Current focus:** **Promote the completed diagnostic Fast Planner multi-goal
qualification to source-bound target evidence by adding endpoint-reported
Soridormi revision identity, using a clean paired checkout, binding running
images/models to source, and making release inputs immutable. Physical pilot
and human voice-device validation remain separate release-support tracks.**
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

The repository contains a default-off Runtime Trace implementation. The shared
tracer provides module-owned generic spans, monotonic duration, wall-clock
correlation, async context propagation, cross-service Orchestrator-to-Agent
carriers and fragments, bounded attributes, immutable snapshots, and
topology-aware summaries. Instrumentation now covers the goal-driven cognitive
and model path, detached voice sessions, VAD/ASR, action execution/providers,
TTS/playback, user-observable milestones, bounded process/host/queue/event-loop
resources, optional non-blocking accelerator observations, idle abandonment,
active-trace checkpoint recovery, retention policy, and late-bound artifact
correlation. Optional `chromie.interaction_trace` Runtime Events and active-trace
attachment to cognitive-integrity incidents are also implemented. Coverage
remains `partial` because representative simulator/hardware traces and approved
environment-specific latency thresholds are not retained; implementation alone
does not establish an end-to-end target-latency claim.

The provider-readiness milestone is complete. A live local Soridormi MCP
endpoint passed the `sim`, recommendation-only `hardware_shadow`, and no-motion
`hardware_dry_run` conformance profiles, profile parity, and all 16 injected
fault scenarios. This is no-motion provider-contract evidence from macOS ARM64;
it is not Linux/GPU MuJoCo, audio-device, or physical-robot evidence.

The current top-level cognitive layer is the unified Goal-driven Runtime and
its single-semantic-authority boundary. The Chromie/Soridormi task-agent
boundary remains the downstream embodied-planning surface. Chromie consumes a
richer Soridormi task API snapshot with
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
classification JSON with `ROUTER_LLM_NUM_PREDICT=512`, and convert
schema-invalid or narrowed quick compound `actions[]` into the unified
Goal-driven Runtime instead of executing or narrowing them. Isolated low-information
ASR fragments clarify even if the fast model calls them chat. Weather/tool
queries with semantic weather evidence are normalized back to the tool lane when
the weather lookup affordance is present, even if a stale route item says chat.
A July 12 live voice log exposed the inverse contamination case: after a weather
turn, a clear walking request was returned as `route=chat`,
`intent=weather_query`. The Router now treats route/intent and exact-capability
route contradictions as invalid model contracts, requests an independent
semantic repair, and clarifies if repair remains inconsistent or uncertain. A
file-backed multi-turn Router-to-Interaction replay now forces that stale output
after a weather turn and verifies that repeated walking requests still produce
the exact bounded walking skill. Low-confidence referential fragments likewise
reach clarification instead of an unsupported acknowledgement. These are Level A
automated regressions, not retained live microphone, simulator, or physical
robot evidence.
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

Semantic task continuity is implemented inside the unified Goal-driven Runtime
and automatically verified. Shared contracts represent open semantic goals, versioned task
operations, active-task snapshots, information gaps, planning results, response
plans, commitments, and speech claims. The Router may propose semantic
create/modify/clarification and other task operations from meaning and bounded
active-task context; Goal Association independently reviews active-goal
relationships and emits stable replay-safe operations. Its model contract is
state-specific: when there are no active goals, association output and target
IDs are absent rather than exposing an impossible empty-target relationship.
Fast and Deep Planning use an exact flat model-facing DTO while the host owns
the canonical plan envelope, plan identity, tier, and authoritative goal set.
Model-facing goal outcomes are keyed by those authoritative goal IDs exactly
once and are materialized into the ordered canonical outcome list by the host.
Goal Satisfaction evaluates prospective plan coverage rather than claiming
that unexecuted work is already complete. Response Composition likewise uses
an exact model-facing schema while the host constructs the coordinated response
envelope and validates optional social attention. Each of these model boundaries
allows at most one bounded repair at the same stage and schema. Planner catalogs
exclude the local `chromie.speak` response transport: conversational work is a
goal-scoped `respond` outcome whose text is composed once by Response Composer,
not an executable planner step. The unified host
coordinator supports `off`, `report_only`, and lane-gated `apply`, validates
targets and confidence, applies accepted operations deterministically, protects replay,
versions goals, supersedes stale plans, invalidates stale confirmations, and
rejects stale planning results. Capability planning reports missing required
parameters as structured information gaps, and clarification answers remain
attached to the original task. Immediate ResponsePlan commitments are checked
against current task state and trusted evidence before fast-first playback. This
is dependency-light automated evidence only. The common safe base applies the
unified path to `chat`; the maintained Soridormi launcher widens it to
`chat,robot_action`. Standalone Goal Association, planner, Response Composer,
and task-continuity observer modes are off because the coordinator owns those
stages. Semantic multi-goal response composition covers per-goal outcomes and
exact step ownership, including mixed execute/respond/clarify/unavailable
turns. Generalized observation planning, retained live-text evidence, and
simulator validation remain open. See [Semantic Task Continuity and Situational
Planning](SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md).

The July 12 voice-log reliability slice is also implemented and automatically
verified. Router Ollama calls now carry an explicit 4096-token context budget so
the common ability menu is not truncated by the global 2048-token default. A
generic `chat/acknowledge` result is independently rechecked by the fast semantic
model when executable embodied affordances are present; internally contradictory
route/intent pairs are repaired or clarified. The old forward-motion and compound
body phrase/regex recovery path has been removed, so normal capability selection
remains model-based. Report-only task continuity no longer blocks the live turn,
resolver failures return safe empty diagnostics instead of HTTP 500, and Agent
disconnects on physical/tool/memory routes fail closed without sending the request
to an unrestricted direct-LLM fallback. Long CJK speech uses smaller punctuation
chunks, tool-prelude generation is default-off, and fragmentary greeting output
gets one compact semantic retry. These are automated and replay evidence only; a
new retained voice run is still required.
The episode evaluator also supports offline good/bad/needs-review case
journaling: `scripts/evaluate_experience_episodes.py` can write
`offline_reviews.jsonl`, owner-review-only proposal output, and scenario
candidates from the same episode evidence. This path is outside realtime audio,
can use optional deepthinking scoring, and keeps raw episode logs out of normal
prompt memory.

Chromie now has a structured mind context layer for an owner-approved self
model, core principles, long-term goals, reflex policy, deliberation policy, and
experience tuning boundaries. The internal self model identifies one stable speaking, perceiving, acting, and body-owning entity, while language and reasoning models are internal components with bounded roles. The prompt-facing social presentation foregrounds the name Chromie, personality, relationship, and current context; system category, embodiment category, age labels, and internal architecture remain background implementation context rather than ordinary self-introduction material. Router, conversation, DeepThinking, and direct-fallback prompts receive this ontology plus bounded runtime capability evidence, allowing the LLM to answer self-description and capability questions semantically without identity-question branches, fixed replies, or normal-language phrase/regex mapping. An append-only
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

At their recorded revisions, both M13 bundles passed the verifier then in use.
The current verifier defaults to the current source and rejects them for
current-release provenance; they remain historical automated target-host
evidence, not current goal-driven or physical microphone/speaker evidence.

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
`sim` behavior. At revision `842a334`, this supported the then-narrowed
generated-speech and Soridormi MuJoCo-executor candidate claim. The current
verifier rejects it as provenance for a newer source revision, and a fresh
goal-driven bundle is still required. It remains historical automated evidence,
not human-supervised physical voice-device evidence.

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
| Realtime microphone/VAD/ASR/TTS/playback loop | Implemented; SenseVoice ASR inference runs off the WebSocket event loop through a final-utterance service boundary; ASR decode and routed-turn execution have separate lifecycles so barge-in does not remain blocked behind Agent/TTS work; one newest VAD utterance is queued while ASR is busy instead of being dropped; `ASR_MODE=final` is the maintained protocol; ASR startup performs a synthetic warm-up decode before accepting WebSocket requests; TTS playback stays ordered while complete speech can be chunked across bounded restartable service workers; startup-primed English/Chinese acknowledgement PCM uses an adaptive hedge timer; TTS health and each successful response expose the resolved and observed DAC device plus model-generation, codec-decode, PCM, queue, IPC, total, and real-time-factor metrics; `scripts/benchmark_tts.py` provides repeatable no-playback measurements | Component concurrency/cancellation, busy-ASR latest-utterance queue, routed-turn replacement, cleanup, SenseVoice model resolution, normalization, ASR accuracy-evaluator tests, TTS worker-pool, TTS alignment, fast-first cache load/prime/hedge/cancellation, codec-device resolution, timing-hook, rolling-summary, benchmark, and worker-startup-metadata tests, plus automatic TTS-generated stdin and virtual-microphone acceptance modes | Local sherpa-onnx CPU and warmed CUDA evidence passed health plus English/Chinese final transcripts; the retained clean SenseVoice English/Chinese smoke showed 0 WER/CER; no Stage 6 TTS benchmark JSON or listening-quality bundle is retained in the repository yet | Sherpa-onnx SenseVoice CUDA provider default with startup warm-up; CPU fallback configurable; cached fast-first audio enabled with a 750 ms hedge; legacy generative tool acknowledgements disabled; DAC device resolves from `TTS_AUDIO_CODEC_DEVICE=auto`; synchronized detailed timing and a 20-request health window are enabled; the RTX 4090 Laptop TTS profile uses 4096 context/max length; prompt/generated token counts are retained and max-length exhaustion is rejected so incomplete audio is not played; FP16 remains unchanged pending measured A/B evidence |
| Deterministic Router operational controls plus quick LLM route classifier | Implemented; interrupt/ignore controls remain deterministic while normal requests use catalog context, the fast Router model, structural route/intent validation, independent semantic repair, safe clarification, or deep model handoff; catalog search does not choose ordinary intent by itself; quick routing can emit ordered unlocked common-catalog compound `RouteDecision.actions` including `chromie.speak` speech tasks with per-action confidence, low-confidence `quick_router_review_request`, and deepthinking accept/revise/supersede review metadata | Router rule, capability-routing, LLM-prompt, route-contract repair, low-confidence clarification, scripted raw-model replay, repeated weather-to-walk multi-turn Router-to-Interaction scenarios, deepthinking, interaction, and regression-scenario tests | The final July 21 diagnostic 10/10 live-text simulator run exercised typo recovery, exact capability routing, safe clarification, compound routing, and all four daily-life requests without hidden Router truncation. It is not microphone or source-bound Target evidence | Enabled by `.env.common` |
| Multi-agent `POST /run` compatibility path | Implemented | Contract and integration tests | Historical compatibility evidence only; it is not the maintained semantic-authority path | Service remains available, but common cognitive `apply` does not use it as semantic authority |
| Structured `POST /interaction` API | Native `InteractionRuntime` is the default; compatibility adapter remains selectable | Native output, strict validation, fallback, and end-to-end named-skill tests | Text-to-live-MuJoCo evidence `20260617T081411Z` passed with ordered walk, nod, turn execution and safe idle on the historical path; it is not evidence for the current cognitive authority path | Enabled in the common safe base |
| Native structured Interaction Agent | Implemented as the strict output and compatibility surface for `InteractionSpeech`/`SkillRequest` accumulation, TaskGraph requests, and optional `SocialAttentionPlan` coordination. Under cognitive `apply`, fingerprint-bound Response Composition is part of the authoritative Goal-driven pipeline rather than a separate background observer. Attention is selected from exact named capabilities or `none`; the host validates target evidence, schemas, latency, confirmation policy, and conflicts and excludes auxiliary attention from user task proposals | Native route, TaskGraph, validation, fail-closed, fallback, response-composition goal coverage/claim/immutability, social-attention selection/none/invalid/latency/target/conflict, exact-intent, and compatibility-mode tests plus file-backed interaction scenarios | The final July 21 diagnostic 10/10 live-text simulator run exercised fingerprint-bound cognitive response composition, ordered speech transport, action requests, execution receipts, and safe closure. Auxiliary Social Attention still lacks its own retained live qualification | Structured interaction enabled; normal profiles keep attention off. Only the explicit architecture-validation overlay selects `sim_only` with calibrated right-side fallback |
| Goal-driven cognitive runtime and single semantic authority | PR1–PR8 contracts and stages are integrated through one host coordinator: state-specific exact-schema Goal Association, exact flat Fast/Deep Planner DTOs with host-owned canonical envelopes, goal-keyed model outcomes, prospective Goal Satisfaction, exact-schema fingerprint-bound Response Composition, response-transport separation, one bounded same-stage repair, lane-gated runtime adaptation, atomic Goal-state application, mixed-plan execution, and existing confirmation/Skill Runtime execution. Maintained `apply` mode is authoritative for enabled routes and fails closed after ownership acquisition. Exact Router actions are adapter-only. The old CapabilityAgent semantic planner is retained only behind host and Agent gates plus a non-empty authoritative emergency claim whose `turn_id` exactly matches the request | The final July 21 gate passed 1106 primary plus 20 legacy Agent tests, 381/381 declarative scenarios, 52/52 Level A general-ability cases, the fail-on-error semantic-authority audit, and documentation validation. The retained cognitive-runtime family contains twelve scenarios and the daily-life Level A class contains eight cases | The final July 21 diagnostic live-text simulator suite passed 10/10 with complete execution receipts and safe idle. All four daily-life cases terminated at Fast; the explicit numeric three-action compound safely rejected a bad Fast substitution and recovered through Deep with 0.2 m/s preserved. Daily-life median cognitive runtime was 40.321 seconds, above the 15.46-second target. Dirty checkouts and absent endpoint revision identity prevent source-bound Target validation | Common safe base: authoritative `chat` apply, structured interaction on, Soridormi off. Maintained Soridormi launcher: authoritative `chat,robot_action`, Soridormi on. Both fail closed; legacy semantic fallback gates are off |
| Semantic compound capability planning | Implemented inside Fast/Deep canonical planning over bounded capability schemas plus provider/resource evidence. The model chooses exact execution, safe adjustment, alternative proposal, clarification, or unsupported; model-authored timing and explanation are preserved. A quick Router that cannot account for the complete effectful goal hands the original utterance to the unified planner instead of declaring the ability missing or invoking the legacy CapabilityAgent planner. Deterministic code validates the complete plan atomically, blocks partial-skill leakage, requires confirmation for material alternatives, and performs authorization/resource arbitration rather than natural-language action interpretation | Exact parallel composition, sequential alternative proposal, unresolved Router-to-planner handoff, unknown concurrency evidence, invalid-substep atomic rejection, confirmation-prompt override, host blocked-state stripping, repeated-step audit identity, and file-backed Chinese walk/blink regression tests | The July 21 diagnostic compound case executed sequential walk at exactly 0.2 m/s, two nods, and a left turn through Deep recovery, then returned safe idle. This is simulator evidence only and makes no claim that concurrent walking and blinking are physically compatible on a particular robot | Unified cognitive planning enabled for configured apply lanes; provider metadata remains authoritative; no normal-language action/count/speed fast-path parser |
| Trusted host Skill Runtime | Implemented | Scheduling, confirmation, timeout, cancellation, and isolation tests | The final July 21 diagnostic 10/10 suite exercised speech and Soridormi requests, sequential multi-step execution, normalized receipts, and safe-idle closure on the current Goal-driven path | Used only by structured path |
| Spoken request-bound confirmation | Implemented with host-owned prompt, exact request fingerprint, expiry, single-use approval, and denial | Approval, denial, ambiguity, replay, mutation, expiry, and authorization tests | Historical synthetic and virtual-mic approval/denial evidence passed; the current goal-driven path still needs a clean retained rerun | Structured path; simulator exemption configurable |
| Local speech skill provider | Implemented | Skill Runtime tests | Exercised by text acceptance; physical speaker validation remains separate | Available in structured path |
| Soridormi named-skill provider | Implemented | Provider and interaction-coordinator tests | Live MCP/MuJoCo planning, execution, and cancellation paths exist | Off in common safe base; enabled by maintained Soridormi launcher |
| Provider failure normalization | Strict catalog/availability/plan/monitor/completion validation, stable timeout/cancellation terminal states, deterministic language-matched speech fallback, and a versioned 16-scenario replayable fault matrix with configurable latency thresholds, status snapshots, and safe-idle enforcement | Matrix, threshold and safe-idle evaluation, provider restart, unavailable skill, deterministic jitter, dropped monitor status, malformed completion, mismatched identity, disconnect-during-cancel, timeout, fallback, and completion-suppression tests | Live Soridormi-owned injection passed 16/16 scenarios; all ended safe-idle with no threshold violations | Used by Soridormi named skills |
| Provider conformance | Shared versioned checks and replayable high-level traces for simulator, recommendation-only hardware shadow, and no-motion hardware dry-run profiles, plus manifest preflight and strict retained-evidence verification | Local three-profile parity, trace-drift detection, opaque-identity normalization, profile-specific no-motion proofs, unsafe-output rejection, manifest preflight, and complete/unsafe bundle tests | Live no-motion `sim`, `hardware_shadow`, and `hardware_dry_run` profiles passed with parity; real hardware mode remains refused | Test tooling; real hardware mode refused |
| Conversation and semantic task state across VAD utterances | Implemented in host memory with optional local recoverable task-context store; includes extracted session/task memory, bounded active-task snapshots, open semantic goals, replay-safe structured task operations, goal/plan versioning, confirmation invalidation, planning-result freshness checks, information gaps, Goal Association, same-turn Router-to-Agent context refresh, atomic operation application, and immediate response-claim validation | Boundary, follow-up, task-context, restart-restore, extracted-memory, semantic-task contract, create/modify/clarification/replay, goal-association continuity/segmentation/ambiguity, task-continuity prompt/target/confidence/idempotency, response-claim, capability information-gap, Router prompt, task-proposal, interaction, and TTS-alignment tests | Available in the host Orchestrator; no retained live semantic-continuity evidence for the current authority path yet | Conversation state and unified cognitive `apply` are enabled in `.env.common` for `chat`; standalone Goal Association, planner, Response Composer, and task-continuity observer modes are off because the unified coordinator owns those stages. Durable personal memory and LLM-assisted extraction remain open |
| High-level Chromie self and ability model | Implemented as an owner-approved structured self model plus a host ability registry above concrete skills. Prompts bind first-person speech, perception, action, and body ownership to the self-model speaker entity, expose language/reasoning models only as internal components, and use a natural social presentation that foregrounds the name Chromie rather than volunteering system category, embodiment category, age labels, or internal architecture; capability inquiries use the supplied catalog/provider evidence semantically and do not execute actions. Stable cognition, speech, memory, social, body, manipulation, navigation, environment, task, safety, and state ability IDs remain available; broad human-like missing abilities can be recorded as `known_missing`/`planned` and surfaced as `missing_ability` proposals | Mind/self-model, conversation prompt, Router inquiry-versus-execution, DeepThinking, direct-fallback, ability-registry, capability-evidence, dialogue-scenario, task-ledger, and Orchestrator TTS-alignment tests | Automated prompt/scenario evidence only; no claim that every live model response will be correct, and only existing text/simulator paths exercise executable abilities | Registry enabled in host Orchestrator; no identity-question branch, hardcoded identity reply, or normal-language identity/capability regex was introduced; most body, social, manipulation, navigation, and environment abilities remain honest non-executable roadmap entries |
| Structured acceptance evidence capture | Readiness preflight plus JSONL events, generated/captured audio, redacted runtime snapshot, case checks, and four explicit voice modes implemented; text-MuJoCo evidence writes route, interaction, execution, status, events, and summary artifacts | Preflight, synthetic/virtual-mic/acoustic framing, isolation, text-MuJoCo, and bundle-verification tests | Historical clean synthetic, virtual-mic, acoustic, and text-MuJoCo evidence is retained for its recorded revisions; a clean current goal-driven rerun remains open. Physical supervised mode is separate support evidence for human voice-device claims | Acceptance-only |
| Developer usability CLI | `python -m tools.chromie_cli` implements `status`, `config show`, `config validate`, `doctor`, `capability check`, `trace view`, and `evidence bundle` with plain/JSON output; `trace explain` remains future work | CLI command, output, validation, doctor, manifest-safety, retained-trace, and evidence-preflight unit tests plus full Level A gate | Local doctor can report service reachability, trace view can summarize retained local artifacts, and evidence preflight can label retained bundle pointers, but none create target evidence or release readiness | Tooling |
| Capability registry and deployment probe | Implemented; materialization preserves provider compatibility tools but forces raw planar `commands[]` controller arrays out of model-facing catalogs, and the static audit rejects visible regressions | Registry, manifest, pagination, schema, materialization-visibility, and CLI safety tests | Checked-in Soridormi manifest is pinned to an upstream commit | Root Compose loads the static manifest by default; live Soridormi provider use remains off in the common safe base; normal model-authored motion uses named skills or structured task goals rather than controller recipes |
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
| Release packaging | `0.0.1` version, candidate notes, compatibility file, archive/checksum generator, and strict release gate implemented | Packaging/evidence unit tests | Historical M13 and acoustic evidence does not validate the current authority path. The current runners record a declared paired Soridormi checkout but no endpoint-reported executing revision; running Chromie images/models are not yet bound to host `HEAD`; maintained image references remain mutable; fresh target-validated voice and text-to-MuJoCo evidence is still required. Human voice-device scope separately requires supervised physical audio evidence | Blocked candidate preparation |

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

The historical task-agent routing, refusal-reporting, host graph-dispatch,
no-motion bridge-acceptance, and reference-candidate verifier refresh after
committed base `f4bbb2f` passed `python scripts/check_docs.py`,
`python scripts/test_matrix.py taskgraph soridormi`, local dry-run
`--task-agent-bridge` acceptance against Soridormi MCP on `127.0.0.1:8011`,
focused interaction/catalog task-agent tests, focused host Skill Runtime graph
dispatch tests, focused Soridormi acceptance tests, focused robot-candidate
verifier tests, and dependency-complete Orchestrator AgentClient coverage. The
retained local `./scripts/run_tests.sh` baseline on 2026-07-04 passed
`python scripts/check_docs.py`, ran 640 `unittest` cases with `OK`, and
then passed 20 dependency-light legacy Agent test functions. The behavior
scenario runner also passed 353/353 adapter, Router, interaction, and dialogue
scenario files with `--no-write`.

The historical 2026-07-09 local gate after the general ability reconstruction
and regression fixes passed the canonical dependency-light suite:
`./scripts/run_tests.sh` completed `python scripts/check_docs.py`, 743
`unittest` cases, and 20 dependency-light legacy Agent tests. Focused
general-ability checks also pass, including
`python scripts/general_ability_acceptance.py --mode check`,
`python scripts/general_ability_acceptance.py --mode level-a` with 35/35 Level
A representative probes, and `python scripts/test_matrix.py general-ability`.
The retained Level A summary is under
`.chromie/acceptance/general-ability/20260709T080845Z-level-a/summary.json`.

The historical 2026-07-12 automated regression gate during goal-driven PR7
runtime migration passed `python scripts/check_docs.py`, 899 `unittest` cases,
and 20 dependency-light legacy Agent tests through `./scripts/run_tests.sh`.
The complete file-backed behavior library passed 373/373 adapter, Router,
Router-dialogue, interaction, dialogue, and cognitive-runtime scenarios with
`--no-write`. General-ability Level A passed 42/42. The scenarios forced the raw quick model to
return observed stale or generic decisions for walking and compound nod/blink
requests, then verify bounded semantic review, exact capability grounding,
confirmation, final Agent skill output, repeated correctness after a weather
turn, and absence of weather or retry fallback speech. Busy-ASR lifecycle tests
verify that only the newest pending utterance is retained and that a newer
routed turn cancels stale turn processing. At that checkpoint, standalone
task-continuity report-only calls were non-blocking and degraded to an empty
advisory result on model failure; effectful
Agent disconnects fail closed instead of falling through to an unrestricted
direct LLM. Stage 6 additionally verifies explicit DAC-device selection,
worker-reported runtime metadata, synchronized model/codec timings, rolling
performance summaries, and benchmark result aggregation. The self-model prompt refresh adds a retained three-turn identity/unavailable-dance/available-blink scenario and a prompt-facing social presentation that foregrounds Chromie by name without making a false human-identity claim. A retained Router scenario verifies that an unresolved compound action preserves the original utterance for complete-goal planning instead of becoming a terminal missing-ability response, and verifies inquiry-versus-execution semantics without introducing an
identity blacklist, fixed identity response, or phrase-matched capability
handler. Unified Fast/Deep capability planning asks the model to reconstruct the
complete requested outcome and choose an exact plan, safe adjustment,
alternative proposal, clarification, or unsupported result from provider and
resource evidence. Capability parameter completion is semantic and schema-grounded. The
planner sees defaults, bounds, safety class, effects, provider
constraints, and the complete user request, then decides whether a missing field
can use a conservative ordinary value or requires a specific user clarification.
Low-consequence defaults are retained with parameter-grounding evidence;
material duration, direction, target, authorization, cost, or irreversible
fields become structured information gaps. The semantic capability-planning
handoff is not redirected to generic DeepThinking solely because the quick
Router reports zero confidence. Stage 6.6 adds retained live-interaction
replays for compound walking and blinking, semantic recovery from an
unstructured/internal placeholder clarification, and a later parameter answer
resuming the original task. Planner-created alternative plans remain
`awaiting_confirmation` instead of being overwritten as scheduled. The host now
force-closes and discards continuously open VAD segments at 20 seconds and
accepts valid high-energy short replies from 450 ms, addressing the observed
242-second false utterance and repeated one-second reply drops.
The runtime validates every proposed step before committing
any of them, preserves model-authored parallel/sequential timing, disables
simulator auto-confirm for material alternatives, and prevents structured
clarification or blocked results from leaking effectful skills. The former
normal-language count/speed/action fast-path parsers were removed. PR1 through
PR8 now provide the Goal-driven contracts, unified runtime, and single-authority
boundary. The common safe base authoritatively applies `chat`; the maintained
Soridormi launcher widens authority to `chat,robot_action`. Both use
fail-closed behavior after ownership acquisition. Atomic Goal-state commit,
bounded host replan, classified operational evidence, and cognitive
text-to-MuJoCo entry points are automatically verified. July 21 diagnostic
Level C runs now exercise the current path live through Router, Agent, Ollama,
Skill Runtime, TTS, and Soridormi MuJoCo. They are not source-bound Target
validation because the paired Soridormi checkout was dirty and its endpoint did
not report the executing revision. A retained Stage 6 GPU benchmark, listening
check, and supervised live voice rerun are also still required.

The historical 2026-07-14 post-PR7 cognitive-architecture and daily-life multi-goal
review passed `python scripts/check_docs.py`, 926 `unittest` cases, 20
legacy Agent tests, 381/381 file-backed behavior scenarios, and 50/50 General
Ability Level A probes. The retained cognitive-runtime family now contains
twelve scenarios, including eight daily-life multi-goal cases that cover
supported sequential actions, repeated identical skills, body action plus
conversation, action plus clarification, supported action plus unavailable
manipulation, and a three-way execute/respond/clarify turn. The review found and
corrected the earlier architecture defects around independent outcomes, commit
ordering, provider-goal association, auxiliary attention, broad reset phrases,
and the trusted adapter's rejection of otherwise valid terminal `mixed` plans.
Active goals preserve conversation continuity across idle boundaries, and every
effectful step is asserted against its exact `source_goal_ids`. These were Level
A automated and harness results. The revised daily-life live manifest
subsequently passed the July 21 diagnostic qualification described below
against deployed Router, Agent, Ollama, and MuJoCo services.

The 2026-07-17 root-cause repair replaced permissive or structurally ambiguous
model contracts at the earliest responsible boundaries. Goal Association now
uses a zero-active-goal schema that cannot emit association targets. Fast and
Deep Planning expose a flat exact DTO, key each outcome by its authoritative
goal ID, evaluate prospective satisfaction, and reject response transport such
as `chromie.speak` as an executable plan step. Response Composer exposes only
its exact model-authored fields and the host constructs the canonical response
envelope. The final required `./scripts/run_tests.sh` command passed 1106
primary tests plus 20 legacy Agent tests; the full Level A general-ability
matrix passed 52/52, including `multi_goal_daily_life` 8/8. The documentation,
381-scenario, semantic-authority, compile, syntax, and diff-hygiene gates also
passed. These results establish the implemented and automatically verified axes
only.

A July 17 diagnostic preview reached valid two-goal planning and response
composition, and the subsequent four-case execute run progressed through three
cases before the mixed blink-and-joke case exposed the speech-transport and
per-goal outcome-shape defects above. The fixes were made after that run. On
July 21, the final hardened working tree completed a fresh ten-case suite,
including all four daily-life cases; the result and its evidence boundary are
recorded below.

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

- Structured interaction and authoritative goal-driven `apply` for `chat` are
  enabled in the common safe base. Soridormi skills, simulation auto-confirm,
  and physical execution remain off there; the maintained Soridormi launcher
  explicitly widens authority to `chat,robot_action` after enabling the trusted
  provider.
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

Treat this revision as a blocked **`0.0.1` release candidate**. Before fresh
goal-driven voice/MuJoCo evidence can count toward publication, the Soridormi
endpoint must report its executing revision, running Chromie images/models must
be bound to the candidate source, and mutable release image references must be
replaced. The release must then be tagged and published. It is not a production
release, physical-robot release, or human voice-device release. Historical
robot execution evidence is limited to Soridormi MuJoCo `sim` and does not
validate the current semantic-authority path. See
[Release and Packaging](RELEASE.md).

## Goal-driven cognitive runtime status

[Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
defines the cognitive constitution, and
[Scenario-Driven Development](SCENARIO_DRIVEN_DEVELOPMENT.md) defines the
required interaction-development method.

PR1 through PR6 implement and automatically verify Goal contracts,
continuity-before-creation association, independent multi-Goal segmentation,
Canonical Plans, complete-coverage Fast Planning, terminal full-catalog Deep
Planning, bounded same-tier revision, consequence-aware parameter resolution,
Goal Satisfaction, response composition, and independent Social Attention.

The current model boundaries are narrower than the canonical host contracts.
Goal Association selects a state-specific exact schema, including an
association-free schema when no active goal exists. Fast and Deep Planning use
flat exact DTOs with goal-keyed outcomes; the host restores canonical identity,
tier, goal order, and metadata. Satisfaction is prospective until execution.
Response Composer uses its own exact DTO and the host builds the coordinated
response envelope. Planner-visible catalogs exclude `chromie.speak`, so
conversational responses remain `respond` outcomes owned by Response Composer.
Each model stage has only one bounded same-stage/schema repair.

PR7 and PR8 integrate those stages behind one host coordinator with `off`,
`report_only`, and lane-gated `apply`. Applied plans still pass the existing
trusted preparation, request-bound confirmation, Skill Runtime, provider, and
evidence boundaries. Goal-state changes are atomic, and optional social
attention is revalidated by the host for target evidence, schema correctness,
and primary-plan resource conflicts.

The common safe base now enables structured interaction and authoritative
`apply` for `chat` while leaving the Soridormi provider off. The maintained
Soridormi launcher enables that trusted provider and widens authority to
`chat,robot_action`. A turn that enters the Goal-driven Runtime cannot fall
through to the old CapabilityAgent planner. Exact Router actions are
adapter-only, and the retained old semantic planner requires host and Agent
gates plus a non-empty authoritative emergency claim whose `turn_id` matches
the request. That claim is internal routing metadata, not caller authentication
or a consumed replay nonce. This single-authority boundary is implemented and
automatically verified without GPU services; see
[Single Semantic Planning Authority](SEMANTIC_AUTHORITY.md).

Evidence and release tooling now rejects provenance drift instead of relabeling
an older bundle as validation for the current source. Cognitive simulator
validation requires an applied cognitive result, completed Soridormi `sim`
execution, explicit safe idle, a clean declared paired checkout, and an
endpoint-reported Soridormi revision matching the manifest and checkout. The
general-ability wrapper now accepts and forwards `--soridormi-repo`, so the
declared paired checkout is recorded defensively even when the standalone runner
is invoked through that wrapper. The endpoint still reports no executing
revision, so current output remains diagnostic rather than target-validated.
Voice evidence and release preparation likewise compare
declared revisions and version with current source, but running Chromie
images/models are not yet bound to host `HEAD`, and maintained image references
remain mutable. These implemented fail-closed checks do not make the current
snapshot release ready or replace the missing provenance bindings and fresh
retained target run.

An operator-supplied July 17 live-text simulator rerun at Chromie revision
`27ed13b6114f0a0fa7fd72078012c34b4ddf0712` passed all four
`multi_goal_daily_life` cases with completed Soridormi `sim` execution and safe
idle. This closes the immediate mixed-plan correctness defect at diagnostic
Level C, but it does not establish successful Fast Planner operation: all four
Fast attempts recorded model-contract failure and the final success came from
Deep Planner recovery. Endpoint-reported Soridormi revision identity was still
absent, so the run does not close release provenance or release readiness. The
repository implementation now follows
[Fast Planner Multi-Goal Contract Path](FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md).
A five-run warm benchmark of that first Fast implementation produced 20/20
`contract_failure` results, invoked Deep Planner for every case, measured a
22.87-second median cognitive runtime, and improved only 3.9 percent against the
23.79-second baseline. The decoder schema allowed empty or partial terminal maps
and optional nested fields that deterministic validation rejected. The revised
implementation now requires the model to author the complete
multi-goal semantic plan, including step IDs, ownership, outcomes, aggregate
disposition, and satisfaction. The host adds only canonical identity and
validates the plan.

An earlier July 21 tuning snapshot passed 12/12 Fast-terminal cases with a
15.355-second aggregate median, but later generic numeric-provenance, decoder,
Router, and Response Composer hardening superseded that snapshot. The final
hardened working tree passed a fresh 4/4 `multi_goal_daily_life` diagnostic run:
every case terminated at Fast Planner, recorded no hidden technical planner
failure or Deep invocation, completed Soridormi `sim` execution, and returned
to explicit safe idle. Its 40.321-second median misses the 15.46-second target,
so latency qualification and the required three-run matrix remain open. The
output is diagnostic Level C rather than source-bound Target validation because
it records a dirty declared paired Soridormi checkout and no endpoint executing
revision. Operational rollout remains governed by
[Goal-Driven Cognitive Runtime Rollout](COGNITIVE_RUNTIME_ROLLOUT.md).

The user-outcome acceptance layer is now implemented. Live general-ability
probes default to architecture-independent observable behavior assertions while
retaining route and planner details as diagnostics. Timeout, prompt/input
truncation, output truncation, incomplete stream, and incomplete structured
output are hard failures that fallback cannot hide. A declarative observation
map translates execution receipts into stable behavior types and is never read
by production planning.

Social Attention is now represented as a high-level behavior domain. Response
Composer may model-author coordinated language style/pacing and auxiliary body
expression under one social purpose. Candidate body behaviors are discovered
from catalog behavior-domain metadata instead of a fixed production list. The
host validates and may drop auxiliary behavior; concrete user-requested actions
remain primary CanonicalPlan goals. Automated verification exists, while fresh
live interaction evidence for contextual appropriateness remains open.

## Runtime Observability Step 7

Step 7 added generic Runtime Trace items for session lifecycle, action execution,
TTS, playback, and first audible response. At that checkpoint, ASR/VAD spans,
first physical motion, resource sampling, crash recovery, and retained live
latency qualification were open. Steps 8-10 subsequently implemented those
instrumentation paths; target latency qualification remains open. See
[Step 7: Session, Execution, and Audio Runtime Trace](STEP7_SESSION_EXECUTION_AUDIO_TRACE.md).

## Runtime Observability Step 8

Step 8 added valid VAD utterances, ASR calls, action-provider acknowledgements,
optional provider-reported first physical motion, and idle-timeout abandonment
of unfinished voice sessions. Resource sampling and persisted process-restart
recovery were added in Step 9; retained target latency baselines remain open.

## Runtime Observability Step 9

Runtime Trace now records optional generic process/host-memory, queue-depth, and
event-loop-lag resource samples. Active voice-session traces can be atomically
checkpointed and recovered after process restart as truthful abandoned evidence.
Normal interaction/session trace Runtime Events support abandoned-trace
retention, latency thresholds, and deterministic sampling, while critical
cognitive-integrity incidents remain independent of normal sampling. Session
traces gain conversation, cognitive-trace, interaction, and episode correlation
IDs as those artifacts become available. At that checkpoint accelerator
telemetry was open; Step 10 subsequently added the optional non-blocking
provider. Retained simulator/hardware latency baselines remain open. See
[Step 9: Resource, Recovery, and Trace Retention](STEP9_RESOURCE_RECOVERY_RETENTION.md).

## Runtime Observability Step 10

Chromie now supports optional non-blocking accelerator telemetry through a
bounded worker-thread provider, represented as generic `resource_sample` trace
items. Retained Runtime Trace event packages can be summarized into reproducible
latency distributions with provenance, environment labels, source digests,
module/resource breakdowns, and p50/p90/p95/p99 statistics. An explicit
baseline-versus-candidate gate verifies sample counts, evidence class,
environment identity, clean revisions, and configured absolute/relative
thresholds. The repository example gate is disabled and is not release
evidence. Real simulator/hardware baselines and approved environment-specific
thresholds remain open operational evidence. See
[Step 10: Accelerator Telemetry and Latency Evidence Gates](STEP10_ACCELERATOR_LATENCY_EVIDENCE.md).
