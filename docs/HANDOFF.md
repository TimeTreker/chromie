# Project Handoff

Last updated: 2026-08-02

This file is the concise resume aid for another checkout or coding session.
Authoritative implementation and evidence claims remain in
[Current Status](STATUS.md), delivery order remains in
[Roadmap](../ROADMAP.md), and exact workflow contracts remain in
[Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

## Resume here

The active Issue is **Close Current-Revision Target Evidence**. Do not begin the
queued response-latency architecture until this evidence Issue closes, except
to repair a reproduced qualification blocker.

The current implementation baseline includes delivered-speech evidence,
explicit location-binding provenance, weather-correction continuity, and the
exact-replacement-binding clarification correction below. The latest
implementation commit subject is `fix: preserve explicit correction bindings`.
These local commits have not been pushed; `main` is ahead of `origin/main`.
Rebuild this exact clean revision and collect a new evidence root before
treating the correction as target evidence.

Chromie retains one Goal-driven semantic authority. The Host validates and
coordinates but does not decide ordinary meaning, capability selection, or
planning. Soridormi owns embodied feasibility and safety. Do not introduce
phrase rules, confidence thresholds, or Host mappings to choose conversational,
Fast, or Deep reasoning paths.

## Retained evidence to preserve

The original delivery false-positive remains at:

```text
.chromie/acceptance/target-evidence/20260801T120756Z
```

It is clean and source-bound to Chromie `9e12a2c`. Preserve it, but **do not
approve, finalize, or resume it**. Its direct question retained valid cognition
but scheduled three TTS chunks, played zero, skipped all three, and recorded
`chromie.speak` as `failed/playback_not_started` while the old scenario still
reported `ok=true`.

The correction is commit `1e892e5`. Manifest-declared speech turns now require
complete correlated delivery and successful `chromie.speak` execution, and
preflight performs a complete generated-environment-bound no-playback TTS
synthesis. The corrected verifier rejects the old root.

The next clean source-bound root is:

```text
.chromie/acceptance/target-evidence/20260802T011257Z
```

It is bound to Chromie `1e892e5` and Soridormi
`c5a3debf4819fa3cc6b631f3b0a25570ce5f5c17`. Preserve it as the originating
episode for the next defect, but **do not finalize or resume it**:

- TTS synthesis preflight passed;
- all five Gateway/Core live-text scenarios passed with complete required
  delivery, including `4/4` chunks for the direct question and `6/6` plus
  `4/4` for the Beijing weather turns;
- the paired walk/nod/turn MuJoCo scenario completed all three Capabilities and
  returned standing and safe idle;
- active cancellation reached the Provider, accepted deterministic `Stop.`,
  cancelled `soridormi.walk_velocity`, suppressed stale speech, and returned
  safe idle;
- Gateway/Core human review remains explicitly `pending`;
- Agent Skill/weather verification failed, so no weather review or
  qualification report may be carried forward;
- required Social Attention and LAN-exposure tracks remain absent.

The later clean source-bound root is:

```text
.chromie/acceptance/target-evidence/20260802T014055Z
```

It is bound to Chromie `bba21a2` and the same Soridormi revision. Preserve it,
but **do not finalize or resume it**. Its complete Gateway/Core automatic
collection passed with delivered speech, paired MuJoCo execution, terminal-
Fast active cancellation, and safe idle; human review remains `pending`.
Weather collection then exposed the adjacent correction-continuity defect
below, so the root is an originating failure rather than closure evidence.

Clean root `20260802T022441Z` on revision `b4157b3` passed both automatic
Gateway/Core and Agent Skill/weather collection. It retained complete TTS,
paired walk/nod/turn MuJoCo execution, active cancellation, safe idle, exact-
result dialogue reuse, and fresh Neixiang correction/reference reads. Local LAN
exposure also passed for `172.20.10.2`. Human reviews and second-machine LAN
evidence remained open. A documentation-only correction then changed the
revision, so preserve this root but **do not finalize or resume it**.

The next final-source attempt is:

```text
.chromie/acceptance/target-evidence/20260802T024019Z
```

It is bound to clean Chromie revision `662a1c7`. Its complete Gateway/Core
automatic collection passed, pending human review. Preserve it as the
originating episode for the clarification-continuity defect below, but **do not
finalize or resume it**: the weather correction was treated as provider
ambiguity, and the final indirect turn consequently returned to Chongqing.

## Reproduced blockers and current correction

The first weather turn in `20260802T011257Z` exposed an explicit-binding
provenance defect:

```text
scenario: neixiang_weather_and_exact_followup / weather_initial
input: 河南省内乡县现在下雨了吗？
Goal Association binding: Xiang County, Henan Province
planned request: chromie.weather.lookup(location="Xiang County, Henan Province")
runtime result: failed / location_not_found
follow-up defect: repeated chromie.weather.lookup instead of using retained evidence
```

The exact artifact is:

```text
.chromie/acceptance/target-evidence/20260802T011257Z/agent-skill-weather/
  live-text/scenarios/neixiang_weather_and_exact_followup/summary.json
```

Root-cause record:

```text
Observed failure: an explicit Chinese place was mistranslated before planning, so the correct provider truth was location_not_found.
Expected contract: a directly named location remains a contiguous verbatim user-language binding; only an indirect reference may use a supplied referent's canonical value.
Earliest wrong component: model-facing Goal Association binding validation.
Fix class: contract/schema validation plus the existing bounded model repair; not a phrase map, route rule, provider alias, or Host semantic choice.
Regression boundary: exact direct-location repair plus indirect-referent preservation, followed by the complete live weather manifest.
Evidence level: clean originating failure plus dirty rebuilt-service diagnostic; clean post-fix target collection still required.
General ability protected: stable entity grounding across languages and providers.
```

`GoalAssociationResolver` now rejects a new direct location binding that has no
referent provenance and is not grounded as a contiguous span of the
authoritative current turn. One existing schema-constrained model repair may
correct it; a second invalid result fails closed. This is typed provenance
validation, not Host extraction of a place name or selection of a meaning.

Dirty diagnostic `/tmp/chromie-weather-binding-diagnostic` is explicitly
non-qualifying but passes the complete two-scenario live manifest: the first
request remains exactly `河南省内乡县`, the Provider completes, the exact follow-up
uses retained dialogue with no second lookup, the correction binds `内乡`, and
the indirect `那边` lookup remains on `内乡`. Its verifier reports only
`runtime identity is not source clean`.

Clean root `20260802T014055Z` then reproduced the next general continuity
defect. The initial Chongqing lookup used a `mixed` Plan but did not receive the
safe-read pre-evidence review. The correction `不是重庆，我说的是内乡。` was routed
as chat, and the planner relabelled the prior Chongqing facts as Neixiang
without executing a new read. The final `那边` turn selected Neixiang but omitted
the supplied referent provenance and failed closed during Goal Association
repair.

Root-cause record:

```text
Observed failure: a material external-read binding correction could reuse and relabel stale facts; mixed safe reads skipped semantic review; indirect repair omitted typed referent provenance.
Expected contract: a material entity correction that still depends on external facts performs a new exact read; only delivered evidence for the same Goal may support a capability-dependent respond outcome; every fresh safe read is reviewed; indirect values carry the supplied referent ID and surface form.
Earliest wrong components: model-owned route continuity review, mixed-plan safe-read classification, and Goal Association repair guidance.
Fix classes: semantic model contract, typed plan/provenance validation, qualification verification, and regression evidence; no Host phrase rule or entity map.
Regression boundary: corrected external-read route, mixed safe-read review, evidence-bound capability response, indirect referent repair, required applied runtime status, then the complete live weather manifest.
Evidence level: clean originating failure plus dirty rebuilt-service diagnostic; clean post-fix target collection still required.
General ability protected: stable cross-turn entity correction and truthful external-result grounding.
```

The current implementation sends material external-read corrections through the
existing model-owned semantic route review, reviews both `execute` and `mixed`
safe reads, requires capability-dependent direct responses to cite delivered
evidence-bound dialogue for the same Goal, and gives the existing bounded Goal
Association repair the complete indirect-reference provenance shape. The
weather verifier now also requires each manifest-declared runtime turn to end
with `status=applied`.

Focused contract coverage passes 229/229. The relevant Level A general-ability
classes `robust_intent_understanding` and
`tool_and_conversation_lane_discipline` pass 17/17. This is deterministic
automatic evidence, not a live provider, speaker, simulator, or target claim.

Dirty diagnostic `/tmp/chromie-weather-continuity-diagnostic-3` is explicitly
non-qualifying. It passes every weather semantic, provider, continuity, runtime,
and TTS assertion; the verifier's only error is `runtime identity is not source
clean`. The exact-result follow-up uses zero Capabilities, while the correction
and final indirect turn each perform a fresh Neixiang lookup. All five turns
have applied runtime events and complete speech delivery with zero failed or
skipped chunks.

Clean root `20260802T024019Z` exposed one remaining nondeterministic continuity
gap. Goal Interpretation and its semantic repair both treated the user's exact
replacement location `内乡` as a request requiring more administrative detail.
Goal Association repeated that judgment, so it committed no corrected Goal or
referent. The final `那边` turn then continued the still-active Chongqing Goal
and executed the wrong provider query.

Root-cause record:

```text
Observed failure: an exact user-supplied replacement binding was mistaken for provider-canonicalization ambiguity, so no corrected Goal was committed and the next indirect reference fell back to stale state.
Expected contract: an exact replacement binding continues the existing external-read responsibility verbatim; the Capability resolves the value or reports provider ambiguity. Clarification is reserved for genuinely underdetermined user meaning.
Earliest wrong components: model-owned Goal Interpretation semantic repair, followed by Goal Association clarification.
Fix classes: semantic model contract plus bounded independent Goal Association review; no Host phrase rule, place-name extraction, provider alias, or deterministic route choice.
Regression boundary: correction-route prompt, candidate-Goal clarification review, complete five-turn weather manifest, provider query, runtime status, and TTS delivery.
Evidence level: clean originating failure plus dirty rebuilt-service diagnostic; clean post-fix target collection still required.
General ability protected: stable cross-turn entity correction without offloading provider resolution to the user.
```

Goal Interpretation now distinguishes user-semantic ambiguity from downstream
provider resolution: an exact replacement binding stays verbatim and continues
the external read. Goal Association applies the same contract and independently
reviews a proposed clarification when a candidate Goal exists and the admitted
route was not clarification. The review remains model-owned and may preserve a
genuinely necessary question.

Dirty diagnostic `/tmp/chromie-weather-continuity-diagnostic-4` is explicitly
non-qualifying because it runs a rebuilt dirty image with the earlier retained
runtime identity. It passes the complete weather verifier with zero semantic or
provider errors: the exact follow-up uses no Capability, the correction and
final indirect turn execute fresh Neixiang reads, all five runtime events are
`applied`, and every scheduled TTS chunk is played with zero failures or skips.
Human review remains pending and is not inferred from the automatic result.

## Resume sequence

1. Confirm the focused Goal Interpretation, Goal Association, discourse, Agent
   Skill, weather, and
   relevant general-ability checks plus the required repository gates remain
   green after any further source change:

   ```bash
   python scripts/check_repository_policies.py
   python scripts/check_test_ownership.py
   python scripts/run_ruff.py
   python scripts/run_mypy.py
   python scripts/check_docs.py
   ./scripts/run_tests.sh
   ```

2. Rebuild all qualification services from the exact clean committed revision.
3. Initialize a **new** `source_bound_development` evidence root. Never carry
   artifacts, reports, or human decisions forward from any retained root.
4. Recollect and review Gateway/Core and Agent Skill/weather, collect and review
   Social Attention, attach local plus second-machine LAN reports, then finalize
   the default closure. Human review remains explicit.

## Work after evidence closure

The accepted response architecture is queued, not yet an implementation claim:

```text
                  +-- Speech lane: safe acknowledgement -> TTS immediately
Shared Goal Frame +-- Action lane: plan -> validate -> confirm -> execute
                  +-- Evidence events -> progress/result speech

Typed Core interpretation
        |
        +-- conversational + no effects -----> direct Speech lane
        +-- simple + complete + validated ---> Fast Planner
        +-- uncertain/complex/risky ---------> Deep Planner
```

Implement it through the existing typed Goal, response, plan, evidence, and
delivery owners. One Core remains the semantic authority. The direct
conversation branch must be model-authored and typed, never selected by a
greeting table. Preserve independent Goals across ordinary overlapping turns;
only explicit deterministic scope or Core-authorized semantic interruption may
cancel them. True incremental audible PCM playback remains a later playback-
delivery lifecycle Issue.
