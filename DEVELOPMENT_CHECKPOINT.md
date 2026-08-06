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

The active Issue remains the vocal Goal/Planner semantic repair only. Its source
mechanism is now implemented on this patch line:

- Goal Association separates completion modality, semantic lane, output mode,
  and exact-provider need without phrase-specific routing;
- mode-specific vocal performance remains Speaking and cannot be closed by
  generic response text or ordinary TTS;
- existing-audio playback remains Activity;
- suspicious three-or-more-effect decompositions are freshly resegmented without
  the previous DTO as semantic authority;
- normal vocal Goals reject `resource_responsibility`; and
- one Planner ownership representation remains authoritative for redundant step
  references.

Next, close the active defect only through the combined source/live gate from
clean paired Chromie and Soridormi checkouts with the deployed Agent, TTS, and
Soridormi simulator services:

```bash
python scripts/vocal_issue_closure.py \
  --soridormi-repo ../soridormi \
  --close-issue
```

The command must report `closure_eligible=true`. It runs the canonical source
gate on that revision and retains the exact walk/sing/blink trace. The live
result must dispatch and complete the independent walking and blinking members,
return exact singing unavailability or refusal with no executable singing step,
match the clean Soridormi endpoint/checkout revision, and return to safe idle.
A focused unit pass does not prove singing, speaker output, MuJoCo motion, or
physical robot behavior.

Do not begin TTS/playback migration, neutral capability-ID indirection, or a
Soridormi execution facade from this Issue. Revisit vocal hosting only through
the separate evidence triggers in the Roadmap. After the vocal defect closes,
resume Orchestrator simplification and current-revision target evidence work.

## Canonical owners

- stable boundaries: [Project Charter](docs/PROJECT_CHARTER.md)
- delivery order: [Roadmap](ROADMAP.md)
- implementation and evidence: [Current Status](docs/STATUS.md)
- target workflow: [Target Evidence Closure](docs/TARGET_EVIDENCE_CLOSURE.md)
- interfaces: [API Reference](docs/API_REFERENCE.md)
- operation: [Runbook](CHROMIE_RUNBOOK.md)
- notable changes: [Changelog](CHANGELOG.md)
