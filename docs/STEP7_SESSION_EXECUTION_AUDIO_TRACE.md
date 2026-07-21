# Step 7: Session, Execution, and Audio Runtime Trace

## Status

Implemented as the second Runtime Observability delivery milestone. The trace
contract remains architecture-independent; this step extends producer coverage.

## Scope

Step 7 adds runtime trace coverage for work that can continue after a cognitive
interaction has completed:

- voice-session lifecycle;
- non-audio action execution;
- action-provider calls;
- TTS generation;
- audio playback; and
- first audible user-observable response.

## Detached session trace

A cognitive interaction trace can finish before TTS generation or playback
finishes. `SessionTracker` therefore owns a detached Runtime Trace for each
voice session. Background work activates that trace by `session_id` before
emitting spans or milestones.

The lifecycle is:

```text
session created
  -> detached trace created
  -> session_started milestone
  -> TTS, playback, and other session work append items
  -> session_finished or abandoned
  -> trace frozen
  -> optional chromie.interaction_trace Runtime Event
```

A new session finalizes an unfinished previous session as `abandoned`. This
preserves partial evidence instead of pretending that the previous session
completed normally.

## Module-owned descriptors

The following producers declare stable module identities:

```text
orchestrator.session
orchestrator.action_executor
orchestrator.action_client
orchestrator.tts
orchestrator.audio_playback
```

No fixed fields such as `tts_ms` or `action_ms` are added to the common trace
schema. Analysis discovers the participating architecture from trace items.

## User-observable latency

The first successful playback start emits:

```text
name = first_audio_playback
kind = user_observable
```

The generic trace analyzer derives `first_user_observable_latency_ms` from the
first item whose kind is `user_observable`.

Later modules may add first-motion, first-display, or other observable
milestones without changing the trace contract.

## Runtime Event behavior

When both tracing and event emission are enabled, a completed or abandoned
session trace is packaged through the existing Runtime Event subsystem:

```text
CHROMIE_RUNTIME_TRACE_MODE=basic
CHROMIE_RUNTIME_TRACE_EMIT_EVENTS=1
CHROMIE_RUNTIME_EVENT_ROOT=.chromie/runtime-events
```

The package contains:

```text
event.json
trace.json
trace-summary.json
```

Chromie packages and triggers the event. The external data loop remains
responsible for merging, resource governance, transfer, cloud delivery, and
retention.

## Remaining coverage

This step does not claim full operational observability. Still open:

- ASR and VAD spans rather than existing workflow events alone;
- first physical motion and execution acknowledgement from robot providers;
- CPU, GPU, memory, queue-depth, and event-loop samples;
- idle-timeout session closure and process-restart recovery;
- dependency-aware cross-trace analysis between cognitive and session traces;
- retained simulator and hardware latency baselines.
