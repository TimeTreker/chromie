# Chromie Development Checkpoint
Status: current resume point
Updated: 2026-08-14
Base main: `85fc0814665aafe2a768c5ff242b8032a5d54606` (`Make Response Composer a single expression owner`).
This is the fast handoff for the next development session. It summarizes the
current project shape and resume point; canonical owners linked below win if a
conflict appears and this checkpoint should then be refreshed.
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
  |-> Fast Understanding -------> locally-ready native conversation
  |-> safe-read progress -------> trusted non-effectful work when ready
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
Social Attention is background, interaction-anchored body decoration around
ongoing behavior; it is not a Goal and not an execution lane.
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
- **Chromie has one personal Vocal domain.** Speech, expressive speech, recitation,
  singing, humming, and nonverbal vocalization are modes of one voice.
  `chromie.voice` is exclusive. Compatible body Activity may overlap Vocal;
  simultaneous personal Vocal modes may not. Existing-media playback is Activity.
- **Social Attention is optional decoration with one semantic owner.**
  `SocialAttentionPlanner` alone authors interaction-anchored body decoration through
  Activity. Explicitly requested motion remains primary Activity. A valid `none` is
  terminal; malformed/conflicting decoration disappears locally with no second call,
  Goal completion authority, speech recomposition, or Goal/Plan mutation.
- **Chromie is embodiment-independent.** Soridormi/MuJoCo is sufficient for the
  core embodied outcome; cognition must not know the backend, and physical-robot
  commissioning is optional provider work rather than a Chromie completion gate.
- **Reality enters through evidence.** Provider evidence and reconciliation own
  runtime truth; cognition may explain that truth but may not promote it.
- **Proof is not a second semantic author.** Goal Association may retain immutable
  coverage evidence. Response Composer has one wording owner; a consequential truth
  check is one immutable accept/reject certificate and cannot rewrite Response, Goal,
  Plan, or Social Attention. Tool Result Interpreter remains a later cleanup target;
  do not add a generic ReviewManager or reviewer-of-reviewer flow.
- **Readiness is local, not pipeline-global.** A branch advances when its own
  meaning, inputs, evidence, dependencies, and authority are sufficient.
- **Stable Mind is not dynamic world knowledge.** Identity/personality/values may
  be cached; changing facts such as weather, news, prices, schedules, and law are
  acquired through trusted information paths.
## Recent architecture closure
Current source bounds Goal/Planner reconsideration, keeps benign chat Fast, makes
Deep/Host semantic rejection terminal, and implements the frozen human-like Core.
Response Composer is the single wording owner. `SocialAttentionPlanner` is now the
single optional-decoration writer; Response composition contains no Social-Attention
DTO, malformed decoration fails soft without repair, and backend/calibration identity
is stripped before model reasoning. Reflection learns forward. These are source
claims only; no new target evidence is implied.

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
- online semantic repair chains, reviewer-of-reviewer flows, and repair-of-repair;
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
Docs-first design is complete. Next source work is Response/Social-Expression
authority cleanup, meaningful Fast/Deep escalation, and deletion of remaining
duplicate writable semantic truth or reviewer/repair chains. Do not add a new
top-level layer. Historical target evidence remains revision-bound.
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
[Turn Loop](docs/COGNITIVE_TURN_LOOP.md) · [Roadmap](ROADMAP.md) ·
[Status](docs/STATUS.md) · [Target Evidence](docs/TARGET_EVIDENCE_CLOSURE.md) ·
[API](docs/API_REFERENCE.md) · [Runbook](CHROMIE_RUNBOOK.md).
