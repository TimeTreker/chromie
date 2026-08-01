# Project Handoff

Last updated: 2026-08-01

This file is the concise resume aid for another checkout or coding session.
Authoritative implementation and evidence claims remain in
[Current Status](STATUS.md), delivery order remains in
[Roadmap](../ROADMAP.md), and exact workflow contracts remain in
[Development Checkpoint](../DEVELOPMENT_CHECKPOINT.md) and
[Target Evidence Closure](TARGET_EVIDENCE_CLOSURE.md).

## Resume here

The active Issue is **Close Current-Revision Target Evidence**. Do not begin the
queued response-latency architecture until this evidence Issue closes, except
to repair the reproduced qualification blocker below.

The latest implementation baseline is clean commit `9e12a2c` (`fix: simplify
numeric plan provenance`). It was pushed to `origin/main` before this handoff
update. The handoff commit is documentation-only, so retained evidence below is
correctly bound to its parent revision rather than to the handoff commit.

Chromie retains one Goal-driven semantic authority. The Host validates and
coordinates but does not decide ordinary meaning, capability selection, or
planning. Soridormi owns embodied feasibility and safety. Do not introduce
phrase rules, confidence thresholds, or Host mappings to choose conversational,
Fast, or Deep reasoning paths.

## Latest retained evidence

Evidence root:

```text
.chromie/acceptance/target-evidence/20260801T120756Z
```

It is clean and source-bound to Chromie `9e12a2c` and Soridormi
`c5a3debf4819fa3cc6b631f3b0a25570ce5f5c17`. Preserve it as diagnostic
evidence, but **do not approve, finalize, or resume it**:

- Gateway/Core live text, paired compound MuJoCo, active cancellation, safe
  idle, and runtime-identity collection stages completed;
- active cancellation used terminal Fast Planner output, exact
  `soridormi.walk_velocity` arguments `vx_mps=0.2` and `duration_s=20`, reached
  Provider start, accepted `Stop.`, cancelled the current interaction, and
  returned to safe idle without Deep Planner;
- Agent Skill/weather automatic verification has zero errors, validates live
  Skill selection and provider-backed weather, and remains `passed=false` only
  because fingerprint-bound human review is pending;
- Gateway/Core and weather human-review files remain `pending` and must never
  be approved automatically;
- required Social Attention and LAN-exposure tracks are absent;
- physical voice and physical robot tracks are optional for the active
  `source_bound_development` profile and their absence is not this blocker.

## First blocker to fix

The retained direct-question turn exposed a false-positive qualification:

```text
scenario: direct_question_admission
input: Chromie, what can you do?
cognitive_interaction_ready: 35.576 s
tts_stream_start: 35.594 s
playback-start deadline: 55.582 s
session result: scheduled_tts=3 played_tts=0 skipped_tts=3
runtime result: failed / playback_not_started
scenario result: ok=true
```

The exact artifact is:

```text
.chromie/acceptance/target-evidence/20260801T120756Z/
  gateway-core/live-text/scenarios/direct_question_admission/summary.json
```

This is the earliest wrong boundary for the claim that the test passed: the
qualification scenario requires admission, Core, and the `chat` lane, but does
not require delivered speech. The live runner rejects `failed_tts` but does not
reject `skipped_tts`, zero playback, or failed `chromie.speak` execution. The
qualification preflight checks Agent and Soridormi readiness but not a complete
no-playback TTS synthesis. The normal operator launcher already warms the TTS
candidates; the low-level service launcher used during collection does not.

Root-cause record:

```text
Observed failure: valid direct-answer cognition produced no playback, while the scenario reported ok=true.
Expected contract: a required-speech live scenario cannot pass without correlated delivery, and collection must fail fast when its selected TTS cannot synthesize within the declared readiness budget.
Earliest wrong component: qualification preflight and live-scenario evidence contract.
Fix class: test-evidence plus operational readiness; not semantic routing or prompt wording.
Regression boundary: preflight readiness test and black-box live-text scenario with scheduled-but-skipped speech.
Evidence level: clean source-bound retained trace, incomplete target closure.
General ability protected: truthful end-to-end evidence coverage.
```

Start source inspection at:

- `benchmarks/manifests/cognitive_gateway_core_qualification_v1.json` — the
  direct-question expectation lacks a delivery requirement;
- `scripts/interaction_text_mujoco_check.py` — required speech currently checks
  scheduling and `failed_tts`, but not skipped/undelivered speech or execution
  failure;
- `scripts/preflight_cognitive_gateway_core_qualification.py` — readiness does
  not establish TTS synthesis readiness;
- `scripts/run_cognitive_gateway_core_qualification.py` — owns stage ordering;
- `tests/test_cognitive_gateway_core_preflight.py` and
  `tests/test_cognitive_gateway_core_qualification.py` — add fail-first
  regression coverage at the evidence boundary.

The correction must remain operational and typed. It must not inspect user
phrases or add a semantic route rule. Do not weaken the existing playback
barrier; make the qualification observe it correctly.

## Resume sequence

1. Reproduce the retained defect from the artifact before editing:

   ```bash
   jq '.turns[0] | {duration_ms, error, session_state}' \
     .chromie/acceptance/target-evidence/20260801T120756Z/gateway-core/live-text/scenarios/direct_question_admission/summary.json
   ```

2. Add a fail-first case in the existing qualification/preflight test owners,
   then implement the smallest evidence/readiness correction.
3. Run focused qualification, preflight, live-text, TTS, and workflow tests,
   followed by the required repository gates:

   ```bash
   python scripts/check_repository_policies.py
   python scripts/check_test_ownership.py
   python scripts/run_ruff.py
   python scripts/run_mypy.py
   python scripts/check_docs.py
   ./scripts/run_tests.sh
   ```

4. Commit the correction and initialize a **new** clean
   `source_bound_development` evidence root. Never carry human approval or
   reports forward from `20260801T120756Z`.
5. Recollect and review Gateway/Core and Agent Skill/weather, collect and review
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
