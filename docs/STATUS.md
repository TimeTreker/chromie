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
| Implementation | One Planner ([PLANNER-AUTHORITY-001](PROJECT_CHARTER.md)): need-first Work begins with `ability_needs`; a non-fitting need triggers one Agent library search and one more plan; with no usable Capability the Planner reports an honest `unavailable` limitation. The Deep Planner, `/deep-plan` and escalation are retired. Value Judgment (VALUE-JUDGMENT-001, `POST /value-judgment`) reviews the turn's first Plan, and any later re-entry Plan in the turn that adds a not-yet-judged Capability listed in `capabilities/value_review.json` (an already judged one reuses its verdict); `ask` adds a confirmation, `decline` or any failure withholds the reviewed effects before provider start. Social Cognition owns every user-facing Communicative Activity. While a Responsibility UMI marked `value_review` waits for Value Judgment, ingress admits only an acknowledgement for its whole turn and sibling speech is answered after the verdict; a value-reviewed Capability alone does not hold back sibling speech. An information Responsibility with citable current perception may be answered from that cited observation. Native decoders serialize mandatory members first: each Responsibility decided work or clarify opens the Planner's counted Activities with its own Activity, and Social Cognition's first act names every result need that must be said now. An information Responsibility that current perception could answer first states its answer source, then its observations. |
| Automatic verification | Canonical gate (`./scripts/run_tests.sh`, clean worktree) on the RTX 5090 host (2026-10-20) with this delivery's repairs: pytest 3,990 passed + 5 skipped (`xgrammar` not installed), benchmarks 172, legacy Agent tests 20; policies, docs, test ownership, ruff, mypy and runtime-structure ratchets pass. Workflow corpus freeze 45 (`019d7726…`) unchanged: the streaming Planner and Social Cognition request formats this delivery changes are not stored in it; strict replay with zero model calls: `scripts/run_workflow_replay.py` 6,000 cases passed, verdict counts equal to freeze 45. The replay corpus runs with an empty value-review list, so it has no Value Judgment coverage. |
| Target validation | Everyday live-text cohort `scenarios/everyday/` (70 cases: 15-case `must_pass` smoke stage, then `core` and `challenge`) on Soridormi MuJoCo. Latest complete-stage live run (2026-10-20, Agent `answer-source-20261020`, Host playback fix, Soridormi `51a2afa`): smoke 15/15 hard-pass and judged correct; core stopped at its 18th case on a transient Open-Meteo timeout (12/18 hard-pass; semantic failures in open work 2); challenge not run. A rerun was stopped at the owner's request after 9 smoke passes. Slow (simple turns 33-41 s, water errand 164 s). Not qualified. No current-revision supervised physical audio or robot evidence (one historical physical voice turn is recorded in [Acceptance](ACCEPTANCE.md)). |
| Deployment state | Live Agent: `chromie-agent:latest` = `answer-source-20261020`, built from the source this delivery records; source identity verified. Soridormi MCP runs Soridormi `main`, which contains the pinned `51a2afa`. GPU smoke 17/17. LLM serving uses SGLang per the maintained [hardware profiles](../HARDWARE_PROFILES.md). No release. Exact identities and commands: [Handoff](../HANDOFF.md). |

Evidence: `.chromie/acceptance/playback-race-20261020/` (latest), `answer-source-20261020/`, `gaze-turn-20261020/`, `said-now-20261020/`, `decided-activity-20261020/` and `main-03974435e-20261020/` (README.md in each); earlier runs `.chromie/acceptance/everyday-20261016/`.

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

1. Complete the everyday cohort: the latest run stopped at `multi_topic_switch_zh` on a
   transient weather-provider timeout; rerun the complete cohort, then challenge.
2. Known live defects: celebrate (UMI may fold the celebration into speech, the
   Planner may wave instead, SC echoes "一起庆祝"); "去那边等我" walks while asking where;
   "blink twice" is declined as unsupported; "Yes, please" after a water-or-milk offer
   promises water then asks which; a conversation-settled "那个" is still asked about;
   hug gestures before asking who; wording: time with date and seconds, "在你的身后" for
   Chromie's own back, device-like "我没有播放音乐的功能", a homework decline offering
   help Chromie cannot give. The corpus has no SC step or perceived-answer turn.
3. Constrained Planner decoding runs about 12-15 tokens/s in grammar-heavy regions,
   so a second Planner pass can miss the turn deadline.
4. Review the SC fresh-turn silence finding; qualify
   Schema/DTO/native grammar, SC context budget and latency, provider scene and
   geographic Evidence, and Goal/action/provenance coverage.
5. After the cohort: narrow current-revision voice proof, then the default
   [target-evidence profile](TARGET_EVIDENCE_CLOSURE.md). Physical microphone,
   speaker and robot evidence stays supervised; text, discarded TTS and simulated
   acquisition do not replace it.

## Evidence interpretation

Historical source tests, automatic passes or owner-reported audio remain bound to
their original revisions; none establish current target validation. A planned
observation, acknowledgement or safe idle alone is never task completion.
