# Development Checkpoint

**Last committed Chromie base:** `4ba7d1d`
**Pinned Soridormi capability revision:** `a092dc704f1ab797fb1d4f542696fe75026eb171`
**Verified date:** 2026-06-14
**Current focus:** Robust simulation and provider readiness development while
Voice-to-MuJoCo alpha target evidence is deferred to Linux

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
virtual-microphone, and supervised evidence is intentionally deferred. Current
local development begins the robust-simulation phase without clearing any alpha
release gate.

## Next sequence

1. Define provider conformance cases shared by simulator and future no-motion
   physical-provider skeletons.
2. Run the versioned Chromie fault matrix against Soridormi-owned injected
   faults when that endpoint is available.
3. Add thresholds for timeout, cancellation,
   and safe terminal behavior.
4. On Linux, resume the full `synthetic`, `virtual-mic`, and `supervised` alpha
   matrices.
5. Clear the compatibility blocker and publish `0.1.0-alpha.1` only after that
   retained evidence passes.

After the alpha, begin the combined fault-injected simulation and provider
conformance work. Do not start physical motion ahead of that gate.

## Verification baseline

```text
186 current unittest cases passed
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
```

Live commands and recovery procedures are maintained in
[CHROMIE_RUNBOOK.md](CHROMIE_RUNBOOK.md).

## Do not regress

- Keep realtime audio and trusted Skill Runtime coordination in the Orchestrator.
- Keep embodied execution and hardware safety in Soridormi.
- Keep operational controls deterministic.
- Keep physical work default-off and sequential.
- Do not expose low-level robot controls to model-facing contracts.
- Do not report automated or dry-run output as target evidence.
- Do not publish the alpha or remove release blockers without retained evidence.
