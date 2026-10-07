# Chromie Current Status

Updated: 2026-10-07. Current focus: Goal-driven single-authority architecture,
canonical local verification, current-revision voice proof and default target-evidence closure.
The [project audit](../ARCHITECTURE_AUDIT.md) records design/source conflicts and
actual module I/O; it does not amend authority or establish full qualification.

## Current verification and deployment state — water acceptance, 2026-10-07

| Axis | Current evidence |
| --- | --- |
| Implementation | UMI's open-ended-help prompt preserves one need/help Responsibility; SGLang GA wire schema bounds ownership rows by current source-ref count; SC requires a fresh terminal-failure result act and avoids a false repeat request. Canonical Host authority is unchanged. New live water-acceptance failures at UMI and Fast Planner remain unrepaired. |
| Automatic verification | Direct recorded GA 3/3 and SC 5/5 Schema/Host replays, focused 68 tests, four relevant Level A classes 22/22 and frozen workflow replay 6,000/6,000 pass. Final `./scripts/run_tests.sh` exited 0 (169 benchmark, 3,983 main, five environment skips, 1,023 subtests, 20 legacy Agent); policy and docs checks pass. Same-model and Level A evidence do not prove live general behavior. |
| Target validation | A diagnostic deployed text cohort attempted all 79 cases: 13 automatic passes, 66 failures, 59 integrity failures, and all 79 retained for semantic review. Agent service loss and identity change left `cohort_complete=false` and `qualification_complete=false`. The first thirst turn offered help, but subsequent accepted water requests failed at UMI or Planner. No supervised microphone, speaker or physical robot proof. |
| Deployment state | Current dirty source was built into the Agent for the diagnostic text run; port 8092 became unavailable mid-cohort and later recovered/recreated. Outage cause is unknown. No release, promotion or stable fixed-identity qualification. |

Private evidence: `.chromie/acceptance/ga-duplicate-20261007/` and
`.chromie/acceptance/sc-internal-failure-20261007/`; originating bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_110927.tar.gz`.
The earlier UMI open-ended-help patch is included in this delivery revision.
Diagnostic evidence: `.chromie/acceptance/thirst-offer-20261007/`; bundle:
`/home/chromie/Downloads/chromie_debug_bundle_20261007_121723.tar.gz`.

## Previous patch — open-ended help interpretation, 2026-10-07

| Axis | Current evidence |
| --- | --- |
| Implementation | UMI prompt preserves one open-ended help Responsibility when a reported need qualifies the request; SC still owns wording and Planner owns HOW. The primary semantic split in live text SID `a87066b5` was the earliest observed failure. No model/profile, Schema, DTO, Host or authority changed. |
| Automatic verification | Frozen eight-case English/Chinese direct-model contrast: baseline 6/8 and selected prompt 8/8 Schema/Host valid. Request-only freeze revision 17 preserves 6,000 non-request records; full strict replay 6,000/6,000 and focused workflow tests 104/104 pass. Robust-intent Level A 8/8, UMI focused 44/44, benchmarks 169/169, main tests 3,981 with five skips/1,023 subtests and legacy Agent 20/20 pass. Policy, ownership, static, configuration, runtime and docs checks pass. The single `run_tests.sh` invocation did not complete successfully in this session; its components were run separately after preserving stale local freeze files and recapturing requests. |
| Target validation | The originating English request is mechanically accepted by the selected model/prompt transaction. The Chinese open-ended help output remains in English despite Host acceptance; bilingual semantic qualification is open. Current-revision deployed Host, live voice, audible/physical and default-target proof were not run. Previous 79-case native cohorts remain historical and incomplete as below. |
| Deployment state | The active operator text console and its pre-patch `chromie-agent:latest` service were left running. Direct SGLang model calls used the current prompt and retained production request/Schema; no Agent rebuild, service restart or promotion occurred. |

Private evidence: `.chromie/acceptance/umi-help-split-20261007/`; originating
bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261007_093607.tar.gz`.
See [checkpoint](../DEVELOPMENT_CHECKPOINT.md) and [handoff](../HANDOFF.md) for
the exact resume sequence and evidence limits.

## Previous verification and deployment state — 2026-10-05

| Axis | Current evidence |
| --- | --- |
| Implementation | Owner-confirmed principle30 is enforced: UMI preserves complete WHAT and cannot author bindings; Planner owns parameter extraction and contextual provenance. Provider perception and GA/SC/Host authority remain. Memory projections now preserve historical creation/update times and sources. Earlier Charter sparse-binding prose is reconciled with principle30. Model/profile and initial activation ownership are unchanged. |
| Automatic verification | Frozen20 Schema/Host and exact-wire pinned decoder20/20 pass; UMI1496/Fast204 references valid, focused215+84 tests pass, Level A19/19. Request-only6000+5 captures conserve every non-request field. Strict6000/6000 replay passes with zero inference. Canonical169 benchmarks,3981 main tests/5 environment skips/1023 subtests and20 legacy tests pass; policy/ownership/pinned static/configuration/docs pass. |
| Target validation | Baseline79:22 automatic pass/57 fail, review6 pass/10 partial/61 fail/2 insufficient. Changed-source79:13 automatic pass/66 fail, review5 pass/7 partial/67 fail. All cases attempted/zero skipped; blocked followups leave cohort/qualification incomplete.86 native UMI outputs have zero binding keys; activation/meaning failures remain. No overall behavior gain, independent, current voice, audible/physical or default-target qualification. |
| Deployment state | Agent-only source imagebc6577e4… preserves original dependency layers; packaged/host source8140dcc3… matches before/after. Profile/environment/model unchanged. Native source/services fixed within each aggregate. A pre-cohort grammar probe caused LLM OOM/automatic recovery; fresh native identity binds the recovered service. No release/promotion; TTS dependency rebuild remains unqualified. |

Current repair evidence: `.chromie/acceptance/umi-no-bindings-20261005/`.
Changed-source bundle: `/home/chromie/Downloads/chromie_debug_bundle_20261005_192414.tar.gz`.
All79 cases were reviewed, including automatic passes. Milk retains ahead/about50meters
but has no initial Planner request; no resource provider is invoked. Walk3s/right-turn2s
completes in simulation but cites the walk duration as the turn-duration source, so
semantic provenance fails. Quote validity alone does not qualify parameter mapping.
Historical Memory projection is proved outside current sight, with original time/source;
actual search, action persistence and resource acquisition remain unproved.

Previous local proof: `.chromie/acceptance/ga-history-fixture-audit-20261005/`:70
upstream historical-description input/target type repairs, with all1500 material
comparisons preserving original meaning, prior Goals and identity choices. Complete
reference validation1500, focused22 and canonical169 benchmark/3968 main tests pass.
No production UMI correction or native inference was performed.

Retained workflow proof: `.chromie/acceptance/workflow-contract-audit-20261005/`:
strict aggregate6000/6000, focused120, complete canonical gate passing. Original83
failures were stale replay records before inference, not model ability failures.
All6000 scenario probes and5 prototypes retain their original semantic/provider/fault
assertions and prior Goals. Frozen source bytes and strict recovery guards are retained;
review is non-independent Level A, not native qualification.

Previous native proof: `.chromie/acceptance/planner-compound-contract-20261004T140758Z/count-scope/source-schema/`.
The full native cohort is complete at the case-admission level; failures blocked
some later turns, so neither cohort-complete nor qualification-complete is claimed.
All79 summaries, exact primary packets, same-agent review and immutable runtime
identity are retained. That historical cohort's single bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20261005_003209.tar.gz`.
Its case SID923cce48 retains count2 binding and all3 requested completed body
results; SID0b0cdc27 retains right-direction source t11:t12 and completed walk/turn.
The direct-stop case has no execution/stop evidence after an unrequested idle was
planned. A planned observation or acknowledgement alone is never completion.
Earlier GA/media, compound and count runs are historical in Handoff/audit, not
substitutes for this revision. Later status-document consolidation is a documentation
only delta from the frozen full-tree identity; packaged Agent source stays fixed.

Two owner-local SC language prompt candidates were rejected, with language4/8
baseline,4/8 system-policy and3/8 output-contract-footer. Each cohort had eight
mechanically accepted primary outputs with unchanged model/context/Schema.
`.chromie/acceptance/sc-language-policy-20261004T125029Z/adjudication.json`
retains all24 outputs and exact source rollback, including inherited changes.
Correct language input is confirmed; intrinsic ability versus prompt/context/profile
reliability is not isolated. No runtime translator or second semantic decision.

The original blink call confirms an UMI primary Planner-request omission, not
an intrinsic ability limit. Later successful blink calls use the same model and
system/Schema/options but different timestamp/context; they do not prove GA caused
UMI to improve. UMI keeps initial activation and GA/Host do not compensate.
Automatic acknowledgment or safe idle alone does not prove task fulfillment.

Historical October1 three-model scores and earlier17/79 provider-fix run remain
bound to their original source identities in Handoff/audit. Superseded admission
chronology has since been repaired; accepted-water Work still fails. Do not turn
those historical comparisons into current model ranking or release evidence.

## Social Cognition migration

The accepted [Charter target](PROJECT_CHARTER.md#social-cognition--accepted-target-2026-09-14)
remains the authority: SC decides whether, when and how to communicate; Planner
selects Capabilities and resolves execution inputs. Ordinary Planner-authored speech,
optional Planner decoration and the former streaming presentation contract are retired.
A fresh addressed turn wakes SC mechanically; UMI requests only non-standing
cognition. Planner is model-selected; Runtime cannot infer activation from task words.
GA output does not author new Goal meaning: Host preserves exact UMI WHAT when
materializing identity-only `new_goals` rows. `turn` is Goal lifetime, not a no-Goal routing rule.

This describes current intended ownership, not full conformance. The audit found
UMI binding conflict is repaired under the owner-confirmed principle 30 boundary;
complete WHAT remains UMI-owned and Planner owns parameter extraction. Attention
same-authority semantic repair and SC fresh-turn silence restrictions still need review.
No amendment to permit UMI parameter extraction was made in this audit.

## Component implementation and qualification

| Existing owner | Source state and current proof limit |
| --- | --- |
| [Gateway](COGNITIVE_GATEWAY.md) / Host admission | Deterministic protective controls and immutable admitted turn exist. Attention model repair conflicts with single semantic authority. Physical audio admission needs source-bound proof. |
| [Turn lifecycle](COGNITIVE_TURN_LOOP.md) / Cognitive Runtime | Concurrent SC and GA/Work, exact identity, cancellation, prerequisite joins and Evidence re-entry exist. Text admission chronology repaired and mechanically proved; water Work activation and native coverage/latency remain open. |
| [Semantic authorities](SEMANTIC_AUTHORITY.md) / UMI, GA, Planner, SC | Source ownership migration is implemented; preserved original wording is authoritative. Current workflow corpus compatibility is repaired; other authority conflicts and native coverage remain unresolved. |
| [Agent Skills](AGENT_SKILLS_ARCHITECTURE.md) / planner and registry | Semantic methods and Capability contracts exist. Frozen references are not independent/native-model qualification. |
| [Execution lanes](EXECUTION_LANES_AND_COORDINATION.md) / Trusted Runtime | Confirmation, cancellation, coordination, provider truth and safe-idle contracts remain blocking. No permission comes from premature speech. |
| [Resource acquisition](RESOURCE_ACQUISITION_AND_DELIVERY.md) / providers | Provider-owned source resolution is implemented; observed milk object/pose and mixed-place qualification remain gaps. Simulator handover does not prove real acquisition. |
| [Cognitive architecture](GOAL_DRIVEN_COGNITIVE_ARCHITECTURE.md) / retained state | Goal continuity, scoped re-entry, Memory and mechanical time wake exist. Old duplicated prose is not current qualification evidence. |
| [Agent mind and Memory](../agent/README.md) / stable and relational Memory | Stable identity and privacy/provenance mechanisms exist. Trusted real-world identity/audience sources and broader live social behavior remain unqualified. |
| [Capability providers](../capabilities/README.md) / Soridormi | Embodied feasibility and safety stay with Soridormi. Simulation perception exists; real camera/person/hardware ingress is incomplete. |
| [Runtime rollout](COGNITIVE_RUNTIME_ROLLOUT.md) / operators | Existing evidence/fallback machinery remains. Retired PresentationCommit promotion text must not substitute for current SC + Work qualification. |
| [Acceptance](ACCEPTANCE.md) / qualification operators | Frozen cohorts, ability classes and strict failure accounting remain required; local failures cannot be averaged into a release pass. |

## Current open work

Follow the [Roadmap migration order](../ROADMAP.md#social-cognition-migration)
and [checkpoint](../DEVELOPMENT_CHECKPOINT.md); the audit does not create a new
feature line or revive historical iteration authorizations.

1. Retain completed bounded Planner compound/count/source proofs; qualify remaining
   primary HOW choices and current stop coverage without changing SC expression authority.
   Attention authority and SC silence findings remain open; UMI cannot author bindings.
2. Retain repaired user-before-assistant admission; qualify accepted-offer Work
   activation against complete actual context before interpreting model-comparison scores.
3. Preserve the passing canonical local gate and current reviewed workflow freeze;
   historical-restatement input types are repaired at their fixture owner. Keep
   reference validity distinct from native-model semantic qualification.
4. Qualify exact Schema/DTO/native grammar, SC context budget/latency, provider
   scene and geographic Evidence, Goal/action/provenance coverage.
5. Retain narrow current-revision voice and the default
   [target-evidence profile](TARGET_EVIDENCE_CLOSURE.md). Physical evidence stays supervised.

## Evidence interpretation

Detailed historical narrative belongs in Git history. Historical source tests,
automatic passes or owner-reported audio remain bound to their original revisions;
none establish this audit's target validation. Exact current resume commands,
private artifact paths and matrix identities are in [Handoff](../HANDOFF.md).
