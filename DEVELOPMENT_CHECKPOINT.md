# Development Checkpoint

**Current committed Chromie base:** `91c60e2`
**Pinned Soridormi capability revision:** `4afb4bc6411db4a4194e97349d9466a62efd2f24`
**Verified date:** 2026-06-18
**Current focus:** Physical pilot preparation after M13 text-to-MuJoCo closure;
physical audio validation remains separate

This file is a short resume marker, not a second status or roadmap. Use
[Status](docs/STATUS.md) for capability claims and [Roadmap](ROADMAP.md) for
milestone intent.

## Resume point

The alpha implementation is present:

- native strict structured interaction;
- trusted host Skill Runtime and Soridormi named skills;
- request-bound spoken confirmation;
- deterministic interruption and cancellation;
- seven-case synthetic, virtual-microphone, and supervised acceptance tooling;
- evidence verification and alpha packaging.
- small-model quick Router classification for normal semantic routing while
  stop/cancel/ignore controls remain deterministic;
- simulator-bounded expressive body cues and safe defaults for underspecified
  walking requests;
- ordered TTS playback with bounded chunked generation through configured
  service workers.

The M13 text interaction scope is closed. Linux RTX 5090 GPU smoke passed
21/21; clean seven-case synthetic and PipeWire virtual-mic bundles passed; and
text-to-MuJoCo evidence `20260617T081411Z` passed at Chromie revision `857c15f`
with ordered walk, nod, and turn execution in MuJoCo plus safe idle. Physical
real-microphone/speaker evidence remains open only as a separate voice-device
release-support track. The robust-simulation and provider-readiness milestone is
complete with live no-motion MCP conformance, three-profile parity, and 16/16
Soridormi-owned fault-injection scenarios.

## Next sequence

1. Select one reference-robot candidate and complete the identity,
   independent emergency-stop, software, network, and workspace sections of
   `docs/ROBOT_COMMISSIONING.md`. Record it with the versioned
   `commissioning/reference_robot_candidate.schema.json` contract and keep the
   real manifest under ignored `.chromie/commissioning/`.
2. Keep all physical-motion gates off while validating no-motion health,
   calibration artifact ownership, stop/recovery procedures, and operator
   responsibilities.
3. If the next supported release claims real microphone/speaker voice-device
   operation, run the full seven-case `supervised` matrix on the reference host,
   review audible output and MuJoCo safe-idle/recovery behavior, verify the
   bundle with `--require-clean`, then clear the compatibility blocker.

Do not start physical motion until the robust-simulation and provider-readiness
target evidence passes and the first reference robot satisfies the commissioning
checklist.

## Verification baseline

```text
309 current unittest cases passed
20 legacy Agent tests passed
documentation checks passed
```

The baseline above is Level A evidence. Retained target-host evidence is listed
in `docs/STATUS.md`.

## Useful commands

```bash
./scripts/run_tests.sh
./scripts/show_profile.sh
./scripts/start_services.sh
./scripts/start_orchestrator.sh
python scripts/m13_voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
python scripts/m13_voice_acceptance.py --preflight-only \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi --start-services
python scripts/provider_fault_matrix.py
python scripts/provider_conformance.py
python scripts/verify_provider_readiness.py preflight
python scripts/verify_robot_candidate.py \
  commissioning/reference_robot_candidate.example.json --allow-draft
```

Live commands and recovery procedures are maintained in
[CHROMIE_RUNBOOK.md](CHROMIE_RUNBOOK.md).
First-reference-robot selection requirements are maintained in
[docs/ROBOT_COMMISSIONING.md](docs/ROBOT_COMMISSIONING.md).

## Do not regress

- Keep realtime audio and trusted Skill Runtime coordination in the Orchestrator.
- Keep embodied execution and hardware safety in Soridormi.
- Keep operational controls deterministic.
- Keep physical work default-off and sequential.
- Do not expose low-level robot controls to model-facing contracts.
- Do not report automated or dry-run output as target evidence.
- Do not publish the alpha or remove release blockers without retained evidence.
