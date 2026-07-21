# Step 8: Input, Action, and Idle Trace Coverage

## Status

Implemented as the next incremental Runtime Observability milestone after the
initial cognitive trace and detached voice-session trace foundations.

## Scope

Step 8 extends the generic Runtime Trace contract without adding architecture-
specific latency fields. The participating modules declare their own identities
and emit normal trace items:

- `orchestrator.vad` records accepted utterance evidence;
- `orchestrator.asr` records reconnect, send, wait, final-result, and failure
  timing inside one model-call span;
- `orchestrator.action_client` records provider acknowledgement and, when the
  provider reports it, first physical motion as a user-observable milestone;
- `orchestrator.session` finalizes unfinished traces after a configurable idle
  timeout.

The trace analyzer continues to derive the real module topology from emitted
items. It does not assume a fixed VAD -> ASR -> planner -> action pipeline.

## VAD and ASR evidence

A valid utterance adds a `vad_validated` item with bounded measurements:

- audio duration;
- audio byte count;
- RMS;
- whether output audio was playing.

The ASR item records operational timing and status without storing recognized
text as a trace attribute. The semantic text remains in the existing session and
episode evidence paths, where privacy and retention policy already apply.

## Action milestones

A successful provider response records `action_acknowledged`. If the provider
returns `result.first_motion_ms`, Chromie also emits `first_physical_motion` with
kind `user_observable`. Providers that do not expose this measurement remain
valid; Chromie does not invent a first-motion timestamp.

## Idle finalization

The orchestrator periodically asks `SessionTracker` to finalize unfinished
sessions whose last activity exceeds:

```text
ORCH_SESSION_IDLE_TIMEOUT_MS=120000
```

The sweep interval is controlled by:

```text
ORCH_SESSION_IDLE_SWEEP_S=5
```

An idle session is finalized as `abandoned`, preserving its partial trace and
optionally emitting the normal Runtime Event package. Idle finalization does not
claim that the interaction completed successfully.

## Remaining work

This step does not yet add continuous CPU/GPU/memory sampling, process-restart
recovery from persisted active sessions, or a provider-independent method for
measuring physical motion. Those require separate evidence sources and should
not be inferred by the host.
