# Development Checkpoint

**Current release-prep base:** `0.0.1`
**Soridormi capability snapshot:** generated from the paired Soridormi checkout; see `capabilities/soridormi.json` metadata for provenance
**Status refresh date:** 2026-07-22
**Current focus:** Finish Fast Planner multi-goal latency qualification and
promote it to source-bound Target evidence: reduce final-source median cognitive
runtime to the accepted threshold, repeat three warm runs, add
endpoint-reported Soridormi revision identity, use a clean paired checkout,
bind running images/models to source, and make release inputs immutable.
Physical pilot and human voice-device validation remain separate tracks.

This file is a short resume marker, not a second status or roadmap. Use
[Status](docs/STATUS.md) for capability claims and [Roadmap](ROADMAP.md) for
milestone intent.

## Resume point

The Fast Planner functional implementation in
[Fast Planner Multi-Goal Contract Path](docs/FAST_PLANNER_MULTI_GOAL_CONTRACT_PATH.md)
has a passing final-working-tree diagnostic run. On July 21, the four daily-life
cases all terminated at Fast Planner, completed Soridormi `sim` execution, and
returned to safe idle. Their 40.321-second median cognitive runtime misses the
15.46-second threshold. An earlier 12/12, 15.355-second tuning result predates
the final generic numeric-provenance and decoder hardening and is not current
qualification evidence. The host still adds only canonical identity and
validation; the model authors skills, arguments, ordering, ownership, outcomes,
aggregate disposition, and satisfaction. Resume with latency work and then the
three-run, clean paired-source, endpoint-identified qualification; do not
promote the current diagnostic result to Target validation.

The current branch also implements the first user-outcome acceptance layer and
Social Attention behavior-domain model. The default live acceptance scope now
asserts normalized user-observable behavior, truthful speech, execution
receipts, final safety, and complete LLM calls without binding release behavior
to a specific planner path. Timeout or truncation remains a hard failure even
when fallback succeeds. Response Composer may model-author contextual language
style and auxiliary body expression under one Social Attention purpose;
candidate actions are discovered from catalog behavior-domain metadata rather
than a fixed gesture list. Explicit user-requested actions remain primary goals.

The current branch also implements the framework-neutral TTS provider boundary.
The maintained OuteTTS worker path now implements `TTSProvider` contract version
1, provider/model provenance and native-streaming truth are exposed through
health/start/end metadata, and unknown adapters fail closed. The shared A/B
runner uses one Mandarin, English, mixed-language, interruption/recovery,
six-turn dialogue, and concurrency matrix and produces objective metrics, WAVs,
and a mandatory listening-review template. Separate exact-lock CosyVoice3 0.5B
and Qwen3-TTS 0.6B Base evaluation images now implement that endpoint using one
hashed bilingual reference voice and restart-on-cancel workers. This is still
not provider-selection evidence. The latest local dirty-tree isolated run,
`20260722-chromie-ai-girl-v1`, used the user-authorized AI-generated candidate
voice and passed 6/6 cases for each provider: CosyVoice3 recorded 3.0987 s
median first binary and 0.5419 median RTF, versus 5.6786 s and 0.9364 for
Qwen3-TTS; post-cancel recovery favored Qwen3-TTS at 8.0885 s versus 18.7919 s.
The same recordings created transcript-validated English, Chinese, and mixed
Oute profiles, but one longer mixed prompt exhausted its token budget without
audio, so mixed-language stability remains open. Candidate-output listening
review, deployment license review, approved recovery bounds, clean repeated
runs, and shared-resource target qualification remain open. The owner approved
the voice style, but it was not promoted to Oute's maintained default: rebuilt
container checks reproduced stochastic token exhaustion with both
`chromie_mixed` and Chinese-aligned `chromie_zh`, and an RTX 5090 8192-token
diagnostic did not fix it. The local profiles and source recordings remain
untracked. This does not approve either candidate-provider result, and
`TTS_PROVIDER=oute` with its built-in speaker remains the maintained default.

The initial Runtime Observability implementation is now present behind a
default-off policy. It provides architecture-independent Runtime Trace items,
module-owned identity, `off`/`basic`/`debug` collection, monotonic duration
measurement, nested sync/async spans, cross-service carriers and mergeable
fragments, bounded attributes, topology-aware summaries, optional
`chromie.interaction_trace` Runtime Events, and active-trace attachment to
cognitive-integrity incidents. Current instrumentation covers the goal-driven coordinator, canonical adapter,
cognitive Agent calls and resolvers, Ollama, detached voice sessions, VAD/ASR,
action execution/providers, TTS/playback, user-observable milestones, bounded
resource samples, idle abandonment, checkpoint restart recovery, retention
policy, artifact correlation, optional non-blocking accelerator telemetry, and
retained-trace latency report/gate tooling. Coverage remains `partial` until
representative simulator/hardware traces and environment-approved thresholds
are retained; code does not manufacture that evidence. See
[Runtime Observability Architecture](docs/RUNTIME_OBSERVABILITY_ARCHITECTURE.md),
[Runtime Trace Contract](docs/RUNTIME_TRACE.md), and
[Step 10: Accelerator Telemetry and Latency Evidence Gates](docs/STEP10_ACCELERATOR_LATENCY_EVIDENCE.md).

The `0.0.1` release implementation is present:

- unified Goal Association, complete-coverage Fast Planning, terminal Deep
  Planning, Response Composition, atomic Goal-state application, and trusted
  Skill Runtime adaptation behind one host coordinator;
- a common safe base with structured interaction and authoritative `chat`
  `apply`, plus a maintained Soridormi launcher that enables the provider and
  widens authority to `chat,robot_action`; both fail closed after ownership;
- a single-semantic-authority boundary: exact Router actions are adapter-only,
  and the old CapabilityAgent planner is emergency-only behind host and Agent
  gates plus a non-empty matching-turn authoritative claim;
- native strict structured interaction;
- trusted host Skill Runtime and Soridormi named skills;
- request-bound spoken confirmation;
- deterministic interruption and cancellation;
- seven-case synthetic, virtual-microphone, acoustic, and supervised acceptance
  tooling;
- evidence verification and release packaging;
- small-model quick Router classification for normal semantic routing while
  stop/cancel/ignore controls remain deterministic;
- model-assisted routing guardrails that treat `qwen3:4b` as a proposer, not
  the authority for capabilities, safety, or physical execution;
- short-term session memory exposed to Router and Agent prompts, plus a
  dedicated deepthinking Agent path for low-confidence or complex requests;
- three-stage routing metadata where emergency filtering, quick intent routing,
  and deepthought handoff can each contribute high-level task/action proposals
  to the merged `RouteDecision.metadata.task_list`;
- host-side task-proposal merge ledger that treats Router task list entries as
  proposals, marks effectful proposals as `not_committed` until matched by a
  final `InteractionResponse` skill, and audits committed speech/skills plus
  static preflight status and rejected deepthinking tasks without widening
  execution authority;
- experience records retain task-proposal and preflight summaries as
  owner-review-only learning signals when mismatches, blocked static checks, or
  truth reconciliation occur; these summaries do not auto-apply rules and do
  not inject raw proposal payloads into prompts;
- host truth reconciliation has a first warning-misread repair path: a mistaken
  quick proposal such as window gaze for "Look out!" is superseded by specific
  warning speech and no physical skill is emitted;
- `shared/chromie_contracts/task_proposal.py` defines the first shared
  proposal ledger contract, including preflight annotations and the
  `superseded` state; Orchestrator ledger output is validated through this
  contract, and Router now emits shared `metadata.task_proposals` alongside
  legacy `metadata.task_list`; the Agent deepthinking path now emits shared
  `metadata.deepthinking_task_proposals`; final Agent speech and skills now
  emit shared `metadata.agent_task_proposals`, including speech as the local
  `chromie.speak` skill;
- host ability registry entries for cognition, speech, memory, social, body,
  manipulation, navigation, environment, task, safety, and state abilities,
  including `known_missing` and `planned` entries for unavailable human-like
  behaviors;
- first two semantic task-continuity slices with shared open-goal/task-operation
  contracts, bounded active-task snapshots, replay-safe versioned goal updates,
  stale-plan and confirmation invalidation, structured information gaps,
  dedicated Agent task-continuity resolution, staged report/apply rollout,
  immediate ResponsePlan claim validation, and same-turn Router-to-Agent task
  context;
- Router route/intent contract recovery for stale cross-turn model output,
  including independent semantic repair, low-confidence clarification, exact-skill
  grounding, and file-backed single-turn plus weather-to-walk multi-turn replay;
- July 12 voice-log reliability hardening: explicit Router context budget,
  model-based generic-chat affordance review for compound body requests, removal
  of normal-language forward/compound regex recovery, background non-blocking
  continuity reporting with fail-safe endpoint degradation, effectful Agent
  disconnect fallback that cannot promise unexecuted work, compact greeting retry,
  and smaller CJK TTS chunks;
- separate ASR and routed-turn lifecycles so a new utterance can replace stale
  Agent/TTS work, with one newest pending VAD utterance retained while ASR is
  still decoding instead of being dropped;
- dream-broadly/execute-honestly proposal contract: quick Router and
  deepthinking may record understood but non-executable desired abilities as
  `missing_ability` task proposals, while executable work still requires exact
  catalog skill IDs and trusted runtime validation;
- goal-driven PR1–PR8 runtime migration with shared Goal and CanonicalPlan
  contracts, continuity-before-creation association, complete-coverage Fast
  Planning, terminal Deep Planning, parameter resolution, Goal Satisfaction,
  fingerprint-bound response composition, lane-gated
  `off`/`report_only`/`apply`, one bounded trusted-validator replan, atomic
  Goal-state application, classified operational evidence, and immediate
  per-lane rollback; maintained configuration uses authoritative `apply`, while
  retained live-text/MuJoCo evidence for that path remains open;
- exact model boundaries for that pipeline: Goal Association selects a
  state-specific schema that omits association when no active goals exist;
  Fast/Deep Planning uses a flat exact DTO with host-owned plan identity, tier,
  canonical goal order, and metadata; per-goal model outcomes are keyed exactly
  once by authoritative goal ID; Goal Satisfaction is prospective; Response
  Composer uses an exact DTO while the host constructs its canonical envelope;
  and each model stage permits only one bounded same-stage/schema repair;
- response-transport separation: planner-visible catalogs exclude
  `chromie.speak`, conversational work is represented as a `respond` outcome,
  and Response Composer owns the single user-facing response instead of the
  planner scheduling speech as a physical step;
- acceptance provenance forwarding: `general_ability_acceptance.py` accepts
  `--soridormi-repo` and passes it to the standalone live-text runner, while
  endpoint-reported executing revision identity remains open;
- model-authored optional social-attention plans that may choose subtle named
  behavior or `none`, use live target evidence before installation calibration,
  stay outside user task proposals, and fail closed on schema/resource/latency
  conflicts; semantic safe defaults remain available for underspecified
  low-consequence parameters;
- ordered TTS playback with bounded chunked generation through configured
  service workers;
- startup-primed English/Chinese fast-first acknowledgement audio cached as
  ignored local WAV/PCM, with a 750 ms adaptive hedge that suppresses the cue
  when the final response is ready first and cancels queued cues before playback;
- TTS Stage 6 performance instrumentation: explicit DAC codec-device resolution,
  worker-reported runtime device inspection, synchronized model-generation and
  codec-decode timing, PCM/queue/IPC/real-time-factor metrics, a rolling health
  summary, token-budget exhaustion detection, and a repeatable no-playback
  benchmark; the RTX 4090 Laptop profile keeps a 4096-token per-chunk context
  after live 2048-token evidence produced partial sentences, while FP16 remains
  the quality-preserving default until retained benchmark and listening evidence
  justify quantization;
- Soridormi task-agent contract loading, structured task submission,
  idempotent `client_task_ref` generation, task-event monitoring, and
  fail-closed handling for task refusal, failure, timeout, and cancellation
  with deterministic blocked-subsystem reporting, trace outcome summaries, and
  trace-only report fallbacks;
- native `chromie.task_graph.execute` Skill Runtime dispatch to the Agent
  planning executor, gated by `AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION`, with
  failed graph traces suppressing completion speech.
- no-motion task-agent bridge acceptance that requires
  `task_api_no_motion=true` before preview/submit and monitors terminal
  `soridormi.task.events`.

The M13 text interaction scope is closed. Linux RTX 5090 GPU smoke passed
21/21; clean seven-case synthetic and PipeWire virtual-mic bundles passed; and
text-to-MuJoCo evidence `20260617T081411Z` passed at Chromie revision `857c15f`
with ordered walk, nod, and turn execution in MuJoCo plus safe idle. Physical
real-microphone/speaker evidence remains open only as a separate human
voice-device release-support track. Automated acoustic generated-speech
evidence `20260704T114654Z` also passed all seven cases at Chromie revision
`842a334`, which supports the narrowed `0.0.1` generated-speech and
Soridormi MuJoCo-executor claim but not a human voice-device claim. The
robust-simulation and provider-readiness
milestone is complete with live no-motion MCP conformance, three-profile
parity, and 16/16 Soridormi-owned fault-injection scenarios.

The temporary `demo-sim-2026-06-27` tag was withdrawn on 2026-06-27 before
publication because the paired repositories needed a documentation/code
consistency audit. Do not publish or recreate that demo tag. The intended
replacement tag is `0.0.1`, after the Chromie and Soridormi validation
gates pass from the intended revisions.

## Next sequence

1. Exercise the authoritative path with retained live-text and MuJoCo
   multi-goal cases. Confirm Goal Association, Fast/Deep Planning, Response
   Composition, atomic Goal-state application, trusted execution, completion,
   Soridormi `sim` mode, and safe idle from the exact recorded Chromie source,
   manifest, clean declared paired Soridormi checkout, and a matching
   endpoint-reported Soridormi revision. Pass the declared paired checkout with
   `--soridormi-repo ../soridormi`; the runner still does not obtain the
   endpoint executing revision, so do not relabel its diagnostic output or
   reuse the historical M13 bundle as evidence for this path. The immediate
   resume action is to add and verify those source-binding guarantees from a
   clean paired checkout; the functional simulator matrix already passes at
   diagnostic Level C.
2. Keep the single-authority boundary fail closed: the common safe base owns
   `chat`, the maintained Soridormi launcher widens ownership to
   `chat,robot_action`, exact Router actions remain adapter-only, and the legacy
   CapabilityAgent planner may run only with both service gates and a fresh
   authoritative emergency claim matching the request turn.
3. Verify evidence and release provenance before any candidate packaging:
   cognitive summaries must record the current revisions and an applied,
   completed, safe-idle result; voice/release evidence must match source
   revision, `VERSION`, the capability manifest, and compatibility declaration.
   Bind the running Chromie service images and loaded models to that revision,
   and replace mutable release image references before publication.
4. Continue the general ability acceptance reconstruction described in
   [docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md](docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md):
   the first manifest/runner slice is implemented, and the next work is better
   live-runner diagnostics, root-cause classification, broader live text
   sampling, and voice-evidence integration without turning one reported
   sentence into a special-case patch.
5. Continue the Developer Usability Tools phase described in
   [docs/DEVELOPER_USABILITY_TOOLS.md](docs/DEVELOPER_USABILITY_TOOLS.md):
   PR0-PR6 are implemented; next harden retained trace examples from real
   bundles and keep `trace explain` deferred until causal semantics are stable.
6. Use [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md) as the trace-viewer
   contract; avoid explanations that obscure session, interaction, TaskGraph,
   Skill Runtime, Soridormi, TTS, and fallback semantics.
7. Treat Soridormi's high-level task and skill surface as declared for the
   current no-motion contract: bounded locomotion, attention, gesture,
   sequence, stop, safe-idle, and planning-hold task types are present in the
   authoritative manifest; navigation, approach, and delivery remain
   future-blocked structured refusals.
8. Keep the Chromie/Soridormi task-agent boundary aligned with Soridormi's
   authoritative manifest. Use structured task goals for rich embodied requests
   and keep concrete named skills for explicit bounded body commands. Preserve
   Soridormi refusal metadata when reporting unsupported embodied tasks.
9. Add Chromie routing and TaskGraph acceptance for Soridormi-declared task
   types only. Missing navigation, approach, gaze, gesture, recovery, or
   manipulation goals must remain structured refusals or clarifications rather
   than velocity recipes.
10. Keep Qwen/small-model routing advisory. Add or revise routing only with
   deterministic-control bypass, catalog constraints, confidence fallback,
   schema validation, Skill Runtime authorization, and Soridormi provider
   refusal/event checks.
11. Select one reference-robot candidate and complete the identity,
   independent emergency-stop, software, network, and workspace sections of
   `docs/ROBOT_COMMISSIONING.md`. Record it with the versioned
   `commissioning/reference_robot_candidate.schema.json` contract and keep the
   real manifest under ignored `.chromie/commissioning/`.
12. Keep all physical-motion gates off while validating no-motion health,
   calibration artifact ownership, stop/recovery procedures, and operator
   responsibilities.
13. If the next supported release claims real microphone/speaker voice-device
    operation, run the full seven-case `supervised` matrix on the reference host,
    review audible output and MuJoCo safe-idle/recovery behavior, verify the
    bundle with `--require-clean`, then clear the compatibility blocker.
14. Before publishing `0.0.1`, bind the running Chromie images/models and the
    Soridormi endpoint-reported source to the candidate revisions, replace
    mutable image references, rerun the Chromie documentation/test/scenario
    gates, rerun the Soridormi task-agent and locomotion-readiness gates, and
    keep the tag claim limited to generated-speech and Soridormi
    MuJoCo-executor evidence.
15. For TTS selection work, keep OuteTTS as the release-locked baseline and add
    candidate services only behind the versioned provider contract. Run
    `python scripts/tts_provider_ab.py --check`, then compare at least two
    endpoints with the same committed matrix. Do not change the default until
    target resource evidence, interruption recovery, blinded listening,
    license review, model locks, rollback, and release support all pass.

Do not start physical motion until the first reference robot satisfies the
commissioning checklist and Soridormi has retained simulator/physical evidence
for the exact bounded motion path. Do not train a Soridormi motion-control
model until the task semantics, target body or simulator, calibration,
telemetry, safety envelopes, and task-level acceptance metrics exist.

## Verification baseline

```text
Current 2026-07-21 full refresh:
./scripts/run_tests.sh passed: 1106 primary tests plus 20 legacy Agent tests
python scripts/check_docs.py passed: 78 Markdown files
python scripts/scenario_runner.py --no-write passed: 381/381
general ability Level A passed: 52/52
python scripts/semantic_authority_audit.py --check passed
live-text simulator execution passed 10/10, including 4/4 final-source
daily-life Fast cases and the exact three-step numeric compound through visible
Deep recovery; all effectful cases completed and every case ended safe idle.
The daily-life median was 40.321 seconds and misses the 15.46-second target.
The output remains diagnostic rather than source-bound Target validation
because both checkouts were dirty and endpoint Soridormi revision identity was
absent.

Historical focused refresh after f4bbb2f:
python scripts/check_docs.py passed
python -m unittest tests.test_robot_candidate_verifier passed: 12 tests
python scripts/test_matrix.py taskgraph passed: 48 tests
python scripts/test_matrix.py soridormi passed: 56 tests
python -m unittest tests.test_soridormi_acceptance passed: 16 tests
Local Soridormi dry-run MCP --task-agent-bridge acceptance passed:
  graph=soridormi-task-agent-acceptance-115cc864fd04
  backend=local_tool_dry_run, no_motion=true, safe_idle=true
  nodes=capabilities, preview, submit, events
Focused interaction/catalog task-agent tests passed: 29 tests
Focused host Skill Runtime graph dispatch tests passed: 59 tests
Widened host/task-agent focused bundle passed: 95 tests, with 2
dependency-light local skips for `aiohttp` client coverage

Historical 2026-07-14 automated regression gate:
python scripts/check_docs.py passed
926 unittest cases and 20 legacy Agent tests passed with
`./scripts/run_tests.sh`
381/381 adapter, Router, Router-dialogue, interaction, dialogue, and cognitive-runtime scenarios
passed with `python scripts/scenario_runner.py --no-write`
50/50 general-ability Level A representative probes passed, including 8/8
daily-life multi-goal coordination cases
That checkpoint covered English and Chinese walking, stale weather intent,
repeated walking after weather, compound nod/blink recovery, exact capability
grounding, confirmation, forbidden fallback speech, bounded VAD segments,
short replies, CJK TTS chunking, codec/timing instrumentation, and the first
multi-goal cognitive scenarios. It predates the current PR8 authority boundary
and is retained only as historical Level A evidence.

At the current resume point, complete-goal semantics belong to the unified
Fast/Deep pipeline. Unresolved effectful Router output preserves the original
utterance for that planner; it does not normally invoke CapabilityAgent.
Standalone PR2-PR6 observers are off. The old planner may run only as an
explicit emergency path with both service gates and a non-empty matching-turn
authority claim. The claim is internal routing metadata, not authentication or
a consumed replay nonce. Evidence and release gates now require exact source/version
provenance. These implementation changes still need the canonical automated
gate and retained live-text/MuJoCo rerun before a target or release claim.

Historical full Level A baseline:
640 unittest cases and 20 legacy Agent tests passed on 2026-07-04 with
`./scripts/run_tests.sh`. The behavior scenario runner also passed 344/344
Router, interaction, and dialogue scenario files with `--no-write`.
```

The focused refresh above is not target evidence and does not replace the full
Level A gate. Retained target-host evidence is listed in `docs/STATUS.md`.

## Useful commands

```bash
./scripts/run_tests.sh
python scripts/semantic_authority_audit.py --check
python scripts/cognitive_runtime_acceptance.py --mode check
python scripts/cognitive_runtime_acceptance.py --mode level-a
python scripts/general_ability_acceptance.py --mode check --no-write
python scripts/general_ability_acceptance.py --mode level-a --no-write
./scripts/show_profile.sh
./scripts/start_services.sh
./scripts/start_orchestrator.sh
python scripts/voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
python scripts/voice_acceptance.py --preflight-only \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi --start-services
python scripts/provider_fault_matrix.py
python scripts/provider_conformance.py
python scripts/verify_provider_readiness.py preflight
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json --task-agent-bridge
python scripts/verify_robot_candidate.py \
  commissioning/reference_robot_candidate.example.json --allow-draft
python scripts/verify_robot_candidate.py \
  .chromie/commissioning/reference_robot_candidate.json \
  --evidence-root .chromie/commissioning \
  --verify-evidence-files \
  --write-report .chromie/commissioning/candidate-verification.json
```

Live commands and recovery procedures are maintained in
[CHROMIE_RUNBOOK.md](CHROMIE_RUNBOOK.md).
First-reference-robot selection requirements are maintained in
[docs/ROBOT_COMMISSIONING.md](docs/ROBOT_COMMISSIONING.md).

## Do not regress

- Keep realtime audio and trusted Skill Runtime coordination in the Orchestrator.
- Keep embodied execution and hardware safety in Soridormi.
- Keep operational controls deterministic.
- Keep small-model routing advisory; never let Qwen or any model become the
  only authority for route, skill, task, safety, or physical execution.
- Keep physical work default-off and sequential.
- Do not expose low-level robot controls to model-facing contracts.
- Do not report automated or dry-run output as target evidence.
- Do not publish `0.0.1` or remove release blockers without retained
  evidence for the exact supported scope.


## Historical staged cognitive checkpoints

The PR1-PR6 notes below record their state when each slice landed. Their
`report_only` statements are historical and are superseded by the unified PR8
runtime described in the resume point above.

Goal-driven cognitive architecture PR1 checkpoint:
- shared GoalAssociation, GoalSet, GoalVersionRef, and ActiveGoalSnapshot contracts added
- stable replay-safe goal operation IDs added
- current TaskContextSnapshot maps to a bounded goal-first compatibility projection
- ConversationStateManager exposes read-only active_goal_snapshots without changing routing or execution
- focused goal/semantic continuity tests passed: 18


Goal-driven cognitive architecture PR2 checkpoint:
- advisory GoalAssociationResolution contract added
- dedicated `/goal-association` Agent endpoint added
- continuity-before-creation prompt receives bounded active goals and recent dialogue
- one turn may update existing goals and create multiple independent new goals
- materially ambiguous references produce natural clarification without exposing goal IDs
- Orchestrator `.env.common` integration is background `report_only`; no runtime state mutation or execution behavior change
- focused Goal Association and PR1 contract tests passed


## Goal-driven architecture PR3 checkpoint

PR3 adds the shared CanonicalPlan contract and a report-only Fast Planner. Complete high-confidence chat or common-capability coverage may be represented as a canonical plan; partial, uncertain, low-confidence, unavailable, or non-common coverage is converted to a zero-step escalation. Runtime routing and execution remain unchanged.


## Goal-driven architecture PR4 checkpoint

PR4 adds an advisory full-catalog Deep Planner using the shared `CanonicalPlan` contract. Fast Planner escalation is one-way; Deep Planner never returns to Fast Planner. Deterministic validation may provide structured feedback for one bounded same-tier revision. The Orchestrator integration remains report-only and does not alter routing, commitment, or execution.


## PR5 Goal Satisfaction checkpoint

Canonical plans now carry structured parameter-resolution strategies and a goal-satisfaction assessment. The model owns semantic importance and default selection; deterministic validation only checks blocking gaps, schema validity, capability availability, and configured satisfaction thresholds. Runtime routing and execution remain unchanged in report-only mode.


## PR6 Response Composition checkpoint

Terminal Fast or Deep canonical plans can now be composed into a fingerprint-bound `CoordinatedResponsePlan` containing goal-scoped `ResponsePlan` stages and an optional auxiliary `SocialAttentionPlan`. The response composer cannot mutate task steps, pre-execution speech cannot claim completion, every canonical goal must be covered, and optional attention is dropped on target, schema, confirmation, or resource-conflict failure. Host integration is report-only and leaves the production interaction path unchanged.

## Current PR7-PR8 runtime checkpoint

PR7 unified Goal Association, Fast Planning, terminal Deep Planning, bounded
trusted-validator replan, Response Composition, trusted adaptation, and atomic
Goal-state application behind `off`, `report_only`, and lane-gated `apply`.
PR8 established one semantic authority for applied lanes, made exact Router
actions adapter-only, constrained Goal Association with the exact model-facing
schema, and retained CapabilityAgent planning only as an emergency path behind
both service gates and a non-empty authoritative claim matching the request turn.

The July 17 model-contract repair makes Goal Association state-specific for the
zero-active-goal case, keeps planner output flat and exact, keys every
model-facing outcome by its authoritative goal, interprets satisfaction
prospectively, and keeps plan identity/tier/order/metadata host-owned. Response
Composer has a separate exact DTO and host-owned envelope. `chromie.speak` is
not a planner-executable capability; conversational goals flow through
`respond` outcomes and Response Composer. Each model stage gets at most one
same-stage/schema repair. The general-ability wrapper also forwards
`--soridormi-repo` to record the declared paired checkout.

The required automated suite, documentation governance check, and daily-life
Level A class passed at the recorded implementation checkpoint. Exact current
counts must be taken from the latest command output rather than this document. A diagnostic execute run progressed through three of four
daily-life cases before the final mixed case exposed the now-fixed boundaries. A fresh
post-fix localhost rerun remains pending because the execution platform denied
command approval. That session limitation is not a product or release blocker,
and no Target validation or Release readiness is claimed.

The common safe base enables structured interaction and authoritative `chat`
apply without Soridormi. The maintained Soridormi launcher enables that
provider and widens authority to `chat,robot_action`. Both fail closed after
ownership acquisition. Level A coverage exists; retained live-text and MuJoCo
target evidence for this path remains open.
