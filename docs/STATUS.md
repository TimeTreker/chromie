# Chromie Current Status

This file is the single current-state owner for implementation, verification,
target validation and deployment status, and the single ordered open-work list.
It holds current facts only; replace a
row when it changes. Per-delivery history belongs in Git history and
[CHANGELOG](../CHANGELOG.md); private run notes stay with their evidence under
`.chromie/acceptance/*/README.md`. The current focus remains the Goal-driven
single-authority architecture.

## Current state

| Axis | Current evidence |
| --- | --- |
| Implementation | Branch `codex/sc-context-budget-failure-notice` retains SC identity-Schema/budget and text failure-notice repairs, primary coverage/delivered-Goal joins, pending-review guard, Planner Work/speech need-first guidance, shared ability-needs Schema and single-visit Schema transformations. Native-prefix cancellation and UMI-handoff timing evidence are corrected; two inherited test oracles bind explicit profiles. Semantic owners, model and budgets are unchanged. The two later UMI candidates were rejected and reverted. |
| Automatic verification | Retained exact source: canonical 172 benchmarks; 4,168 main tests / 5 skipped / 1,007 subtests; 20 legacy Agent tests pass. Policies (15 families, zero exceptions), pinned Ruff, mypy, ownership and docs pass. Four Level A classes: 16 unique checks pass. Strict 6,000-case architecture replay passes with zero native model calls. Freeze 49 changes only reviewed requests, preserving references and exact matching. |
| Target validation | NOT qualified. Candidate-5 milk/rain focus passes with both Goals done. Full 124-case cohort: six complete / one interrupted / 117 unstarted; six automatic passes but manual five pass / one ordering failure. Ten original user inputs: 10 automatic passes; manual six pass / two partial / two fail; no overflow or silence, but food context remains wrong. New assistant replies differ from the original transcript, so its exact promise chain is not qualified. Ten-total-iteration limit reached; no overall nonregression, physical audio, robot or release claim. |
| Deployment state | Final Agent `6ef83c7fb9c0`, image `2637a60e0286`, packaged-source digest `45a20786a43c` verified. Source tree exactly restored to candidate 5 before final replay. Gemma4 12B container `417cc0e6dee7` / image `6b73a8a988ac`, runtime profile and deadlines unchanged. Text/discarded-TTS/MuJoCo evidence only; pinned Soridormi `a49a87f`. Commit/push of the working branch authorized; main merge is not authorized. |

Current private evidence and detailed report: `.chromie/acceptance/optimize-20261106-extended/README.md`;
earlier three iterations: `.chromie/acceptance/optimize-20261106/`; originating repair:
`.chromie/acceptance/sc-context-budget-20261102/`. Ignored evidence is retained locally,
not included in Git. [Handoff](../HANDOFF.md) owns exact identities, results and commands.

## Social Cognition migration

The accepted [Charter target](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
remains the authority: SC decides whether, when and how to communicate; Planner
selects Capabilities and resolves execution inputs. Ordinary Planner-authored speech,
optional Planner decoration and the former streaming presentation contract are retired.
A fresh addressed turn wakes SC mechanically; UMI requests only non-standing
cognition. Planner is model-selected; Runtime cannot infer activation from task words.
GA output does not author new Goal meaning: Host preserves exact UMI WHAT when
materializing identity-only `new_goals` rows. `turn` is Goal lifetime, not a no-Goal routing rule.
UMI preserves complete WHAT and cannot author bindings; Planner owns parameter
extraction and contextual provenance.

This describes current intended ownership, not full conformance; see the open work below.

## Component implementation and qualification

| Existing owner | Source state and current proof limit |
| --- | --- |
| [Gateway](COGNITIVE_GATEWAY.md) / Host admission | Deterministic protective controls and immutable admitted turn exist. Attention Review makes one call and suppresses only confident inactive ambient speech. Physical audio admission needs source-bound proof. |
| [Turn lifecycle](COGNITIVE_TURN_LOOP.md) / Cognitive Runtime | Concurrent SC and GA/Work, exact identity, cancellation, prerequisite joins and Evidence re-entry exist. Text admission chronology is repaired and mechanically proved; native coverage and latency remain open. |
| [Semantic authorities](SEMANTIC_AUTHORITY.md) / UMI, GA, Planner, Value Judgment, SC | Source ownership migration is implemented; preserved original wording is authoritative. Native coverage remains unqualified. |
| [Agent Skills](AGENT_SKILLS_ARCHITECTURE.md) / Planner and registry | Semantic methods, Capability contracts and need-first library search exist. Frozen references are not independent native-model qualification. |
| [Execution lanes](EXECUTION_LANES_AND_COORDINATION.md) / Trusted Runtime | Confirmation, cancellation, coordination, provider truth and safe-idle contracts remain blocking. No permission comes from premature speech. |
| [Resource acquisition](RESOURCE_ACQUISITION_AND_DELIVERY.md) / providers | Provider-owned source resolution is implemented; observed object/pose and mixed-place qualification remain gaps. Simulator handover does not prove real acquisition. |
| [Cognitive architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md) / retained state | Goal continuity, scoped re-entry, Memory and mechanical time wake exist. |
| [Agent mind and Memory](../agent/README.md) / stable and relational Memory | Stable identity, Stable Mind values and privacy/provenance mechanisms exist. Trusted real-world identity/audience sources and broader live social behavior remain unqualified. |
| [Capability providers](../capabilities/README.md) / Soridormi | Embodied feasibility and safety stay with Soridormi. Simulation perception exists; real camera/person/hardware ingress is incomplete. |
| [Runtime rollout](COGNITIVE_RUNTIME_ROLLOUT.md) / operators | Evidence and fallback machinery remain. |
| [Acceptance](ACCEPTANCE.md) / qualification operators | Frozen cohorts, ability classes and strict failure accounting remain required; local failures cannot be averaged into a release pass. |

## Current open work

This is the single ordered open-work list, blockers included. The
[Roadmap](../ROADMAP.md#social-cognition-migration) owns longer-range delivery
order; the [checkpoint](../DEVELOPMENT_CHECKPOINT.md) owns the active Issue,
repairs and owner decisions in force.

1. Review the branch delivery and retained failures; ten total optimization iterations are
   exhausted. No main merge without owner approval. Local mechanical gates are green, but
   current-target qualification is not. Next behavior work must retain the exact UMI/GA/Planner/SC
   workflow: food context present only in a rationale is not preserved WHAT; speech mode alone
   is not proof Work was wrongly omitted. Preserve order/concurrency across split effects and
   remove the missing-answer parallel-default gap without another semantic author. Also retain
   unselected drink alternatives, SC covered-Need versus act-binding inconsistency,
   refused-Goal lifecycle, current-WHAT preservation and milk-position grounding. The final two
   UMI candidates were rejected (3/8 and 5/8 contrasts) and reverted, not qualified by partial gains.
   A complete immutable cohort or its truthful hard stop, exact-context food workflow and narrow
   current-revision voice proof remain due. Workflow I/O, raw packets and commands:
   [Handoff](../HANDOFF.md).

2. Invention and Evidence fidelity: `cap_what_can_you_do_zh` claims chatting, research and planning (a trusted
   ability list plus a general rule changed nothing in 3 replays, not adopted); `long_math_help_zh` gives a
   question now but confirms "十二" for 15 + 27; `timer_wave_bye_zh` waves at once (the need list drops the delay,
   and the streaming Planner contract has no time condition); a cross-turn "那上海呢？" chose today by about 5.5 nats in replay,
   though it chose tomorrow in both live runs since.
3. Known live defects: an offer of "something to drink" leaves "Yes, please" asking which drink;
   Value Judgment no longer asks where to wait (it was standing in
   for a Planner clarification); a conversation-settled "那个" is still asked about; with no offer made, "Yes,
   please" takes the first-listed perceived object (known gemma4 12B limit, owner 2026-10-21); the
   Value Judgment facts list scene objects and positions as separate strings; wording: time
   with date and seconds, weather read out in fragments with the date, "好的。" before a refusal,
   "我没看清楚" when both bottles are in view, device-like "设置提醒或闹钟的功能". The corpus has
   no SC step or perceived-answer turn. A GA-requested re-plan still replaces the first Plan rather than revising
   it (owner decision 2026-10-08); only a self-contradictory revision is now rejected.
4. Long-running social skill (owner-approved 2026-10-28; [Roadmap](../ROADMAP.md) item 2): implemented
   (Soridormi `a49a87f`, `attend_to_person`; Host `orchestrator/runtime/long_running_social_skill.py`; Social
   Cognition field `social_skill`). Soridormi's scene observation marks the speaking person; the Host copies that
   one mark into trusted target evidence. Social Cognition alone starts the skill, changes its posture and stops it.
   Soridormi gives way to body tasks and ends it 5 s after the person is lost or after 10 minutes; the Host ends it
   on a reflex stop, a new conversation or conversation idle. Live focused runs (diagnostic, 7 cases): the three
   attention cases pass (started on the greeting, suspended during a 201 s fetch and resumed, stopped on
   "别一直盯着我看了"), and the looks suspend and resume it. Restating an unchanged attend cost every Social
   Cognition call about 23 generated tokens (first reply +2.5 s); while the skill runs the decoder now offers
   `keep` instead of `null` or the unchanged attend (offering neither made the model alternate postures). Focused
   reruns: 6/6, 10 of 20 calls `keep`, no alternation. Full cohort (1f7954402): keep 81, attend 59, stop 2,
   null 7 of 149 calls; ingress p50 15.7 s against 13.9 s before, first audio 30.8 s against 28.5 s. Open: the
   speech-to-gaze time on the physical robot and the rate of voices not addressed to Chromie need a supervised
   voice session; the onset-glance reflex waits for those measurements.
5. The same request can change a near-tie decision between `chromie-llm` restarts (about 3 nats
   observed), and within one lifetime after other traffic (2026-10-23: the unchanged coffee request
   worded its need "brew a cup of coffee", then after probe calls "walk to a physical object and
   deliver it", which fits a fetch); measure logprob margins across restarts before a prompt repair
   claims stability, and start cohorts on a fresh lifetime.
6. Constrained Planner decoding runs about 12-15 tokens/s in grammar-heavy regions,
   so a second Planner pass can miss the turn deadline.
7. Review the SC fresh-turn silence finding; qualify
   Schema/DTO/native grammar, SC context budget and latency, provider scene and
   geographic Evidence, and Goal/action/provenance coverage.
8. After the cohort: narrow current-revision voice proof, then the default
   [target-evidence profile](TARGET_EVIDENCE_CLOSURE.md). Physical microphone,
   speaker and robot evidence stays supervised; text, discarded TTS and simulated
   acquisition do not replace it.

## Evidence interpretation

Historical source tests, automatic passes or owner-reported audio remain bound to
their original revisions; none establish current target validation. A planned
observation, acknowledgement or safe idle alone is never task completion.
