# Chromie Roadmap

Last reviewed: June 8, 2026

Chromie's roadmap is organized around deployable milestones. A milestone is complete only when its code, contracts, tests, and relevant operating documentation agree.

## Current Position

**Current milestone: M4 - TaskGraph production integration (in progress).**

The capability registry, TaskGraph schema, safety validator, dry-run executor, and transport-neutral `ToolInvoker` exist. M4 is moving those pieces from CLI/test-only infrastructure into the running Agent service before any real MCP or robot transport is enabled.

## Milestones

| Milestone | Status | Outcome |
|---|---|---|
| M0 - Runtime foundation | Complete | Docker services, host Orchestrator boundary, hardware profiles, and generated runtime configuration |
| M1 - Realtime voice loop | Complete | ASR, Router, Agent, Ollama, TTS, interruption, playback, and deterministic fallback behavior |
| M2 - Contracts and safety | Complete | Cross-service contracts, confirmation gating, mock hardware flow, and GPU-free regression suite |
| M3 - Target GPU verification | Tooling complete; target run pending | Automated GPU, service health, Ollama, ASR WebSocket, and TTS backend smoke checks |
| M4 - TaskGraph production integration | **In progress** | Agent API validation/dry-run, trace inspection, runtime planning integration, and guarded execution boundary |
| M5 - External capability transport | Planned | Invoke approved MCP/Soridormi tools through `ToolInvoker` transport adapters |
| M6 - Extended autonomy | Planned | Vision, richer memory, recovery policies, observability, and longer-running tasks |

## M4 Exit Criteria

- Agent API exposes TaskGraph validation, dry-run execution, and trace lookup.
- Agent planning can produce a structured graph from an eligible routed request.
- Every generated graph is validated against the active capability registry before execution.
- Real tool execution remains behind `ToolInvoker`; physical motion requires confirmation and safety monitoring.
- Graph lifecycle, failures, fallbacks, and timing are observable.
- Integration tests cover valid, invalid, declined-confirmation, and interrupted task flows.

## Immediate Sequence

1. [Complete] Expose validation, dry-run, and trace lookup through `chromie-agent`.
2. [Complete] Load configured external capability manifests into the Agent registry.
3. [Complete] Add an explicit TaskGraph planning path without changing the existing fast conversation path.
4. [In progress] Implement MCP/Soridormi transport adapters behind `ToolInvoker`
   (Streamable HTTP adapter, policy guards, and default-off read-only execution complete;
   confirmation/monitor-backed side-effect execution pending).
5. Run the target GPU smoke test and then perform supervised hardware acceptance tests.

## Evidence

- `47a60a3`: documentation consolidation and runtime configuration alignment
- `6287f9e`: GPU-free control-plane integration tests
- `2d41e1b`: target-machine GPU smoke test tooling
- `2aa0549`, `a0db0f6`, `47618ea`: capability registry, TaskGraph validation/execution, and tool invocation bridge

The target GPU smoke test must still be run on the Linux NVIDIA host. That operational check is tracked separately from implementation completion.
