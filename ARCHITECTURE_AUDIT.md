# Chromie project principles and implementation audit

**Updated:** 2026-09-12. **Audited current revision:** `f5522f874671ff1b8bd42553a22793eaad0b1f51`, `main`, initially clean and equal to fetched origin. This continuation incorporates the owner-supplied external process review and the delivered #49–#51 changes.

**Audience:** project owner and maintainers selecting one Issue at a time. **Owner:** the project owner owns audit decisions; linked Issues own follow-up work. This report is evidence and recommendations, not a replacement for the [Charter](docs/PROJECT_CHARTER.md), [Status](docs/STATUS.md) or [Roadmap](ROADMAP.md).

The architecture's division of responsibility remains coherent: GI owns WHAT, GA owns continuity, Planner owns HOW and ordinary speech, and Runtime/providers own execution and evidence. Three reproduced audit defects are now delivered. Cancellation reporting and Reflection integration still contradict that design. Target qualification is still blocked. Large classes and documentation raise maintenance cost, but their size alone does not prove an authority defect.

This delivery updates the report, status and handoff documents. It applies no behavior, Schema, prompt, model-profile or policy change. The available development Agent was rebuilt at the unchanged audited revision for a fresh live baseline. The [original full audit and reproducible probe appendix](https://github.com/TimeTreker/chromie/blob/3e1c50414b6709a2b7222269cadce203e5e6661a/ARCHITECTURE_AUDIT.md) remain immutable evidence for `191083dc`; its failure counts must not be presented as current results.

## Issue map and next work

| Finding | Current disposition | Next independent work |
| --- | --- | --- |
| <a id="a01"></a>A01 — cross-interaction resource exclusion | [#49](https://github.com/TimeTreker/chromie/issues/49) delivered and closed at `c1585e78` | Preserve atomic complete-resource acquisition and cancellation while waiting. |
| <a id="a02"></a>A02 — lossy Planner inputs | [#50](https://github.com/TimeTreker/chromie/issues/50) delivered and closed at `9be7b23f` | Preserve complete required context or reject before inference. |
| <a id="a03"></a>A03 — staged progress and premature Goal closure | [#51](https://github.com/TimeTreker/chromie/issues/51) delivered and closed at `f5522f87` | Preserve partial acquisition, unmet obligations, exact Evidence re-entry and delivered-speech closure. Whole-role qualification remains open. |
| <a id="a04"></a>A04 — cancellation scope/capability truth | [#52](https://github.com/TimeTreker/chromie/issues/52), P1, freshly reproduced; no repair | Separate reporting permission from Goal meaning and catalog facts; reconcile the Fast/Deep admission mismatch. |
| <a id="a05"></a>A05 — Reflection delays ready response | [#53](https://github.com/TimeTreker/chromie/issues/53), P2, freshly reproduced | Remove optional Reflection from aggregate response dependency; preserve bounded background lifecycle and cancellation. |
| <a id="a06"></a>A06 — Mind/Reflection/Planner handoff | [#54](https://github.com/TimeTreker/chromie/issues/54), P2, freshly reproduced | Supply approved Mind to Reflection and valid advisory context to Planner without another semantic reviewer. |
| <a id="a07"></a>A07 — deployable profile qualification | [#24](https://github.com/TimeTreker/chromie/issues/24), [#32](https://github.com/TimeTreker/chromie/issues/32), [#35](https://github.com/TimeTreker/chromie/issues/35), P1, open | Start from the retained live GI failure; qualify one fixed current revision/profile through all required evidence. |
| <a id="a08"></a>A08 — current evidence/documentation drift | [#55](https://github.com/TimeTreker/chromie/issues/55), P2, open | Continue reconciling owned current claims. This delivery consolidates checkpoint/handoff history but does not close all #55 criteria. |
| Process — contract typing coverage | [#56](https://github.com/TimeTreker/chromie/issues/56), P2, new | Enforce the complete contract package through the existing ratchet at its approved place in the delivery order. |
| Process — lifecycle ownership review | [#57](https://github.com/TimeTreker/chromie/issues/57), P2, new | Review one real lifecycle seam and extract only if ownership and independent testing become clearer. |

**Priority correction:** the original audit's linear A01 → … → A07 suggestion must not postpone evidence closure behind every maintenance item. The binding delivery line remains canonical gate → current-revision live voice proof → default target-evidence closure. Run an unchanged aggregate live baseline before a broad behavior change, diagnose its first failed boundary, and keep bounded contract repairs attached to that evidence. #52 is the next separate contract candidate; #53/#54 and maintenance do not qualify a target by themselves. #56/#57 retain the existing policy's post-closure sequencing unless the owner explicitly changes it. This is not permission to run multiple agents or modify source during a live cohort.

## Current cancellation diagnosis — #52

Planner owns the permitted Plan and truthful communication for admitted Goals. It must not rewrite their WHAT, invent cancellation success, grant execution permission, reuse revoked confirmation, or infer global capability absence from a restricted invocation.

The retained cases are `dpdl_v1_confirmation_and_cancellation_revision_08_{boundary,supported}_{en,zh}`. Their Goal remains creation of an 8 p.m. reminder. Boundary cases supply trusted `cancelled` evidence; supported cases supply `not_cancelled` with `stale_confirmation_released`. The reminder fixture is available. These are historical scenario bindings, not a real reminder product or current schedule.

| Order / owner | Authoritative input → actual output | Expected contract / verdict |
| --- | --- | --- |
| Retained GI/GA + control Evidence | Canonical stateful-effect Goal; exact scoped control status and selected Evidence refs | Correct fixture input. GI/GA/control models and real cancellation were not invoked by the offline probe. |
| Planner context and catalog projection | Cancellation re-entry makes `response_only=true`; resolver empties executable catalog; prompt calls the original Goal provider-free direct speech | **First wrong boundary:** no Work permission is appropriate, but it must not erase capability truth or change Goal meaning. All 16 captures (four cases × two provider states × Fast/Deep) hide the reminder and contain the false speech description. |
| Fast Schema and Host, scripted correct report | `respond`, no Work, complete accounting, satisfaction 0 with the original reminder explicitly unmet → two Schema-branch rejections and Host `goal_satisfaction_not_exact` | **Additional contract mismatch:** Fast cannot admit the truthful report at honest non-completion. It retains the speech as undelivered advisory and escalates. |
| Deep Schema and Host, same scripted report | Same raw report → accepted `respond`, zero steps, original Goal unsatisfied | Correct representability in the existing Deep/Canonical DTO. It does not prove Runtime reconciliation. |
| Fresh Deep primary model, cancelled EN/ZH | `respond`, truthful cancellation report, zero Work, satisfaction 0 and original reminder unmet | Passes the frozen region and semantic review; does not establish the other control statuses. |
| Fresh Deep primary model, released confirmation EN/ZH | `unavailable`; both replies claim no reminder capability is available | False global limitation encouraged by the missing catalog facts; both frozen cases fail. Model fault is not isolated from the incorrect upstream projection. |
| Runtime/provider | No provider dispatch in capture/Host replay; no real token or delivery transition tested in this continuation | Contained proposal boundary only. Runtime revocation, sibling authority and speech-delivery behavior remain closure work. |

```text
stateful Goal + scoped control Evidence + available reminder fixture
  -> response-only permission
  -> empty catalog + incorrect direct-speech description
       -> Deep: false provider absence after confirmation release
       -> correct scripted report: Deep admits / Fast rejects honest non-completion
```

Source boundaries at the audited revision: [context](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/agent/app/planner_context.py#L725), [Fast catalog](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/agent/app/fast_planner.py#L662), [Deep catalog](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/agent/app/deep_planner.py#L161), [misleading prompt](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/agent/app/planner_prompt.py#L1104), [Fast admission](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/agent/app/planner_fast_validation.py#L310), [existing Deep exemption](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/agent/app/planner_deep_validation.py#L39).

**Proposed repair:** preserve Goal and capability facts while restricting executable choices; distinguish confirmed cancellation, unverified stop, running/not-cancelled and released-confirmation states. Reconcile scoped Fast reporting with existing Deep/Canonical non-completion meaning. Do not globally lower satisfaction thresholds or let Host invent a semantic result. If the chosen design changes canonical lifecycle/authority meaning, obtain the Charter-required owner decision before implementing it.

**Closure matrix:** freeze bilingual contrasts for those four control states × available/unavailable provider × Fast/Deep, plus mismatched Evidence, revoked token and independent-sibling regressions. Require zero unintended Work, truthful status, explicit original unmet obligations, no stale authorization and no false global limitation. Preserve existing failed raw outputs and original oracle identity; justify any new region before inference. Replay the real Runtime/delivery boundaries and rerun both complete Planner cohorts. No new oracle or repair was applied in this audit.

## Reflection findings remain current — #53/#54

The unchanged original synthetic probes were rerun against `f5522f87`:

| Boundary | Observed | Meaning |
| --- | --- | --- |
| Host aggregate closure → optional Reflection → result Planner | Result Planner had not entered while Reflection was pending; entered only after release | #53 remains a dependency defect. This is event-order proof, not a live latency measurement. |
| Host → Reflection context | No `mind`; rendered Stable Mind is `null` | #54's upstream context gap remains. |
| Retained advisory → Fast/Deep prompt | Advisory absent from both prompts | #54's downstream projection gap remains. |

The closure probe ends `planner_reentry_unavailable` because its scripted Planner dependency supplies no successful result. The observed assertion is ordering and context, not a successful user response. The original report retains the exact runnable probe; current outputs are `remaining-reflection-probes.json` in R below. Fix these existing owners rather than using class extraction as a prerequisite.

## Assessment of the external process review

The review examined an in-flight #51 patch. Its 2,984-test and 40-new-test statements are historical review claims; the delivered revision freshly passes 2,988 tests and the staged-progress module has 32 passing cases. Its broad positive architecture assessment is consistent with this audit, but does not establish live qualification or the absence of semantic defects.

| Review point | Current evidence and decision |
| --- | --- |
| Documentation burden | Before this delivery: 102 tracked Markdown files / 39,094 lines; HANDOFF 4,975 lines / 363,462 bytes / 90 second-level sections; checkpoint 422 lines. Valid reading-cost concern. This delivery consolidates current facts into the two existing owners and links complete prior records by immutable Git revision, following `docs/DOCUMENTATION_AUTHORITY.md`. Checkpoint is now 68 lines and HANDOFF 193; all 102 Markdown owners remain. No in-tree archive or new document owner is added. |
| Enforced size limits | Do not adopt automatically: the owner explicitly approved informational size measurements in [#45](https://github.com/TimeTreker/chromie/issues/45). Reinstating numeric ceilings would reverse that decision. Ownership and safety checks remain blocking. |
| Large runtime classes | Confirmed: `VoiceAssistant` 104 methods / 7,549 file lines; `ConversationStateManager` 105 methods / 6,172 file lines. #57 asks for a real seam/episode review, not a mechanical split or a claim that method count proves a bug. |
| Narrow typing | Confirmed five enforced files, three tooling. Fresh strict diagnostics pass both suggested modules **and the entire 30-file contract package**. #56 follows the already approved package-based expansion strategy; no Mypy scope was changed here. Static typing still cannot prove semantic correctness. |
| Qualification last | The original audit's suggested order deserved correction. The latest #51 delivery already attempted live qualification and reached a GI failure; this continuation also runs the full discovered cohort before any behavior edit. Evidence work remains an active prerequisite, not a final polishing step. |
| Ruff `I`/`UP` | Possible future rule-family review, not an urgent architecture repair. Their complete scope and supported-Python consequences were not evaluated here. No formatter/rule change or clean-baseline claim is made. |
| Derived continuation property | A credible serialization-regression risk, not a reproduced failure in this audit. Preserve its source-derived, non-model-writable meaning; #57 requires a boundary regression if that seam changes. |
| Large test files | Review scenario/fixture ownership when touching them. Line counts alone do not justify splitting tests or reducing coverage. |

## Fresh evidence and limits

R = `.chromie/acceptance/issue52-cancellation-scope-20260912/` (ignored; transfer separately). All production source, corpora, prompts and Schemas remained unchanged during the baselines. Candidate inference used fixed `gpt-5.6-sol/high`, one target-blind primary call per case, no retries or output repair. Reviews are post-hoc agent reviews, non-independent; they are never Runtime decisions. Deep inference began after Fast inference/mechanical adjudication while Fast semantic review was still underway; this audit does not claim completion of the method’s ordered Optimize cycle. No behavior edit followed those baselines.

| Evidence | Observed result | Limit |
| --- | --- | --- |
| Canonical source gate | 2,988 tests, 794 subtests, 145 benchmarks, 20 legacy tests; policy/static/config/docs/ownership passed; two existing FastAPI warnings | Source only. Final documentation checks are retained separately. |
| Staged-progress regression | 32/32 passed | Fresh local check of delivered #51, not a new #51 qualification run. |
| Strict contract typing diagnostic | All 30 package files pass current configuration | Diagnostic scope is larger than the enforced five-file ratchet. |
| Full Fast baseline | 204/204 Schema and Host; 201/204 frozen hard passes | Three valid #51 staged reads outside old regions remain frozen failures. Review also flags an ungrounded dewdrop topic in `direct_communicative_planning_06_supported_en` and two future-read exact-satisfaction cases for further #35 review. No aggregate semantic pass claimed. |
| Full Deep baseline | 40/40 Schema and Host; 36/40 frozen hard passes | Two staged reads outside composite-only regions, plus two false capability claims after confirmation release. All 40 semantic output projections reviewed. |
| Review coverage | All 244 cases reviewed using scenario context, raw semantic-content projections and exact mechanical adjudication; suspected cases inspected in full | Not an independent review or complete Runtime/response-adapter replay. Two Fast future-read satisfaction interpretations remain explicitly unresolved. |
| Cancellation probe | 16 prompt captures; correct scripted report rejected by Fast, admitted unchanged by Deep | No model inference, token revocation, speech delivery or provider execution in this probe. |
| Live unchanged aggregate | 51 must-pass cases discovered; 1 completed GI failure, 1 interrupted startup, 49 unrun | Incomplete failed preview; no #52 path reached, no microphone/audible speaker/physical or simulator execution proof. |

The live Agent was rebuilt and all 112 Agent/shared Python files were verified against source. The selected existing generated environment matches the qualification profile; the stale voice-runtime environment was rejected and left unedited. Agent/TTS/LLM identity was captured; ASR was not running or claimed. Current services remain development services, not a qualified deployment.

The first live request (`compound_walk_nod_turn`, session `67cc5d79`) asked for walking at “0.2 speed” for ten seconds, nodding twice, then turning left. Primary GI emitted one body-action responsibility with the whole turn copied into a `subtype` binding. Semantic validation rejected it with `invalid_primary_goal_interpretation_semantics` / HTTP 503 before GA, Planner or execution. This matches the existing upstream failure class, but does not prove the prompt/provider/model root cause in isolation. The next case had begun startup when the hard-failure stop took effect. Source/provider identities stayed unchanged; final simulator status was safe idle. Owned simulator/MCP processes were stopped.

Exactly one debug bundle was collected for this cohort: `/home/chromie/Downloads/chromie_debug_bundle_20260912_171920.tar.gz`. Original raw response digest was verified; a transport record marked accepted is not semantic admission. The [handoff](HANDOFF.md) retains exact call/runtime identities, commands, artifact paths and transfer limitations. Private #51 artifacts from the other machine are absent here and have not been reclassified as fresh evidence. #24/#32/#35 remain open; release readiness remains development only.

## Publication and reproducibility

This report and both delivery owners are committed together. The complete preceding handoff is [retained at f5522f87](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/HANDOFF.md); the [preceding checkpoint](https://github.com/TimeTreker/chromie/blob/f5522f874671ff1b8bd42553a22793eaad0b1f51/DEVELOPMENT_CHECKPOINT.md) preserves #49–#51's exact delivery evidence and decisions. Historical evidence is archived in Git, not discarded or relabeled.

A fresh clone can run the canonical gate, strict typing diagnostic, original synthetic probes and the tracked full Planner corpora. Exact candidate raw replay and this live run require R and its retained bundle from this machine. The current handoff explains that boundary and the next commands. No new runtime switch, authority, architecture term, current document or numeric size rule is introduced.
