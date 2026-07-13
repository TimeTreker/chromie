# Development Checkpoint

**Current release-prep base:** `0.0.1`
**Soridormi capability snapshot:** generated from the paired Soridormi checkout; see `capabilities/soridormi.json` metadata for provenance
**Status refresh date:** 2026-07-12
**Current focus:** Freeze `0.0.1` through the Chromie/Soridormi boundary with
Soridormi using MuJoCo `sim` execution; physical pilot preparation and human
voice-device validation remain separate tracks

This file is a short resume marker, not a second status or roadmap. Use
[Status](docs/STATUS.md) for capability claims and [Roadmap](ROADMAP.md) for
milestone intent.

## Resume point

The `0.0.1` release implementation is present:

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

1. Continue the semantic task-continuity implementation described in
   [docs/SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md](docs/SEMANTIC_TASK_CONTINUITY_AND_SITUATIONAL_PLANNING.md):
   the shared contracts, host-applied versioned operations, active-task prompt
   projection, dedicated staged continuity endpoint, capability information-gap
   handling, immediate speech-claim validation, and non-blocking report-only
   degradation are implemented; next collect retained report-only live-text
   evidence, add full multi-goal response composition and
   repair for rejected claims, then add generalized observation planning.
2. Continue the general ability acceptance reconstruction described in
   [docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md](docs/GENERAL_ABILITY_TEST_RECONSTRUCTION.md):
   the first manifest/runner slice is implemented, and the next work is better
   live-runner diagnostics, root-cause classification, broader live text
   sampling, and voice-evidence integration without turning one reported
   sentence into a special-case patch.
3. Continue the Developer Usability Tools phase described in
   [docs/DEVELOPER_USABILITY_TOOLS.md](docs/DEVELOPER_USABILITY_TOOLS.md):
   PR0-PR6 are implemented; next harden retained trace examples from real
   bundles and keep `trace explain` deferred until causal semantics are stable.
4. Use [docs/TRACE_SCHEMA.md](docs/TRACE_SCHEMA.md) as the trace-viewer
   contract; avoid explanations that obscure session, interaction, TaskGraph,
   Skill Runtime, Soridormi, TTS, and fallback semantics.
5. Treat Soridormi's high-level task and skill surface as declared for the
   current no-motion contract: bounded locomotion, attention, gesture,
   sequence, stop, safe-idle, and planning-hold task types are present in the
   authoritative manifest; navigation, approach, and delivery remain
   future-blocked structured refusals.
6. Keep the Chromie/Soridormi task-agent boundary aligned with Soridormi's
   authoritative manifest. Use structured task goals for rich embodied requests
   and keep concrete named skills for explicit bounded body commands. Preserve
   Soridormi refusal metadata when reporting unsupported embodied tasks.
7. Add Chromie routing and TaskGraph acceptance for Soridormi-declared task
   types only. Missing navigation, approach, gaze, gesture, recovery, or
   manipulation goals must remain structured refusals or clarifications rather
   than velocity recipes.
8. Keep Qwen/small-model routing advisory. Add or revise routing only with
   deterministic-control bypass, catalog constraints, confidence fallback,
   schema validation, Skill Runtime authorization, and Soridormi provider
   refusal/event checks.
9. Select one reference-robot candidate and complete the identity,
   independent emergency-stop, software, network, and workspace sections of
   `docs/ROBOT_COMMISSIONING.md`. Record it with the versioned
   `commissioning/reference_robot_candidate.schema.json` contract and keep the
   real manifest under ignored `.chromie/commissioning/`.
10. Keep all physical-motion gates off while validating no-motion health,
   calibration artifact ownership, stop/recovery procedures, and operator
   responsibilities.
11. If the next supported release claims real microphone/speaker voice-device
    operation, run the full seven-case `supervised` matrix on the reference host,
    review audible output and MuJoCo safe-idle/recovery behavior, verify the
    bundle with `--require-clean`, then clear the compatibility blocker.
12. Before publishing `0.0.1`, record the paired Chromie and Soridormi
    revisions, rerun the Chromie documentation/test/scenario gates, rerun the
    Soridormi task-agent and locomotion-readiness gates, and keep the tag claim
    limited to generated-speech and Soridormi MuJoCo-executor evidence.

Do not start physical motion until the first reference robot satisfies the
commissioning checklist and Soridormi has retained simulator/physical evidence
for the exact bounded motion path. Do not train a Soridormi motion-control
model until the task semantics, target body or simulator, calibration,
telemetry, safety envelopes, and task-level acceptance metrics exist.

## Verification baseline

```text
Focused refresh after f4bbb2f:
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

Current 2026-07-12 automated regression gate:
python scripts/check_docs.py passed
834 current unittest cases and 20 legacy Agent tests passed with
`./scripts/run_tests.sh`
369/369 adapter, Router, Router-dialogue, interaction, and dialogue scenarios
passed with `python scripts/scenario_runner.py --no-write`
42/42 general-ability Level A representative probes passed
The current reliability scenarios include English and Chinese walking requests,
a forced stale weather intent, repeated walking after a weather turn, a Chinese
nod-and-blink compound request misclassified as generic chat, exact capability
grounding, confirmation, final Agent skill output, and forbidden
weather/fallback speech checks. Task-continuity report-only work is now
non-blocking, Agent disconnects fail closed for effectful routes, and long CJK
responses use smaller TTS chunks. The prompt-facing self model now binds first-person speech, perception, action, and body ownership to Chromie while exposing language models as internal components and runtime capabilities as evidence. Its social presentation foregrounds Chromie's name and natural personality rather than volunteering system category, embodiment category, age labels, or internal architecture. Unresolved effectful Router outputs now hand the original utterance to CapabilityAgent semantic planning instead of ending in a generic missing-ability clarification. Identity and capability inquiries are handled by LLM semantics rather
than question-specific branches, fixed replies, or normal-language regexes.
Compound embodied requests are now reconstructed and planned by the Capability
Agent as complete semantic outcomes. The model decides whether an exact plan,
safe adjustment, alternative plan, clarification, or unsupported result is
appropriate from capability/provider evidence. Missing parameter resolution is
also model-driven: low-consequence reversible fields may receive an explicit or
conservative schema-bounded default, while material fields become specific
structured questions retained on the original task. Semantic capability-planner
handoffs are not re-delegated to generic DeepThinking solely because the quick
Router reported zero confidence; deterministic code only validates
the full structured plan, commits all validated steps atomically, binds material
alternatives to confirmation, and prevents partial or unconfirmed degraded plans
from executing. Legacy normal-language capability fast-path parsers were removed. Stage 6.6
retains the observed compound walk-and-blink interaction as multi-turn replay
evidence. Unstructured model clarification is reviewed semantically against the
complete capability surface before any user-facing question is spoken; internal
schema placeholders are never used as dialogue. Alternative plans remain
`awaiting_confirmation`, their structured gaps survive follow-up turns, and no
partial skill can leak into execution. The host force-closes and discards VAD
segments that remain open for more than 20 seconds, while valid high-energy short
replies from 450 ms remain eligible for ASR.
TTS unit coverage now also verifies explicit
codec-device resolution, detailed stage timing, rolling performance summaries,
benchmark aggregation, and restartable-worker startup metadata. This is
automated evidence only; no Stage 6 live benchmark or listening result is
retained yet.

Historical full Level A baseline:
640 current unittest cases and 20 legacy Agent tests passed on 2026-07-04 with
`./scripts/run_tests.sh`. The behavior scenario runner also passed 344/344
Router, interaction, and dialogue scenario files with `--no-write`.
```

The focused refresh above is not target evidence and does not replace the full
Level A gate. Retained target-host evidence is listed in `docs/STATUS.md`.

## Useful commands

```bash
./scripts/run_tests.sh
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


Goal-driven cognitive architecture PR1 checkpoint:
- shared GoalAssociation, GoalSet, GoalVersionRef, and ActiveGoalSnapshot contracts added
- stable replay-safe goal operation IDs added
- current TaskContextSnapshot maps to a bounded goal-first compatibility projection
- ConversationStateManager exposes read-only active_goal_snapshots without changing routing or execution
- focused goal/semantic continuity tests passed: 18
