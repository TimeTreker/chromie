# Chromie Roadmap

Last reviewed: June 8, 2026

Chromie's roadmap is organized around deployable milestones. A milestone is complete only when its code, contracts, tests, and relevant operating documentation agree.

## Current Position

**Current milestone: M5 - External capability deployment and acceptance (in progress).**

M4 is complete: TaskGraph planning, validation, dry-run, guarded MCP execution,
single-use confirmation grants, cancellation, traces, monitor gating, and
emergency fallback orchestration are integrated into the Agent service. M5
connects those boundaries to Soridormi, the robot cerebellum, and validates
them on a target GPU/robot host. Hardware profiles are deployment choices, not
part of the cross-project capability contract.

## Milestones

| Milestone | Status | Outcome |
|---|---|---|
| M0 - Runtime foundation | Complete | Docker services, host Orchestrator boundary, hardware profiles, and generated runtime configuration |
| M1 - Realtime voice loop | Complete | ASR, Router, Agent, Ollama, TTS, interruption, playback, and deterministic fallback behavior |
| M2 - Contracts and safety | Complete | Cross-service contracts, confirmation gating, mock hardware flow, and GPU-free regression suite |
| M3 - Target GPU verification | Tooling complete; target run pending | Automated GPU, service health, Ollama, ASR WebSocket, and TTS backend smoke checks |
| M4 - TaskGraph production integration | Complete | Agent planning, validation, traces, guarded MCP execution, one-time grants, cancellation, and emergency fallbacks |
| M5 - External capability deployment | **In progress** | Connect a real Soridormi manifest/server and complete target-host acceptance |
| M6 - Extended autonomy | Planned | Vision, richer memory, recovery policies, observability, and longer-running tasks |

## M4 Exit Criteria

- Agent API exposes TaskGraph validation, dry-run execution, and trace lookup.
- Agent planning can produce a structured graph from an eligible routed request.
- Every generated graph is validated against the active capability registry before execution.
- Real tool execution remains behind `ToolInvoker`; physical motion requires confirmation and safety monitoring.
- Graph lifecycle, failures, fallbacks, and timing are observable.
- Integration tests cover valid, invalid, declined-confirmation, and interrupted task flows.

## M4 Completion

1. [Complete] Expose validation, dry-run, and trace lookup through `chromie-agent`.
2. [Complete] Load configured external capability manifests into the Agent registry.
3. [Complete] Add an explicit TaskGraph planning path without changing the existing fast conversation path.
4. [Complete] Implement MCP Streamable HTTP behind `ToolInvoker`, including read-only and supervised side-effect execution.
5. [Complete] Add single-use graph-bound confirmation grants, execution cancellation, and emergency fallback handling.

## M5 Exit Criteria

- A real Soridormi capability manifest loads through `AGENT_CAPABILITY_MANIFESTS`.
- Chromie validates and executes Soridormi safe-read/planning tools over MCP.
- A supervised physical graph proves confirmation, monitor activation, and emergency fallback behavior.
- Cancellation is verified against the real MCP server and robot safety layer.
- Target GPU smoke tests and supervised hardware acceptance checks pass.
- Deployment configuration and runbook document the accepted Soridormi endpoint and recovery procedure.

## M5 Progress

1. [Complete] Add a safety-scoped Soridormi deployment manifest with a runtime-configured MCP endpoint.
2. [Complete] Add fail-fast manifest environment expansion and a paginated MCP `tools/list` name/schema contract probe.
3. [Complete] Add a probe-gated, zero-motion status/planning acceptance runner.
4. [Complete] Materialize all nine tools and DAG hints from Soridormi `main` rather than maintaining a duplicate hand-written contract.
5. [Complete] Separate stateful non-physical planning execution from strictly read-only execution.
6. [Complete] Add Soridormi's dedicated Streamable HTTP MCP container without merging the Chromie and Soridormi deployments.
7. [Complete local] Probe the real Soridormi server and run cross-process read/planning acceptance.
8. [Complete dry-run] Verify confirmation, monitor activation, execution, stop fallback, and persistent emergency-stop state over MCP.
9. [Complete tooling] Add runtime cancellation acceptance with emergency fallback and retained safety-state verification.
10. [Complete tooling] Add one supervised target runner that captures GPU, MCP contract, cancellation, endpoint, profile, and recovery-state evidence.
11. [Pending runtime target] Connect the MCP service to Soridormi's long-running runtime and run the supervised target acceptance.
12. [Pending target evidence] Record the accepted endpoint, hardware profile, GPU results, and completed recovery procedure.

## Immediate Sequence

1. Deploy Soridormi's `soridormi-mcp` container on the target host and configure `SORIDORMI_MCP_URL`.
2. Replace the local dry-run tool service with a Soridormi runtime-backed adapter.
3. Run `SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 ./scripts/m5_target_acceptance.sh`.
4. Complete Soridormi's recovery procedure and retain the generated evidence directory.
5. Record the accepted endpoint, hardware profile, and recovery result in this roadmap.

## Evidence

- Soridormi `fb006a3`: dedicated MCP container and authoritative nine-tool
  Streamable HTTP service
- June 8, 2026 local cross-process acceptance: 9/9 tools, planning, confirmed
  dry-run execution, monitor activation, stop fallback, and emergency-stop
  state retention
- `47a60a3`: documentation consolidation and runtime configuration alignment
- `6287f9e`: GPU-free control-plane integration tests
- `2d41e1b`: target-machine GPU smoke test tooling
- `2aa0549`, `a0db0f6`, `47618ea`: capability registry, TaskGraph validation/execution, and tool invocation bridge
- M4 implementation: production APIs, manifest loading, planning, MCP
  transport, guarded execution, cancellation, and emergency fallbacks

The target GPU smoke test must still be run on the Linux NVIDIA host. That operational check is tracked separately from implementation completion.
