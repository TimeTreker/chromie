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
| Implementation | One Planner ([PLANNER-AUTHORITY-001](PROJECT_CHARTER.md)): need-first Work begins with `ability_needs`; a non-fitting need triggers one Agent library search and one more plan; with no usable Capability the Planner reports an honest `unavailable` limitation. The Deep Planner, `/deep-plan` and escalation are retired. Value Judgment (VALUE-JUDGMENT-001, `POST /value-judgment`) reviews the turn's first Plan, and any later re-entry Plan in the turn that adds a not-yet-judged Capability listed in `capabilities/value_review.json` (an already judged one reuses its verdict); `ask` adds a confirmation, `decline` or any failure withholds the reviewed effects before provider start. Social Cognition owns every user-facing Communicative Activity. While a Responsibility UMI marked `value_review` waits for Value Judgment, ingress admits only an acknowledgement for its whole turn and sibling speech is answered after the verdict; a value-reviewed Capability alone does not hold back sibling speech. An information Responsibility with citable current perception may be answered from that cited observation. Native decoders serialize mandatory members first: each Responsibility decided work or clarify opens the Planner's counted Activities with its own Activity, and Social Cognition's first act names every result need that must be said now. An information Responsibility that current perception could answer first states its answer source, then its observations. Evidence re-entry with up to two Goals lets new Work belong only to Goals decided execute. A newer perception observation replaces the one it supersedes in Situation. UMI understands a bodily need told without a request ("I'm really thirsty") as asking for help Chromie could give, so SC offers it; Situation carries each perceived object's identity and position as separate interpretations of one subject. Value Judgment's facts narrow what follows (a concern about someone else needs someone else affected; no concern decides proceed), and it asks before taking another family member's personal things. Ingress Social Cognition may ask right away about a meaning uncertainty UMI listed for a task, and that question stands until the person answers (no goal_state Social Cognition for the same Responsibilities in that turn); before a task's Evidence or a supplied need, Social Cognition speaks of it only as received, being checked or in progress at every moment. The Fast decoder writes every declared temporal-scope realization and repetition count; a read-only Plan starts no Work-state Social Cognition call; words said before Work Evidence cannot cover the need that reports it; a stated preference is kept once its words have played, and the reply language defers to a kept language preference; a `respond` outcome that leaves its own Goal unmet with no Work or named gap is a contract failure, so a failed GA revision keeps the first Plan; a GA result whose new Goal only links to finished Goals leaves the running Plan in force; an outcome citation that misses its value is re-anchored to the value's single run in that outcome; an acknowledgement said before an answer cannot be reused to cover it. SenseVoice's own emotion and notable-sound cues (`voice_cues`) reach Social Cognition with their utterance and shape only its tone. The Mind's personality and social expression are one configurable character style (`config/mind/character_styles.json`); the factory Chromie is `lively_cute` with the `lively` expression preset. |
| Automatic verification | Canonical gate (`./scripts/run_tests.sh`, clean worktree, RTX 5090 host, 2026-10-27) on this delivery's source: pytest 4,072 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; every policy, docs, test ownership, ruff, mypy and runtime-structure check passes. Every Social Cognition response-schema shape the Host builds (300 request combinations) compiles on the live SGLang/XGrammar (2026-10-23, committed source). Workflow corpus freeze 47 (`bdb8db08…`) is unchanged: the corpus has no Social Cognition or Value Judgment step and no scene perception; strict replay `scripts/run_workflow_replay.py` 6,000 cases passed on freeze 47 with unchanged verdicts (2026-10-21). |
| Target validation | Everyday live-text cohort `scenarios/everyday/` (119 cases: a 15-case `must_pass` smoke stage, 93 `core` and 11 `challenge` cases, 50 of them written for three buyer personas; one more in `scenarios/model_limited/`) on Soridormi MuJoCo with local gemma4 12B in quiet mode (raised timeouts). Latest cohort (2026-10-27, `.chromie/acceptance/it3-person-20261027/cohort/`, fabf2c910): stopped at 89/119 on a hard integrity failure (a streaming Planner decoder state, repaired in owner loop 2 iteration 4); smoke 15/15; core 71/74 automatic and 61/74 judged (63/74 once two acceptance-oracle defects are corrected); challenge not reached. Open judged failures: a delivered bottle described as poured water, praise for a drawing or shirt Chromie cannot see, abilities she lacks in her self-description, no offer of company for boredom or loneliness, a wave without a greeting, an echoed celebration. Compound fetch-and-read turns take 344-490 s. Previous complete cohorts: loop 1 iteration 8 (`iter8-20261026/`, 9358ba34c, the 69-case library) 69/69 automatic and 65/69 judged; acc1 (2026-10-24) smoke 15/15, core 44/50, challenge 3/5. First audio p50 28.2 s in quiet mode (iter8), about 20 s in performance mode. Not qualified. No current-revision supervised physical audio or robot evidence (one historical physical voice turn is recorded in [Acceptance](ACCEPTANCE.md)). |
| Deployment state | Live Agent: `chromie-agent:latest`, built from the source the latest delivery records and deployed with the quiet-mode timeout overrides; its exact image, digest and source-identity check are kept only in the [Handoff](../HANDOFF.md). Soridormi MCP runs Soridormi `main`, which contains the pinned `51a2afa`. GPU smoke 17/17. LLM serving uses SGLang per the maintained [hardware profiles](../HARDWARE_PROFILES.md). No release. Exact identities and commands: [Handoff](../HANDOFF.md). |

Evidence: `.chromie/acceptance/it4-cues-20261027/` (latest), `it3-person-20261027/`, `it2-ground-20261027/`, `it1-memory-20261026/`, `iter8-20261026/` (last complete cohort) and `acc1-20261024/` (README.md in each); the [Handoff](../HANDOFF.md) lists every retained evidence directory.

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

1. The owner's 8-iteration loop is complete (iteration 8: 69/69 automatic, 65/69 judged). Per the owner, 50 persona cases were
   added on 2026-10-26 (119 cases); their first cohort stopped at 30/119 on a weather read for an invented
   place. Read-only tools now declare an unservable request (no such place or period, no result) as an honest
   non-completion, so the runner judges such a case. Its rerun (`personas2-20261026/`, b78e89457) stopped at 10/119
   on an open-meteo geocoding timeout (a service failure). Owner loop 2 (6 iterations, 2026-10-26): Chromie keeps a lasting fact the person tells
   about themselves (where they work) the way a friend would, with no "要我记住吗？" question (owner decision
   2026-10-27, Charter amended), bound to that person (`person:primary` until speaker identification) and kept as
   profile Memory; a later conversation used it for "明天早上上班要不要带伞？". A cross-script value stands only where a
   served outcome or a kept fact states it, and a required read input that no source states is asked for instead of
   read. Iteration 2's cohort stopped at 70/119 (GA decoded a free-form binding change; fixed with empty impossible
   arrays): smoke 15/15, core 47/55 judged. Iteration 3 also takes "嘘，安静一会儿" as silence and cites a place the
   person said earlier in the same turn. The streaming Planner still decides
   work with an assumed place for an unstated workplace (clarify trails by 12-15 nats; four prompt and decision-field
   probes moved nothing); the owner wants Chromie to ask where the person works and remember it. Open judged failures: "Say hi to my friend with a
   wave!" waves without a greeting; "你都会做些什么呀？" describes chatting and small tasks rather than real abilities;
   "是不是十二？" is confirmed for 5 + 3; "半分钟后跟我挥挥手说再见。" waves at once. The lively style did not raise
   expression use.
2. Invention and Evidence fidelity: `cap_what_can_you_do_zh` claims chatting, research and planning (a trusted
   ability list plus a general rule changed nothing in 3 replays, not adopted); `long_math_help_zh` gives a
   question now but confirms "十二" for 15 + 27; `timer_wave_bye_zh` waves at once (the need list drops the delay,
   and the streaming Planner contract has no time condition); a cross-turn "那上海呢？" chose today by about 5.5 nats in replay,
   though it chose tomorrow in both live runs since.
3. Known live defects: an offer of "something to drink" leaves "Yes, please" asking which drink;
   SC echoes the person's words (celebrate: the Planner waves instead and SC echoes "快跟我一起庆祝一下！"); "Say hi to my
   friend with a wave!" waves without the greeting; Value Judgment no longer asks where to wait (it was standing in
   for a Planner clarification); a conversation-settled "那个" is still asked about; with no offer made, "Yes,
   please" takes the first-listed perceived object (known gemma4 12B limit, owner 2026-10-21); the
   Value Judgment facts list scene objects and positions as separate strings; wording: time
   with date and seconds, weather read out in fragments with the date, "好的。" before a refusal,
   "我没看清楚" when both bottles are in view, device-like "设置提醒或闹钟的功能". The corpus has
   no SC step or perceived-answer turn. A GA-requested re-plan still replaces the first Plan rather than revising
   it (owner decision 2026-10-08); only a self-contradictory revision is now rejected.
4. The same request can change a near-tie decision between `chromie-llm` restarts (about 3 nats
   observed), and within one lifetime after other traffic (2026-10-23: the unchanged coffee request
   worded its need "brew a cup of coffee", then after probe calls "walk to a physical object and
   deliver it", which fits a fetch); measure logprob margins across restarts before a prompt repair
   claims stability, and start cohorts on a fresh lifetime.
5. Constrained Planner decoding runs about 12-15 tokens/s in grammar-heavy regions,
   so a second Planner pass can miss the turn deadline.
6. Review the SC fresh-turn silence finding; qualify
   Schema/DTO/native grammar, SC context budget and latency, provider scene and
   geographic Evidence, and Goal/action/provenance coverage.
7. After the cohort: narrow current-revision voice proof, then the default
   [target-evidence profile](TARGET_EVIDENCE_CLOSURE.md). Physical microphone,
   speaker and robot evidence stays supervised; text, discarded TTS and simulated
   acquisition do not replace it.

## Evidence interpretation

Historical source tests, automatic passes or owner-reported audio remain bound to
their original revisions; none establish current target validation. A planned
observation, acknowledgement or safe idle alone is never task completion.
