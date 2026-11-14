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
| Implementation | Owner-authorized WHAT-only UMI is implemented; Planner owns HOW/Skills and SC owns communication. Existing need-first, provenance, stage isolation, permission and provider concurrency rules remain. This delivery also forwards diagnostic multi-turn continuation, carries trusted quiet controls through both terminal SC paths, respects outstanding ambient-poll cancellation, and retains visited Schema objects to make lossless projection deterministic. Model and budgets are unchanged. GA/Planner semantic candidates were rejected and are not defaults. |
| Automatic verification | Required local gates pass:176 benchmarks /4,361 main /1,042 subtests /20 legacy;5 host xgrammar skips supplemented by30 native controls in the deployed compiler. Policy and docs pass;98 Markdown /15 core readings. Current strict6,000 passes and45 Level A cases pass. Four full native grammar positives and9 negatives pass. Additional9 exact-case native controls yield8 expected decisions and1 unexpected GA terminal-supersede admission; this is an open integrity blocker. These prove only their declared contracts, not native semantic qualification. |
| Target validation | NOT qualified. Before-repair126:automatic105/126, Codex semantic 50 pass /6 partial /70 fail (26 hard-gate failures included); only156/163 main turns were attempted by the old inner loop. Current126:automatic108/126, Codex semantic 53 pass /9 partial /64 fail (26 hard-gate failures included); all163 main turns plus1 during-motion stop were attempted. Current original10/10 inputs reach terminal notifications but food-to-water substitution at Planner10 and duplicate/outdated speech remain. Two additional historically parked cases also finish4/4 admitted turns,0/2 semantic passes; a separate failed startup attempt had0 admissions. All cases were reviewed, including automatic passes. Diagnostic keep-going is explicitly owner-authorized; hard failures stay failed. No owner-human or physical acceptance is claimed. |
| Deployment state | Branch codex/sc-context-budget-failure-notice, pre-delivery HEAD cd038af616b7; expected resume revision is the latest commit containing the three delivery owners. Agent78f7c3f01221/image25f89b77bea3 matches Agent/shared9ee2082fa27d. Model1e5d4ace2318/imageab5368ff1306, ASR/TTS and all effective model/budget settings remain unchanged. Soridormi a49a87f remains clean and unedited. Evidence is deployed services/text/discarded TTS/MuJoCo/mock delivery; no physical proof or release. Branch-only diagnostic delivery is authorized; main merge requires approval. |

Current retained evidence: `.chromie/acceptance/semantic-full-review-20261114/`.
The current126-case table, both aggregate summaries and exact workflow audit are private/local in
`comprehensive-review.md` and `workflow-audit.md`; raw transactions and failed candidates
remain with them. Earlier dirty work and compiler proofs remain under
`meaning-coverage-repair-20261112/` and `sc-context-budget-20261102/`.
[Handoff](../HANDOFF.md) owns exact identities and resume commands.

## Social Cognition migration

The accepted [Charter target](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
remains the authority: SC decides whether, when and how to communicate; Planner
selects Capabilities and resolves execution inputs. Ordinary Planner-authored speech,
optional Planner decoration and the former streaming presentation contract are retired.
A fresh addressed turn wakes SC mechanically; UMI requests only non-standing
cognition. Planner is model-selected; Runtime cannot infer activation from task words.
GA output does not author new Goal meaning: Host preserves exact UMI WHAT when
materializing identity-only `new_goals` rows. Goal lifetime is not a UMI output or a no-Goal routing rule.
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

This is the single ordered open-work list. The [Roadmap](../ROADMAP.md#social-cognition-migration)
owns delivery order; the [checkpoint](../DEVELOPMENT_CHECKPOINT.md) owns the active Issue and decisions.

1. Repair the reproduced native GA constraint gap first: the exact wire excludes a completed
   Goal from supersedes, yet the real compiler admits it; Host correctly rejects it. Keep the
   legal contrasting new Goal representable. Repair semantic owners without restoring UMI output/lifetime labels or
   relaxing Planner. UMI still invents an agreement for a nod and misses the request/background
   distinction plus value review in the cookie-deception case. GA still links unrelated tasks to
   old Goals. Planner still substitutes partial/body/perception effects for complete singing,
   food and future reminders, and misclassifies already supplied facts as missing
   external abilities. Frozen complete-role candidates do not qualify; none was adopted.
2. Reconcile current Fast/canonical information semantics and complete existing Agent Skill
   disclosure. Fast has an overbroad all-information-needs-read rule, while canonical guidance
   permits supplied facts/intrinsic reasoning; /plan-advance still bypasses progressive Skill
   disclosure and story/joke methods remain absent. Their intended method-level target is not
   implemented. Preserve need-first single-authority semantics, stage isolation, provenance and
   permission rules; do not insert a semantic critic, a phrase router or a second wording owner.
3. Repair SC/Host commitment and result readiness using Need identity, qualified Evidence and
   actual played coverage. A pending result Need is not made ready by an addressed ID. Reconcile
   independent source obligations without replaying complete answers; a fresh explicit repeat
   remains valid. Do not prune pending Needs, deduplicate text or mark a promise fulfilled.
   Current quiet+nod executes with zero speech, but final stored Goal closure remains unproven.
4. Fix existing runtime/provider contracts: independent safe-read Evidence must not wait behind
   an unrelated slow body task (clock answer215.44s old); semantic look-left needs provider-owned
   direction and measured result, not raw joint inputs; weather current/day/period fields and
   summary must have consistent scope. Forecast HTTP timeouts are separate service failures.
   Fit story delivery within the unchanged30s speech budget; prompt completion is not playback.
   Missing SC personal-fact/preference proposals precede cross-conversation recall failures;
   test the proposal/transport/storage boundaries separately. No model or budget change.
5. After each authorized general repair, freeze and qualify the complete role transaction,
   replay the original10 and all126 cases, inspect all actual outputs, retain exactly one bundle
   after each cohort, and rerun canonical gates plus strict6,000/ability evidence. The owner's
   current diagnostic instruction permits keep-going through failures to finish coverage; it
   does not waive release gates or confer a semantic pass. Current semantic review is by Codex,
   not the project owner's independent review. Preserve rejected artifacts and reference gaps.
6. After native qualification, obtain narrow current-revision voice proof and the default
   [target-evidence closure](TARGET_EVIDENCE_CLOSURE.md). Physical microphone, speaker and robot
   evidence remains supervised. No main merge or release before the applicable evidence gates
   and explicit owner approval. Do not attribute current failures to model weights alone while
   role inputs, prompt conflicts, missing methods and runtime/provider defects remain.

## Evidence interpretation

Historical source tests, automatic passes or owner-reported audio remain bound to
their original revisions; none establish current target validation. A planned
observation, acknowledgement or safe idle alone is never task completion.
