# Chromie Current Status

This file is the single current-state owner for implementation, verification,
target validation and deployment status. It holds current facts only; replace a
row when it changes. Per-delivery history belongs in Git history and
[CHANGELOG](../CHANGELOG.md); private run notes stay with their evidence under
`.chromie/acceptance/*/README.md`. The current focus remains the Goal-driven
single-authority architecture.

## Current state

| Axis | Current evidence |
| --- | --- |
| Implementation | One Planner ([PLANNER-AUTHORITY-001](PROJECT_CHARTER.md)): need-first Work begins with `ability_needs`; a non-fitting need triggers one Agent library search and one more plan; with no usable Capability the Planner reports an honest `unavailable` limitation. The Deep Planner, `/deep-plan` and escalation are retired. Value Judgment (VALUE-JUDGMENT-001, `POST /value-judgment`) reviews the turn's first Plan, and any later re-entry Plan in the turn that adds a not-yet-judged Capability listed in `capabilities/value_review.json` (an already judged one reuses its verdict); `ask` adds a confirmation, `decline` or any failure withholds the reviewed effects before provider start. Social Cognition owns every user-facing Communicative Activity; while a turn waits for Value Judgment, ingress admits only an acknowledgement. An information Responsibility with citable current perception may be answered from that cited observation. Latest repair on `main`: UMI lists Responsibilities in word order and ends a reply to news where the sharing ends. |
| Automatic verification | Last recorded canonical gate (`./scripts/run_tests.sh`, clean worktree, latest delivery): pytest 3,845 passed + 5 skipped, benchmarks 169, legacy Agent tests 20, policies, docs and test ownership pass. Workflow corpus freeze 41 (`a36b1ebf…`); strict replay 6,000/6,000 with zero model calls. The replay corpus runs with an empty value-review list, so it has no Value Judgment coverage. |
| Target validation | Everyday live-text cohort `scenarios/everyday/` (70 cases: 15-case `must_pass` smoke stage, then `core` and `challenge`) on Soridormi MuJoCo. Latest live runs on `rootcause18-20261016`: smoke 15/15 mechanical; core stopped at 4/55 on a hard UMI 503 that the latest repair addresses but which is not yet live. Core and challenge have not completed. Not qualified. No current-revision supervised physical audio or robot evidence (one historical physical voice turn is recorded in [Acceptance](ACCEPTANCE.md)). |
| Deployment state | `chromie-agent:latest` = `rootcause18-20261016`; `rootcause19-20261016` (latest repair) built, not deployed. LLM serving uses SGLang per the maintained [hardware profiles](../HARDWARE_PROFILES.md). No release. Exact identities and commands: [Handoff](../HANDOFF.md). |

Evidence: `.chromie/acceptance/everyday-20261016/` (README.md).

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

Follow the [Roadmap migration order](../ROADMAP.md#social-cognition-migration)
and the [checkpoint](../DEVELOPMENT_CHECKPOINT.md).

1. Deploy the latest Agent image and complete the everyday cohort: smoke, then
   `core` and `challenge`.
2. Known live defects: the homework decline offers reminders Chromie cannot set;
   "去那边等我" is acknowledged with "好的。" although no go-to-a-place ability exists;
   Value Judgment asks consent or meaning questions that belong elsewhere (hug);
   SC echoes the user's words (celebrate). The corpus has no SC step or
   perceived-answer turn; replays and unit tests cover them.
3. Constrained Planner decoding runs about 12-15 tokens/s in grammar-heavy regions,
   so a second Planner pass can miss the turn deadline.
4. Review the SC fresh-turn silence finding; qualify
   Schema/DTO/native grammar, SC context budget and latency, provider scene and
   geographic Evidence, and Goal/action/provenance coverage.
5. Narrow current-revision voice proof and the default
   [target-evidence profile](TARGET_EVIDENCE_CLOSURE.md). Physical evidence stays supervised.

## Evidence interpretation

Historical source tests, automatic passes or owner-reported audio remain bound to
their original revisions; none establish current target validation. A planned
observation, acknowledgement or safe idle alone is never task completion.
