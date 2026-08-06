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

The active Issue is the vocal Goal/Planner semantic repair only. Keep the current
ownership boundary while implementing it:

1. add typed completion-lane, output-mode, and provider-need judgments without
   phrase-specific routing;
2. keep singing, humming, and recitation in Speaking and existing-audio playback
   in Activity;
3. preserve exact provider-prefixed capability identity, using a Chromie-owned
   vocal capability such as `chromie.vocal.perform`;
4. reject invented vocal `resource_responsibility`, stale semantic-review
   anchoring, and unknown Planner step references;
5. run the retained walk/sing/blink episode, generalized vocal/media scenarios,
   the general-ability class, and the canonical source gate; and
6. retain live evidence honestly. A unit pass does not prove singing, speaker
   output, MuJoCo motion, or physical robot behavior.

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
