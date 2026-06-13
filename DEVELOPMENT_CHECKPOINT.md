# Development Checkpoint

**Last committed Chromie base:** `05ce82c304051f57456a8190fe501aaf596a2df3`
**Pinned Soridormi capability revision:** `a092dc704f1ab797fb1d4f542696fe75026eb171`
**Verified date:** 2026-06-14
**Current focus:** Voice-to-MuJoCo alpha evidence and release

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

The next work is operational evidence, not another interaction architecture
rewrite.

## Next sequence

1. Confirm the GPU-free baseline with `./scripts/run_tests.sh`.
2. Start the five Chromie services and a runtime-backed MuJoCo Soridormi MCP
   endpoint.
3. Run and retain the full `synthetic` alpha matrix.
4. Run and retain the full `virtual-mic` matrix.
5. Commit the candidate revision, run the complete `supervised` matrix, and
   review audio, safe idle, cancellation, recovery, IDs, and privacy.
6. Clear the compatibility blocker only after evidence passes.
7. Generate and publish the narrowly scoped `0.1.0-alpha.1` prerelease.

After the alpha, begin the combined fault-injected simulation and provider
conformance work. Do not start physical motion ahead of that gate.

## Verification baseline

```text
170 current unittest cases passed
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
