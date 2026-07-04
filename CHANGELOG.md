# Changelog

All notable user-visible changes should be recorded here.

## Unreleased

- No changes yet.

## 0.0.1 - 2026-07-04

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

### Implemented in the current release snapshot

- Hardened release reproducibility with versioned container references, exact
  direct dependency pins, immutable ASR/TTS model revisions, runtime image and
  Ollama digest capture, resolved dependency provenance, and fail-closed
  publishable bundle generation.
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
  correlated sessions, and separation of automated from release-closing
  supervised evidence.
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
