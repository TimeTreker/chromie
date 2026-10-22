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
| Implementation | One Planner ([PLANNER-AUTHORITY-001](PROJECT_CHARTER.md)): need-first Work begins with `ability_needs`; a non-fitting need triggers one Agent library search and one more plan; with no usable Capability the Planner reports an honest `unavailable` limitation. The Deep Planner, `/deep-plan` and escalation are retired. Value Judgment (VALUE-JUDGMENT-001, `POST /value-judgment`) reviews the turn's first Plan, and any later re-entry Plan in the turn that adds a not-yet-judged Capability listed in `capabilities/value_review.json` (an already judged one reuses its verdict); `ask` adds a confirmation, `decline` or any failure withholds the reviewed effects before provider start. Social Cognition owns every user-facing Communicative Activity. While a Responsibility UMI marked `value_review` waits for Value Judgment, ingress admits only an acknowledgement for its whole turn and sibling speech is answered after the verdict; a value-reviewed Capability alone does not hold back sibling speech. An information Responsibility with citable current perception may be answered from that cited observation. Native decoders serialize mandatory members first: each Responsibility decided work or clarify opens the Planner's counted Activities with its own Activity, and Social Cognition's first act names every result need that must be said now. An information Responsibility that current perception could answer first states its answer source, then its observations. Evidence re-entry with up to two Goals lets new Work belong only to Goals decided execute. A newer perception observation replaces the one it supersedes in Situation. UMI understands a bodily need told without a request ("I'm really thirsty") as asking for help Chromie could give, so SC offers it; Situation carries each perceived object's identity and position as separate interpretations of one subject. Value Judgment's facts narrow what follows (a concern about someone else needs someone else affected; no concern decides proceed), and it asks before taking another family member's personal things. Ingress Social Cognition may ask right away about a meaning uncertainty UMI listed for a task; before a task's Evidence or a supplied need, Social Cognition speaks of it only as received, being checked or in progress at every moment. |
| Automatic verification | Canonical gate (`./scripts/run_tests.sh`, clean worktree) on the RTX 5090 host (2026-10-22) with this delivery: pytest 4,005 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets pass. Every Social Cognition response-schema shape the Host builds (300 request combinations) compiles on the live SGLang/XGrammar. Workflow corpus freeze 47 (`bdb8db08…`) is unchanged: the corpus has no Social Cognition or Value Judgment step and no scene perception; strict replay `scripts/run_workflow_replay.py` 6,000 cases passed on freeze 47 with unchanged verdicts (2026-10-21). |
| Target validation | Everyday live-text cohort `scenarios/everyday/` (70 cases: 15-case `must_pass` smoke stage, then `core` and `challenge`) on Soridormi MuJoCo, local gemma4 12B in quiet mode (CPU turbo off, GPU clocks locked and power capped, raised timeouts). Latest runs (2026-10-22): on `ad898cf7f` must_pass 14/15 (ingress asked "which one?" inside an acknowledgement); with this delivery's ingress question smoke 15/15 and core 27/32, stopped by a raw tab in Planner JSON (repaired); with every repair in this delivery smoke 15/15 and core 22/29, stopped at `info_umbrella_zh` when the Planner cited another Responsibility's words (open work 1); challenge not run. Slow in quiet mode (simple turns 45-60 s, water errand 190 s). Not qualified. No current-revision supervised physical audio or robot evidence (one historical physical voice turn is recorded in [Acceptance](ACCEPTANCE.md)). |
| Deployment state | Live Agent: `chromie-agent:latest` = `sc-evidence-20261022` (`2eadc0bbc248`), built from the source this delivery records, with the quiet-mode timeout override; source identity verified. Soridormi MCP runs Soridormi `main`, which contains the pinned `51a2afa`. GPU smoke 17/17. LLM serving uses SGLang per the maintained [hardware profiles](../HARDWARE_PROFILES.md). No release. Exact identities and commands: [Handoff](../HANDOFF.md). |

Evidence: `.chromie/acceptance/sc-evidence-20261022/` (latest), `sc-ask-uncertain-20261022/`, `main-ad898cf7f-20261022/`, `vj-facts-20261021/`, `thirsty-offer-20261021/` (freeze 47 scripts in `freeze47/`), `main-6f8525947-quiet-20261021/`, `umi-time-margin-20261021/`, `main-3178a822c-20261021/` (freeze 46 scripts), `playback-race-20261020/`, `answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`, `decided-activity-20261020/` and `main-03974435e-20261020/` (README.md in each); earlier runs `.chromie/acceptance/everyday-20261016/`.

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

1. Social Cognition after an ingress question: a later turn of the same request read Chromie's own
   question "你是说那个牛奶瓶吗？" as the person's answer ("是的，就是那个。") and, covering the
   Planner's clarify need, promised "好的，我这就拿给你。" with no answer and no fetch. The question
   asked at ingress must count as asked and awaiting the person until they answer. Then the
   Planner choosing `unavailable` for an uncertain referent whose ability need fits; the Planner
   citing another Responsibility's words (`info_umbrella_zh` hard stop); rerun the complete cohort.
2. Known live defects: an offer of "something to drink" leaves "Yes, please" asking which drink;
   SC echoes the person's question before answering; celebrate (the Planner waves instead, SC echoes "一起庆祝"); "Say hi to my
   friend with a wave!" waves without the greeting since the need-report UMI wording; "去那边等我"
   may walk, and Value Judgment no longer asks where (it was standing in for a Planner
   clarification); "blink twice" is declined as unsupported; "点两下头" nods without
   the count; a conversation-settled "那个" is still asked about; with no offer made, "Yes, please"
   takes the first-listed perceived object (known gemma4 12B limit, owner 2026-10-21); the
   Value Judgment facts list scene objects and positions as separate strings; wording: time
   with date and seconds, weather read out in fragments with the date, "好的。" before a refusal,
   "我没看清楚" when both bottles are in view, device-like "设置提醒或闹钟的功能". The corpus has
   no SC step or perceived-answer turn.
3. The same request can change a near-tie decision between `chromie-llm` restarts (about 3 nats
   observed); measure logprob margins across restarts before a prompt repair claims stability.
4. Constrained Planner decoding runs about 12-15 tokens/s in grammar-heavy regions,
   so a second Planner pass can miss the turn deadline.
5. Review the SC fresh-turn silence finding; qualify
   Schema/DTO/native grammar, SC context budget and latency, provider scene and
   geographic Evidence, and Goal/action/provenance coverage.
6. After the cohort: narrow current-revision voice proof, then the default
   [target-evidence profile](TARGET_EVIDENCE_CLOSURE.md). Physical microphone,
   speaker and robot evidence stays supervised; text, discarded TTS and simulated
   acquisition do not replace it.

## Evidence interpretation

Historical source tests, automatic passes or owner-reported audio remain bound to
their original revisions; none establish current target validation. A planned
observation, acknowledgement or safe idle alone is never task completion.
