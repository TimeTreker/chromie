# Changelog

All notable user-visible changes should be recorded here.

## Unreleased

### Runtime observability

- Added a default-off, architecture-independent Runtime Trace foundation with
  stable module descriptors, nested synchronous/asynchronous spans, monotonic
  duration measurement, wall-clock correlation, bounded attributes,
  `contextvars` propagation, and immutable complete or abandoned snapshots.
- Added cross-service trace carriers and mergeable Agent fragments so the
  Orchestrator can reconstruct the actual cognitive/model topology without a
  fixed Router/Planner schema.
- Instrumented the goal-driven coordinator, canonical plan adapter, cognitive
  Agent service calls, Goal Association, Fast and Deep Planning, Response
  Composer, and Ollama model calls while retaining existing `timings_ms` fields.
- Added reproducible trace summaries with inclusive/exclusive module time,
  largest items, user-observable latency support, parallel leaf-work analysis,
  and a versioned interval/topology critical-path approximation.
- Added optional `chromie.interaction_trace` Runtime Event packages and active
  trace attachment to cognitive-integrity incidents; execution, audio, TTS,
  provider/resource, session-recovery, and retained live latency evidence remain
  open.
- Added default-off non-blocking accelerator telemetry with bounded NVIDIA GPU
  utilization, memory, temperature, and power observations represented as
  ordinary Runtime Trace resource items.
- Added retained Runtime Trace latency reports with environment/provenance
  binding, p50/p90/p95/p99 distributions, module/resource breakdowns, source
  digests, and per-trace correlations.
- Added an evidence-qualified baseline-versus-candidate latency gate that fails
  invalid when sample counts, evidence class, environment, or clean revision
  requirements are not satisfied. The bundled example policy remains disabled
  until a real target baseline is approved.

### Goal-driven cognitive runtime rollout

- Integrated Goal Association, complete-coverage Fast Planning, terminal Deep
  Planning, bounded trusted-validator replanning, Response Composition, and
  runtime adaptation behind `off`, `report_only`, and lane-gated `apply` modes.
- Enabled structured interaction and authoritative `chat` apply in the common
  safe base; the maintained Soridormi launcher enables that provider and widens
  authority to `chat,robot_action`. Both fail closed after ownership.
- Made exact Router actions adapter-only and reduced the old CapabilityAgent
  semantic planner to an emergency path requiring host and Agent gates plus a
  non-empty authoritative claim whose `turn_id` matches the request.
- Constrained Goal Association with the exact model-facing schema, one bounded
  contract repair, and host-owned transport/persistence identities.
- Hardened Fast and Deep Planning around an exact flat semantic DTO: canonical
  identity remains host-owned, multi-goal outcomes are keyed exactly once by
  authoritative Goal IDs, satisfaction is prospective plan adequacy, and typed
  plan-relation/confirmation fields reject unsafe alternatives.
- Moved response-transport speech out of goal-driven task steps: conversational
  goals use `respond` outcomes, while Response Composition uses its own exact
  schema, host-owned coordination envelope, and one bounded same-stage repair.
- Applied Goal-state updates atomically only after trusted response preparation.
- Added privacy-conscious operational evidence, deterministic cognitive
  scenarios, and a cognitive text-to-MuJoCo evidence entry point.
- Hardened cognitive, voice, and release evidence provenance: target validation
  now requires the current Chromie revision, a clean declared Soridormi
  checkout, matching endpoint-reported Soridormi source, and applied,
  completed, safe-idle cognitive `sim` execution; release preparation rejects
  source, version, manifest, compatibility, or retained-evidence revision
  drift.
- Returned `0.0.1` metadata to candidate state with explicit blockers for
  endpoint-reported Soridormi source identity, running Chromie image/model
  binding, immutable image references, and fresh current-revision Goal-driven
  voice/MuJoCo evidence. No release-readiness or physical-execution claim is
  added by these changes.


## 0.0.1 candidate snapshot - 2026-07-04

This section records the July 4 candidate snapshot; `0.0.1` has not been
published. Current corrections remain under Unreleased and the compatibility
declaration still blocks publication.

- Prepared the first `0.0.1` release metadata, compatibility declaration, and
  release notes.
- Narrowed the release claim to generated-speech voice regression, structured
  text/speech interaction, and MuJoCo `sim` execution through the pinned
  Soridormi contract.
- Added automated acoustic acceptance, which generates TTS prompt audio, plays
  it through the host output, and captures it through the configured host input
  without requiring a human speaker for every regression run.
- Kept human microphone/speaker support, verified Jetson packaging, unattended
  deployment, and physical robot support outside the release claim.

### Implemented in that candidate development line

- Added release reproducibility checks for immutable container references,
  exact direct dependency pins, immutable ASR/TTS model revisions, runtime
  image/Ollama digest capture, resolved dependency provenance, and fail-closed
  publishable bundle generation. The maintained `latest` development aliases
  still block publication.
- Added versioned provider conformance traces, recommendation-only hardware
  shadow coverage, safe-idle status checks, and a first-reference-robot
  commissioning checklist.
- Normalized provider catalog and unavailable-skill failures into stable
  terminal results and expanded the deterministic fault matrix to 16 scenarios.
- Added provider-readiness manifest preflight, explicit live/stub evidence
  provenance, and strict target evidence bundle verification.
- Added live Soridormi-owned fault injection, three safe no-motion provider
  modes, MCP error normalization, and opaque-plan-aware profile parity.
- Added a versioned reference-robot candidate schema, rejected draft template,
  and fail-closed verifier for Physical pilot preparation.
- Fixed the Ollama container healthcheck to use a reachable loopback client
  address while the service continues listening on all interfaces.
- Scoped M13 capability probing to the production surface while retaining
  strict full-manifest probing for provider-readiness conformance.
- Prevented host proxy variables from intercepting Agent-to-Ollama traffic on
  the trusted Compose network.
- Retained passing RTX 5090 GPU smoke plus complete synthetic and PipeWire
  virtual-microphone M13 evidence; supervised physical audio remains open.
- Aligned release and roadmap wording with sherpa-onnx as the maintained ASR
  default and scoped supervised audio blockers to physical voice-device release
  claims.

- Structured `InteractionResponse` contracts with recursive low-level-field
  rejection.
- Trusted host Skill Runtime with bounded scheduling, confirmation, timeout,
  cancellation, traces, and provider isolation.
- Soridormi named-skill catalog import and MCP planning/monitor/execute path.
- TaskGraph validation, dry run, read-only execution, planning-only execution,
  guarded execution, one-time confirmation grants, cancellation, and retained
  in-memory traces.
- Shared process-local resource arbitration and bounded parallel read/planning
  execution.
- Short-term host conversation state across VAD utterances.
- Host-owned spoken request-bound confirmation with exact request fingerprints,
  expiry, single-use approval, deterministic denial, and evidence events.
- Operational stop, cancel, and emergency phrases cancel any pending
  confirmation and continue through the deterministic Router control path.
- Hardware-aware generated runtime configuration and multiple NVIDIA profiles.
- GPU, Soridormi, text-interaction, and supervised target acceptance tooling.
- Correlated JSONL session-event evidence that cannot break the realtime loop.
- Four-mode seven-case voice/MuJoCo runner: automatic TTS-generated stdin
  injection, PulseAudio/PipeWire virtual microphone capture, acoustic
  host-output/input capture, and final supervised real-microphone evidence.
- Strict evidence verifier for native mode, clean revisions, all cases,
  correlated sessions, and separation of automated evidence from supervised
  human voice-device evidence.
- `0.0.1` version, compatibility declaration, release notes,
  source archive generation, manifest, tests log, and checksums.

### Documentation refresh

- Reclassified the project from stale historical milestone documentation to the
  current MuJoCo-executor release delivery.
- Added a stable project charter and a focused three-milestone delivery
  sequence: `0.0.1` with Soridormi MuJoCo execution, robust/provider-ready
  simulation, and a physical reference pilot.
- Consolidated duplicated setup, status, and handoff prose into their owning
  documents; removed redundant `CLAUDE.md` and `LLM_CONTEXT.md` copies.
- Reduced the Chinese guide to a maintained project overview and navigation
  entry instead of duplicating the full runbook and acceptance manual.
- Added authoritative implementation, API, configuration, acceptance, release,
  security, support, and contribution documentation.
- Reconciled `/interaction` documentation with the native output path and explicit compatibility controls.
- Clarified that the host hardware daemon currently uses only the mock driver.
- Added automated documentation consistency checks.

### Native interaction output

- Added `InteractionRuntime`, which accumulates strict speech and skill objects
  directly instead of converting a final `AgentResult`.
- Added serialized contract revalidation, fail-closed default behavior,
  explicit `legacy-adapter` mode, and opt-in validation fallback.
- Kept `/run` unchanged for compatibility and switched the named-skill
  integration test to the native path.

### Still open before a human voice-device release

- Reviewed reference-host microphone/MuJoCo evidence bundle for a physical
  voice-device claim.
- Clean reviewed supervised spoken approval/denial evidence for real
  microphone/speaker support.
- Physical microphone/speaker and supervised recovery evidence for
  voice-device support.
- A future release must declare physical voice-device compatibility separately;
  `0.0.1` intentionally does not include that claim.

## Runtime Trace Step 7

- Added detached per-session Runtime Traces so TTS and playback can remain
  observable after cognitive interaction traces finish.
- Added execution, action-provider, TTS, playback, session lifecycle, and first
  audible response instrumentation using module-owned descriptors.
- Added complete and abandoned session finalization plus optional Runtime Event
  packaging.

### Runtime Observability Step 8

- Added generic VAD and ASR trace items on detached voice-session traces.
- Added provider acknowledgement and optional first-physical-motion milestones.
- Added configurable idle-timeout finalization for unfinished session traces.
- Preserved the architecture-independent trace contract and avoided invented
  physical-motion timing when the action provider supplies no evidence.
### Runtime Observability Step 9

- Added generic process CPU, process/system memory, load, queue-depth, and
  event-loop-lag Runtime Trace resource samples.
- Added atomic active-session trace checkpoints and process-restart recovery as
  abandoned Runtime Event evidence.
- Added latency-threshold, abandoned-trace, and deterministic-sampling retention
  decisions for normal trace Runtime Events.
- Added late-bound session trace correlation with cognitive traces, interactions,
  conversations, and experience episodes.
