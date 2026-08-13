# Acceptance and Evidence

This document centralizes validation that was previously scattered across
milestones and component notes.

## Evidence levels

| Level | Environment | What it proves |
|---|---|---|
| A | GPU-free automated tests | Contracts, policy, scheduling, fallback, and deterministic behavior. |
| B | Deployed local services | Container health, HTTP/WebSocket interfaces, model presence, and control-plane round trips. |
| C | Live simulator / MCP | Cross-project capability compatibility, named-skill execution, cancellation, and safe idle recovery. |
| D | Target GPU/audio/hardware | Real latency, device behavior, hardware safety, recovery, and release supportability. |

A higher level does not replace lower-level regression tests.

Chromie's core embodied acceptance target is a qualified simulator provider.
The cognitive and interaction layers must not know whether Soridormi's backend
is MuJoCo or a physical body. Level D physical-robot evidence is therefore an
optional provider/deployment qualification, not a prerequisite for core Chromie
completion. Physical audio remains valid direct evidence for the host voice
device path and is independent of robot embodiment.

The active Gateway/Core qualification procedure is [Cognitive Gateway/Core Source-Bound Qualification](COGNITIVE_GATEWAY_CORE_QUALIFICATION.md).

## Current evidence summary

| Area | A | B | C | D |
|---|:---:|:---:|:---:|:---:|
| Canonical local gate | Repository policy, test ownership, Ruff, Mypy, documentation, and the complete primary plus legacy Agent suites pass from the documented setup; quote the exact output of a fresh `./scripts/run_tests.sh` run rather than a copied count | Not applicable | Not applicable | Not applicable |
| Core voice-to-embodied path | Full speech/control/runtime acceptance tooling and exact evidence contracts are implemented | Retained synthetic and virtual-microphone runs completed VAD, ASR, cognition, TTS/playback, and trusted dispatch; clean `90aa72a` validates the Goal-driven generated-voice path | Clean paired Chromie `a36444b` / Soridormi `fa8080d2` completed Goal-driven compound MuJoCo execution, cancellation, reconciliation, and safe idle | The host voice-device chain separately passed one supervised physical microphone-to-audible-speaker turn; physical robot deployment is optional and not needed to complete this row |
| Narrow current-revision live voice loop | Strict profile and focused rejection/regression tests pass | Clean `90aa72a` rebuilt comprehensive profile passed all mechanical voice/GPU checks with one independent-review skip; merged `a36444b` paired services remained healthy with clean logs | Not applicable | Target validated for one supervised English physical microphone-to-audible-response turn in `20260809T122818Z`; broader accuracy, latency, and release claims remain open |
| Goal Interpretation/Agent contracts | Yes | RTX smoke passed | Not required | Physical audio review open |
| Cognitive Gateway/Core single authority | Five-module, admitted-envelope, identity, and verifier tests pass | Clean rebuilt comprehensive model distribution passed its mechanical matrix; the independent semantic reviewer remains an explicit skip | Clean merged `a36444b` paired proof completed exact compound planning/execution and deterministic provider-start cancellation against Soridormi `fa8080d2` | Not claimed |
| Interaction contracts and Trusted Capability Runtime | Yes | Text path | Clean merged-revision exact arguments, ordered execution, Goal reconciliation, cancellation, and safe-idle recovery passed | Physical audio open separately |
| TaskGraph read/planning execution | Yes | Endpoint tooling | Soridormi acceptance | Target retention open |
| Guarded cancellation and emergency fallback | Yes | Acceptance tooling | Runtime-backed path available | Supervised hardware evidence open |
| ASR/TTS GPU use | TTS provider contract, transcript-plus-acoustic validated Oute speaker creation, candidate adapters, and common A/B matrix; ASR/TTS component coverage remains limited | The `e3d57ff` diagnostic retained both Ollama models on the RTX 5090, non-empty TTS PCM, and 19/19 GPU-smoke passes; this is generated/service evidence, not physical listening | Not applicable | One supervised EDIFIER H230P input/output turn passed exact ASR and audible delivery; comparative shared-resource and broader physical-listening evidence remain open |
| Audio devices and barge-in | Startup validation, runtime OS-default reselection, explicit pinning, input-boundary reset, output rollover, reversible ducking, order-aware echo matching, and cancellation-authority contracts pass | Clean exact-revision synthetic `issue-5-94718ab-clean` passed echo 6/6 and external barge-in 7/7 with 0.0 ms duck and 8.3 ms confirmed silence | Can pair with sim | The single-turn EDIFIER H230P physical input/output chain is target validated; physical acoustic echo, barge-in, audible latency, and live hot-plug review remain open |

Retained reference-host evidence from June 14 and June 17, 2026:

| Evidence ID | Revision | Result | Scope |
|---|---|---|---|
| GPU `20260614T130944Z` | `280c36a` | 21 passed, 0 failed | RTX 5090 service/GPU smoke, Ollama GPU placement, ASR/TTS health, generated PCM |
| Synthetic voice pipeline `20260614T132934Z` | `f0e22ba` | 7/7 passed | Synthetic framed PCM through VAD, ASR, the former Router revision, Agent, Skill Runtime, TTS, and MuJoCo |
| Virtual-microphone voice pipeline `20260614T133155Z` | `f0e22ba` | 7/7 passed | PipeWire virtual-microphone capture through the same interaction and MuJoCo path |
| Synthetic voice pipeline `20260617T075825Z` | `4604a03` | 7/7 passed | Clean synthetic framed PCM through VAD, ASR, the former Router revision, Agent live Soridormi catalog, host confirmation, Skill Runtime, TTS, and MuJoCo |
| Text-MuJoCo `20260617T081411Z` | `857c15f` | passed | Direct text input through the former Router revision and Agent `/interaction`, host Skill Runtime, live Soridormi MCP, ordered walk/nod/turn execution, and safe-idle status |

### Post-merge comprehensive diagnostic

On 2026-08-07, clean merged revision `e3d57ff` ran
`scripts/qualification/run_comprehensive_test.sh --strict-exit --capture auto
--languages zh,en --stop-services`. The retained bundle under
`.chromie/comprehensive/20260807T070706Z` reported 40 passes, 8 failures, and one
skip. Missing pinned host test dependencies explained the source, benchmark,
and scenario-command failures. The live logs also exposed genuine delivered-
speech ledger, stale event-contract, Goal-association, memory-repair, and
safe-read composition defects; those are recorded with their earliest
responsible boundaries in [Current Status](STATUS.md). The semantic multi-model
review was skipped because reviewers were not configured. This diagnostic is
neither a passing full profile nor physical/release evidence.

The first post-audit dirty replay rebuilt the Agent and proved that ordinary
final speech now reaches the delivered-turn ledger and acoustic capture. It
also reproduced a session-memory model that repeated invalid durable-only
fields, a weather segmentation that treated result delivery as a second Goal,
and nested-runner build/verification defects. These were treated as blockers;
the dirty replay is diagnostic only and cannot replace the required final clean
run.

Later focused dirty replays retained the repaired behavior without widening the
claim. `.chromie/acceptance/post-merge-audit-failclosed-20260807T085330Z`
delivered one memory response only after commit and one grounded recall.
`.chromie/acceptance/post-merge-audit-pure-safe-read-20260807T090032Z`
delivered exactly one `post_execution` weather response per turn, answered the
umbrella decision first, passed unique-delivery and acoustic checks, and measured
CER 0.046154. The workflow status remains `review` with
`semantic_review_pending=true`; manual audit found the retained speech natural
and evidence-consistent, but that inspection is not relabelled as an automated
external semantic pass. Both bundles were captured from a dirty source tree and
are diagnostic evidence only. Final closure still requires a clean committed
revision and the full comprehensive profile.

The first clean committed replay at `bed08e6`, retained under
`.chromie/comprehensive/20260807T091712Z`, reported 47 passes, one failure, one
skip, and no timeouts. All 12 idle and all 12 shared-GPU bilingual workflow
cases passed their mechanical, audio, completion, unique-delivery, and ordering
checks; the three retained synthetic voice cases also passed. The sole failure
was not a Runtime result: the comprehensive shell passed that three-case
diagnostic bundle to the separately owned full seven-case MuJoCo release
verifier. That verifier correctly rejected the absent body cases and live
Soridormi source binding. The collector no longer makes the inapplicable call;
the repaired committed replay remains required before closure. Semantic review
also remains pending rather than being inferred from the mechanical result.

The repaired clean committed replay at `d3f7b62`, retained under
`.chromie/comprehensive/20260807T094903Z`, reported 47 passes, zero failures,
zero timeouts, and one skipped external semantic review. All deterministic,
service, GPU, idle/shared-load workflow, and selected synthetic voice checks
passed mechanically. That result was still not accepted as closure: manual
inspection of the retained delivered text found one Chinese family-help turn
that fell back after valid primary speech was coupled to malformed optional
Social Attention, plus two umbrella follow-ups that still replayed weather
before the requested decision. These were semantic contract failures even
though transport and audio assertions passed, so they were not averaged into a
pass or hidden behind the pending external reviewer.

Dirty focused replay after the general fixes is retained only as diagnostic
evidence. `.chromie/acceptance/targeted-family-20260807c` delivered one natural
family-help response with one completed speech event, unique delivery, and CER
0.0. `.chromie/acceptance/targeted-semantic-20260807b` delivered the umbrella
decision first, followed by one grounded support clause, with unique delivery
and CER 0.068966. A forced deployed `/fast-plan` chat probe separately exercised
the new communication-review branch and revised evidence-first text to “是的，您
需要带伞。” before the supporting weather clause. An earlier family attempt in
the same targeted run hit a cold service connection reset and TTS startup
timeout; the warmed repeat, rather than that failed attempt, is the relevant
behavior diagnostic. None of these dirty probes replaces final clean,
revision-bound comprehensive evidence or external semantic adjudication.

Clean commit `258d0ec`, retained under
`.chromie/comprehensive/20260807T103838Z`, again reported 47 passes, zero
failures, zero timeouts, and one skipped external semantic review. All 24 idle
and shared-GPU workflow cases passed mechanical delivery, ordering, capture,
and transcription checks. Manual review accepted the repaired Chinese
family-help and umbrella-decision boundaries, but correctly withheld closure:
the shared-load English multi-part response invented that the user had “a busy
day tomorrow.” That unsupported personal circumstance is a semantic grounding
defect even though both requested Goals were completed. The clean bundle is
therefore retained as diagnostic evidence, not final closure evidence.

Dirty focused grounding replay is retained separately. The first attempt at
`.chromie/acceptance/targeted-grounding-20260807d` failed before connection
during cold service startup. The next attempt at
`.chromie/acceptance/targeted-grounding-20260807e` authored a grounded response
but the cold TTS worker missed the 20-second playback-start gate, so no speech
was delivered and the case failed mechanically. After explicit TTS warmup,
`.chromie/acceptance/targeted-grounding-20260807f` delivered both requested
Goals once and in order, used only the general benefit of getting enough rest,
did not invent a personal schedule or circumstance, and measured WER 0.044444.
This focused dirty evidence does not replace final clean revision binding.

Clean committed revision `90aa72a` ran the corrected comprehensive collector
under `.chromie/comprehensive/20260807T135248Z`. Its service log records a real
image build followed by force recreation; nested voice acceptance reused that
same stack. The run retained 46 passes, zero failures, zero timeouts, and one
skipped independent semantic-review check. Strict mode therefore returned
`incomplete`, and `release_qualified=false` remains correct. The archive is
`/home/chromie/Downloads/chromie-comprehensive-90aa72aa7549-20260807T135248Z.tar.gz`;
its SHA-256 is
`c2fafdf827b6bd42e253ce125b2549b97128cf11b48ebe2ac2baecbaea4ea45a`.

The retained current-revision matrix passed 403 deterministic behavior
scenarios, 19 GPU-smoke checks with zero failures, bilingual acoustic transport,
all 12 idle and all 12 shared-GPU workflow cases, and all selected synthetic
speech-only, barge-in, and follow-up cases. The barge-in case measured 0.0 ms
from VAD start to duck and 4.7 ms from confirmed speech to silence, retained the
independent output-only Gateway receipt, and proved that stale playback did not
resume. Warm median TTS first-audio time was 1.107 seconds idle and 1.227 seconds
under shared GPU load, with no generation-limit hits. The retained cold-start
distribution includes a roughly 40.2-second first generation and a later
14.0-second Chinese sample, so no release latency claim is made.

Manual review of all workflow outputs found no recurrence of the audit's hard
semantic blockers: family answers were direct, stable knowledge was correct,
session memory recalled blue, the weather correction switched location, the
umbrella response led with the recommendation, multipart responses stayed
grounded, and ordered stories were complete and unique. That inspection does
not substitute for or relabel the skipped external semantic adjudication.
Generated speech and acoustic loopback do not prove a physical microphone,
speaker, human pronunciation, or physical robot.

### Final clean-main Level C proof

After PRs #12 and #13 merged, the paired stack was rebuilt from clean Chromie
`a36444b6fe870afc4604fc79e2d2f92bcda254a5` and clean Soridormi
`fa8080d2a4a5e1c47a1c77a1748aa65e6dec4d83`. The retained runtime identity at
`.chromie/acceptance/post-merge-audit-final/a36444b/runtime-identity.json` is
complete and has SHA-256
`4d1ba0381e8ea10a6e581f572b6c960d097e001f2aa4ff442fa55a9c00902ec9`.
The evidence runner independently confirmed that the checkout, manifest,
running endpoint, and declared upstream all identify that Soridormi revision.

The natural-language compound scenario retained under
`.chromie/acceptance/post-merge-audit-final/a36444b/compound/mujoco` passed with
exact ordered `walk_velocity(vx_mps=0.2,duration_s=10)`,
`nod_yes(count=2)`, and `turn_in_place` steps. All provider requests completed,
all three Goals reconciled exactly, no internal planner language entered the
response, and pre/post status remained standing safe-idle with no active task.

The provider-start cancellation scenario under the adjacent
`cancellation/mujoco` directory passed with `ok=true` and no errors. It observed
the active `walk_velocity(vx_mps=0.2,duration_s=20)` provider request before
injecting `Stop.`. The production Gateway selected the deterministic
`current_interaction` reflex, dispatched it in 31.1 ms with zero provider or
dispatch failures, received `cancelled_current_interaction`, reconciled the Goal
as cancelled, suppressed stale completion speech, and verified safe idle with
no active task. The interrupt transaction took 59.6 ms end to end. These are
Level C simulator and trusted-runtime claims only.

Post-scenario health and a 15-minute, 1,000-line-per-source log review found all
paired endpoints ready and no fatal startup pattern in either launcher, ASR,
TTS, Agent, Ollama, or Soridormi Runtime MCP output. The JSON WebSocket health
probes generated no incomplete-handshake traceback. This closes the post-merge
audit's clean merged-revision Level C requirement. At that revision, physical
microphone, speaker, audible acoustic behavior, physical robot safety, real
vocal/media providers, publishable artifact provenance, independent semantic
adjudication, and release qualification remained open Level D or release
evidence tracks. The later supervised result below closes only its declared
single speech-only physical voice turn.

After the executable scenarios were aligned with the evidence-before-claim
contract, the complete source gate passed: 102 benchmark tests, 2,095 maintained
tests, 20 legacy Agent tests, and every repository-policy, ownership, Ruff, Mypy,
configuration, structure, and documentation check. The Level A general-ability
profile passed 66/66 across all ten ability classes. These results establish
automatic source behavior only; they do not replace clean revision-bound
service, audio, simulator, or hardware evidence.

The retained voice-pipeline automated bundles are historical evidence for their recorded
revisions and legacy semantic path; they are not current goal-driven validation.
They can be inspected by supplying their recorded revisions through the
verifier's `--expected-*` options. The verifier defaults to the current source
and therefore rejects them as release evidence for a newer revision. They report
they are not eligible for a human physical voice-device claim. The retained
Text-MuJoCo bundle closes the historical text interaction scope. It
intentionally skips microphone and ASR and therefore does not prove physical
audio-device quality.

## Proof-before-refactor live voice profile

With the canonical local gate restored, the active repository Issue is to retain
the smallest complete current-revision live loop before structural refactoring:

```text
physical microphone
→ ASR final utterance
→ Cognitive Gateway admission
→ Goal-driven chat handling
→ validated speech
→ TTS scheduling and audible playback
```

The existing runner already accepts:

```bash
python scripts/voice_acceptance.py \
  --mode supervised \
  --cases speech-only \
  --start-services
```

Before it starts services or creates an evidence bundle, the supervised
preflight checks the selected `CHROMIE_CONDA_ENV` (default
`Chromie`) against the repository's Python 3.11+ requirement. The Orchestrator
launcher repeats the same check before installing dependencies or warming
models. An incompatible environment is an operational blocker, not evidence;
select or create a conforming environment and rerun from a clean revision.
The runner owns one generated `speech` operator-mode environment for both the
service stack and host Orchestrator. This keeps the retained runtime profile,
running service fingerprint, effective host environment, and captured runtime
identity on the same configuration authority.

The default verifier still requires the full seven-case matrix, Soridormi
source binding, and both applied `chat` and `robot_action` lanes. The separate
`current-revision-live-voice` profile verifies the honest smaller claim:

```bash
python scripts/verify_voice_evidence.py \
  .chromie/acceptance/voice/<acceptance-id> \
  --profile current-revision-live-voice \
  --require-clean
```

It requires clean Chromie source, captured running runtime identity, generated
profile and effective models, immutable image IDs for Agent/LLM/ASR/TTS, real
microphone and output recordings, selected audio devices, `asr_final`, admitted
Gateway/Core processing bound to that identity, applied `chat`, zero executable
skills, correlated TTS playback completion, exact command/artifact digests, and
an operator audible-output verdict. It rejects synthetic input, critical model
failure, truncation, post-authority fallback, stale playback, dirty/mismatched
source, missing runtime identity, artifact tampering, or executable work. The
successful `chromie.speak` delivery result is part of validated speech, not an
executable body/tool skill; any other skill result still fails this profile.

A passing narrow profile supports only this claim: one reviewed
current-revision speech-only conversation completed through the physical audio
loop. It does not establish broad microphone accuracy, simulator behavior,
Soridormi execution, physical-robot support, or release readiness. The profile
is automatically verified; until a clean supervised bundle is retained, target
validation remains open.

On 2026-07-31, attempt `20260731T110834Z` ran from clean revision `e931af3`
with healthy services but no attached microphone. After an input device became
available, attempts `20260731T134457Z` and `20260731T134946Z` captured physical
VAD activity. The second retained ASR finals `I.` and `.`, neither containing
the required Moon meaning, so the runner correctly stopped before cognition or
an audible response. All three directories are diagnostic-only failures and do
not satisfy or weaken this profile.

On 2026-08-09, the supervised speech-only run
`.chromie/acceptance/voice/20260809T122818Z` passed against clean host revision
`f8d5eae61d8556dc2bae0404bc97726f60ceb0e1`. The EDIFIER H230P physical
microphone produced the exact ASR transcript “Tell me one short fact about the
moon.” for session `192dfb82`. The retained Core resolution applied `chat` with
one speech output and no executable capabilities; `chromie.speak`, both
playback parts, and the session completed. All six machine checks passed and the
supervising user recorded an audible `pass`. The strict
`current-revision-live-voice` verifier accepted 23 manifested artifacts with
zero errors and runtime identity SHA-256
`f06a9c798666a8f2da5235f13eefe38ed27a8b4b00cdd26b3c94992851e6b7e6`.
This is successful end-to-end target evidence for that physical microphone ->
ASR -> cognition -> TTS -> speaker turn; its narrow claim and exclusions remain
those defined above.

## Level A — automated suite

```bash
./scripts/run_tests.sh
```

This runs the documentation consistency checker, all current `unittest` cases
discovered under `tests/`, and the dependency-light legacy Agent tests. Report
the exact command output when making a claim; do not use a stale hardcoded test
count as evidence.

If the host Python environment is intentionally minimal, install the declared
host test dependency set while running the gate:

```bash
INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh
```

You can also run the same gate in the service dependency envelope:

```bash
./scripts/compose.sh run --rm --no-deps \
  -v "$PWD:/workspace" -w /workspace \
  chromie-agent ./scripts/run_tests.sh
```

For roadmap-aligned module and combination checks, use:

```bash
python scripts/test_matrix.py --list
python scripts/test_matrix.py goal-interpretation
python scripts/test_matrix.py behavior
python scripts/test_matrix.py general-ability
python scripts/test_matrix.py asr tts goal-interpretation
python scripts/test_matrix.py local-modules
python scripts/test_matrix.py voice-mujoco-sim
python scripts/tts_provider_ab.py --check
```

This runner is a Level A convenience layer over existing tests. It lets modules
be tested independently or in declared combinations, but it does not replace the
canonical `./scripts/run_tests.sh` gate and it does not create GPU, microphone,
MuJoCo, or hardware evidence.

`scripts/scenario_runner.py` remains as a low-level deterministic scenario
engine for fixture authoring and focused debugging. It is not the preferred
behavior-quality gate. New user-visible behavior claims should use the general
ability acceptance layer below so the report names the protected ability class
and evidence level.

The committed fixtures live under [`../scenarios/`](../scenarios/). Each file
contains one deterministic scenario and expectation set. The runner writes a
timestamped `summary.json` with pass/fail details and, when a baseline is
provided, lists regressions, improvements, new cases, and removed cases. These
reports are Level A automated evidence only; they do not prove live service,
GPU, microphone, speaker, simulator, or robot behavior.
Interaction fixtures may opt into host response preparation to assert
preflight, proposal-ledger, revision/supersede, and correction metadata without
executing live TTS, simulator, or hardware side effects.

For claim-oriented behavior coverage, run the general ability acceptance layer:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class deterministic_safety_controls
```

The manifest lives at
[`../scenarios/general_ability_acceptance.json`](../scenarios/general_ability_acceptance.json).
It groups representative scenario files by the general ability class they
protect: robust intent understanding, stable capability grounding, natural
uncertainty handling, composable action planning, truthful embodied speech,
tool/conversation lane discipline, deterministic safety controls, and evidence
claim discipline, plus multi-goal daily-life planning. The runner writes evidence summaries under
`.chromie/acceptance/general-ability/` unless `--no-write` is supplied.

A passing `--mode level-a` run is still Level A deterministic evidence only. It
does not prove live services, microphone/speaker behavior, simulator execution,
or physical robot behavior. When it fails, the retained summary marks
`root_cause_report_required=true`; the next patch must identify the earliest
wrong boundary before changing prompts or wording.

The live general-ability runner defaults to `--assertion-scope user-outcome`.
This scope evaluates stable observable behaviors, speech truthfulness, execution
receipts, final safety, and LLM-call integrity while retaining route and planner
path differences as diagnostics. Use `--assertion-scope full` only when the
internal path itself is the claim. See
[User-Outcome Acceptance Framework](USER_OUTCOME_ACCEPTANCE.md).

Any critical LLM timeout, input/output truncation, incomplete stream, or
incomplete structured output is a hard case failure even when a later fallback
produces a correct final action. Architecture-validation timeouts remain long so
qualification first answers whether the complete workflow can succeed.

Against deployed services, the same manifest can run live text probes:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

Use `--execute` only for supervised simulator runs. Live text preview checks the
Goal Interpretation, Agent, and Soridormi status/preflight boundary but does not execute
motion; live text execution can support a Level C simulator claim only when the
summary shows successful Trusted Capability Runtime execution and safe idle. Neither mode is
microphone, speaker, or physical hardware evidence.
`--soridormi-repo` records a declared paired checkout for diagnostic
provenance; it does not prove which source revision is executing behind the MCP
endpoint.

A live case may declare ordered `turns`. The runner reuses one Host conversation
state while giving every turn a fresh SID and artifact directory, so retained
Goals, tool evidence, and dialogue state reach the next turn exactly where the
live Runtime would expose them. Each turn and the episode rollup contain an
acceptance-only score, hard-gate failures, objective Goal/provenance/integrity
metrics, and the earliest suspect boundary. The score never overrides a hard
failure. Use `--only-case CASE_ID` for the originating defect, then run the full
ability class after the fix.

### Fast Planner multi-goal qualification

The repository implements the accepted
[Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md).
Its component-specific `multi_goal_daily_life` qualification uses
`--assertion-scope full` and must prove more than 4/4 user-outcome success. The simple retained matrix must terminate with
`planner_tier=fast`, omit Deep Planner invocation, contain no Fast
`structured_output_validation` diagnostic, preserve exact per-goal outcomes
and skill ownership, avoid premature physical-completion speech, and finish
Soridormi simulation in safe idle. Clean semantic-escalation scenarios must
show empty steps and outcomes plus a specific escalation reason without
contract repair. Technical Fast failures must remain visible even if Deep
Planner recovers the turn.

Target qualification retains at least three consecutive warm simulator runs
and compares cognitive-runtime latency with the July 17 diagnostic baseline.
The target is at least a 35 percent median reduction without weakening any
execution or evidence boundary.

The RTX 5090 and RTX 4090 Laptop hardware profiles currently use qualification
time budgets: 120 seconds per Agent cognitive stage, 150 seconds per host stage,
and 900 seconds for the complete cognitive pipeline. The live runner therefore
defaults to a 1200-second outer case timeout. Do not reduce these values while
validating LLM capability and end-to-end architecture; optimize latency only
after retaining successful warm-run evidence.

The reconstruction design and staged implementation plan are maintained in
[General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md).

To grow the scenario library, use the authoring helper:

```bash
python scripts/scenario_author.py new --suite goal_interpretation --id draft_case \
  --text "Hello Chromie."
python scripts/scenario_author.py edit --suite goal_interpretation --id draft_case
python scripts/scenario_author.py validate-all
python scripts/scenario_author.py prompt --suite interaction --count 20
```

The prompt command is for generating reviewed candidate JSON with an LLM; the
LLM is not used as the pass/fail judge during regression runs.

That restriction applies to the deterministic `scenarios/` regression runner:
scenario generation must not silently become its oracle. It does not prohibit
the separately owned hybrid benchmark method. A normalized benchmark with
`oracle_policy.mode=semantic_review` or `hybrid` may retain live module or
integration output and apply a versioned LLM or human judgment for declared
semantic dimensions. In that path there is no single fixed response truth; the
scenario declares an acceptable behavior region and the reviewer judges meaning
from the retained result and evidence. Deterministic schema, safety,
authorization, capability, execution-truth, provenance, and LLM-integrity
failures remain non-overridable.

For a model-role qualification such as Goal Association, build the cohort from
Chromie's actual Goal lifecycle, Vocal and Activity lanes, identity and body
truth, uncertainty rules, capabilities, and retained interaction context. Run
every candidate through the same explicit benchmark adapter, package the raw
report with `python -m benchmarks.review package`, retain reviewer identity and
rationale, and apply the review with `python -m benchmarks.review apply`.
Prefer blinded independent reviewers for model comparison. A single LLM session
may produce useful diagnostic evidence, but it must be reported as one-reviewer
evidence and cannot close independent semantic adjudication or release
qualification. The authoritative workflow and multi-model commands are in
[Chromie-specific semantic qualification workflow](CHROMIE_BENCHMARK_SUITE.md#chromie-specific-semantic-qualification-workflow).

The target organization, common case contract, distribution metrics, and staged
rollout are defined in the
[Chromie Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md) and its
[Benchmark Suite](CHROMIE_BENCHMARK_SUITE.md). Benchmark
failures must be fixed through general model, prompt, context, contract,
architecture, or provider improvements; they must not introduce phrase-specific
Host behavior rules.

## Model-assisted routing guardrails

The fast Goal Interpretation model is accepted only as an advisory semantic interpreter.
Level A routing evidence must continue to prove:

- deterministic stop, cancel, emergency, silence, and unusable-audio paths do
  not depend on model output;
- semantic ambient suppression is isolated to a structured addressedness and
  speech-act contract, requires inactive host engagement plus high confidence,
  cannot authorize effects, suppresses only explicitly ambient acts, and fails
  open to the original route on direct-question/request contradictions; one
  schema-constrained model repair may correct an internally contradictory
  `addressed=false` directed/unclear pair, but deterministic code must not
  invent the ambient label;
- the retained
  `goal_interpretation/inactive_direct_weather_question_false_addressedness` scenario
  replays the inactive host context, grounded weather-tool decision, and false
  high-confidence question review through the real Goal Interpretation recovery pipeline;
- model routes are bounded by capability-catalog candidates and schema
  finalization;
- low-confidence, ambiguous, unsupported, or unavailable routes clarify, refuse,
  ignore, or fall back safely;
- native InteractionRuntime and the host Trusted Capability Runtime re-resolve capabilities
  before execution;
- Soridormi task preview, refusal, events, cancellation, and safe-idle status
  remain authoritative for embodied goals.

See [Goal-Driven Cognitive Architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
and [Human-Like Interaction Contract](HUMAN_LIKE_INTERACTION_CONTRACT.md).

## Level B — deployed service checks

```bash
./scripts/start_services.sh
./scripts/compose.sh ps
curl -fsS http://127.0.0.1:8092/health
curl -fsS http://127.0.0.1:11434/api/tags
./scripts/verify_tts_gpu.sh
```

For a complete GPU smoke pass:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

This checks host/container GPU visibility, Compose health, Cognitive-Core-to-Agent
round trip, ASR/TTS WebSockets, Ollama generation, model GPU placement, and
optional non-empty TTS PCM generation. It does not evaluate microphone or
speaker quality.

### TTS provider verification and comparison

Level A verifies the framework-neutral provider schema, default CosyVoice
adapter, Oute/Qwen alternatives, streaming event rules, cancellation
propagation, reference binding, common matrix, and fail-closed inputs:

```bash
python -m unittest \
  tests.test_tts_provider_contract \
  tests.test_tts_provider_ab \
  tests.test_tts_candidate_providers \
  tests.test_tts_reference \
  tests.test_tts_benchmark \
  tests.test_fast_first_audio_cache
python scripts/tts_provider_ab.py --check
```

Validate the installed default voice before a deployed service check:

```bash
python scripts/tts_reference.py validate
./scripts/start_chromie.sh --no-orchestrator --keep-services
./scripts/verify_tts_gpu.sh
```

The default health response must report
`provider_id=fun-cosyvoice3-0.5b`, a ready worker, immutable runtime/model
revisions, the bound reference SHA, CUDA visibility, and one declared worker. A
no-playback warm synthesis must return nonempty PCM before the launcher opens the
microphone.

Run the pinned isolated CosyVoice/Qwen comparison with:

```bash
./scripts/run_tts_candidate_ab.sh
```

The committed matrix uses identical Mandarin, English, mixed-language,
interruption/recovery, six-turn dialogue, and concurrent requests. It retains
provider/model declarations, reference identity, WAVs, first-binary/total
latency, RTF, dialogue/concurrency status, and a listening-review template. The
workflow temporarily releases normal shared-GPU services, so it does not prove
sustained coexistence with ASR, Agent/Cognitive Core, and Ollama.

The repeated isolated results showed CosyVoice leading ordinary first-audio and
RTF while Qwen recovered faster after forced worker termination. Oute later
failed requested-text and Mandarin listening diagnostics despite valid acoustic
conditioning. These results justify the current default but do not replace a
Mandarin-focused blinded listening review or an approved interruption bound.

The fast-first cache additionally rejects overlong or ASR-mismatched cues. This
prevents known content leakage from entering playback; it does not prove natural
pronunciation.

## Level C — Soridormi contract and simulator

Probe the live MCP endpoint before execution. Prefer the Agent container so
the probe uses the same MCP SDK and dependency versions as the deployed Agent:

```bash
./scripts/build_runtime_env.sh
./scripts/compose.sh up -d chromie-agent
./scripts/compose.sh exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

`docker-compose.yml` maps `host.docker.internal` to the Linux host gateway for
`chromie-agent`. When Soridormi runs in the same Docker network, pass its
service hostname instead. A host-side probe remains available for development
after installing `agent/requirements.txt`.

The general probe verifies the complete manifest by default. Voice interaction
acceptance adds `--exclude-effect test_control` because its production
voice-to-simulator path does not depend on hidden fault-injection controls.
Provider-readiness evidence continues to require those controls separately.

Run safe status and zero-motion planning:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json
```

Require a ready runtime-backed simulator endpoint:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --runtime-preflight \
  --expected-backend runtime \
  --expected-mode sim
```

The older single-skill text acceptance command has been removed because it used
a fixture-like legacy Agent result and could be mistaken for acceptance
evidence. Use the general ability runner for behavior claims and
`interaction_text_mujoco_check.py` for retained text-to-simulator evidence.

The old standalone text skill sweep has been removed because it can overstate
coverage and has been observed to fail unclearly when live inventory or service
calls hang. Add representative live text probes to
[`../scenarios/general_ability_acceptance.json`](../scenarios/general_ability_acceptance.json)
instead.

For a deployed text-to-MuJoCo check that skips microphone and ASR while keeping
Goal Interpretation, the goal-driven runtime, the host Trusted Capability Runtime, live Soridormi
MCP, and optional real speaker playback, start Chromie with the Soridormi
manifest loaded and run:

```bash
python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --no-speaker
```

That command is the natural no-microphone rehearsal: Chromie infers the route,
speech, and skills from the text exactly as it would after ASR. Add
`--expect-*` flags only when you want a regression assertion after planning:

```bash
python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --expect-skill soridormi.walk_velocity \
  --expect-skill soridormi.nod_yes \
  --expect-skill soridormi.turn_in_place \
  --expect-arg 0:vx_mps=0.2 \
  --expect-arg 0:duration_s=10 \
  --expect-arg 1:count=2 \
  --expect-arg 2:yaw_radps=0.12
```

This runner defaults to the maintained goal-driven path; use
`--no-cognitive-runtime` only for an explicitly labelled compatibility run. It
writes `route.json`, `interaction_response.json`,
`execution.json`, status snapshots, session events, recordings when enabled,
and `summary.json` under `.chromie/acceptance/text-mujoco/<id>/`. The summary
records the Chromie checkout revision/version/clean state, Soridormi manifest,
the user-supplied declared paired checkout and its clean state, selected
semantic path, and apply lanes. `--soridormi-repo` alone does not prove which
source the MCP endpoint executes. When the live Soridormi status reports
`source_revision`, the runner records it; Level C target validation requires it
to match the clean paired checkout. It fails if
Trusted Capability Runtime execution fails, if the simulator does not return to safe idle,
or, when assertion flags are supplied, if the ordered Soridormi skills or
expected arguments do not match. Use `--no-speaker` for headless automation;
otherwise Chromie schedules TTS through the configured output device. The
runner uses a 120s per-Soridormi-skill diagnostic timeout by default; pass
`--skill-timeout-s 0` to use catalog/default timeouts unchanged. It prints
compact debug lines for route, staged task list, skills, speech count, and
errors before the JSON summary. The runner refuses non-`sim` Soridormi modes
unless `--allow-non-sim` is supplied under separate supervision.

### Vocal Goal/Planner Issue #1 closure

After committing the vocal semantic and canonical-gate patches, run the exact
retained closure workflow from a clean Chromie checkout with a clean paired
Soridormi checkout and the deployed Agent/TTS/Soridormi simulator services:

```bash
python scripts/vocal_issue_closure.py \
  --soridormi-repo ../soridormi
```

The runner executes `./scripts/run_tests.sh`, then checks the maintained paired
deployment. By default `--deployment-mode auto` reuses a ready stack or starts
the repository-owned headless stack with current images; `reuse` forbids
startup and `start` forces a clean lifecycle restart. It captures the running
image/model identity only after readiness, submits the original Chinese
walk/sing/blink turn through the maintained Goal-driven path, executes the body
members in Soridormi/MuJoCo, and then validates the retained evidence. Use
`--rebuild-no-cache` when cached images are not acceptable and
`--keep-deployment` only when the started stack must remain available after the
run. Closure requires exactly one typed
Vocal/singing Goal, at least two typed Activity/body Goals, parallel walking
and blinking requests with the preserved 15-second duration, an
`unavailable` or `refused` singing outcome with no executable step, completed
Soridormi results for the exact configured walk and blink capabilities, matching
clean Chromie/Soridormi revisions, and safe idle before and after execution.
Ordinary TTS, media playback, Social Attention, or a body result may not be
recorded as singing evidence.

A failed canonical gate stops before deployment startup; a failed deployment or
runtime-identity capture stops before the live request. The retained report
includes the exact subprocess error rather than only `capture failed` or
`summary missing`. The output lives under
`.chromie/acceptance/vocal-issue-1/<id>/` and includes canonical/live logs,
runtime identity, the underlying text-to-MuJoCo bundle,
`closure_summary.json`, and its SHA-256 sidecar. `issue_comment.md` is written
only after every closure condition passes; a failed run writes
`closure_failure.md` instead. A zero exit status makes Issue #1 eligible to
close for its declared Level A/C scope only. Add `--close-issue` to let an
authenticated GitHub CLI close `TimeTreker/chromie#1` after the evidence passes;
the runner refuses that mutation when `closure_eligible=false`. It does not
validate a singing provider, physical microphone/speaker quality, physical
robot behavior, or release readiness. `--skip-canonical-gate` is diagnostic-only
and can never produce closure-eligible evidence.

### Exact vocal-provider source qualification

Issue #6 source acceptance uses a fake provider so exact identity, mode
negotiation, cancellation, and evidence failure semantics can be tested without
making a singing or physical-audio claim:

```bash
python -m unittest \
  tests.test_vocal_provider_contract \
  tests.test_execution_lanes \
  tests.test_tts_provider_contract
python scripts/scenario_runner.py \
  --only cognitive_runtime/qualified_vocal_provider_exact_recitation
python scripts/general_ability_acceptance.py \
  --mode level-a \
  --ability-class stable_capability_grounding
./scripts/run_tests.sh
```

The focused scenario must preserve `chromie.vocal.perform`, the exact requested
mode, source Goal ownership, and `execution_lane=speaking` through Goal
Association, both Planner tiers, Response Composer, and Host materialization.
Provider tests must cover declaration evidence, unsupported-mode refusal before
backend invocation, silent-downgrade rejection, exact request cancellation, and
the final Trusted Capability Runtime/turn-closure evidence identity. Ordinary
TTS regression tests must remain passing.

This is Level A source evidence only. The existing clean walk/sing/blink Level C
profile remains the live default-provider proof: singing is unavailable with no
executable step while independent body work completes and safe idle holds. A
real mode may be marked target validated only after a clean current-revision run
retains that provider's immutable declaration, exact-mode completion, audible
delivery evidence, and the applicable automated or supervised target notes.

### Exact peer-media source qualification

Issue #7 source acceptance uses a qualified stateful fake provider; it does not
claim that the default deployment can play media or that a physical speaker was
heard:

```bash
python -m unittest tests.test_media_provider_contract
python scripts/scenario_runner.py \
  --only cognitive_runtime/qualified_media_walk_parallel \
  --only goal_interpretation/stop_media_output_scope
python scripts/general_ability_acceptance.py \
  --mode level-a \
  --ability-class stable_capability_grounding \
  --ability-class deterministic_safety_controls
./scripts/run_tests.sh
```

The provider suite must cover all seven exact public operations, supported-kind
rejection before backend invocation, persistent playback identity and bounded
progress, exact operation/state evidence, qualified catalog exposure without a
backend-name leak, explicit speech-over-media ducking, and distinct
stop-talking/media/all receipts. The mixed walk+media scenario must preserve two
Activity Goals and the exact Soridormi and `chromie.media.play` steps through
Goal Association, both Planner tiers, Response Composer, and Host
materialization. The stop-media scenario must take `media_output` with zero
model calls.

The highest safe live default-provider check is different: because no media
provider is configured, a current-revision deployed run must retain a typed
Activity/media Goal and an unavailable media outcome with zero media execution,
while ordinary TTS, vocal performance, and any independent body work retain
their own evidence. A real media operation may be marked target validated only
after its immutable provider declaration and current-revision runtime evidence
retain the exact operation, playback lifecycle/progress, mixer behavior where
applicable, cancellation receipt, and target notes. Text, fake-provider, or
simulator evidence must not be promoted to physical speaker evidence.

Use `--reject-internal-speech` when investigating planner/TTS leakage. For the
known ASR-style walk typo regression, run:

```bash
python scripts/interaction_text_mujoco_check.py \
  "Wal forward for 15 seconds, quickly." \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --preview-only \
  --no-speaker \
  --expect-skill soridormi.walk_forward \
  --reject-internal-speech
```

That preview-only check fails if no walking skill is emitted or if spoken text
contains internal labels such as `Task Split`, `Key Risk`, `Next Step`, or
model-facing `soridormi.*` skill IDs. It still writes `route.json`,
`interaction_response.json`, session events, and `summary.json` for diagnosis.

The retained `20260617T081411Z` text bundle is historical text-to-MuJoCo `/interaction`
closure evidence. It does not contain the provenance or cognitive status needed
to validate the current goal-driven path. Produce a new clean goal-driven bundle
when the claim includes the current semantic-authority boundary.

The old standalone text scenario suite has been removed for behavior claims.
Its useful cases are represented by the general ability manifest so failures
are reported by ability class rather than as a flat list of examples. Use:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

That command is preview-only and headless by default. Use `--execute` only for
supervised simulator execution.

## Task-agent bridge acceptance

Against a live Soridormi endpoint that exposes the no-motion task API, run:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --task-agent-bridge
```

This probes the manifest endpoint, calls `soridormi.task.get_capabilities`,
requires `task_api_no_motion=true` and at least one declared task type before
any preview or submit call, previews a structured task goal, submits it with a
Chromie-owned `client_task_ref`, and monitors `soridormi.task.events` until a
terminal no-motion completion. It fails if Soridormi does not declare the
no-motion task contract, if preview would create a persistent task, if submit
does not return a `task_id`, or if terminal monitoring does not end
`safe_idle=true`.

Use `--task-goal-json` to supply another structured task goal. This acceptance
mode is contract evidence only; it does not authorize or prove physical motion.

## High-level task enrichment acceptance

When Soridormi adds a high-level task type, Chromie acceptance should treat it
as routable only after the authoritative manifest and live endpoint expose the
contract and the no-motion or simulator evidence passes. Near-term task types
are:

- `navigate_to_location`;
- `approach_target`;
- `look_at_target`;
- `perform_gesture`;
- `recover_safe_idle`.

For each task type, retain evidence for manifest probing, task capability
inspection, preview, submit, event monitoring, terminal state, safe idle,
cancellation where applicable, refusal or blocked-subsystem behavior, and
Chromie user-facing routing/reporting. Unsupported task types must remain
structured refusals or clarifications. Do not treat a task as physical
completion unless Soridormi returns retained simulator or commissioned hardware
execution evidence for that exact path.

Motion-control model training is not an acceptance shortcut. It requires a
selected simulator or robot target, calibration and telemetry, task-level
metrics, and Soridormi-owned safety envelopes.

## Guarded and recovery acceptance

Against a disposable Soridormi dry-run process:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --guarded-dry-run
```

Add `--exercise-emergency-stop` only when the process may be restarted. The
command intentionally leaves emergency stop active.

Against a supervised runtime-backed endpoint:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --exercise-runtime-cancellation
```

This dispatches a long zero-velocity plan, cancels it, requires the emergency
fallback, and verifies retained e-stop state. Complete Soridormi’s recovery
procedure before further motion.

## Source-bound target-evidence closure

New target evidence is coordinated by
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md). The retired broad supervised runner combined unrelated smoke, cancellation, and
recovery artifacts without one source-bound profile or fingerprinted review. Use
the unified workflow for Gateway/Core, Agent Skill/weather, Social Attention, LAN,
and optional supervised physical evidence.

```bash
python scripts/run_target_evidence_closure.py --help
```

The default profile does not require or claim physical support. The physical
pilot profile requires dedicated voice and robot evidence under their safety
procedures.

## Voice audio acceptance modes

New voice evidence uses functional script names and the
`.chromie/acceptance/voice/` directory. Historical text-to-MuJoCo evidence remains
documented separately.

## Provider fault matrix

The Chromie-side provider matrix runs without Docker, audio devices, a live MCP
endpoint, or MuJoCo:

```bash
python scripts/provider_fault_matrix.py
```

It executes 16 versioned deterministic scenarios for provider restart, skill
unavailability, jitter, plan, safety-monitor status loss, execution, timeout,
disconnect, malformed-result, runtime-cancellation, and operator-cancellation
behavior. Each result compares the interaction terminal state, body-skill
terminal state, reason code, user-facing speech, and exact tool-call sequence.
Use `--scenarios` for a subset and `--output` to retain a machine-readable JSON
summary. This is automated contract evidence, not live simulator or hardware
validation.

Against a Soridormi endpoint that declares hidden test controls, run the same
matrix through the real MCP transport:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
python scripts/provider_fault_matrix.py --live \
  --manifest capabilities/soridormi.json \
  --output .chromie/provider-readiness/fault-matrix.json
```

The matrix also records total scenario and terminal latency. Defaults require
each scenario to finish within 1000 ms, timeout terminal handling within 500
ms, and operator cancellation terminal handling within 250 ms. Override these
with `--max-scenario-ms`, `--max-timeout-terminal-ms`, and
`--max-cancel-terminal-ms` for a declared target environment. A threshold
violation fails the matrix and is retained in the JSON result.

After every scenario, the runner reads `soridormi.robot.get_status`. A scenario
passes only when the status call succeeds, `active_task` is empty, and
`emergency_stop` is explicitly false. The retained result includes the complete
high-level status snapshot and aggregate safe-idle count.

The shared provider conformance suite verifies the same high-level contract for
`sim`, a recommendation-only `hardware_shadow` skeleton, and a no-motion
`hardware_dry_run` skeleton:

```bash
python scripts/provider_conformance.py
```

It checks the versioned catalog, opaque plan identity, safety monitor,
authorized explicit completion, cancellation, provider status, safe idle, and
rejection of low-level device fields. It refuses real `hardware` mode. When a
safe live endpoint is available, use `--live` with one explicit safe
`--profile` and configure `SORIDORMI_MCP_URL`.

Multi-profile output includes a parity result. Profile-specific checks such as
the declared mode, recommendation-only shadow proof, and dry-run no-motion
proof are compared separately. All shared checks must have the same names and
pass/fail outcomes. Versioned traces retain each high-level call, arguments,
authorization context, and normalized outcome; parity also requires the shared
trace sequence and terminal statuses to match. Use `--output` to retain the
replayable JSON evidence. Compare separately retained live runs without making
new provider calls:

```bash
python scripts/provider_conformance.py --compare \
  evidence/provider-sim.json \
  evidence/provider-shadow.json \
  evidence/provider-dry-run.json \
  --output evidence/provider-parity.json
```

The hardware selection requirements and rejection conditions are maintained in
the [Reference Robot Commissioning Checklist](ROBOT_COMMISSIONING.md).

Before starting target services, check whether the pinned Soridormi manifest
declares every required safe mode and the test-only fault-injection contract:

```bash
python scripts/verify_provider_readiness.py preflight \
  --manifest capabilities/soridormi.json
```

The fault-injection declaration lives under
`metadata.provider_readiness.fault_injection`. It names test-only
`configure_tool` and `clear_tool` capabilities, which must be
`llm_visible=false`, plus the supported versioned scenario IDs. The checked-in
manifest is pinned to a Soridormi revision that declares all three safe modes
and the hidden live fault-injection contract.

Retained target evidence uses one directory containing:

- `metadata.json` with target, endpoint, exact Chromie and Soridormi revisions,
  clean-worktree state, and `status=passed`;
- one live conformance JSON file for each safe profile;
- the offline profile parity result;
- a live 16-scenario fault-matrix result; and
- reviewed `operator-notes.md`.

Verify it with:

```bash
python scripts/verify_provider_readiness.py verify \
  evidence/provider-readiness/<run-id> \
  --require-clean \
  --write-report evidence/provider-readiness/<run-id>/verification.json
```

The verifier rejects local-stub conformance output, missing profiles or
scenarios, version drift, threshold violations, unsafe-idle results, dirty
revisions when required, and missing operator review.

## Reference robot candidate preflight

Physical pilot preparation uses a separate machine-readable candidate record:

```bash
python scripts/verify_robot_candidate.py \
  .chromie/commissioning/reference_robot_candidate.json \
  --evidence-root .chromie/commissioning \
  --verify-evidence-files \
  --write-report .chromie/commissioning/candidate-verification.json
```

The report separates structural validity, readiness for no-motion review, and
selection for the pilot. Missing identity, unpinned revisions, absent
emergency-stop evidence, missing calibration hashes, unspecified limits or
exclusions, invalid timestamps, and unknown fields all fail closed. Candidate
selection never authorizes physical motion. With `--verify-evidence-files`, the
verifier also requires referenced procedure and safety files to exist and
remain inside the evidence root, requires the provider manifest's
`metadata.upstream_commit` to match `revisions.soridormi`, and requires
calibration artifact SHA-256 values to match.

## Bilingual generated-speech closed loop

The default end-to-end audio qualification does not require an operator to
speak. Run:

```bash
python scripts/closed_loop_e2e.py --start-services --capture auto
```

The manifest at
`benchmarks/manifests/closed_loop_e2e_v1.json` contains both Chinese and
English cases. The runner retains two related evidence paths:

1. source text -> language-matched Chromie TTS -> WAV/PCM -> Chromie ASR;
2. injected user text -> Cognitive Gateway/Core/Agent/tools -> TTS -> actual
   host playback capture -> Chromie ASR.

`--capture auto` prefers the default Pulse/PipeWire sink monitor, so the
workflow validates the emitted speaker stream without room noise. When monitor
capture is unavailable it uses the physical microphone while Chromie's own TTS
plays through the speaker; no human pronunciation is graded. Use
`--capture acoustic` explicitly for that physical speaker-to-microphone path.

Chinese cases are evaluated primarily with character error rate; English cases
use word error rate. Workflow playback is compared with the exact speech that
Chromie actually delivered during the same turn, not with a hard-coded model
answer. Separate manifest terms check the intended response outcome. This keeps
ASR in the role of an automated audio observer rather than making a human
accent part of the release gate.

The generated-speech report is strong evidence for bilingual TTS, ASR,
playback routing, and end-to-end workflow delivery. It does not claim arbitrary
human-speech recognition accuracy.

For a complete revision-bound collection, use the maintained orchestrator:

```bash
./scripts/qualification/run_comprehensive_test.sh --capture auto
```

It runs the source gate, existing deterministic benchmark owners, service/GPU
checks, bilingual closed-loop cases, retained synthetic acceptance, and bounded
shared-GPU contention, then collects all host and Compose logs into one
hash-indexed archive. The script does not define expected AI answers: fixture
and contract truth stays deterministic, while declared semantic dimensions are
packaged for external LLM or human review. `--capture acoustic` still uses
Chromie's generated TTS rather than the operator's voice. The collector is
diagnostic and always records `release_qualified=false`.

`scripts/voice_acceptance.py` has four explicit modes. All four retain
correlated JSONL events, exact revisions, redacted configuration, generated or
captured audio, Orchestrator logs, and per-case checks.

| Mode | Input path | Operator interaction | What it proves | Human voice-device closure |
|---|---|---|---|---:|
| `synthetic` (default) | Chromie TTS WAV -> framed Orchestrator stdin -> VAD -> ASR | None | Reproducible speech/control-plane/Trusted Capability Runtime regression | No |
| `virtual-mic` | Chromie TTS WAV -> Pulse/PipeWire null sink monitor -> normal host capture -> VAD -> ASR | None | Host audio-device capture plus the automated control path | No |
| `acoustic` | Chromie TTS WAV -> host output -> configured host input device -> VAD -> ASR | None | Repeatable host audio-device path for generated speech; physical evidence when bound to a real speaker/microphone pair | No |
| `supervised` | Real microphone -> normal host capture -> VAD -> ASR | Audible/visual verdict after machine checks pass | Reference-host microphone, speaker, pronunciation, and observed simulator behavior | Yes, for physical voice-device release claims |

The `synthetic` and `virtual-mic` modes intentionally use response playback
`discard` mode. Audio is paced in real time, so `playback_start`, barge-in,
cancellation, and stale playback checks still execute without requiring a
physical speaker or risking speaker-to-microphone feedback. The `acoustic`
mode uses host playback and configured input-device capture, so it is useful
for low-cost microphone/speaker regression when bound to real devices, but it
proves generated speech rather than arbitrary human pronunciation.

The focused reversible-barge-in profile is:

```bash
python scripts/voice_acceptance.py \
  --mode synthetic \
  --cases barge-in-echo,barge-in \
  --start-services
```

`barge-in-echo` waits for one completed output chunk, replays that exact retained
PCM through the selected automated input path, and requires generation-bound
echo suppression, release of the same playback session, unique playback starts,
and a clean terminal `session_done` before another case begins. `barge-in`
injects confirmed external speech during active playback and requires distinct
acoustic and Gateway receipts. Both acoustic receipts must retain
`cancel_cognitive_work=false`; VAD-start-to-duck and
confirmed-speech-to-silence must each be at most 250 ms. A pause/restart error,
late old-session TTS or playback, dispatch failure, duplicate start, missing
terminal completion, or cross-case overlap is a hard failure. Captured-output
replay is automated-only; physical acoustic barge-in behavior still requires
its own supervised evidence. The basic physical
microphone-to-audible-speaker chain already has separate supervised evidence in
`20260809T122818Z`.

The current development compatibility policy lists `synthetic`,
`virtual-mic`, and `acoustic` as eligible generated-speech modes. That policy
does not turn them into human voice-device evidence. Before a bundle can enter
policy evaluation, the verifier also requires the goal-driven acceptance
override, correlated applied `chat` and `robot_action` cognitive events,
exclusive Soridormi `sim` provider events, clean matching checkouts, and an
endpoint-reported Soridormi revision. The current runner records only a
`declared_paired_checkout`, so it cannot yet produce a policy-ready bundle.

Use `scripts/interaction_text_mujoco_check.py` when the goal is to skip both
microphone and ASR but still hear Chromie through the speaker. Use
`synthetic` voice-acceptance mode when the goal is to skip only the microphone: generated
Chromie TTS audio is injected as input and still passes through VAD and ASR.

### Automatic synthetic acceptance

Start the five Chromie services and a supervised MuJoCo-backed Soridormi MCP
endpoint. Check all prerequisites before creating an evidence bundle:

```bash
python scripts/voice_acceptance.py \
  --preflight-only \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The preflight checks the generated-runtime script, Docker CLI and daemon,
automatic Python runtime, TTS startup plan, and the external Soridormi endpoint
and repository. It does not start services or create evidence. Once it reports
`Overall: ready`, run:

```bash
python scripts/voice_acceptance.py \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner generates each unique test utterance once through the existing TTS
WebSocket service and stores it under:

```text
.chromie/acceptance/voice/<id>/generated-input/
```

Before generating fixtures, the runner waits for application-level TTS health
to report both a ready provider and a live worker. Attempts are retained in
`tts-readiness.log`; a listening TCP port or a container in `starting` state is
not treated as fixture-generation readiness.

It then injects a private framed PCM16 stream through the Orchestrator process's
stdin. No network injection endpoint is opened. The Orchestrator resamples the
packet, feeds normal VAD frames, sends the resulting utterance to ASR, and uses
the same Cognitive Gateway, Agent/Cognitive Core, Trusted Capability Runtime, TTS, and Soridormi paths as a microphone
session.

This mode is the recommended first run because it removes pronunciation,
microphone selection, room noise, and operator timing from the result. It is
also intentionally optimistic: Chromie's TTS voice is generally easier for its
ASR to recognize than arbitrary human speech.

Verify automatic evidence with:

```bash
python scripts/verify_voice_evidence.py --allow-automated \
  .chromie/acceptance/voice/<id>
```

When its recorded Chromie version/revision and Soridormi manifest and declared
paired-checkout revisions match the current clean source, the verifier may
report passing diagnostic automated evidence. It sets
`policy_evaluation_ready=true` only when the endpoint also reports the matching
executing Soridormi revision. The current runner/endpoint path does not provide
that binding, while
`human_voice_device_claim_eligible=false` remains reserved for clean supervised
evidence. Release preparation separately applies the narrowed compatibility
policy's accepted modes. Historical inspection requires explicit
`--expected-*` values and does not transfer evidence to a newer build.

The retained reference-host synthetic run is `20260614T132934Z`; all seven
cases passed at Chromie revision `f0e22ba`.

### Automatic virtual-microphone acceptance

`virtual-mic` mode requires PulseAudio or PipeWire. It uses `pactl`/`paplay`
when available and otherwise falls back to native
`pw-cli`/`pw-cat`/`pw-dump` tools:

```bash
python scripts/voice_acceptance.py \
  --mode virtual-mic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner creates a temporary null sink named `chromie_voice_test` by default,
sets its monitor as `PULSE_SOURCE` for the Orchestrator, plays each generated WAV
into that sink, and unloads the module during cleanup. Override the sink name
with `--virtual-mic-sink` when needed.

This mode exercises normal `sounddevice` capture, sample-rate conversion, host
buffering, VAD, and ASR. It still does not prove a physical microphone or
speaker.

The retained PipeWire run is `20260614T133155Z`; all seven cases passed at
Chromie revision `f0e22ba`.

### Automatic acoustic acceptance

Use `acoustic` mode when the goal is to test the reference host's configured
speaker/input-device loop without requiring a human to speak all seven cases:

```bash
ORCH_INPUT_DEVICE=0 ORCH_OUTPUT_DEVICE=16 ORCH_INPUT_GAIN=80 \
python scripts/voice_acceptance.py \
  --mode acoustic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner generates each prompt with Chromie TTS, plays it through the
host audio player, and waits for the normal Orchestrator microphone path to
capture and recognize it. The default player is `auto`, which prefers
`pw-play`, then `paplay`, then `aplay`, and falls back to `sounddevice`.
Tune `ORCH_INPUT_DEVICE`, `ORCH_OUTPUT_DEVICE`, `ORCH_INPUT_GAIN`,
`--acoustic-playback-gain`, `--acoustic-player`, and
`--acoustic-output-target` for the host room and device levels. Chromie's own
responses use paced discard playback by default to avoid echoing confirmation
prompts back through host input bridges; use
`--acoustic-response-output-mode device` only when the selected input is a real
microphone path that tolerates response playback. This is target audio-path
evidence for generated speech, not a human pronunciation or
operator-observation claim; treat it as physical microphone evidence only when
the recorded `ORCH_INPUT_DEVICE` is known to be the real microphone path.

### Physical audio supervised acceptance

Commit the evaluated revision first, then run:

```bash
python scripts/voice_acceptance.py \
  --mode supervised \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

For each utterance the runner displays a countdown and `SPEAK NOW`, waits for
`asr_final`, shows expected and recognized text, and prints the current
session's Goal Interpretation, interaction, skill, playback, cancellation, and completion
events. It asks for an audible/visual operator verdict only after all machine
checks pass. Missing ASR or required runtime events automatically fail the case.
Before opening the microphone, supervised mode also waits for the live TTS
worker and performs one retained, no-playback synthesis with the effective
`TTS_SPEAKER_ID` from generated `.env.runtime`. This primes the same response
voice the Orchestrator will use; `tts-readiness.log` and
`tts-warmup/manifest.json` distinguish provider readiness or cold-start failure
from microphone, cognition, and playback evidence. A failed warm-up stops before
the operator is asked to speak rather than weakening the playback-start safety
deadline.

Only a clean, passing `supervised` bundle can satisfy a human-supervised
voice-device release verifier:

```bash
python scripts/verify_voice_evidence.py --require-clean \
  .chromie/acceptance/voice/<id>
```

The host runner uses `ORCH_RUNTIME_OVERRIDE_FILE` and does not edit the
operator's `.env.local` or generated `.env.runtime`. The Soridormi capability
probe runs inside `chromie-agent` by default; host-loopback endpoints are
translated to `host.docker.internal` only for that container command.

This supervised mode is not required for text-to-MuJoCo interaction closure. Use it
when the claim being tested includes real microphone recognition, real speaker
playback, and operator-observed behavior.

### Shared controls

```text
--cases all|speech-only,speech-skill,...
--asr-timeout-s 20
--asr-retries 1
--case-timeout-s 60
--continue-after-failure
--tts-url ws://127.0.0.1:5000
--tts-speaker-id default
```

A command-only rehearsal remains non-evidence:

```bash
python scripts/voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

## Voice and MuJoCo acceptance matrix

Run from the repository root with the structured path enabled and a live
MuJoCo-backed Soridormi endpoint. All four modes execute these cases in the
order below; only `acoustic` and `supervised` use a physical host audio path,
and only `supervised` adds human speech and operator observations.

| Case | User input | Required evidence |
|---|---|---|
| Speech only | General question | ASR final text, prepared speech with zero body skills, correlated TTS schedule, playback start/end, and clean session completion. Audible output is additionally judged only when the selected mode uses a physical output device. |
| Speech plus body skill | “Nod” or equivalent, then “Yes” | Exact nod/count proposal; request-bound confirmation prompt scheduled and fully played before approval; requested, approved, and authorized events bound by confirmation ID and fingerprint; completed skill result; safe idle. |
| Refusal | Valid body request, then “No thanks” | Requested, denied, and rejected events bound by confirmation ID and fingerprint; no Soridormi result; completed denial speech output. |
| Barge-in | Interrupt while speaking | Active old-session playback linked to the new interrupt session, deterministic interrupt route, and no old-session playback after interruption completes. |
| Body cancellation | Confirm, then interrupt a cancellable simulated skill | Bound approval, host-observed Trusted Capability Runtime cancellation, host interruption completion, and post-cancellation safe-idle/no-active-task status. This does not claim a provider cancel RPC unless a provider event explicitly records one. |
| Stop/emergency | Explicit stop during active work | Deterministic operational route linked to the active prior session, with no later old-session output or completed work. |
| Follow-up | “Remember … blue,” then ask for the color | Same conversation ID, both intended ASR utterances, and completed second-response output containing `blue`. |

For every case retain:

- repository and Soridormi revisions;
- `.env.runtime` profile name without secrets;
- audio device names, sample rates, and VAD thresholds;
- Goal Interpretation decision, Agent/interaction metadata, skill results, and correlated IDs;
- confirmation ID, exact request fingerprint, expiry, and approval or denial;
- timing logs and operator pass/fail notes;
- simulator/hardware state before and after the case;
- recovery confirmation when stop or emergency behavior is exercised.


## Structured event evidence

Set `ORCH_EVENT_LOG_PATH` to append one JSON object per session event. The
acceptance runner configures this automatically. Each record contains a UTC
timestamp, session ID, elapsed milliseconds, event name, and rendered message.
Evidence writing is best-effort and cannot crash the realtime loop.

Do not place event logs in the repository or publish them without review; ASR
text and operator-visible context may contain private speech.

## Pass/fail discipline

- Do not count a dry run as simulator or hardware evidence.
- Do not infer confirmation authority or safety evidence from simulator or hardware identity.
- Do not infer broad deployment support from text-input acceptance alone.
- Do not publish logs containing execution tokens or private environment data.
- Record failure evidence as well as successful reruns; otherwise regressions are
  difficult to diagnose.

## Runtime Trace Latency Evidence

Runtime Trace latency reports are derived from immutable completed trace event
packages. Build a report for one declared environment with:

```bash
python scripts/runtime_trace_latency.py summarize \
  --source .chromie/runtime-events \
  --evidence-class target \
  --environment <exact-target-label> \
  --label <candidate-label> \
  --output .chromie/latency/candidate.json
```

Compare it with a retained baseline only after an explicit policy has been
reviewed and enabled:

```bash
python scripts/runtime_trace_latency.py gate \
  --baseline .chromie/latency/baseline.json \
  --candidate .chromie/latency/candidate.json \
  --policy env/validation/runtime_trace_latency_gate.json \
  --output .chromie/latency/gate-result.json
```

The gate returns invalid rather than pass when evidence class, environment,
sample count, revision cleanliness, or required metric samples are not
qualified. The committed `.example.json` policy is disabled and carries no
release authority. See
[Accelerator Telemetry and Latency Evidence Gates](ACCELERATOR_LATENCY_EVIDENCE.md).
