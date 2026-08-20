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
- trusted host Trusted Capability Runtime scheduling, request-bound confirmation,
  cancellation, timeout, and trace evidence;
- generated-speech regression through `synthetic`, `virtual-mic`, and
  `acoustic` modes;
- structured speech/text routing into Soridormi named skills and MuJoCo `sim`;
- TaskGraph validation and gated read, planning, guarded, and physical-policy
  paths, with physical execution gates remaining off.

## Explicit Non-Claims

- physical-robot deployment is optional provider work outside core Chromie
  acceptance; no production physical-provider claim is made here;
- the retained supervised reference-host microphone/speaker pass is not a claim
  that every human voice, audio device, language, or acoustic environment works;
- no verified Jetson distribution is claimed or required for core completion;
- no unattended deployment;
- no claim that one revision's retained evidence automatically validates every
  later source revision.

## Engineering Evidence Needed

Current development should continue to improve source-bound evidence without
treating that evidence as a publication gate:

- endpoint-reported Soridormi source identity;
- running Chromie image/model binding to the checked-out source;
- clean current-revision Goal-driven live-text and MuJoCo evidence;
- explicit E-stop and safe-idle postcondition evidence;
- representative latency traces and environment-approved thresholds.

## Diagnostic disablement

There is no maintained semantic rollback to the retired Agent planner. For fault
isolation an operator may disable the Goal-driven runtime:

```env
ORCH_COGNITIVE_RUNTIME_MODE=off
```

`off` fails ordinary cognition closed; it does not reactivate `/run`,
`/interaction`, CapabilityAgent, direct-LLM, or another semantic fallback.
Restore `apply` after the fault is understood.
