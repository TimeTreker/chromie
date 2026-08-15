# Chromie Development Checkpoint
Status: current resume point
Updated: 2026-08-15
Base main: `5546511dd18feba67f6d7fd54de61874e375aecc` (`close goal authority and social activity milestone`).
This is the fast handoff for the next development session. Canonical owners linked below win if a conflict appears; refresh this checkpoint afterward.
## Project in one minute
Chromie is a local-first realtime interaction control plane for a voice assistant
that can use embodied capabilities safely. Chromie owns user-facing cognition,
Goal meaning and continuity, cross-provider planning, personal Vocal behavior,
trusted authorization, coordination, and evidence reconciliation. Soridormi is a
peer embodied Capability Provider beneath Activity. Its advertised capability
granularity may change over time: a whole workflow can be one atomic capability,
or Chromie can compose smaller advertised capabilities.
The core separation is: **models reason about meaning; trusted mechanisms own
authorization, execution, resources, and evidence.** Capability unavailable,
execution failed, empty result, and successful result are different truths.
Read first: [Project Charter](docs/PROJECT_CHARTER.md),
[Goal-Driven Cognitive Architecture](docs/GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md)
(the canonical WORLD/PERSON → Fast/Deep → Responsibility → Goal → Planner →
Provider → Evidence → Response/Reflection design is frozen there),
[Execution Lanes](docs/EXECUTION_LANES_AND_COORDINATION.md),
[Current Status](docs/STATUS.md), and [Roadmap](ROADMAP.md).
## Current architecture
```text
admitted UserTurnEnvelope
        |
Cognitive Gateway ---- deterministic stop/cancel/emergency reflexes
        |
Goal-Driven Continuous Mind
  |-> Fast Understanding -------> provider-neutral Responsibility evidence
  |                               + optional locally-ready native conversation
  `-> Goal Association ---------> canonical Goals / Responsibilities
                                  |
                            Fast / Deep Planner
                                  |
                             Canonical Plan
                    .-------------+-------------.
                    |                           |
             Response Composer          Trusted Capability Runtime
                    |                           |
                  Vocal                Activity / providers
                    '-------------+-------------'
                                  |
                         trusted evidence
                                  |
                   reconciliation -> result interpretation
```
Social Attention is optional body decoration anchored to a concrete semantic primary human-observable Activity—what Chromie is doing, not how a lane/mode/Capability realizes it; it is not a Goal, execution lane, or cognition-milestone reaction.
Durable Mind stays small: Stable Mind, unfinished Goals, selective Memory.
Situation is bounded, revisable, mostly reconstructable live soft state.
Evidence/Ledger plus Progress/Plan/Request/Execution/Outcome are the grounding and
work substrate. `Responsibility` and `Work` are architecture vocabulary, not new
parallel manager objects.
## Settled boundaries
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
  runtime truth; cognition may explain that truth but may not promote it.
- **Proof is not a second semantic author.** Goal Association may retain immutable
  coverage evidence. Response Composer has one wording owner; a consequential truth
  check is one immutable accept/reject certificate and cannot rewrite Response, Goal,
  Plan, or Social Attention. Tool Result Interpreter follows the same one-writer rule:
  one evidence-bound answer, immutable truth proof, no semantic rewrite/reviewer chain.
- **Readiness is local, not pipeline-global.** A branch advances when its own
  meaning, inputs, evidence, dependencies, and authority are sufficient.
- **Stable Mind is not dynamic world knowledge.** Identity/personality/values may
  be cached; changing facts such as weather, news, prices, schedules, and law are
  acquired through trusted information paths.
## Recent architecture closure
Current source bounds Goal/Planner reconsideration, keeps benign chat Fast, makes
Deep/Host semantic rejection terminal, and implements the frozen human-like Core.
Response Goal coverage is now a Host-derived read-only projection. The Response
Composer model owns wording but cannot author `covers_goal_ids`; canonical Goal
ownership and exact reused-speech provenance project that delivery bookkeeping
mechanically. This removes another duplicate writable semantic truth without
changing playback/evidence correlation.
Response Composer is the single wording owner. `SocialAttentionPlanner` is the sole
optional-decoration writer; malformed decoration fails soft and backend/calibration
identity is stripped before model reasoning. Reflection is evidence-bound future
adaptation: actions require recorded outcome/evidence, apply only to open Responsibility,
and cannot reopen completed outcomes or current-turn authority.
The current daily-life source correction also closes the general boundaries exposed by the generated-voice suite: Capability choice requires declared semantic entailment rather than topical proximity; state mutations are not information resources; local/private sensor state stays unknown without a trusted Provider; unavailable persistent work cannot be phrased as a future promise; and Gateway Attention uses bounded recent dialogue for temporary user-authored addressedness policy with one fail-open judgment and no online repair/reviewer chain. The follow-up authority correction makes the weather case explicit: Fast Goal Interpretation preserves typed provider-neutral information scope as Responsibility evidence, but exact Capability identity, executable arguments, and actions belong only to planning after canonical Goal Association. Pre-Goal local progress is limited to already-complete native speech or prospective Goal Progress Communication; provider work does not start before the canonical Goal exists. Social Attention is now keyed to semantic primary human-observable Activity meaning rather than to cognition milestones, execution modalities, or a once-per-turn budget. Responsibility/Goal sits above Activity; one Goal may own several semantic Activities/Work items, and a high-level provider Capability may realize one Activity atomically. Final `InteractionResponse` transport objects, Vocal modes, body/media requests, and Capability IDs are realization evidence only. Canonical conversational acts and Plan-step meaning provide Activity granularity; execution modality never does. Planner execution eligibility is derived from canonical Goal completion semantics, never from Fast Goal Interpreter compatibility route/intent fields.
These are source claims only; no new target evidence is implied.
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
Docs-first core design and this authority cleanup are implemented. Next rerun the daily-life generated-voice suite and compare capability grounding, Goal correction/reasoning, future-commitment truth, and temporary addressedness. Do not add a new top-level layer or phrase-specific case rules; historical target evidence remains revision-bound.
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
