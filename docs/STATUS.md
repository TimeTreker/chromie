# Chromie Current Status

**Updated:** 2026-08-31
**Current focus:** The owner-authorized Goal-driven single-authority path is restored at the GI boundary: one primary WHAT result, at most one source-based Deep delegation for genuine unresolved meaning, and terminal validation without same-authority repair. Explicit measurement units, standalone social Responsibilities, material unfamiliar-name uncertainty, and GI-authored/GA-preserved `output_mode` now have one coherent contract. The final target-blind offline cohort is retained; exact deployed-provider qualification is next, while live voice, simulator, and physical behavior remain separate evidence claims.

This file contains current facts only. Historical implementation narratives,
superseded architecture, old test totals, and revision-specific diagnostics belong in
Git history, `CHANGELOG.md`, retained evidence bundles, and archived reports. Historical
evidence remains useful for the exact revision it records, but it does not define the
current architecture or qualify later source automatically.

## Current architecture

The maintained authority line is:

```text
Person / World
      ↓
Cognitive Gateway
      ↓
Goal Interpretation                 WHAT
      ↓
Responsibility
      ├──────────────────────┐
      ↓                      ↓
Planner                  Goal Association
fast / deep passes       Goal continuity
      ↓                      ↓
Plan / Activities        Canonical Goals
  + optional auxiliary Activities
      └──────────┬───────────┘
                 ↓
       Trusted Capability Runtime
                 ↓
              Provider
                 ↓
       Async Runtime Event             what happened
                 ↓
        Host-bound Evidence            what is true
                 ↓
Responsibility + Goal + Situation + actual Work + Evidence
                 ↓
        CognitiveOpportunity           ephemeral readiness trigger
                 ↓
              Planner                  what to do now
                 ↓
       0..N Activity changes
       or no new Activity
```

The authoritative definitions live in `docs/PROJECT_CHARTER.md`. In particular:

- Goal Interpretation owns provider-neutral Responsibility meaning, not Work or speech.
- Goal Association owns canonical Goal identity and continuity, not replanning.
- Planner is one HOW authority; fast and deep are cognition passes of that same owner.
- Planner owns ordinary Communicative Activities and exact wording.
- The same primary Planner result may own bounded `auxiliary_activities[]`; these are
  fingerprinted Plan truth but never Goal-owned Work or completion Evidence.
- Trusted Capability Runtime and Providers own effect realization/lifecycle, not Goal
  interpretation.
- Runtime events report what happened. Host-correlated Evidence records what is true.
- `CognitiveOpportunity` is an ephemeral readiness carrier. It owns no Goal, Evidence,
  response, or execution truth and may legitimately lead Planner to do nothing.
- Auxiliary-only events cannot create a `CognitiveOpportunity` or fabricate its required
  non-empty Goal scope.
- Existing-Work comparison, reuse, cancellation, replacement, or supplementation are
  Planner operations, not a mandatory Work-Reconciliation stage.

The 2026-08-22 source audit found live Host semantic-authority leaks; Phase 1A-1D now
close the verified confirmation, cancellation, ordinary result-meaning, and body-recovery
source paths. Confirmation owns authorization facts only; named cancellation returns typed
Evidence to Planner; deterministic `status -> sentence` outcome composition is removed; and
recoverable body failure exposes bounded provider retryability facts without Host retry
planning. This is **source closure**, not target qualification: current-revision
bilingual/provider/simulator/live evidence is still required before `SPEECH-OWNER-001` or
human-facing behavior is considered qualified.

## Current implementation and verification state

Charter principles 30–31 now require semantic grounding/coverage evidence to be
authored in each authority's primary result and prohibit same-authority LLM
reviewer/semantic-repair chains. GI source now follows that contract: its primary
result carries per-Responsibility source-token evidence, resolved valid meaning uses
one model call, genuine unresolved meaning may delegate once to source-based Deep GI,
and every invalid primary or Deep DTO fails closed without a same-authority repair.
Goal Association now follows the same single-authority
rule: its primary result owns the complete continuity transaction, a Pydantic-invalid
DTO may receive one mechanical JSON repair, and trusted conservation/grounding checks
cannot trigger another model. Fast and Deep Planner now also close truth, Goal coverage,
evidence scope, wording, and satisfaction in their primary results; the former
same-owner qualification/coverage calls and dedicated truth-model role are removed.
The existing frozen `UserTurnEnvelope` now remains the sole stored source of admitted
wording. GI receives its exact original text explicitly; GA and Planner receive a compact
read-only source projection; and scoped Planner re-entry carries the same digest-validated
original wording while keeping `request.text`, Responsibilities, Goals, Plan, and Evidence
restricted to the affected Goal subset. The source is visible for fidelity and correlation
but grants no downstream authority to reinterpret or repair WHAT.
This is source and automated-contract closure, not qualified target behavior. The current
source starts Goal Association and one Fast Planner stream
concurrently from the immutable GI result. The internal model output is one text stream
with a closed `<presentation_commit>` payload followed by a closed `<terminal_plan>`
payload, not one top-level JSON object. The Agent exposes only a fully parsed typed
`PresentationCommit`, then a terminal frame or typed pre/post-commit failure from the same
model invocation. Raw tokens never reach TTS; Goal-owned Work waits for the complete
terminal result, GA binding, and canonical validation. The accepted commit and terminal
CanonicalPlan carry the same commit identity and cannot duplicate or re-author speech.
The separate post-resolution Social Attention bridge has now been removed:
`PresentationCommit`, terminal Fast output, and canonical Fast/Deep primary outputs own
optional `auxiliary_activities[]` directly under exact primary anchors.
This amendment is source/contract closure, not target behavior, audible voice, executed
simulation, or hardware evidence.
Core/challenge did not start; release readiness remains development only.

The RTX 4090 Laptop profile now assigns every LLM role to one `qwen3.5:4b` runner.
GI retains its 16K/512 request budget; GA, Fast, and Deep retain their declared 32K
contexts and stage output limits. Ollama 0.32.14 reports that `qwen35` does not support
parallel requests and creates `n_seq_max=1` even when `OLLAMA_NUM_PARALLEL=2`; the
maintained profile therefore declares one provider slot and one resident model. This
fits beside CosyVoice on the 16 GB laptop GPU, but it cannot realize the architecture's
concurrent GA/Fast inference.

The current-source aggregate is retained at
`.chromie/acceptance/general-ability/qwen35-all-roles-current-20260829T133621Z/live-text`,
bound to runtime identity
`2ab46a7cb42053391fe9fc0acbef77bc8d562bc3e9f6fd30c70f7f9becbeee91` and dirty
source-tree SHA-256
`428c51bb87cffe96d42f3f20f324eccfa0ec44a64c3f99e8cfbb7d50d4186c42`.
It hard-passed 0/50 must-pass cases; core/challenge were gated off. Mutually exclusive
earliest failures were 18 GI `ReadTimeout`s, eight invalid location-provenance outputs,
five dropped/rewritten numeric bindings, two overlapping independent source spans, one
invented duration, 14 typed Fast-stream timeouts after accepted GI, and two preview-only
reflex limitations. All 14 accepted GI outputs were low confidence and ten retained
unresolved meaning. The exactly one post-cohort bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260829_214253.tar.gz`. This is diagnostic
C-preview evidence only; no Capability was dispatched and no simulator, audio, or physical
behavior is qualified.

An isolated RTX 4090 Laptop vLLM 0.24.0 qualification now proves the candidate transport
can enforce strict JSON, stream SSE, overlap two short sequences, isolate cancellation,
and remain healthy. It does not yet qualify a production model. The unchanged five-case
primary GI screen scored Qwen3.5-4B 1/5, Qwen3.5-9B 2/5, Gemma-3-12B 0/5, and Qwen3-8B
1/5. Short fresh-turn location spelling is now decoder-constrained to exact source
surfaces, source provenance identifies user -> Chromie, and the Deep mechanical constraint
uses wire `binding_items`; the remaining failures are model-authored semantic omissions,
misclassification, invented ambiguity/location, or duplicate outcomes. Qwen3.5-4B plus
TTS peaked at 14,953 MiB, while two long decode streams slowed generated-but-unplayed TTS
first audio by 2.37x. Production remains on Ollama and the current profile.

A no-HTTP-deadline Ollama follow-up used the same five-case current-checkout GI screen.
Ministral-3-14B scored 2/5, Ministral-3-8B 1/5, Gemma4-e4B 1/5, and Gemma4-12B 2/5.
GPT-OSS-20B returned empty content for all five required non-thinking requests; the
provider documents that its reasoning cannot be disabled. A diagnostic `think: low` run
scored 3/5 but still misbound the weather time scope and dropped an explicit duration.
It used 12,951/16,376 MiB with TTS stopped, so it also lacks the measured resident budget
to coexist with TTS. This is isolated provider/GI evidence, not authority approval or
workflow qualification, and production remains unchanged.

The primary GI prompt/schema now exposes decoder-visible `unresolved[]` and overlapping-binding
contracts, then preflights atomic decomposition, typed modifier coverage, and uncertainty. That
change added no Host semantic owner, but an older reachable source-based repair remains. On the
unchanged screen, Qwen3.5-4B reached 3/5 once and 2/5 on a fresh rerun; the discarded typed-wire
Ministral-3-14B prototype reached 5/5 mechanically but failed manual review and reached 6/8
mechanically/about 4/8 manually on holdout. All other candidates were at most 3/5; none was promoted.

An RTX 5090 dirty-checkout diagnostic separates raw GI model potential from production-contract
compatibility through six dimensions. Under one simplified V2 prompt/schema, Ministral-3-14B
retained 28/28 evaluable decomposition and output-mode passes over two repeats, 26/28 outcome
and unresolved passes, 24/28 coordination passes, and 16/28 binding passes. Granite4.2-8B
preserved all 15 outcomes and modes but passed only 3/15 binding cases and invented or mis-typed
values. Its diagnostic-only Ollama digest is `f586c02fdecdf151b656207c339aa003997345774a41768bac1fd6d2fb85913b`.

The selected GI base prompt is a 15,212-character provider-neutral decision procedure over
all 25 binding dimensions, cross-clause outcomes, sparse grounded values, source perspective,
decoder-safe order, and minimal predicate evidence. Context-only rules add no call. Digest:
`73729710f5baef12ba690ff13ef949aeef00017643fb188e143ed3cc76626df6`.

An assistant-reference audit applied that prompt and each exact decoder schema to all 16 primary GI manifest cases without an external model/provider call. All 16 passed schema, Host validation, and six semantic dimensions. This proves only strong-reference prompt clarity, not deployed-model qualification: any candidate result measures the combined model + prompt + schema + decoder transaction and cannot alone prove the prompt correct or defective. Runtime contracts remain unchanged; no model was promoted.

A full offline Codex GI diagnostic exercised all 1,496 bilingual daily-life scenarios on fixed source/prompt identities through five bounded iterations. The selected final target-blind iteration completed 1,496/1,496 calls and generated-schema/production-Host checks; mechanical candidate equality was 835, including 1,496 decomposition, 1,490 output-mode, and 1,474 unresolved matches. A post-hoc one-reviewer, same-model self-audit judged 1,366 raw outputs valid and 130 invalid, recommended no prompt change, and judged only 1,136 assistant-authored references valid. Broader decision-procedure and source-span wording experiments regressed decomposition or semantic quality and were rejected. The current prompt preserves 406/406 explicit digit-plus-unit measurement bindings and exact Goal relationship/`output_mode` in 136/136 continuity scenarios. The separate source-based Deep-GI diagnostic covered all 68 genuinely unresolved reference cases: 68/68 calls/schema/Host and 55/68 same-model semantic passes, again with no prompt-change recommendation. Because Codex collapses production roles and carries the schema as prompt text, and because the reviewer is the same non-independent model and misread four schema-valid `schema_version` fields, these are diagnostic lower-bound counts rather than provider qualification, independent review, or training approval.

The contract defects found by the call-path audit are now fixed. Primary and Deep GI no longer have a same-stage repair call; the repository policy checker rejects restoration of those call markers. Measured values retain an exact number-and-unit source/context surface, standalone social acts remain speech Responsibilities, and unfamiliar names become unresolved only when the category/referent choice materially changes WHAT. Charter principle 31 now agrees with runtime: GI authors `output_mode`, GA preserves it under decoder `const` plus conservation checks, and the Host derives execution projections after validation. The 1,496-case candidate corpus passes generated schema and Host validation with 68 genuine unresolved cases and a pinned 406 digit-measurement-surface count. The final changed-worktree primary and Deep diagnostics are retained under ignored `.chromie/acceptance/model-qualification/` paths; no model/profile was promoted.

| Area | Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|---|
| Cognitive Gateway / Attention | Maintained configuration controls Attention Review; deterministic protective reflex remains separate. Disabled or unavailable semantic review fails open without fabricating high-confidence addressedness. | Source and focused contract regressions cover admission, fail-open behavior, temporary addressedness rules, and schema boundaries. | Current-revision open-room microphone behavior still requires live evidence. | Development only. |
| Goal Interpretation / Goal Association | GI is WHAT-only and its one primary result owns atomic Responsibilities, exact output modes, bindings, relations, and per-item source-token evidence. Invalid primary/Deep DTOs fail closed; only genuine unresolved meaning may delegate once to source-based Deep GI. Trusted code validates mechanics and cannot resegment, source-repair, or call a semantic reviewer. Explicit units remain human-semantic source surfaces. Standalone social acts remain speech Responsibilities and harmless unfamiliar names remain resolved. GA separately owns canonical Goal identity and continuity, preserves GI `output_mode` under a decoder constant, and may use only its existing Pydantic-only mechanical repair; grounding or conservation rejection is terminal. | Focused GI/GA regressions cover one-call resolved meaning, terminal invalid DTOs, one Deep delegation, units, social acts, name materiality, source evidence, atomic siblings, GA conservation, and policy guards. The 1,496-case candidate corpus passes generated schema and Host validation with 68 genuine unresolved cases and 406 pinned digit-measurement surfaces; it remains ineligible for training and lacks independent semantic review. The selected final target-blind diagnostic completed 1,496/1,496 schema/Host checks and retained 1,366/1,496 non-independent same-model semantic passes with no prompt-change recommendation; the 68-case Deep subset retained 55 semantic passes and the same no-change judgment. The relevant Level-A classes pass 12/12. | Current provider/model compatibility remains unqualified. A candidate run binds prompt, schema, decoder transport, profile, and revision; no model/profile was promoted. | Development only. |
| Planner / communication | One Planner authority owns HOW, exact Communicative Activities, Capability choice, args, realization, per-Goal satisfaction, and optional auxiliary social Activities. The model-side `/fast-advance` invocation is one text stream with exactly two closed tagged payload frames: `presentation_commit`, then `terminal_plan`. The Agent validates those payloads and exposes typed NDJSON: validated `PresentationCommit`, then terminal result or typed failure from that same invocation. GA starts concurrently; all Goal Work waits for terminal result, GA binding, and canonical validation. The terminal Fast result and CanonicalPlan reference the same immutable commit. Canonical Communicative Acts retain immediate/pre-action/progress/final delivery phase; mixed Response Projection covers only communicative Goal IDs, and an independent context-grounded final speech Goal may remain ordered after Work without becoming completion evidence for an executable Goal. `CanonicalPlan.auxiliary_activities[]` remains fingerprinted but structurally outside Goal-owned `steps[]`; Runtime validates, executes, or suppresses exact proposals and cannot reselect. The independent Social Attention and separate Fast First Response endpoint/model/config paths are removed. | Focused protocol, Planner, client, Runtime, scenario, and repository-policy tests cover one-call ownership, ordered typed frames, exact commit reference, before/after-commit failure, no early Goal Work, auxiliary anchor/catalog/Goal isolation, post-primary scheduling, communicative-only mixed-Goal coverage, context-grounded after-Work speech, provenance, cancellation, and terminal Evidence. The previous Ollama structured-JSON probe is superseded by the owner-approved tagged-frame protocol and cannot qualify the new wire path. | Current tagged-frame provider protocol, semantic quality, accepted-commit latency, TTS first PCM, playback start, complete-Plan latency, commit/terminal consistency under load, GPU residency/contention, target validity, restraint, and live execution require current-revision qualification. | Development only. |
| WorkDAG / DAGEngine | Planner is the sole ordinary semantic author/modifier of revisioned WorkDAG topology. GA changes Goal continuity only. DAGEngine owns acyclicity/contract checks, readiness, bounded parallel dispatch, dependency/blocked/cancellation state, trace, and immutable completed-node inheritance; normal completion advances mechanically while material change returns Evidence to Planner. Provider-local DAGs remain provider internals. | Focused WorkDAG revision tests prove exact `revision + 1`, stable `dag_id`, completed-node immutability and no redispatch; DAGEngine/Planner/capability tests guard removal of `residual_replan` and engine-authored outcome meaning. | Current-model quality of Planner-authored DAG topology and live multi-Goal revision/merge behavior still requires target qualification. | Development only. |
| Async Runtime / Evidence/Situation re-entry | Terminal Runtime events are correlated into Evidence and may create bounded `CognitiveOpportunity` re-entry. Every Planner re-entry now carries an immutable `PlannerReentryScope` with exact trigger, affected Goals, Evidence refs/opportunity, and optional source Plan fingerprint; Fast/Deep prompt projection and decoder Goal sets are restricted to that scope, so closed siblings are not silently reintroduced. `SituationProjection` v3 carries bounded current interpretations plus exact authority-owned source refs. Meaningful live provider progress is the first production trusted Situation ingress: blocked/waiting/degraded/paused/recovering or material phase/member-state transitions become typed `SituationRevisionObservation` input and may raise `situation_revision`; running heartbeats and percentage churn are ignored. Provider Runtime state is explicitly **not Evidence**, so provider-state and restart revalidation no longer fabricate Evidence refs or `post_evidence` speech truth. Restored open Goals retain exact Responsibility provenance and may re-enter from fresh provider truth without replaying the old Plan or fabricating a UserTurn. Structured Goal/Plan-bound `time_condition` state is production-wired to a mechanical wall-clock wake loop and likewise may re-enter with zero Evidence refs. A Situation-digest opportunity is accepted only with the exact validated Situation/Goal binding. Generic scene/body/environment Situation ingress remains an **implementation gap**. Planner-authored structured time conditions are part of the canonical Plan: Planner supplies exact Goal/time semantics, while ConversationState adds current Plan identity plus original Responsibility provenance before durable registration. Host never polls the world semantically or parses free-form deadlines into timers. Situation re-entry readiness is selective: no semantic delta creates no opportunity; benign waiting/recovering/running or phase-only changes are local and do not call an LLM; ordinary revisions use Fast Planner; blocked/degraded/failed/unsafe state requests Slow cognition and enters Deep Planner without spending a Fast pass. | Focused regressions cover exact two-of-three Goal re-entry projection, incremental terminal Evidence, Situation v3 reconstruction/source binding, provider Runtime-state Situation ingress without Evidence promotion, follow-up Work while siblings continue, cancellation/supersession containment, duplicate-execution prevention, missing-provenance rejection, durable restart revalidation, one-shot due-time wake/re-entry, and shutdown cancellation of the long-lived mechanical wake task. | Provider-backed weather/body episodes should be retained on the exact current revision; live blocked/waiting Situation-revision and restart-revalidation episodes still require target qualification. Generic camera/scene/body/environment ingress cannot be qualified until its production source adapters exist; Planner-authored time-condition quality still needs current-model target qualification. | Development only. |
| Memory activation | Existing session/profile Memory remains the sole retained-meaning owner. Prompt selection now uses bounded current-context cues from the latest user turn, open task/Goal context, and discourse focus so an older relevant Memory can outrank unrelated recent entries; recency remains fallback/fill. Selection does not create Evidence, change Goal meaning, authorize effects, or add a retrieval model/vector store. | Focused MemoryStore/ConversationState regressions prove older relevant activation, CJK phrase activation, recent fallback, durable-memory compatibility, and bounded prompt projection. | Current-model usefulness of activated Memory across longer bilingual episodes still requires target qualification. | Development only. |
| Semantic expectations / Active Perception | Canonical executable steps now distinguish ordinary effect Work from `acquire_information` Work and may carry a bounded Planner-authored `expected_outcome`. Information-seeking gaze/tool/body behavior remains normal Capability Work under existing safety/provider authority. On trusted terminal re-entry, the prior expectation is projected beside actual Evidence for the same Planner; Host never treats the expectation as Evidence or performs semantic mismatch inference itself. | Focused contract/re-entry regressions prove non-empty observation expectation for acquisition Work, canonical prompt preservation, and terminal re-entry exposure without Evidence promotion. | Current-model choice of useful observation Work and live expectation-mismatch recovery require target qualification with actual providers. | Development only. |
| Identity / personality truth | Chromie's owner-approved social identity is a six-year-old girl and family young secretary. That is not a biological-human claim; truthful robotic embodiment remains available when relevant. | Mind-profile, prompt-context, and identity/body benchmark contracts guard the two-layer truth boundary. | Bilingual live identity conversation remains to be requalified on the current model/profile. | Development only. |
| Social Attention behavior domain | Optional embodied decoration remains subordinate to a concrete Planner-authored Main Activity, has no speech or Goal-completion authority, and may validly be empty. A `PresentationCommit`, terminal Fast result, or canonical Fast/Deep Plan may author it under an exact primary anchor; Runtime only validates, suppresses, or executes after primary launch. Explicitly requested gestures remain Goal-owned steps. | Focused source contracts cover candidate filtering, decoder-bound capability/args, canonical fingerprinting, anchor validity, exact execution, Goal isolation, post-primary scheduling, confirmation-held suppression, and suppression without reselection. Repository guards reject restoration of the retired second writer. | Historical independent-planner probes are diagnostic only. Current Planner prompt/model behavior and physical expression remain unqualified. | Development only. |
| Host structural boundary | Pure Planner-reentry policy lives in `orchestrator/runtime/planner_reentry.py`; TTS text segmentation lives in `orchestrator/runtime/tts_text.py`; Goal-list console projection lives in `orchestrator/runtime/goal_list_console.py`; fail-soft observability recording policy lives in `orchestrator/runtime/observability_recording.py`; fixed-reflex confirmation-token revocation/audit bookkeeping lives with the existing `ConfirmationDialogue` owner in `orchestrator/runtime/confirmation.py`; OS-default audio-device detection/queue/apply lifecycle lives in `orchestrator/runtime/audio_device_lifecycle.py`; top-level process teardown now lives in stateless `orchestrator/runtime/shutdown_lifecycle.py`, reusing the existing InputTurn/Playback/Session owners rather than reimplementing their task or transport truth in `VoiceAssistant`; accelerator sample scheduling, detached task tracking, and trace attachment now live with the existing fail-soft observability policy in `orchestrator/runtime/observability_recording.py`; PlaybackTransport now owns its provider/output methods directly, so the seven `VoiceAssistant` playback/TTS compatibility delegates have been removed while the same session trace spans live on the transport owner; `InputSessionRuntime` now likewise calls its own microphone/VAD/ASR/routed-turn/session-idle operations directly, removing twelve input/session compatibility delegates from `VoiceAssistant` while `InputTurnLifecycle` remains the task-state owner. These are existing Host concerns extracted without adding semantic owners, managers, or state stores. The audited CognitiveRuntime closure also extracts the former nested Fast-advance phase into a typed helper on the same owner; `_resolve()` drops from 1117 to about 1036 lines while preserving concurrent provisional-work cancellation. | Focused regressions pass; the method ratchet moves `159 -> 150 -> 142 -> 139 -> 136 -> 129 -> 127 -> 124 -> 117 -> 105 -> 104`, with the current maintained ceiling at `104 methods / 300 init lines / 108 initialized attributes / 0 direct-LLM calls`. | Not a runtime target; full Host decomposition remains separate from behavior qualification. | Development only. |
| Static quality gates | Repository policy, documentation, configuration ownership/inventory, structure ratchets, and selected static-analysis scopes are maintained. Documentation authority now explicitly includes the canonical cognitive architecture, human-interaction contract, and acceptance contract; the docs gate rejects retired positive deepthinking/memory-route claims. Phase 2 guards documentation authority; Phase 4 additionally rejects verified obsolete prompt/client artifacts and direct re-copying of shared whitespace/JSON-Schema mechanisms. The pinned test environment now includes `pytest-asyncio`. | Dependency-free gates can run without GPU. The incremental Ruff/Mypy ratchet now also owns `scripts/run_mypy.py`; further widening remains one verified slice at a time rather than a blanket repo-wide switch. | Not a runtime target. | Development only. |

## Current open work

1. **Close the reproduced all-Qwen resource and semantic blockers.** The complete
   current-source must-pass cohort is retained and mechanically judged. Qwen3.5 still
   fails GI availability/provenance/authority contracts, while Ollama exposes one sequence
   slot for concurrent GA/Fast work. Do not use Host resegmentation, another semantic call,
   validator weakening, or timeout inflation to conceal either failure class. A different
   vLLM transport is now qualified in isolation, but all screened laptop-fit candidates
   failed primary GI semantics or the current non-thinking authority contract. Do not
   promote a provider until primary-result binding coverage passes the frozen screen,
   then the complete workflow, TTS contention, and directory-discovered live cohort pass
   on one revision. Do not substitute phrase rules or a second semantic call for coverage.
2. **Close Issue #32 source gates and target evidence before final Fast-Planner
   Prompt/model promotion.** The one typed production path is implemented and the
   superseded endpoint/DTO/model/config surface is removed. Retain ordered-frame,
   commit/terminal identity, pre/post-commit failure, and no-early-Work regressions; then
   measure the exact target provider/model under the real single-slot resource profile.
   Do not stream raw tokens to TTS or add another semantic writer/repair call.
3. **Run the `current_revision_qualification` evidence profile on the committed target.**
   The profile requires the canonical source report, the directory-discovered retained live
   interaction cases, the live provider fault matrix, Gateway/Core, Agent Skill/weather,
   Social Attention, and LAN evidence on the same clean revision. WorkDAG revision/no-redispatch
   remains an explicit source gate; selected live cases cover bilingual effectful speech,
   cancellation, provider-backed Evidence re-entry, multi-goal behavior, follow-up continuity,
   duplicate-effect cardinality, and declared warm Planner/playback budgets. Physical voice
   and physical robot remain separate optional evidence tracks.
4. **Retain the structural rule during qualification and later maintenance.** Reopen
   decomposition only for a concrete ownership seam or defect; file size alone is not
   permission to add a Speech Manager, Reconciliation Manager, Meta Planner, or one manager
   per cognitive term. Source
   implementation, automated verification, target validation, and release readiness remain
   separate axes.

Phase 2 documentation convergence is source-closed: `docs/chromie_mind.md` now describes
MindProfile as bounded context rather than deleted agents/routes; the duplicated
`docs/CONFIGURATION.md` tail is removed; current architecture docs no longer retain the
reviewed Host-result-fallback or route/intent-GI contradictions; and the docs gate protects
those boundaries mechanically.

Phase 6 qualification infrastructure is source-complete, but Phase 6 itself is not closed by
that source change. `target_evidence_closure_eligible=true` from a
`current_revision_qualification` bundle is the retained target-evidence exit condition. A
source report alone, preview-only General Ability run, local-stub provider fault matrix, or
older revision remains insufficient.

## Evidence interpretation

Source implementation, automated verification, target validation, and release readiness
are separate axes. A passing unit/integration suite does not prove microphone, audible
speaker, GPU latency, simulator, or physical-provider behavior. Likewise, retained live
evidence from an older revision does not silently qualify the current source after a
material cognition, model, provider, prompt, or timing change.

Chromie remains a development project. No publication or release-readiness claim is made
by this status page.
