# Chromie Current Status

**Updated:** 2026-08-21
**Current focus:** Goal-driven single semantic authority with event-driven,
readiness-driven cognition.

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

## Current implementation and verification state

| Area | Implementation | Automated verification | Target validation | Release readiness |
|---|---|---|---|---|
| Cognitive Gateway / Attention | Maintained configuration controls Attention Review; deterministic protective reflex remains separate. Disabled or unavailable semantic review fails open without fabricating high-confidence addressedness. | Source and focused contract regressions cover admission, fail-open behavior, temporary addressedness rules, and schema boundaries. | Current-revision open-room microphone behavior still requires live evidence. | Development only. |
| Goal Interpretation / Goal Association | GI is WHAT-only. GA is the canonical Goal-continuity writer. Standalone admitted greetings may speak before GA but still receive canonical conversational Goal continuity. | Contract and focused Goal/continuity tests are maintained. | Live-model semantic quality remains revision-bound and must be requalified after material model/prompt changes. | Development only. |
| Planner / communication | One Planner authority owns HOW and exact Communicative Activities. Fast/deep are passes, not separate owners. Legacy Response Composer and GI fast-speech semantic ownership are not maintained paths. | Planner, speech-provenance, playback-identity, and duplicate-delivery regressions protect the current owner boundary. | The declared warm latency targets still require current-revision live qualification. | Development only. |
| Async Runtime / Evidence re-entry | Terminal Runtime events are correlated into Evidence and may create bounded `CognitiveOpportunity` re-entry. Planner may answer, create follow-up Work, revise existing Work, wait, or do nothing. Re-entry is not response-only and does not fabricate a UserTurn, Responsibility, or confirmation. Missing originating Responsibility provenance retains Evidence but fails that opportunity closed. | Focused async regressions cover incremental terminal Evidence, follow-up Work while siblings continue, cancellation/supersession containment, duplicate-execution prevention, and missing-provenance rejection before Planner invocation. | Provider-backed weather/body episodes should be retained on the exact current revision. | Development only. |
| Identity / personality truth | Chromie's owner-approved social identity is a six-year-old girl and family young secretary. That is not a biological-human claim; truthful robotic embodiment remains available when relevant. | Mind-profile, prompt-context, and identity/body benchmark contracts guard the two-layer truth boundary. | Bilingual live identity conversation remains to be requalified on the current model/profile. | Development only. |
| Social Attention | Optional embodied decoration remains subordinate to a concrete primary Activity, has no speech or Goal-completion authority, and may validly return none. | Source-level behavior and capability-grounding checks exist. | Reviewed live baseline remains open for the current revision. | Development only. |
| Host structural boundary | Pure Planner-reentry policy lives in `orchestrator/runtime/planner_reentry.py`; TTS text segmentation lives in `orchestrator/runtime/tts_text.py`; Goal-list console projection lives in `orchestrator/runtime/goal_list_console.py`. These are existing Host concerns extracted without adding semantic owners, managers, or state stores. | Focused regressions pass; the method ratchet moves `159 -> 150 -> 142`, with the current ceiling at `142 methods / 305 init lines / 110 initialized attributes / 0 direct-LLM calls`. | Not a runtime target; full Host decomposition remains separate from behavior qualification. | Development only. |
| Static quality gates | Repository policy, documentation, configuration ownership/inventory, structure ratchets, and selected static-analysis scopes are maintained. | Dependency-free gates can run without GPU. Ruff/Mypy scopes are still deliberately narrow and must be widened only after the pinned analyzers pass on each added slice. | Not a runtime target. | Development only. |

## Current open work

1. **Close the canonical local gate in a dependency-complete environment.** Keep
   identity truth, Attention evidence, greeting continuity, speech ownership, prompt
   projection, asynchronous Responsibility provenance, and current documentation aligned
   with the Charter requirements.
2. **Requalify human-facing latency on the current revision.** The owner-approved warm
   targets remain `<=2.0 s` from validated GI handoff to first valid Planner
   Communicative-Activity commitment and `<=3.0 s` from that commitment to playback
   start. Long qualification watchdogs are not evidence that these interaction targets
   pass.
3. **Retain current-revision asynchronous episodes.** At minimum, prove provider-backed
   information Evidence can trigger useful follow-up planning without waiting for
   unrelated sibling Work, and prove embodied terminal Evidence can likewise advance an
   open Responsibility without callback-owned speech.
4. **Widen Ruff/Mypy ratchets incrementally.** The existing four-file scopes are not a
   meaningful quality claim for the whole cognitive/runtime core. Expand along existing
   ownership seams only after the pinned toolchain passes; do not weaken the gate or add
   compatibility exclusions merely to increase coverage.
5. **Continue structural simplification separately.** Planner-reentry policy plus the
   purely mechanical TTS-text and Goal-list projection seams are extracted and the Host
   ratchet is lower. Large Host/Planner/GA files remain a maintainability risk, but later decomposition must
   follow existing configuration, input-lifecycle, prompt-projection, validation,
   runtime, evidence, cancellation, and observability seams. Do not create one
   manager/service per cognitive concept and do not mix broad refactors into semantic
   behavior fixes.
6. **Complete revision-bound human-like interaction evidence.** Open-room addressedness,
   greeting uniqueness, identity questions, fresh information, barge-in, late Goal
   results, multi-Goal cancellation, timeout behavior, Social Attention, and startup
   orientation should be judged as complete episodes with actual delivery/effect
   evidence.

## Evidence interpretation

Source implementation, automated verification, target validation, and release readiness
are separate axes. A passing unit/integration suite does not prove microphone, audible
speaker, GPU latency, simulator, or physical-provider behavior. Likewise, retained live
evidence from an older revision does not silently qualify the current source after a
material cognition, model, provider, prompt, or timing change.

Chromie remains a development project. No publication or release-readiness claim is made
by this status page.
