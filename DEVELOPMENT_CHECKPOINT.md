# Chromie Development Checkpoint

Status: current resume point

## Direction

Continue the **Goal-driven single semantic authority** architecture. The
Cognitive Gateway owns ingress, deterministic protective reflexes, and attention
admission. The Goal-driven Cognitive Core owns ordinary semantic interpretation,
goal association, planning, response composition, and outcome reconciliation.
Effects remain authorized only by trusted Host and provider boundaries.

## Current checkpoint

The latest source cleanup establishes:

- typed `interpretation_unavailable` instead of invented semantic fallback;
- strict catalog-backed action proposals in semantic repair;
- memory in maintained Goal-driven apply profiles;
- fail-closed excluded lanes without legacy semantic re-entry;
- a current Gateway-to-Core-to-Fast-Planner smoke contract;
- archive-portable deterministic source identity;
- benchmark validation in the canonical source gate;
- removal of duplicate audits, handoffs, implementation plans, and obsolete
  Route2/Route3 or named-skill planning documents.

`/interaction` and `/run` remain compatibility surfaces. Their semantic planner
is emergency-only and must not be used as ordinary fallback.

## Resume commands

From the repository root:

```bash
python scripts/check_repository_policies.py
python scripts/check_test_ownership.py
python scripts/runtime_configuration_inventory.py --check
python scripts/check_runtime_structure.py
python scripts/check_docs.py
python scripts/semantic_authority_audit.py --check
./scripts/benchmark_check.sh
python -m unittest discover -s tests -p 'test_*.py'
```

In a dependency-complete environment, use the canonical gate instead:

```bash
./scripts/run_tests.sh
```

For a running Agent service:

```bash
python scripts/control_plane_smoke.py --base-url http://127.0.0.1:8092
```

For the maintained GPU profile and service lifecycle, use:

```bash
bash scripts/gpu_smoke_test.sh
```

Do not report GPU, microphone, speaker, MuJoCo, or physical-provider validation
unless the command actually ran against that target and retained its evidence.

## Next engineering work

The vocal Goal/Planner defect has passed the combined canonical and live Level C
gate. The clean retained bundle at
`.chromie/acceptance/vocal-issue-1/20260807T032038Z` records Chromie `6809a84`,
Soridormi `1c15371`, exact typed Goal ownership through body execution, parallel
walking/blinking completion, truthful singing unavailability with zero steps,
and safe idle before and after. It does not prove a singing provider, physical
microphone or speaker behavior, physical robot behavior, or release readiness.

Issue #5 has met its source and highest safe automated audio criteria. Clean
Chromie `94718ab` passed `barge-in-echo` 6/6 and `barge-in` 7/7 in
`.chromie/acceptance/voice/issue-5-94718ab-clean`. The retained output replay
ducked in 0.0 ms, survived ASR distortion through order-aware echo matching,
resumed the same generation, and completed 11/11 scheduled chunks before the
next case. Confirmed external speech ducked in 0.0 ms, reached output silence in
8.3 ms, retained `cancel_cognitive_work=false`, and produced a later distinct
Gateway output-only receipt with zero provider or dispatch failures. Physical
microphone/speaker, arbitrary human pronunciation, audible device latency, and
the real acoustic echo path remain supervised target evidence rather than source
closure claims.

The active semantic Issue remains #6 through its final clean current-revision
default-provider replay. Its exact `chromie.vocal.perform` source contract now
preserves the Speaking lane and the current Chromie playback boundary:

- one provider-prefixed capability identity survives proposal, validation,
  authorization, execution, cancellation, and evidence in source tests;
- requests use typed vocal modes and declarations bind supported modes to
  streaming, timing, sample format, concurrency, cancellation, provenance, and
  retained mode-specific evidence;
- ordinary TTS regressions remain passing and distinct from recitation, humming,
  and singing evidence;
- unsupported modes return exact unavailable outcomes and silent downgrades
  fail; and
- the focused cognitive-runtime scenario passes through Goal Association, Fast
  Planner, Deep Planner, Response Composer, and Host materialization with
  `execution_lane=speaking`.

The pre-commit source evidence passed the focused provider/TTS suite, the exact
recitation scenario, the `stable_capability_grounding` class 8/8, and the full
canonical gate with 2,041 maintained tests, 20 legacy Agent tests, and 102
benchmark tests. Commit this reviewed source, run
`scripts/vocal_issue_closure.py` from that clean revision, inspect the complete
retained live output, and only then advance to Issue #7.

Do not place backend names in semantic Goals, add a neutral late-binding alias,
move playback ownership into Soridormi, or begin Issue #7 before Issue #6 meets
its clean current-revision delivery evidence. Real singing remains unvalidated
until mode-specific target evidence exists.

## Canonical owners

- stable boundaries: [Project Charter](docs/PROJECT_CHARTER.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
- notable changes: [Changelog](CHANGELOG.md)
