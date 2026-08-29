# Chromie Current Status

**Updated:** 2026-08-29
**Current focus:** The owner-approved Planner-owned auxiliary social-decoration amendment is source-closed inside the Goal-driven single-authority architecture. Resume model-facing Prompt/schema optimization and controlled model comparison against the retained qwen3.5 GI semantic and downstream latency evidence line. Source closure and target evidence remain separate claims.

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
one model call, one mechanically malformed DTO may be regenerated once, genuine
unresolved meaning may delegate once to source-based Deep GI, and semantic or authority
contradictions fail closed. Goal Association now follows the same single-authority
rule: its primary result owns the complete continuity transaction, a Pydantic-invalid
DTO may receive one mechanical JSON repair, and trusted conservation/grounding checks
cannot trigger another model. Fast and Deep Planner now also close truth, Goal coverage,
evidence scope, wording, and satisfaction in their primary results; the former
same-owner qualification/coverage calls and dedicated truth-model role are removed.
This is source and automated-contract closure, not qualified target behavior. A current
RTX 4090 Laptop/Qwen3 4B C-preview must-pass aggregate on dirty identity
`86a04a8da490c02918545d2dfe01674800b516e5cf0b80e838b34a06c9906546` completed all
50 cases with zero hard-passes. Its mutually exclusive earliest failures were 24 GI
source-span overlaps, eight GI transport timeouts, one GI whole-turn binding rejection,
six GA timeouts, three foreground deadlines, four other Runtime timeouts, two preview-only
reflex limitations, one Fast timeout, and one speech-only semantic miss. Raw GI results
also duplicated atomic effects, invented temporal Responsibilities, and labeled embodied
requests as speech. The current source admits concurrent Fast Advance and Goal Association
before first-speech TTS. The separate post-resolution Social Attention bridge has now
been removed: Fast Advance and canonical Fast/Deep primary outputs own optional
`auxiliary_activities[]` directly, while Fast First Response has no auxiliary surface.
This amendment is source/contract closure, not target behavior, audible voice, executed
simulation, or hardware evidence.
Core/challenge did not start; release readiness remains development only.

A later GI-only `qwen3.5:4b` comparison cohort hard-passed 2/50 cases. Of the 48
GI-invoked cases, 18 reached an accepted interpretation, 25 timed out, and five failed
closed validation; 16 of the accepted results retained spurious unresolved meaning. The
RTX 4090 Laptop profile now assigns only GI to `qwen3.5:4b`, bounds it at 16K/512, and
allows it to remain resident beside the unchanged downstream Qwen3 runner. This closes
the reproduced alternating model-eviction mechanism, not semantic or end-to-end target
qualification. Two provider request slots are not retained because they expand the 32K
downstream runner beyond the shared 16GB CosyVoice envelope.

The post-default cohort at
`.chromie/acceptance/general-ability/gi-qwen35-default-fixed` mechanically hard-passed
2/50 and is bound to runtime identity
`78847784d3ff08df8b606fb921eb28010a0e87f34b146da41c4fabe1cc9341b8`.
Manual review rejects both passes because they retain invented unresolved meaning, so the
strict semantic result is 0/50. Top-level retained GI results improved from 17 to 29 and
explicit GI `ReadTimeout` cases fell from 25 to six, confirming the residency fix. However,
26/29 retained results still contain false unresolved meaning, frequently invoking the one
allowed Deep GI pass and exhausting the outer deadline. The 48 mechanical failures divide
into 13 GI availability/outer-deadline cases, three GI numeric-binding authority rejections,
30 downstream single-slot failures including multi-turn predecessors, and two preview-only
reflex limitations. Its exactly one debug bundle is
`/home/chromie/Downloads/chromie_debug_bundle_20260829_063447.tar.gz`.

| Area | Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|---|
| Cognitive Gateway / Attention | Maintained configuration controls Attention Review; deterministic protective reflex remains separate. Disabled or unavailable semantic review fails open without fabricating high-confidence addressedness. | Source and focused contract regressions cover admission, fail-open behavior, temporary addressedness rules, and schema boundaries. | Current-revision open-room microphone behavior still requires live evidence. | Development only. |
| Goal Interpretation / Goal Association | GI is WHAT-only and its one primary result owns atomic Responsibilities, exact output modes, bindings, relations, and per-item source-token evidence. Trusted code validates closed source/reference/order/non-overlap/value-provenance mechanics and cannot resegment or call a semantic reviewer. RTX 4090 Laptop now assigns only GI to `qwen3.5:4b` in a resident 16K/512 runner; every other model role is unchanged. GA separately owns canonical Goal identity and continuity in one primary result, with at most one Pydantic-only mechanical DTO repair; grounding or conservation rejection is terminal. | Focused GI/GA regressions cover primary evidence, atomic siblings, exact modes/bindings, one-call resolved meaning, bounded mechanical repair, genuine Deep GI delegation, fail-closed semantic violations, GA conservation, and configuration ownership. | The post-default cohort retained 29 top-level GI results versus 17 before residency and reduced explicit GI `ReadTimeout` cases from 25 to six. It still produced false unresolved meaning in 26/29 retained results and strict semantic review passed 0/50 end-to-end cases. | Development only. |
| Planner / communication | One Planner authority owns HOW, exact Communicative Activities, Capability choice, args, realization, per-Goal satisfaction, and optional auxiliary social Activities in the same primary result. Fast First Response has no auxiliary surface. `CanonicalPlan.auxiliary_activities[]` is fingerprinted but structurally outside Goal-owned `steps[]`; Runtime validates, executes, or suppresses the exact proposal and cannot reselect. The independent Social Attention model, endpoint, configuration, and queue/worker are removed. Host commit and primary launch precede auxiliary scheduling; confirmation-held or rejected primary work does not schedule decoration. | Planner/schema/runtime tests and repository policy guard one-call ownership, auxiliary anchor/catalog/Goal isolation, no social-only cognitive re-entry, post-primary scheduling, confirmation-held suppression, shared semantic validation, provenance, cancellation, terminal Evidence, and critical-fan-out-before-presentation order. The canonical gate passes 2,017 maintained tests plus 20 legacy Agent tests; the relevant Level A matrix passes 18/18. | Prior cohorts exercise the retired independent path and do not qualify the new Planner prompt/schema. Current-model expression quality, target validity, restraint, latency, and live execution require a new current-revision cohort. | Development only. |
| WorkDAG / DAGEngine | Planner is the sole ordinary semantic author/modifier of revisioned WorkDAG topology. GA changes Goal continuity only. DAGEngine owns acyclicity/contract checks, readiness, bounded parallel dispatch, dependency/blocked/cancellation state, trace, and immutable completed-node inheritance; normal completion advances mechanically while material change returns Evidence to Planner. Provider-local DAGs remain provider internals. | Focused WorkDAG revision tests prove exact `revision + 1`, stable `dag_id`, completed-node immutability and no redispatch; DAGEngine/Planner/capability tests guard removal of `residual_replan` and engine-authored outcome meaning. | Current-model quality of Planner-authored DAG topology and live multi-Goal revision/merge behavior still requires target qualification. | Development only. |
| Async Runtime / Evidence/Situation re-entry | Terminal Runtime events are correlated into Evidence and may create bounded `CognitiveOpportunity` re-entry. Every Planner re-entry now carries an immutable `PlannerReentryScope` with exact trigger, affected Goals, Evidence refs/opportunity, and optional source Plan fingerprint; Fast/Deep prompt projection and decoder Goal sets are restricted to that scope, so closed siblings are not silently reintroduced. `SituationProjection` v3 carries bounded current interpretations plus exact authority-owned source refs. Meaningful live provider progress is the first production trusted Situation ingress: blocked/waiting/degraded/paused/recovering or material phase/member-state transitions become typed `SituationRevisionObservation` input and may raise `situation_revision`; running heartbeats and percentage churn are ignored. Provider Runtime state is explicitly **not Evidence**, so provider-state and restart revalidation no longer fabricate Evidence refs or `post_evidence` speech truth. Restored open Goals retain exact Responsibility provenance and may re-enter from fresh provider truth without replaying the old Plan or fabricating a UserTurn. Structured Goal/Plan-bound `time_condition` state is production-wired to a mechanical wall-clock wake loop and likewise may re-enter with zero Evidence refs. A Situation-digest opportunity is accepted only with the exact validated Situation/Goal binding. Generic scene/body/environment Situation ingress remains an **implementation gap**. Planner-authored structured time conditions are part of the canonical Plan: Planner supplies exact Goal/time semantics, while ConversationState adds current Plan identity plus original Responsibility provenance before durable registration. Host never polls the world semantically or parses free-form deadlines into timers. Situation re-entry readiness is selective: no semantic delta creates no opportunity; benign waiting/recovering/running or phase-only changes are local and do not call an LLM; ordinary revisions use Fast Planner; blocked/degraded/failed/unsafe state requests Slow cognition and enters Deep Planner without spending a Fast pass. | Focused regressions cover exact two-of-three Goal re-entry projection, incremental terminal Evidence, Situation v3 reconstruction/source binding, provider Runtime-state Situation ingress without Evidence promotion, follow-up Work while siblings continue, cancellation/supersession containment, duplicate-execution prevention, missing-provenance rejection, durable restart revalidation, one-shot due-time wake/re-entry, and shutdown cancellation of the long-lived mechanical wake task. | Provider-backed weather/body episodes should be retained on the exact current revision; live blocked/waiting Situation-revision and restart-revalidation episodes still require target qualification. Generic camera/scene/body/environment ingress cannot be qualified until its production source adapters exist; Planner-authored time-condition quality still needs current-model target qualification. | Development only. |
| Memory activation | Existing session/profile Memory remains the sole retained-meaning owner. Prompt selection now uses bounded current-context cues from the latest user turn, open task/Goal context, and discourse focus so an older relevant Memory can outrank unrelated recent entries; recency remains fallback/fill. Selection does not create Evidence, change Goal meaning, authorize effects, or add a retrieval model/vector store. | Focused MemoryStore/ConversationState regressions prove older relevant activation, CJK phrase activation, recent fallback, durable-memory compatibility, and bounded prompt projection. | Current-model usefulness of activated Memory across longer bilingual episodes still requires target qualification. | Development only. |
| Semantic expectations / Active Perception | Canonical executable steps now distinguish ordinary effect Work from `acquire_information` Work and may carry a bounded Planner-authored `expected_outcome`. Information-seeking gaze/tool/body behavior remains normal Capability Work under existing safety/provider authority. On trusted terminal re-entry, the prior expectation is projected beside actual Evidence for the same Planner; Host never treats the expectation as Evidence or performs semantic mismatch inference itself. | Focused contract/re-entry regressions prove non-empty observation expectation for acquisition Work, canonical prompt preservation, and terminal re-entry exposure without Evidence promotion. | Current-model choice of useful observation Work and live expectation-mismatch recovery require target qualification with actual providers. | Development only. |
| Identity / personality truth | Chromie's owner-approved social identity is a six-year-old girl and family young secretary. That is not a biological-human claim; truthful robotic embodiment remains available when relevant. | Mind-profile, prompt-context, and identity/body benchmark contracts guard the two-layer truth boundary. | Bilingual live identity conversation remains to be requalified on the current model/profile. | Development only. |
| Social Attention behavior domain | Optional embodied decoration remains subordinate to a concrete Planner-authored Main Activity, has no speech or Goal-completion authority, and may validly be empty. Fast Advance and canonical Fast/Deep Plans may author it; Runtime only validates, suppresses, or executes after primary launch. Explicitly requested gestures remain Goal-owned steps. | Focused source contracts cover candidate filtering, decoder-bound capability/args, canonical fingerprinting, anchor validity, exact execution, Goal isolation, post-primary scheduling, confirmation-held suppression, and suppression without reselection. Repository guards reject restoration of the retired second writer. | Historical independent-planner probes are diagnostic only. Current Planner prompt/model behavior and physical expression remain unqualified. | Development only. |
| Host structural boundary | Pure Planner-reentry policy lives in `orchestrator/runtime/planner_reentry.py`; TTS text segmentation lives in `orchestrator/runtime/tts_text.py`; Goal-list console projection lives in `orchestrator/runtime/goal_list_console.py`; fail-soft observability recording policy lives in `orchestrator/runtime/observability_recording.py`; fixed-reflex confirmation-token revocation/audit bookkeeping lives with the existing `ConfirmationDialogue` owner in `orchestrator/runtime/confirmation.py`; OS-default audio-device detection/queue/apply lifecycle lives in `orchestrator/runtime/audio_device_lifecycle.py`; top-level process teardown now lives in stateless `orchestrator/runtime/shutdown_lifecycle.py`, reusing the existing InputTurn/Playback/Session owners rather than reimplementing their task or transport truth in `VoiceAssistant`; accelerator sample scheduling, detached task tracking, and trace attachment now live with the existing fail-soft observability policy in `orchestrator/runtime/observability_recording.py`; PlaybackTransport now owns its provider/output methods directly, so the seven `VoiceAssistant` playback/TTS compatibility delegates have been removed while the same session trace spans live on the transport owner; `InputSessionRuntime` now likewise calls its own microphone/VAD/ASR/routed-turn/session-idle operations directly, removing twelve input/session compatibility delegates from `VoiceAssistant` while `InputTurnLifecycle` remains the task-state owner. These are existing Host concerns extracted without adding semantic owners, managers, or state stores. The audited CognitiveRuntime closure also extracts the former nested Fast-advance phase into a typed helper on the same owner; `_resolve()` drops from 1117 to about 1036 lines while preserving concurrent provisional-work cancellation. | Focused regressions pass; the method ratchet moves `159 -> 150 -> 142 -> 139 -> 136 -> 129 -> 127 -> 124 -> 117 -> 105 -> 104`, with the current maintained ceiling at `104 methods / 300 init lines / 108 initialized attributes / 0 direct-LLM calls`. | Not a runtime target; full Host decomposition remains separate from behavior qualification. | Development only. |
| Static quality gates | Repository policy, documentation, configuration ownership/inventory, structure ratchets, and selected static-analysis scopes are maintained. Documentation authority now explicitly includes the canonical cognitive architecture, human-interaction contract, and acceptance contract; the docs gate rejects retired positive deepthinking/memory-route claims. Phase 2 guards documentation authority; Phase 4 additionally rejects verified obsolete prompt/client artifacts and direct re-copying of shared whitespace/JSON-Schema mechanisms. The pinned test environment now includes `pytest-asyncio`. | Dependency-free gates can run without GPU. The incremental Ruff/Mypy ratchet now also owns `scripts/run_mypy.py`; further widening remains one verified slice at a time rather than a blanket repo-wide switch. | Not a runtime target. | Development only. |

## Current open work

1. **Close the reproduced qwen3.5 GI and downstream resource-profile blockers.** The
   complete post-change must-pass cohort is retained and manually judged. Address false
   unresolved meaning/Deep-GI deadline amplification separately from unchanged single-slot
   GA/Fast contention. Do not use Host resegmentation, another semantic call, validator
   weakening, or a non-GI model substitution.
2. **Run the `current_revision_qualification` evidence profile on the committed target.**
   The profile requires the canonical source report, the directory-discovered retained live
   interaction cases, the live provider fault matrix, Gateway/Core, Agent Skill/weather,
   Social Attention, and LAN evidence on the same clean revision. WorkDAG revision/no-redispatch
   remains an explicit source gate; selected live cases cover bilingual effectful speech,
   cancellation, provider-backed Evidence re-entry, multi-goal behavior, follow-up continuity,
   duplicate-effect cardinality, and declared warm Planner/playback budgets. Physical voice
   and physical robot remain separate optional evidence tracks.
3. **Retain the structural rule during qualification and later maintenance.** Reopen
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
