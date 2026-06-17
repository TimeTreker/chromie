# Development Checkpoint

**Last committed Chromie base:** `f0e22ba`
**Pinned Soridormi capability revision:** `4afb4bc6411db4a4194e97349d9466a62efd2f24`
**Verified date:** 2026-06-15
**Current focus:** Physical pilot preparation while Voice-to-MuJoCo alpha waits
for supervised real-microphone/speaker closure

This file is a short resume marker, not a second status or roadmap. Use
[Status](docs/STATUS.md) for capability claims and [Roadmap](ROADMAP.md) for
milestone intent.

## Resume point

The alpha implementation is present:

- native strict structured interaction;
- trusted host Skill Runtime and Soridormi named skills;
- request-bound spoken confirmation;
- deterministic interruption and cancellation;
- seven-case synthetic, virtual-microphone, and supervised acceptance;
- evidence verification and alpha packaging.

The alpha implementation remains frozen except for defects. Linux RTX 5090 GPU
smoke passed 21/21, and clean seven-case synthetic and PipeWire virtual-mic
bundles passed at `f0e22ba`. Supervised real-microphone/speaker evidence remains
open. The robust-simulation and provider-readiness milestone is complete with live
no-motion MCP conformance, three-profile parity, and 16/16 Soridormi-owned
fault-injection scenarios. This does not clear any alpha release gate.

## Next sequence

1. Run the full seven-case `supervised` alpha matrix on the reference host,
   review audible output and MuJoCo safe-idle/recovery behavior, and verify the
   bundle with `--require-clean`.
2. Clear the compatibility blocker and publish `0.1.0-alpha.1` only after that
   retained evidence passes.
3. Select one reference-robot candidate and complete the identity,
   independent emergency-stop, software, network, and workspace sections of
   `docs/ROBOT_COMMISSIONING.md`. Record it with the versioned
   `commissioning/reference_robot_candidate.schema.json` contract and keep the
   real manifest under ignored `.chromie/commissioning/`.
4. Keep all physical-motion gates off while validating no-motion health,
   calibration artifact ownership, stop/recovery procedures, and operator
   responsibilities.

Do not start physical motion until the robust-simulation and provider-readiness
target evidence passes and the first reference robot satisfies the commissioning
checklist.

## Verification baseline

```text
273 current unittest cases passed
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
