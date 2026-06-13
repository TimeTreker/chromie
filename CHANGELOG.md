# Changelog

All notable user-visible changes should be recorded here. This project has not
yet published an official release.

## Unreleased

### Implemented in the current development snapshot

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
- Hardware-aware generated runtime configuration and multiple NVIDIA profiles.
- GPU, Soridormi, text-interaction, and supervised target acceptance tooling.
- Correlated JSONL session-event evidence that cannot break the realtime loop.
- Guided seven-case microphone/MuJoCo runner with redacted configuration,
  audio-device capture, automated checks, and operator verdicts.
- Strict M13 evidence verifier for native mode, clean revisions, all cases, and
  correlated sessions.
- `0.1.0-alpha.1` candidate version, compatibility declaration, release notes,
  source archive generation, manifest, tests log, and checksums.

### Documentation refresh

- Reclassified the project from stale M6 documentation to current M13 status.
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

### Still open before the first alpha release

- Non-skippable confirmation dialogue.
- Reviewed reference-host microphone/MuJoCo M13 evidence bundle.
- Spoken request-bound confirmation dialogue and evidence.
- Reference-target GPU/audio evidence and supervised recovery evidence.
- Published GitHub prerelease; candidate artifacts and compatibility declaration
  are prepared but intentionally blocked.
