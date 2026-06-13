# Development Checkpoint

**Last committed Chromie base:** `868da56`
**Pinned Soridormi capability revision:** `a092dc704f1ab797fb1d4f542696fe75026eb171`
**Verified date:** 2026-06-14
**Current focus:** Robust simulation and provider readiness target validation
while Voice-to-MuJoCo alpha target evidence is deferred to Linux

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

The alpha implementation remains frozen except for defects. Linux/GPU,
virtual-microphone, and supervised evidence is intentionally deferred. The
Chromie-side robust-simulation and provider-readiness implementation is now
complete without clearing any alpha release gate. Milestone closure waits for
live Soridormi provider and fault-injection evidence.

## Next sequence

1. Update the pinned Soridormi capability snapshot after upstream adds
   `hardware_shadow`, dry-run named skills, and test-only fault injection; run
   `verify_provider_readiness.py preflight` until it passes.
2. Run the shared conformance suite against live Soridormi `sim`,
   `hardware_shadow`, and `hardware_dry_run` providers when available and
   retain their traces and parity result.
3. Run the versioned Chromie fault matrix against Soridormi-owned injected
   faults when that endpoint is available.
4. Verify the complete provider-readiness bundle with `--require-clean`.
5. On Linux, resume the full `synthetic`, `virtual-mic`, and `supervised` alpha
   matrices.
6. Clear the compatibility blocker and publish `0.1.0-alpha.1` only after that
   retained evidence passes.

Do not start physical motion until the robust-simulation and provider-readiness
target evidence passes and the first reference robot satisfies the commissioning
checklist.

## Verification baseline

```text
202 current unittest cases passed
20 legacy Agent tests passed
documentation checks passed
```

This is Level A evidence only.

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
