# Runtime Event Architecture

## Purpose

Chromie produces several kinds of evidence that must participate in the same
external data loop without becoming one undifferentiated log stream. Runtime
Events provide a shared package envelope and delivery notification while
preserving the semantics of each producer.

The first supported producers are:

- Cognitive Integrity, which captures immutable failure-boundary evidence; and
- Episode Recorder, which captures longitudinal interaction snapshots for
  offline evaluation and scenario mining.

A Runtime Event is a durable local evidence package. It is not a cloud upload
receipt and it is not automatically a training example.

## Responsibility boundary

Chromie owns:

- event classification;
- payload selection and organization;
- correlation identifiers;
- atomic local persistence;
- a versioned manifest;
- notification of the external data-loop inbox; and
- truthful reporting of local capture and trigger status.

The external data loop owns:

- uniqueness guarantees and deduplication;
- event and transport merging;
- bandwidth, storage, retention, and deletion policy;
- retries and resumable cloud transfer;
- cloud delivery receipts;
- access governance; and
- downstream analysis and dataset construction.

## Package lifecycle

Every event is first written beneath:

```text
<event-root>/.staging/<event-id>/
```

After all payload files and `event.json` are durable, the complete directory is
atomically renamed to:

```text
<event-root>/ready/<event-id>/
```

The ready directory is the source of truth. If a data-loop inbox is configured,
Chromie then atomically writes a lightweight trigger descriptor. Trigger failure
must not invalidate or delete the ready package.

## Shared manifest

All producers use this top-level structure:

```json
{
  "schema_version": 1,
  "event_id": "evt_...",
  "event_type": "chromie.cognitive_integrity_failure",
  "event_subtype": "llm_output_truncated",
  "severity": "critical",
  "occurred_at": "...",
  "producer": {"name": "chromie.cognitive_runtime"},
  "fingerprint": "sha256...",
  "correlations": {},
  "attributes": {},
  "derivation": {},
  "files": [],
  "capture_status": "complete"
}
```

`correlations` contains identifiers used to join independent evidence packages,
such as:

```text
episode_id
conversation_id
session_id
interaction_id
turn_index
```

`attributes` contains low-cardinality facts used for filtering, grouping, and
fingerprinting. Large or sensitive evidence belongs in declared payload files,
not in the manifest.

`derivation` declares what downstream systems may derive. It does not perform or
authorize the derivation itself.

## Cognitive Integrity events

Cognitive Integrity retains its existing event type:

```text
chromie.cognitive_integrity_failure
```

Its payload includes failure facts, runtime state, model exchange, and user
interaction evidence. It remains fail-closed and explicitly forbids automatic
retry, context reduction, trusting the incomplete result, and new execution.

The shared Runtime Event writer changes only the package envelope and atomic
persistence implementation. It does not weaken the integrity policy.

## Episode snapshot events

Episode Recorder continues to append `episodes.jsonl` for the existing offline
evaluation and scenario-mining workflow. Runtime Event emission is optional and
does not replace that log.

When enabled, each new episode snapshot produces:

```text
event_type    = chromie.experience_episode
event_subtype = episode_snapshot
payload       = episode.json
```

The event is correlated by episode, conversation, session, interaction, and turn
index. This allows the data loop or cloud analysis to join a precise incident
with the surrounding longitudinal episode.

Enable episode event emission with:

```text
ORCH_EMIT_EPISODE_RUNTIME_EVENTS=1
CHROMIE_RUNTIME_EVENT_ROOT=/var/lib/chromie/runtime-events
CHROMIE_DATA_LOOP_TRIGGER_ROOT=/var/lib/data-loop/inbox
```

The default is disabled to avoid changing bandwidth and storage behavior before
the external data-loop resource policy is available.

`CHROMIE_EVENT_ROOT` remains a compatibility fallback for Cognitive Integrity.
New deployments should use `CHROMIE_RUNTIME_EVENT_ROOT`.

## Scenario derivation

Scenario candidates are derived artifacts, not runtime evidence.

The intended flow is:

```text
Cognitive incident ─┐
                    ├─ correlation and analysis
Episode snapshots ──┘
          ↓
Episode evaluation
          ↓
Candidate scenario
          ↓
Human review
          ↓
Committed regression scenario
```

Scenario extraction must not run synchronously inside a critical failure path.
It must not mutate the incident or episode package. Automatic promotion into the
regression suite or training dataset remains forbidden.

## Extension rules

A new Runtime Event producer must:

1. use a stable namespaced event type;
2. keep large evidence in declared JSON payloads or future declared attachments;
3. provide useful correlation identifiers;
4. avoid claiming cloud delivery;
5. remain operationally independent of data-loop availability; and
6. document whether scenario or dataset derivation is allowed and whether human
   review is required.
