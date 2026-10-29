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
| Implementation | One Planner ([PLANNER-AUTHORITY-001](PROJECT_CHARTER.md)): need-first Work begins with `ability_needs`; a non-fitting need triggers one Agent library search and one more plan; with no usable Capability the Planner reports an honest `unavailable` limitation. The Deep Planner, `/deep-plan` and escalation are retired. Value Judgment (VALUE-JUDGMENT-001, `POST /value-judgment`) reviews the turn's first Plan, and any later re-entry Plan in the turn that adds a not-yet-judged Capability listed in `capabilities/value_review.json` (an already judged one reuses its verdict); `ask` adds a confirmation, `decline` or any failure withholds the reviewed effects before provider start. Social Cognition owns every user-facing Communicative Activity. While a Responsibility UMI marked `value_review` waits for Value Judgment, ingress admits only an acknowledgement for its whole turn and sibling speech is answered after the verdict; a value-reviewed Capability alone does not hold back sibling speech. An information Responsibility with citable current perception may be answered from that cited observation. Native decoders serialize mandatory members first: each Responsibility decided work or clarify opens the Planner's counted Activities with its own Activity, and Social Cognition's first act names every result need that must be said now. An information Responsibility that current perception could answer first states its answer source, then its observations. Evidence re-entry with up to two Goals lets new Work belong only to Goals decided execute. A newer perception observation replaces the one it supersedes in Situation. UMI understands a bodily need told without a request ("I'm really thirsty") as asking for help Chromie could give, so SC offers it; Situation carries each perceived object's identity and position as separate interpretations of one subject. Value Judgment's facts narrow what follows (a concern about someone else needs someone else affected; no concern decides proceed), and it asks before taking another family member's personal things. Ingress Social Cognition may ask right away about a meaning uncertainty UMI listed for a task, and that question stands until the person answers (no goal_state Social Cognition for the same Responsibilities in that turn); before a task's Evidence or a supplied need, Social Cognition speaks of it only as received, being checked or in progress at every moment. The Fast decoder writes every declared temporal-scope realization and repetition count; a read-only Plan starts no Work-state Social Cognition call; words said before Work Evidence cannot cover the need that reports it; a stated preference is kept once its words have played, and the reply language defers to a kept language preference; a `respond` outcome that leaves its own Goal unmet with no Work or named gap is a contract failure, so a failed GA revision keeps the first Plan; a GA result whose new Goal only links to finished Goals leaves the running Plan in force; an outcome citation that misses its value is re-anchored to the value's single run in that outcome; an acknowledgement said before an answer cannot be reused to cover it unless it replied to that speech Responsibility, and a fresh activity ID never extends a retained one. Reminders get an honest limitation (the iteration-5 `chromie.memory.keep` was removed: the local Planner planned every reminder as a keep); a handover's result need names what was handed over; a read merged across Responsibilities cites the value the person said from the first served outcome holding it once. SenseVoice's own emotion and notable-sound cues (`voice_cues`) reach Social Cognition with their utterance and shape only its tone. The Mind's personality and social expression are one configurable character style (`config/mind/character_styles.json`); the factory Chromie is `lively_cute` with the `lively` expression preset. |
| Automatic verification | Canonical gate (`./scripts/run_tests.sh`, clean worktree, RTX 5090 host, 2026-10-29) on this delivery's source: pytest 4,113 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; every policy, docs, test ownership, ruff, mypy and runtime-structure check passes. Every Social Cognition response-schema shape of the running-skill set (600 request combinations) compiles on the live SGLang/XGrammar (2026-10-29). Workflow corpus freeze 48 (`35403e5d…`) recaptures every UMI request for the remembering repair; strict replay `scripts/run_workflow_replay.py` 6,000 cases passed on freeze 48 with unchanged verdicts (2026-10-29). The corpus has no Social Cognition or Value Judgment step and no scene perception. |
| Target validation | Everyday live-text cohort `scenarios/everyday/` (124 cases: a 15-case `must_pass` smoke stage, 98 `core` and 11 `challenge` cases; two more in `scenarios/model_limited/`) on Soridormi MuJoCo with local gemma4 12B in quiet mode (raised timeouts). Latest complete cohort (2026-10-29, `.chromie/acceptance/loop1-20261029/cohort/`, 1f7954402, no hard stop): 119/124 automatic; judged smoke 15/15, core 84/98, challenge 6/11; counting a reply played twice as a failure (found that day in 19 of 156 sessions with speech; the user-outcome view had merged identical texts) smoke 13/15, core 74/98, challenge 4/11. Open judged failures: comfort phrased as a question (boredom, a scraped knee, loneliness); praise for a drawing or shirt Chromie cannot see and abilities she lacks; denying the attention she has just stopped; the water's position read from the milk's row; a wave without a greeting; 5 + 3 confirmed as 12; a delayed goodbye wave done at once; watching a younger brother answered with a look; a favourite food named; the umbrella turn that names the city skips the read. First audio p50 30.8 s; ingress Social Cognition p50 15.7 s (13.9 s before the long-running skill). Not qualified. No current-revision supervised physical audio or robot evidence (one historical physical voice turn is recorded in [Acceptance](ACCEPTANCE.md)). |
| Deployment state | Live Agent: `chromie-agent:latest`, built from the source the latest delivery records and deployed with the quiet-mode timeout overrides; its exact image, digest and source-identity check are kept only in the [Handoff](../HANDOFF.md). Soridormi MCP runs Soridormi `main` at the pinned `a49a87f`, whose scene observation marks the current speaker and which runs the long-running skill `attend_to_person`. GPU smoke 17/17. LLM serving uses SGLang per the maintained [hardware profiles](../HARDWARE_PROFILES.md). No release. Exact identities and commands: [Handoff](../HANDOFF.md). |

Evidence: `.chromie/acceptance/it6-final-20261028/` (latest), `it5-keep-20261027/`, `it4-cues-20261027/`, `it3-person-20261027/`, `it2-ground-20261027/`, `it1-memory-20261026/`, `iter8-20261026/` (last complete cohort) and `acc1-20261024/` (README.md in each); the [Handoff](../HANDOFF.md) lists every retained evidence directory.

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

1. Owner loop 3 (2026-10-28: up to 18 turns; my recommendations decide; commit and push each turn). Turn 1:
   asking Chromie to remember what the person tells her is speech, not a `stateful_effect`; the applied output
   stop reaches UMI as a trusted fact; a turn left silent because Work outran Social Cognition gets one more
   decision; a reply to a speech Responsibility is re-cited instead of spoken again; an expression target states
   its source first; a decoration the Runtime never ran keeps its provenance. Focused live runs pass the targeted
   cases (diagnostic). Its cohort (68d97c9e7) ran smoke 15/15 with no repeated reply and stopped at 41/124: a
   deliberation while the skill ran failed its own schema (turn 2 fixes it: deliberation leaves the skill
   decision empty). A cited-observation projection for the water question was replayed and not shipped (the
   original answers correctly in a new lifetime; a memory citation lost its answer). Still open from earlier loops: the streaming Planner decides
   work with an assumed place for an unstated workplace; a note kept across conversations waits in
   `scenarios/model_limited/`.
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
