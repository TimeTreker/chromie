# Conversation State

## Status

Implemented, process-local, bounded, and covered by automated tests. It is not a
durable memory service and does not persist across Orchestrator restart.

## Identity model

Chromie uses two related identifiers:

- `sid`: a per-utterance/session-turn identifier used for tracing requests;
- `conversation_id`: a longer-lived identifier shared across related turns.

A new SID does not automatically start a new conversation. The store keeps the
conversation identifier until a reset phrase, configured topic boundary, hard
idle expiry, or process restart.

## Stored state

The host store can retain bounded representations of:

- recent user and assistant turns;
- active interaction metadata;
- pending task hints;
- follow-up context;
- the current conversation identifier and timestamps.

Limits are enforced for turn count, text length, context size, pending tasks,
and idle age. Older content is trimmed rather than allowed to grow without
bound.

The state is intended to improve short conversational continuity. It should not
be treated as authoritative robot state, a durable user profile, or a database
of completed side effects.

## Boundaries and reset behavior

Configured reset phrases clear the active conversational context. New-topic
starters and idle thresholds can cause a fresh conversation boundary. Follow-up
phrases help preserve context for short dependent questions.

Operational interruption does not erase the entire conversation by default,
but active interaction and pending execution metadata must be updated so an
interrupted action is not later represented as completed.

## Configuration

Preferred names:

```env
ORCH_ENABLE_CONVERSATION_STATE=1
ORCH_CONVERSATION_ID=
ORCH_CONVERSATION_MAX_TURNS=12
ORCH_CONVERSATION_TURN_MAX_TEXT_CHARS=1200
ORCH_CONVERSATION_MAX_CONTEXT_CHARS=6000
ORCH_CONVERSATION_MAX_PENDING_TASKS=8
ORCH_CONVERSATION_IDLE_TIMEOUT_SEC=300
ORCH_CONVERSATION_HARD_IDLE_TIMEOUT_SEC=1800
ORCH_CONVERSATION_RESET_PHRASES=
ORCH_CONVERSATION_NEW_TOPIC_STARTERS=
ORCH_CONVERSATION_FOLLOWUP_PHRASES=
```

Legacy `ORCH_CONTEXT_*` aliases remain accepted for compatibility. Use the
current names in new deployments. Exact defaults and precedence are documented
in [`CONFIGURATION.md`](CONFIGURATION.md).

## Privacy and durability

The default state lives only in memory, which reduces accidental long-term
retention but does not make the content non-sensitive. Logs, optional audio
recordings, acceptance artifacts, and external service logs may still contain
user text or voice data.

Before adding durable memory:

- define explicit user consent and deletion behavior;
- separate conversational hints from verified system state;
- encrypt and scope stored data;
- avoid allowing model-written memory to authorize future side effects;
- add migration, retention, and redaction tests.
