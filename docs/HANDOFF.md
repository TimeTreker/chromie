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

The latest clean committed implementation baseline before the current
location-binding correction is local commit `1e892e5` (`fix: require delivered
speech in target evidence`). It has not been pushed; `main` is ahead of
`origin/main`. The current correction must be committed and recollected in a
new evidence root before it can become target evidence.

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

## Current reproduced blocker and correction

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

## Resume sequence

1. Run the focused Goal Association, discourse, Agent Skill, and weather
   qualification tests, then the required repository gates:

   ```bash
   python scripts/check_repository_policies.py
   python scripts/check_test_ownership.py
   python scripts/run_ruff.py
   python scripts/run_mypy.py
   python scripts/check_docs.py
   ./scripts/run_tests.sh
   ```

2. Commit the correction and rebuild the Agent image from that exact clean
   revision.
3. Initialize a **new** `source_bound_development` evidence root. Never carry
   artifacts, reports, or human decisions forward from either retained root.
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
