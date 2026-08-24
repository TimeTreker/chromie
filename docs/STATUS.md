# Chromie Current Status

**Updated:** 2026-08-24
**Current focus:** Phase 6 current-revision qualification of the Goal-driven single-authority architecture. The Phase 1-5 source remediation is closed; retain source, bilingual live-text/simulator, provider-fault, Social Attention, LAN, and latency evidence on one exact clean revision before making target-behavior claims.

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
- Trusted Capability Runtime and Providers own effect realization/lifecycle, not Goal
  interpretation.
- Runtime events report what happened. Host-correlated Evidence records what is true.
- `CognitiveOpportunity` is an ephemeral readiness carrier. It owns no Goal, Evidence,
  response, or execution truth and may legitimately lead Planner to do nothing.
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

| Area | Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|---|
| Cognitive Gateway / Attention | Maintained configuration controls Attention Review; deterministic protective reflex remains separate. Disabled or unavailable semantic review fails open without fabricating high-confidence addressedness. | Source and focused contract regressions cover admission, fail-open behavior, temporary addressedness rules, and schema boundaries. | Current-revision open-room microphone behavior still requires live evidence. | Development only. |
| Goal Interpretation / Goal Association | GI is WHAT-only. GA is the canonical Goal-continuity writer. Standalone admitted greetings may speak before GA but still receive canonical conversational Goal continuity. GA representation mechanics are internally layered: `goal_association_contract.py` owns model DTO/typed representation, `goal_association_schema.py` owns constrained-decoder schemas, `goal_association_validation.py` owns deterministic normalization/grounding/coverage checks, and `goal_association_prompt.py` owns bounded prompt projection/system prompts. Resolver/inference and canonical continuity remain in the single `GoalAssociationResolver` authority. | Contract and focused Goal/continuity tests are maintained, including guards that none of the extracted mechanical modules owns a model client/runtime/Goal-commit authority and that the Resolver does not re-own their mechanics. | Live-model semantic quality remains revision-bound and must be requalified after material model/prompt changes. | Development only. |
| Planner / communication | One Planner authority is the target HOW and ordinary Communicative-Activity owner; Fast/Deep remain cognition-depth passes of that owner. Both passes now consume one shared canonical Goal/Evidence projection from `planner_context.planner_goal_context`, including cancellation and terminal-result re-entry execution shape, and one shared capability-applicability/provenance-normalization kernel in `planner_validation.py`. Fast qualification/fail-safe mechanics and Deep repair/safety/diagnostic mechanics remain pass-specific in `planner_fast_validation.py` and `planner_deep_validation.py`; those modules may specialize depth policy but may not re-own Goal meaning, Evidence projection, Capability applicability, or common output provenance mechanics. Phase 1A closes generic Confirmation Dialogue wording; Phase 1B closes named-cancellation narration and Host confirmation-remainder synthesis by returning typed cancellation Evidence to Planner; Phase 1C removes deterministic outcome/result wording and returns terminal outcome truth to Planner; Phase 1D removes Host body-recovery Plan/prompt synthesis and exposes only bounded provider retryability facts through Evidence. | Planner/GA/runtime tests and repository policy guard the shared Fast/Deep semantic kernel, terminal-Evidence execution shape, confirmation, named-cancellation, outcome-result, and body-recovery Host semantic ownership plus cancellation/terminal-Evidence binding and Planner re-entry. | Warm latency and complete user-facing authority still require current-revision qualification after source closure. | Development only. |
| WorkDAG / DAGEngine | Planner is the sole ordinary semantic author/modifier of revisioned WorkDAG topology. GA changes Goal continuity only. DAGEngine owns acyclicity/contract checks, readiness, bounded parallel dispatch, dependency/blocked/cancellation state, trace, and immutable completed-node inheritance; normal completion advances mechanically while material change returns Evidence to Planner. Provider-local DAGs remain provider internals. | Focused WorkDAG revision tests prove exact `revision + 1`, stable `dag_id`, completed-node immutability and no redispatch; DAGEngine/Planner/capability tests guard removal of `residual_replan` and engine-authored outcome meaning. | Current-model quality of Planner-authored DAG topology and live multi-Goal revision/merge behavior still requires target qualification. | Development only. |
| Async Runtime / Evidence re-entry | Terminal Runtime events are correlated into Evidence and may create bounded `CognitiveOpportunity` re-entry. Live provider progress may also create a `provider_state` opportunity, but only for a meaningful state transition such as blocked/waiting/degraded/paused/recovering or a material member-state change; running heartbeats and percentage churn are deliberately ignored. Restored open Goals whose pre-restart Runtime bindings are stale retain only bounded original Responsibility provenance; after a fresh provider catalog/state observation, Planner may re-enter from the durable Goal plus that provenance without replaying the old Plan or fabricating a UserTurn. Old request/Plan bindings are invalidated before any newly planned Work can be recorded. Planner may answer, create follow-up Work, revise existing Work, wait, or do nothing. Re-entry is not response-only and does not fabricate a UserTurn, Responsibility, or confirmation. Missing or superseded originating provenance fails that opportunity closed. `situation_revision` and `time_condition` now have bounded producer contracts: trusted Situation observations wake only on a new projection digest, while ConversationState durably owns structured Goal/Plan-bound time conditions and consumes due conditions once. No free-form deadline parsing or background semantic thinking loop is introduced; live Situation-source wiring and Planner-authored time-condition registration still require target qualification. | Focused async regressions cover incremental terminal Evidence, follow-up Work while siblings continue, cancellation/supersession containment, duplicate-execution prevention, missing-provenance rejection before Planner invocation, filtering/relevance policy for live provider-state cognition, and durable restart revalidation that clears stale Runtime bindings only after fresh provider truth reaches Planner. | Provider-backed weather/body episodes should be retained on the exact current revision; live blocked/waiting provider-state and restart-revalidation episodes still require target qualification. The new Situation/time producer boundaries have source regressions; end-to-end trusted Situation input and useful Planner-authored time-condition episodes still require current-revision target evidence. | Development only. |
| Identity / personality truth | Chromie's owner-approved social identity is a six-year-old girl and family young secretary. That is not a biological-human claim; truthful robotic embodiment remains available when relevant. | Mind-profile, prompt-context, and identity/body benchmark contracts guard the two-layer truth boundary. | Bilingual live identity conversation remains to be requalified on the current model/profile. | Development only. |
| Social Attention | Optional embodied decoration remains subordinate to a concrete primary Activity, has no speech or Goal-completion authority, and may validly return none. | Source-level behavior and capability-grounding checks exist. | Reviewed live baseline remains open for the current revision. | Development only. |
| Host structural boundary | Pure Planner-reentry policy lives in `orchestrator/runtime/planner_reentry.py`; TTS text segmentation lives in `orchestrator/runtime/tts_text.py`; Goal-list console projection lives in `orchestrator/runtime/goal_list_console.py`; fail-soft observability recording policy lives in `orchestrator/runtime/observability_recording.py`; fixed-reflex confirmation-token revocation/audit bookkeeping lives with the existing `ConfirmationDialogue` owner in `orchestrator/runtime/confirmation.py`; OS-default audio-device detection/queue/apply lifecycle lives in `orchestrator/runtime/audio_device_lifecycle.py`; top-level process teardown now lives in stateless `orchestrator/runtime/shutdown_lifecycle.py`, reusing the existing InputTurn/Playback/Session owners rather than reimplementing their task or transport truth in `VoiceAssistant`; accelerator sample scheduling, detached task tracking, and trace attachment now live with the existing fail-soft observability policy in `orchestrator/runtime/observability_recording.py`; PlaybackTransport now owns its provider/output methods directly, so the seven `VoiceAssistant` playback/TTS compatibility delegates have been removed while the same session trace spans live on the transport owner; `InputSessionRuntime` now likewise calls its own microphone/VAD/ASR/routed-turn/session-idle operations directly, removing twelve input/session compatibility delegates from `VoiceAssistant` while `InputTurnLifecycle` remains the task-state owner. These are existing Host concerns extracted without adding semantic owners, managers, or state stores. | Focused regressions pass; the method ratchet moves `159 -> 150 -> 142 -> 139 -> 136 -> 129 -> 127 -> 124 -> 117 -> 105`, with the current maintained ceiling at `105 methods / 301 init lines / 108 initialized attributes / 0 direct-LLM calls`. | Not a runtime target; full Host decomposition remains separate from behavior qualification. | Development only. |
| Static quality gates | Repository policy, documentation, configuration ownership/inventory, structure ratchets, and selected static-analysis scopes are maintained. Phase 2 guards documentation authority; Phase 4 additionally rejects verified obsolete prompt/client artifacts and direct re-copying of shared whitespace/JSON-Schema mechanisms. The pinned test environment now includes `pytest-asyncio`. | Dependency-free gates can run without GPU. The incremental Ruff/Mypy ratchet now also owns `scripts/run_mypy.py`; further widening remains one verified slice at a time rather than a blanket repo-wide switch. | Not a runtime target. | Development only. |

## Current open work

1. **Run the `current_revision_qualification` evidence profile on the committed target.**
   The profile requires the canonical source report, the manifest-owned retained live
   interaction cases, the live provider fault matrix, Gateway/Core, Agent Skill/weather,
   Social Attention, and LAN evidence on the same clean revision. WorkDAG revision/no-redispatch
   remains an explicit source gate; selected live cases cover bilingual effectful speech,
   cancellation, provider-backed Evidence re-entry, multi-goal behavior, follow-up continuity,
   duplicate-effect cardinality, and declared warm Planner/playback budgets. Physical voice
   and physical robot remain separate optional evidence tracks.
2. **Retain the structural rule during qualification and later maintenance.** Reopen
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
