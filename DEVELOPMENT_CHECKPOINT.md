# Chromie Development Checkpoint

Status: current resume point

## Direction

Continue the **Goal-driven single semantic authority** architecture. The
Cognitive Gateway owns ingress, deterministic protective reflexes, and attention
admission. The Goal-driven Cognitive Core owns ordinary semantic interpretation,
goal association, planning, response composition, and outcome reconciliation.
Effects remain authorized only by trusted Host and provider boundaries. The
approved target keeps the Chromie Interaction Orchestrator in Chromie and moves
platform-facing body, vocal, media, sensor, and device execution behind the
Soridormi Execution Runtime and its private Platform Provider.

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

## Approved target boundary

The target architecture is documented but **not implemented yet**:

- Chromie retains session and turn lifecycle, VAD/ASR coordination, Gateway/Core,
  Goal state, response meaning, vocal mode, confirmation, cancellation scope,
  authorization, and end-to-end evidence correlation.
- `soridormi-runtime` executes platform-facing body, vocal, and media
  capabilities and owns provider-local preparation, scheduling, resources,
  synchronization, cancellation, recovery, and normalized evidence.
- `soridormi-platform` is the only simulator or physical-platform adapter and
  owns microphone, speaker, sensors, controllers, drivers, calibration, state
  estimation, and hardware safety.
- External information or memory providers may remain peer platform-neutral
  capabilities when they do not adapt robot or device interfaces.

At the current revision, Chromie still owns TTS synthesis/playback and
Soridormi mainly owns body execution. The live walk/sing/blink episode is not
closed: singing can still be misclassified or rejected before execution, and no
validated singing provider exists. Do not claim the new boundary, singing, or
multimodal synchronization from documentation or unit tests alone.

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

Work the ordered Issue sequence in
[Roadmap: Chromie-Soridormi execution-boundary migration](ROADMAP.md#chromie-soridormi-execution-boundary-migration).
The active implementation Issue is the first one only:

1. reproduce and repair vocal-mode Goal and Planner semantics for the retained
   walk/sing/blink episode;
2. keep singing in the Speaking lane, media playback in Activity, and ordinary
   TTS claims separate from verified singing capability;
3. prevent invented vocal `resource_responsibility`, anchored semantic review,
   unknown Planner step references, and silent body or media substitution;
4. run the focused scenario, its general-ability class, and the canonical source
   gates; and
5. retain live evidence honestly. A unit pass does not prove Soridormi motion or
   vocal execution.

After that Issue closes, proceed to the immutable execution envelope, Soridormi
runtime facade, vocal/TTS migration, media migration, platform audio adaptation,
provider-local multimodal coordination, Orchestrator slimming, and target
evidence in that order. The deferred speech-start barge-in Issue remains
recorded in the Roadmap and must not be folded into the first semantic repair.

## Canonical owners

- stable boundaries: [Project Charter](docs/PROJECT_CHARTER.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
- notable changes: [Changelog](CHANGELOG.md)
