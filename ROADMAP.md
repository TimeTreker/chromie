# Chromie Roadmap

Last reviewed: June 12, 2026

Chromie's roadmap is organized around deployable milestones. A milestone is complete only when its code, contracts, tests, and relevant operating documentation agree.

## Current Position

**Current engineering milestone: M6 - Interaction Agent and Skill Runtime (in progress).**

M4 is complete: TaskGraph planning, validation, dry-run, guarded MCP execution,
single-use confirmation grants, cancellation, traces, monitor gating, and
emergency fallback orchestration are integrated into the Agent service. M5's
generic Soridormi MCP integration is implemented locally; target-host and
hardware evidence remain operational acceptance work. M6 builds the missing
product mainline: one Interaction Agent proposes speech and named skills, and a
trusted Skill Runtime validates and coordinates local speech with
MCP-backed Soridormi body execution.

## Milestones

| Milestone | Status | Outcome |
|---|---|---|
| M0 - Runtime foundation | Complete | Docker services, host Orchestrator boundary, hardware profiles, and generated runtime configuration |
| M1 - Realtime voice loop | Complete | ASR, Router, Agent, Ollama, TTS, interruption, playback, and deterministic fallback behavior |
| M2 - Contracts and safety | Complete | Cross-service contracts, confirmation gating, mock hardware flow, and GPU-free regression suite |
| M3 - Target GPU verification | Tooling complete; target run pending | Automated GPU, service health, Ollama, ASR WebSocket, and TTS backend smoke checks |
| M4 - TaskGraph production integration | Complete | Agent planning, validation, traces, guarded MCP execution, one-time grants, cancellation, and emergency fallbacks |
| M5 - External capability deployment | Implementation complete; target evidence pending | Connect a real Soridormi manifest/server and complete target-host acceptance |
| M6 - Interaction Agent and Skill Runtime | **In progress** | Turn voice intent into validated speech, named skills, or both, then coordinate execution |
| M7 - Extended autonomy | Planned | Vision, richer memory, recovery policies, observability, and longer-running tasks |

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
11. [Complete upstream] Add Soridormi's runtime-backed simulation MCP adapter with preemptive stop, cancellation, emergency stop, and safe hold.
12. [Complete tooling] Fail target acceptance before GPU checks unless Soridormi reports the runtime backend, expected mode, and a cleared emergency stop.
13. [Pending runtime target] Deploy the runtime adapter with the Soridormi simulator and run the supervised target acceptance.
14. [Pending hardware backend] Implement Soridormi's real `HardwareRobot` boundary before enabling MCP hardware mode.
15. [Pending target evidence] Record the accepted endpoint, hardware profile, GPU results, and completed recovery procedure.

## M6 Exit Criteria

- The Interaction Agent returns a validated response containing speech, named
  skills, or both.
- A trusted Skill Runtime resolves registered providers, validates arguments,
  enforces confirmation policy, schedules work, cancels it, and records traces.
- Soridormi publishes and executes named social, attention, locomotion, and
  stop skills over MCP without exposing raw joints or `action_14d`.
- The Orchestrator executes coordinated speech and body work instead of only
  logging planned body actions.
- Microphone acceptance in MuJoCo proves greeting, looking, attention, nod,
  interruption, stop, and refusal flows.
- Hardware remains disabled until the separate Soridormi commissioning gates
  pass.

## M6 Plan

1. [Complete] Freeze cross-project interaction and skill contracts.
2. [Complete] Build the Skill Runtime with local speech and mock/MCP providers.
3. [Complete upstream] Expose Soridormi named body skills over MCP and import
   the authoritative tool fixture into Chromie.
4. [In progress] Expose `InteractionResponse` from the Agent, then consolidate
   semantic routing and talking into native structured output.
5. [In progress] Connect Orchestrator execution, timing, interruption, and
   traces; the structured path is implemented behind a default-off rollout
   flag.
6. [Planned] Run the full cross-project MuJoCo acceptance matrix.

The detailed design and gates are in
[Interaction Agent and Skill Runtime](docs/interaction_agent_skill_runtime.md).

## Immediate Engineering Sequence

1. [Complete headless] Run text-input acceptance through the Agent compatibility
   path and trusted Skill Runtime.
2. [Complete headless] Run live Soridormi named-skill execution in MuJoCo and
   verify interruption.
3. Replace compatibility conversion with native Interaction Agent structured
   generation.
4. Add confirmation dialogue for skills that are not skippable in the active
   runtime mode.
5. Prove microphone input in MuJoCo.

## Remaining M5 Target Sequence

1. On the target host, start Soridormi's simulator and `run_runtime_mcp_server.sh`.
2. Configure Chromie's `SORIDORMI_MCP_URL` for that runtime-backed endpoint.
3. Run `SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 ./scripts/m5_target_acceptance.sh`.
4. Restart the Soridormi MCP process after acceptance, verify safe state, and retain the generated evidence directory.
5. Record the accepted endpoint, hardware profile, and recovery result in this roadmap.

## Evidence

- June 12, 2026 Chromie I0/I1: interaction contract round trips, nested
  low-level-field rejection, registry/schema/version validation, local speech,
  opaque Soridormi MCP planning/execution, parallel and sequential scheduling,
  confirmation, timeout, cancellation, traces, and legacy adapters; 99
  unittest cases plus 20 legacy Agent tests pass
- June 12, 2026 Chromie I3 start: `POST /interaction`, shared contract package
  in the Agent image, host client support, and compatibility translation from
  `head.nod`, `head.shake`, and `head.look_at_user` to Soridormi named skills
- June 12, 2026 Chromie I4 start: host structured-response rollout flag, local
  speech scheduling, lazy live Soridormi catalog import, provider-managed
  safety monitoring, simulation confirmation policy, background body
  execution, and interruption cancellation
- June 12, 2026 headless MuJoCo acceptance: the Agent container discovered all
  12/12 Soridormi tools; text input `nod` scheduled local speech and completed
  a real, non-dry-run `soridormi.nod_yes` execution in 7.177 seconds
- June 12, 2026 interruption acceptance: cancelling the same text-input flow
  after 0.5 seconds returned `cancelled` in 0.563 seconds; Soridormi then
  reported `active_task: null` and `emergency_stop: false`
- Soridormi `a092dc7`: authoritative named-skill MCP catalog, opaque planning,
  runtime-backed execution, and cancellation imported into Chromie's fixture
- Soridormi `027b626`: runtime-backed simulation MCP adapter with bounded
  execution, preemptive stop/cancel/e-stop, safe hold, and dedicated Compose profile
- Soridormi `fb006a3`: initial dedicated MCP container and authoritative
  nine-tool Streamable HTTP service
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
