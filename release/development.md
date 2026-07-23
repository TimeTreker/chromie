# Chromie Development Scope

> **Status:** active development snapshot. No release version or publication target is currently planned.

This document records the maintained engineering surface so tests, evidence,
and compatibility checks share one bounded scope. It is not release notes and
does not promise support for any deployment target.

## Maintained Engineering Surface

- realtime host audio loop, VAD, ASR coordination, TTS generation, ordered
  playback, and deterministic interruption paths;
- native strict `InteractionResponse` output with explicit compatibility
  rollback;
- trusted host Skill Runtime scheduling, request-bound confirmation,
  cancellation, timeout, and trace evidence;
- generated-speech regression through `synthetic`, `virtual-mic`, and
  `acoustic` modes;
- structured speech/text routing into Soridormi named skills and MuJoCo `sim`;
- TaskGraph validation and gated read, planning, guarded, and physical-policy
  paths, with physical execution gates remaining off.

## Explicit Non-Claims

- no production physical-robot support;
- no general human microphone/speaker support;
- no verified Jetson distribution;
- no unattended deployment;
- no claim that historical evidence validates the current Goal-driven authority path.

## Engineering Evidence Needed

Current development should continue to improve source-bound evidence without
treating that evidence as a publication gate:

- endpoint-reported Soridormi source identity;
- running Chromie image/model binding to the checked-out source;
- clean current-revision Goal-driven live-text and MuJoCo evidence;
- explicit E-stop and safe-idle postcondition evidence;
- representative latency traces and environment-approved thresholds.

## Rollback

An intentional rollback from the unified Goal-driven path to the legacy Agent
adapter requires both host and Agent switches; it does not change `/run`
callers:

```env
ORCH_COGNITIVE_RUNTIME_MODE=off
ORCH_LEGACY_SEMANTIC_FALLBACK_ENABLED=0
AGENT_INTERACTION_OUTPUT_MODE=legacy-adapter
AGENT_NATIVE_INTERACTION_FALLBACK=0
AGENT_LEGACY_CAPABILITY_FALLBACK_ENABLED=0
```

Do not enable validation fallback as a permanent compatibility mode; use the
explicit adapter mode when rollback is intentional.
