# Chromie Current Status

## Current delivery — Perception can ground a provider-owned resource source, 2026-10-09

| Axis | Current evidence |
| --- | --- |
| Implementation | Owner-approved option A plus "trust what you see". An unbound provider-owned resource `source` is `{"status":"unknown"}` with no citation, or `{"status":"known"}` with a cited span or a current Situation observation (`situation_interpretation_ref`). The decoder encodes this as `oneOf` branches; native decoders ignored the old `if`/`then`. Host admits only established, perception-grounded observations of this turn, and rejects observed numbers cited to the person's words. The Plan records `observed_context`. Fast prompt guidance appears only when the qualified catalog has a provider-owned source; the Situation part only when something is observed. The text harness now runs ambient perception (`08f018296`), proven live. |
| Automatic verification | 18 targeted regressions (red on `08f018296`); canonical gate in a clean worktree exit 0 (169/4,031/5 skips/1,065 subtests/20 legacy); strict replay 6,000/6,000 with zero model calls. Frozen native contrast over 37 retained requests, each arm on a fresh SGLang lifetime: rev6 reproduces 37/37 across a restart; weather and speech are byte-identical to the baseline. When water was visible, 4/4 cite the observation; b15 cites the milk it sees (owner rule). Remaining: milk cited for water when only milk is visible (3/3, synthetic), and "known" plus "sure" when nothing is observed (7/9, legacy no-Situation captures). |
| Target validation | Live water cohort on rev6 (fresh SGLang lifetime): 4/4 delivery turns cite the correct observation (milk for milk, water for water, even with both visible); no user words cited for an observed place. 1/4 cases pass end to end. The other 3 fail on a pre-existing contract (a lone `parallel` auxiliary Activity; Host needs a group of 2 or more), seen in bundles since 2026-10-07. Case 1 also missed a TTS start. |
| Deployment state | `chromie-agent:latest` = `situation-source-rev6-20261009` (rollback `pre-situation-source-20261009`). SGLang image changed by the parallel memory session (`b419ac92…`, output-neutral on a fresh restart). Greedy outputs depend on server-lifetime history, so a contrast arm needs its own restart. Dirty-source diagnostic identity; no release. |

Evidence: `.chromie/acceptance/provider-source-branches-20261009/` (README.md); bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261009_144736.tar.gz`.

## Previous delivery — Information-query free text must cite its source span, 2026-10-08

| Axis | Current evidence |
| --- | --- |
| Implementation | Owner-approved option A. For `acquire_information` Capabilities, the Fast decoder now requires an `argument_sources` span for required free-text inputs (weather `location`), as it already did for numbers. The Host checks that a same-script cited value appears in its span; cross-script renderings (`北京`→`Beijing`) remain allowed. Authored text (vocal/speak) and enum strings keep their existing paths. Prompt unchanged. |
| Automatic verification | Frozen native contrast over all 20 retained weather requests. The baseline repeated identically; candidate Schema errors were 0. Genuine weather cases accepted by Host provenance went from 10/16 to 16/16, and all 56 candidate citations pass the new Host check. New decoder-level regression red→green; weather literal contract test updated, with negatives (other city, prefix, sibling) still rejected. Strict replay 6,000/6,000 with zero model calls (no recapture); canonical gate 169/4,011/5 skips/1,065 subtests/20 legacy. |
| Target validation | Agent rebuilt (source `8b820086…`). Same 13 weather/clock live cases: 8/13 automatic passes (4/13 before). 10/11 weather questions got correct grounded answers, including Beijing (previously rejected). Two failed only the SC 2 s latency target. 内乡县 was mistranslated and the provider failed. Date/time questions are still routed to weather lookup and now fail at the provider instead of the Host (separate clock-choice defect). |
| Deployment state | `chromie-agent:latest` rebuilt from the Oct 7 base with current `agent/app`; the previous image is tagged `chromie-agent:pre-string-provenance-20261008`. Dirty-source diagnostic identity; no release. |

Evidence: `.chromie/acceptance/string-input-provenance-20261008/`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_174448.tar.gz`.

## Previous delivery — SC answers ordered after body Work are spoken again, 2026-10-08

| Axis | Current evidence |
| --- | --- |
| Implementation | The interaction coordinator's exemption for context-grounded speech ordered after Work (not a result claim) now accepts the trusted `social_cognition` source as well as the legacy Planner source. The Sep 14 SC split changed that source without updating the exemption, so every such SC answer was dropped as "result speech for re-entry". Result-claim speech remains deferred to terminal Evidence. |
| Automatic verification | New SC-source coordinator regression red→green; strict replay 6,000/6,000 with zero model calls; `multi_goal_daily_life` Level A 10/10; canonical gate 169/4,007/5 skips/1,065 subtests/20 legacy. |
| Target validation | Live `multi_goal_daily_life` class (simulator executed), 5/6 automatic passes. "你好！" after the nod and the joke after the blink are now actually played; neither was before. The remaining failure is the known TTS start deadline: the initial "Got it." took 4,786 ms to first PCM against 3,500 ms, was cancelled, and SC reported delivery failure. |
| Deployment state | Host-side change; Agent source unchanged; dirty-source diagnostic identity. |

Evidence: `.chromie/acceptance/after-work-speech-20261008/`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_162840.tar.gz`.

## Previous delivery — GA-triggered Planner revision no longer erases a valid first plan, 2026-10-08

| Axis | Current evidence |
| --- | --- |
| Implementation | Owner decision implemented at the existing Cognitive Runtime owner, per Charter lines 559-585/725. A successful GA-requested plan supersedes the UMI plan (newer continuity state). A failed GA plan no longer cancels or erases a valid UMI plan for the same Responsibilities. A failed UMI plan waits for a requested GA plan. Both failures are retained as diagnostics. No new model call, authority, switch or prompt change. |
| Automatic verification | Four new regressions (revision exception, revision contract failure, first-plan failure rescued, both fail) are red on the original source and green now. The existing supersession test is unchanged. The Oct 7 late-failure test now fails both plans so its delivered-response containment stays covered. Strict replay 6,000/6,000 with zero model calls; canonical gate passes. |
| Target validation | Live retained race episodes (water ×2, "把那个拿给我"): the GA-revision path ran once (water "sure"). Both plans were rejected by Planner provenance/readiness validation, so the turn failed honestly. The old code would have failed earlier without waiting for the GA plan. Keeping a valid first plan is proven only by regression tests so far. 0/3 automatic passes; all failures are Planner provenance or LLM transport. |
| Deployment state | Host-side change; Agent source unchanged; dirty-source diagnostic identity; no rebuild, promotion or release. |

Evidence: `.chromie/acceptance/ga-revision-containment-20261008/`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_160823.tar.gz`.

## Previous delivery — SC act identity no longer copies Planner Work IDs, 2026-10-08

| Axis | Current evidence |
| --- | --- |
| Implementation | Host projection of Fast Planner communicative Needs into SC `facts` omits the Planner `activity_id`; it remains encoded in `need_id` and step order. SC owns act identity; no prompt, Schema, model or authority change. |
| Automatic verification | Frozen native contrast of all 16 retained SC requests that carried the fact (baseline repeated, stable): Planner ID copied 7→0, delivered words re-authored under a new ID 4→0, Schema errors 0→0. One request (c11) now leaves its need pending in silence instead of reusing the delivered act. Unit regression red→green; strict replay 6,000/6,000 with zero model calls; canonical gate 169/4,003/5 skips/1,063 subtests/20 legacy. |
| Target validation | Live simulator run of 11 former duplicate cases: 34 SC calls, 0 copied IDs, 0 duplicate replays, 7 correct delivered-ID reuses; 3/11 automatic passes. Remaining failures are Planner contract failures (water ×3, identity, reminder) and SC latency (5.2–10.0 s vs 2 s). A pre-existing defect surfaced: SC speech ordered after body Work (`final` phase) is authored but never played; an A/B on the original code reproduces it. |
| Deployment state | Host-side change; Agent source unchanged (`2b4f2298…` verified). Dirty-source diagnostic identity; no rebuild, promotion or release. |

Evidence: `.chromie/acceptance/sc-act-identity-20261008/`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_153201.tar.gz`.

## Previous delivery — Evidence-bound claim oracle, 2026-10-08

| Axis | Current evidence |
| --- | --- |
| Implementation | Acceptance-only: scenarios declaring `require_evidence_bound_claims` (13 clock/weather lookup turns) turn an SC `respond`/`inform` act without Evidence refs or an addressed Host need into hard `provenance:unsupported_evidence_claim`. Production runtime, prompts, Schemas and the workflow freeze are unchanged. |
| Automatic verification | Original harness fails the 6 new evidence-bound regressions; patched harness passes 40 focused tests. Canonical gate passes 169 benchmark, 4,002 main, 5 skips, 1,063 subtests, 20 legacy. Evidence-class Level A 6/6. Retroactive re-score of 713 retained flagged-turn summaries (19 contain SC acts) flags only the Oct 7 fabricated date. |
| Target validation | Dirty-source diagnostic simulator run of the 13 declared cases: 4/13 automatic pass, 0 unsupported-claim hits across 24 SC acts. 7 cases fail at Fast Planner `weather.lookup.location` provenance, including clock questions routed to weather lookup; 1 SC delivery failure; 1 weather provider failure. The Oct 7 fabrication did not recur because UMI typed the question `information` this time (it typed `speech/turn` on Oct 7). |
| Deployment state | Agent packaged source matched checkout (`2b4f2298…`); the harness change is host-side only. No rebuild, promotion or release. |

Evidence: `.chromie/acceptance/evidence-bound-claims-20261008/`; bundle
`/home/chromie/Downloads/chromie_debug_bundle_20261008_134254.tar.gz`.

## Previous in-progress isolation, 2026-10-07

| Axis | Current evidence |
| --- | --- |
| Implementation | Dirty UMI accepted-effect context/prompt repair, equivalent default array projection, retained Planner decoder title through readiness/lookup, typed late SC request failure containment, and retained initial delivery/Goal completion across silent state re-entry. Unsafe relocation of decision alternatives withdrawn. UMI compound, Planner semantic/provenance and same-scope invocation failures remain open. |
| Automatic verification | Current focused 42 tests/85 subtests pass; exact native grammar preserves SC silent-need restrictions and compiles corrected Fast. Native Fast replay HTTP 200/complete JSON still fails Schema/semantics. Accepted-effect UMI14 passes limited scope. Frozen25 compound baseline/candidates remain unqualified. Final6000+5 request capture preserves non-request data; freeze20 strict6000 and gate169/3991/5skip/1063subtests/20legacy pass before the latest silent-state/closure fix; current44 focused/85subtests and adjacent8 pass; final gate169/3993/5skip/1063subtests/20legacy, strict6000/6000 and Level A30 distinct cases/six classes pass. Latest SC ID namespace contrast supports context ambiguity but is not broadly qualified or applied. Historical freeze19 gate passed but tested withdrawn projection. |
| Target validation | Bound aggregate stopped first compound case: relation-only overlapping UMI output (1/79). Focused water stopped at greeting: late SC422 after speech caused generic apology; subsequent water turns unrun. Corrected Agent bound aggregate executed three simulator actions but TTS missed playback-start deadline; focused water repeats greeting under new SC ID and loses completed thirst response to later silence before a Planner DTO failure. Latest Host retention/closure proof pending. No supervised physical audio/robot evidence. |
| Deployment state | Agent rebuilt from existing dependencies and packaged source verified as2b4f2298… before diagnostic live runs; voice_mujoco retained. Native field-order experiment hit global host OOM; LLM automatically recovered, requiring fresh identity binding. Fixed Gemma4-12B, owner-authorized in-progress Git delivery; no promotion, release or qualification. |

Private evidence: `.chromie/acceptance/water-context-repair-20261007/`.
One bundle per stop: `171342` aggregate, `172100` greeting and `173617` provider OOM
under `/home/chromie/Downloads/chromie_debug_bundle_20261007_<time>.tar.gz`.
See [audit](../ARCHITECTURE_AUDIT.md), [checkpoint](../DEVELOPMENT_CHECKPOINT.md)
and [handoff](../HANDOFF.md) for actual module I/O and resume order.

Updated: 2026-10-08. Current focus: Goal-driven single-authority architecture,
canonical local verification, current-revision voice proof and default target-evidence closure.
The [project audit](../ARCHITECTURE_AUDIT.md) records design/source conflicts and
actual module I/O; it does not amend authority or establish full qualification.

## Previous verification snapshot — water acceptance, 2026-10-07

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
