# Chromie Development Checkpoint
Status: current resume point
Updated: 2026-08-18
Base main before this delivery: `2eea3408e6f82df7675a190c0a494b7b58af64c9`. This is the fast handoff for the next development session; canonical owners linked below win if a conflict appears.
## Project in one minute
Chromie is a local-first realtime interaction control plane for a voice assistant that can use embodied capabilities safely. Chromie owns user-facing cognition, Goal meaning and continuity, cross-provider planning, personal Vocal behavior, trusted authorization, coordination, and evidence reconciliation.
Soridormi is a peer embodied Capability Provider beneath Activity; its advertised granularity may be one atomic workflow or smaller capabilities that Chromie composes.
The core separation is: **models reason about meaning; trusted mechanisms own authorization, execution, resources, and evidence.** Capability unavailable, execution failed, empty result, and successful result are different truths.
Read first: [Project Charter](docs/PROJECT_CHARTER.md), [Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md) (the canonical expanded flow is frozen there and in the Charter: Session Context → GI → Fast Planner first Communicative Activity → concurrent remaining Fast Activity planning and GA → deterministic Goal binding → Goal-grouped Trusted Capability Runtime → Evidence/Response, with Deep Planner only for complex HOW), [Execution Lanes](docs/EXECUTION_LANES_AND_COORDINATION.md), [Current Status](docs/STATUS.md), and [Roadmap](ROADMAP.md).
## Current architecture
```text
admitted UserTurnEnvelope + bounded Session Context
  -> Goal Interpretation (Responsibility + Goal relation + bounded unresolved meaning)
  -> Fast Planner -> first exact Communicative Activity or silence
  -> same-result concurrent continuation
       |-> same Fast Planner -> input resolution + remaining Communicative/Capability Activities
       |     |-> Host-validated act -> Vocal/TTS; or user-resolvable clarification
       |     `-> Deep Planner only for complex HOW
       `-> Goal Association -> sole canonical Goal commit/version authority
  -> bind Activities into one task-list view per Goal
  -> Trusted Capability Runtime resource-aware scheduling
  -> Providers -> Host-bound Evidence -> Fast Planner re-entry -> per-Goal reconciliation/Response
```
Social Attention is optional body decoration anchored to a concrete semantic primary human-observable Activity—what Chromie is doing, not how a lane/mode/Capability realizes it; it is not a Goal, execution lane, or cognition-milestone reaction.
Durable Mind stays small: Stable Mind, unfinished Goals, selective Memory.
Situation is bounded, revisable, mostly reconstructable live soft state.
Evidence/Ledger plus Plan/Request/Execution/Outcome ground Work; `Responsibility` and
`Work` are architecture vocabulary, not parallel manager objects.
## Settled boundaries
- **Goal Interpretation stops at Responsibility evidence.** GI may not author response wording, Work, Primary Activities, Plan/execution/realization contracts, Capabilities, planning InformationGaps, execution-input completeness, blocking state, or input-source/default/clarification policy. It may report bounded unresolved meaning for a genuinely ambiguous outcome, scope, or referent. Fast Planner first owns HOW/Activity and input resolution without changing Responsibility meaning; it may request Deep Planner continuation for complex HOW without absorbing Deep authority. GA independently consumes the same GI result without waiting for Fast.
- **Goal = canonical unfinished Responsibility.** Planning, waiting, confirmation,
  scheduling, running, retry/recovery, and provider state belong to Work/runtime.
- **Responsibility completeness is contained.** Every newly proposed Goal set
  uses an authority-ephemeral model-owned coverage certificate; the Host derives
  only its verdict, allows at most one fresh interpretation, and fails closed on
  invalid or repeatedly incomplete output.
- **`output_mode` is the sole model-authored Goal execution discriminant.** The
  Host derives responsibility kind, execution lane, and provider requirement.
  Reverse inference and model-authored copies are not supported protocol.
- **Unavailability never erases a requested responsibility.** Preserve the Goal
  and report the limitation; ordinary speech, media, or body motion cannot silently
  substitute for a provider-required vocal or effectful outcome.
- **Chromie has one personal Vocal Expression domain.** `speech` (speaking),
  `expressive_speech`, `recitation`, `singing`, `humming`, and
  `nonverbal_vocalization` are modes of one personal voice. `chromie.voice` is
  exclusive. A compatible body/media realization may overlap Vocal; simultaneous
  personal Vocal modes may not. Existing-media playback is realized through the
  Activity Execution Lane, not through personal Vocal Expression.
- **Social Attention is optional decoration with one semantic owner and one semantic primary-Activity anchor.**
  `SocialAttentionPlanner` alone authors decoration for the concrete human-observable
  behavior Chromie is doing: for example greet Alice, tell a joke, walk toward the
  user, sing a song, hand over water, or show/play something. Execution lanes, Vocal
  modes, Capability IDs, provider requests, and transport objects describe how that
  Activity is realized; they are not Primary-Activity kinds. Multiple realization
  items for one semantic Activity share one decoration opportunity, while independent
  semantic Activities may independently choose `none` or expression. Cognition
  milestones, planning state, evidence arrival, and waiting are not anchors.
  Malformed/conflicting decoration disappears locally with no second call, Goal
  completion authority, speech recomposition, or Goal/Plan mutation.
- **Chromie is embodiment-independent.** Soridormi/MuJoCo is sufficient for the
  core embodied outcome; cognition must not know the backend, and physical-robot
  commissioning is optional provider work rather than a Chromie completion gate.
- **Reality enters through evidence.** Provider evidence and reconciliation own
  runtime truth; evidence integrity is not automatically claim sufficiency.
- **Planner owns complete Communicative Activities.** Maintained GI does not own
  speech. Fast Planner selects an immediate act's function, exact wording,
  timing, Responsibility/Goal provenance, exact reason provenance to GI
  unresolved meaning or a Planner-owned InformationGap, truth stage, and
  Evidence references. The Host validates without rewriting; TTS/playback owns
  physical delivery Evidence.
- **Cross-cutting contracts are inputs, not authorities.** Claim qualification,
  retention/privacy, and bounded adaptation cannot inherit Goal/Plan/effect authority.
- **Readiness is local, not pipeline-global.** A branch advances when its own
  meaning, inputs, evidence, dependencies, and authority are sufficient.
- **Stable Mind is not dynamic world knowledge.** Identity/personality/values may
  be cached; changing facts such as weather, news, prices, schedules, and law are
  acquired through trusted information paths.
## Recent architecture closure
Current source bounds Goal/Planner reconsideration, keeps benign chat Fast, makes
Deep/Host semantic rejection terminal, and implements the frozen human-like Core.
Response Goal coverage is a Host-derived read-only projection. Planner owns
wording while canonical Goal ownership and exact reused-speech provenance
project delivery bookkeeping mechanically. No second response-writing model
sits between Planner and Vocal delivery.
The authority rule is act-scoped: maintained Goal Interpretation owns Responsibility
meaning only. Fast Planner owns complete Communicative Activities in its first Activity Plan;
`SocialAttentionPlanner` is the sole
optional-decoration writer. Accepted design now separates open-Goal
Reflection actions from terminal-history learning proposals: future online adaptation is
bounded advisory Memory with independent scope/lifetime and can never self-modify shared
cognitive policy or cache semantic decisions.

The owner-capped fifth rebuilt-Agent live-text run for “你好，今天重庆白天天气怎么样啊？”
is retained at `.chromie/acceptance/general-ability/20260817T224316Z-live-text/`. It
proves GI no longer requested the already-supplied location/date, GA committed the
Chongqing/today/day Goal, and Runtime dispatched `chromie.weather.lookup`. It then
exposed arbitrary Fast `speech_act` text with an invalid Deep continuation and a
weather-adapter mismatch between `Chongqing Municipality` and `Chongqing`. Current
source closes both through constrained Fast decoding and provider administrative-suffix
normalization. The canonical gate passes 1,900 tests, all 44 Level A cases pass, and a
real-network provider probe resolves `重庆`. The five-cycle limit leaves no sixth
combined proof; the fifth-run GI also narrowed the open question to sunny/not-sunny,
so that semantic fidelity remains an explicit evidence gap.
The current daily-life source correction also closes the general boundaries exposed by the generated-voice suite: Capability choice requires declared semantic entailment rather than topical proximity; state mutations are not information resources; local/private sensor state stays unknown without a trusted Provider; unavailable persistent work cannot be phrased as a future promise; and Gateway Attention uses bounded recent dialogue for temporary user-authored addressedness policy with one fail-open judgment and no online repair/reviewer chain. The owner-approved GI/Fast-Planner boundary is now implemented: Goal Interpretation preserves typed provider-neutral Responsibility meaning, Goal relation, and bounded unresolved meaning only; Fast Planner owns planning InformationGaps, execution-input completeness, source/default/blocking policy, and clarification selection. The temporary Deep-GI external-evidence defense and GI gap strategy fields are removed. One source-based Deep GI pass remains only for genuine semantic ambiguity. The same GI result first enters Fast Planner's bounded first-response phase; after that commitment, remaining Fast planning and GA continue concurrently. GA commits the narrowest source-grounded Goal but cannot author the question. Runtime deterministically binds each Planner gap to that exact Goal and commits it before clarification delivery. Fast Planner remains the first HOW owner and authors Communicative Acts plus Capability Activities; safe side-effect-free reads may start while GA commits canonical Goal identity, while effects remain Goal/confirmation/authorization gated. Trusted Capability Runtime presents one task-list view per Goal and never duplicates a shared task identity. Social Attention is keyed to semantic primary human-observable Activity meaning rather than to cognition milestones, execution modalities, or a once-per-turn budget. Responsibility/Goal sits above Activity; one Goal may own several semantic Activities/Work items, and a high-level provider Capability may realize one Activity atomically. Final `InteractionResponse` transport objects, Vocal modes, body/media requests, and Capability IDs are realization evidence only. Canonical Communicative Acts and Plan-step meaning provide Activity granularity; execution modality never does. Planner execution eligibility is derived from canonical Goal completion semantics. The maintained Goal Interpretation handoff has no route/intent compatibility fields; Responsibility moves into downstream cognition through typed `CognitiveWorkRequest`.
The consolidated current-source gate passes all 13 repository-policy families, 119 benchmark tests, 1,835 maintained tests, 20 legacy Agent tests, all 44 Level A cases, test ownership, static analysis, configuration, structure, and documentation checks. These are source claims only; no new target evidence is implied.
## Do not resurrect
- independent Router semantic authority;
- `social_attention` as a third execution lane or standalone Goal;
- `Speaking` as a sibling domain to singing/humming, or multiple personal mouths;
- reverse `responsibility_kind -> output_mode` compatibility inference;
- Host phrase tables/regexes deciding ordinary intent or planning;
- a generic global semantic-review layer merely because local stages review;
- random idle animation disguised as Social Attention;
- silent capability substitution, evidence promotion, or response text as proof;
- compatibility machinery for an owner-replaced architecture;
- online semantic repair chains, reviewer-of-reviewer flows, and repair-of-repair (the semantic-authority audit must reject their return);
- Host replanning after a terminal Deep plan has failed trusted validation;
- model-authored duplicate copies of one semantic fact;
- managers/layers/prompt mountains without a distinct required owner or invariant.
## Engineering decision rule
The Charter requires the **best-known technically justified architecture** as the
default target. First determine what is technically strongest; then weigh current
code, compatibility, migration effort, sunk cost, schedule, and diff size. Those
costs matter but do not have architecture veto power. If the stronger design needs
new owner authority, explain why it is stronger, alternatives, tradeoffs, risks,
migration/removal impact, and the exact authority required, then ask the owner.
Do not silently downgrade because authority is absent.
This checkpoint does **not** grant blanket architecture authority to later
sessions; use Charter governance when new authority is needed.
## Resume point
The GI/GA/Fast-Planner ownership migration, Planner-owned communication, Main-Activity-attached Social Attention opportunity, and Host Evidence → Fast Planner result re-entry are source-closed. Preserve their regressions and finish exact-revision evidence closure: qualified warm runs must retain Planner commitment at or below 2,000 ms, audible playback start at or below 3,000 ms, the attached Social Attention opportunity (including valid `none`), and terminal Evidence re-entry without duplicate execution. Historical target evidence remains revision-bound and does not validate these new boundaries. After closure, resume the semantic Issue order in `ROADMAP.md`; do not recreate a later wording/result model, GA-authored questions, or standalone Social Attention.
## Resume and verification commands
`docs/STATUS.md` owns implementation/evidence claims. Do not claim live-model,
audio, MuJoCo, GPU, or physical-provider qualification unless that exact gate ran
and retained evidence.
```bash
git switch main && git pull --ff-only
git status --short
git log -10 --oneline
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_runtime_structure.py
python scripts/check_docs.py
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
./scripts/run_tests.sh   # canonical gate in a dependency-complete environment
```
Canonical owners: [Charter](docs/PROJECT_CHARTER.md) ·
[Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md) ·
[Turn Loop](docs/COGNITIVE_TURN_LOOP.md) · [Roadmap](ROADMAP.md) · [Status](docs/STATUS.md) ·
[Target Evidence](docs/TARGET_EVIDENCE_CLOSURE.md) · [API](docs/API_REFERENCE.md) · [Runbook](CHROMIE_RUNBOOK.md).
