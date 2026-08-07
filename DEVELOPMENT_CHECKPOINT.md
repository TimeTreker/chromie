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

The next active semantic Issue is #5, speech-start barge-in with reversible
playback ducking. Diagnose and fix the earliest acoustic/playback boundary:

- credible speech start during playback immediately ducks or temporarily pauses
  audible output without cancelling Cognitive Core work, Goals, body work, or
  capability execution;
- a bounded confirmation window uses available echo or AEC evidence;
- confirmed external speech aborts the current output generation;
- likely echo or noise restores safely without replay or duplication; and
- later ASR and Gateway handling retains sole authority for semantic cancellation
  scope.

Retain the originating playback/VAD episode, reproduce the late-silence boundary,
add focused latency and cancellation-authority assertions, run its general-ability
class, then run the canonical gates and highest safe automated audio E2E profile.
Physical microphone and speaker evidence remains supervised and must be reported
as open when it has not run. Do not move VAD, playback, echo handling, or
user-level cancellation into Soridormi, and do not begin Issue #6 or #7 before
Issue #5 meets its acceptance evidence.

## Canonical owners

- stable boundaries: [Project Charter](docs/PROJECT_CHARTER.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
- notable changes: [Changelog](CHANGELOG.md)
