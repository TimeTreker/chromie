# Development Checkpoint

Checkpoint date: June 8, 2026

## Revisions

- Chromie: `11e4952` (`main`, pushed to `origin/main`)
- Soridormi: `027b626` (`main`, pushed to `origin/main`)

The Chromie checkpoint commit containing this file may be newer than the
revision above. Use the Git tag documented below as the exact resume point.

## Current Milestone

M5 external capability deployment is implementation-complete through the
runtime-backed simulation boundary. The remaining work requires a Linux NVIDIA
target with Soridormi simulator assets.

Completed:

- Nine-tool Soridormi MCP contract and schema probe.
- Safe planning and guarded dry-run acceptance.
- Runtime-backed Soridormi simulation adapter.
- Preemptive stop, cancellation, emergency stop, and safe hold.
- Chromie runtime cancellation acceptance.
- Supervised target runner with evidence capture.
- Fail-fast runtime preflight requiring:
  - `backend=runtime`
  - `mode=sim`
  - `emergency_stop=false`

Pending:

- Run runtime-backed acceptance on the Linux NVIDIA simulator target.
- Retain `.chromie/acceptance/<timestamp>/` evidence.
- Implement Soridormi `HardwareRobot` before enabling real hardware MCP mode.

## Verification

Chromie:

```text
93 passed
```

Soridormi focused MCP suite:

```text
21 passed
```

Soridormi full suite on this macOS host:

```text
475 passed, 1 skipped, 4 unrelated Bash 3.2 portability failures
```

The four failures are in existing shell wrappers using newer Bash features.

## Resume Sequence

On the Linux NVIDIA target:

1. Check out the tagged revisions in both repositories.
2. Populate Soridormi policy/simulator assets.
3. Start the Soridormi simulator:

   ```bash
   ./scripts/run_sim_server.sh \
     --backend mujoco \
     --profile open_duck_forward \
     --no-viewer
   ```

4. Start Soridormi's runtime-backed MCP adapter:

   ```bash
   ./scripts/run_runtime_mcp_server.sh
   ```

5. Configure Chromie's `.env.local` with the reachable endpoint:

   ```env
   AGENT_CAPABILITY_MANIFESTS=/app/capabilities/soridormi.json
   SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp
   AGENT_ENABLE_PLANNING_TASK_GRAPH_EXECUTION=1
   ```

6. Run supervised target acceptance:

   ```bash
   SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 \
     ./scripts/m5_target_acceptance.sh
   ```

7. Restart the Soridormi MCP process after acceptance and verify safe simulator
   state before any further motion.
8. Record the accepted endpoint, hardware profile, GPU results, and recovery
   result in `ROADMAP.md`.

## Safety Notes

- Do not run Soridormi's standalone runtime loop and runtime MCP adapter against
  the same robot backend simultaneously.
- The runtime adapter currently rejects hardware modes.
- Acceptance intentionally leaves Soridormi emergency-stopped.
- Do not bypass the target preflight or the supervision acknowledgement.

## Checkpoint Tag

Both repositories use:

```text
checkpoint-m5-runtime-target-ready-2026-06-08
```
