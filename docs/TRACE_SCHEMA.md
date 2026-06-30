# Trace Schema

This document defines the local trace artifacts that Chromie's developer CLI can
inspect. It is an operator/debugging schema, not a release-evidence authority.
Use [Status](STATUS.md) and [Acceptance](ACCEPTANCE.md) for validation claims.

## Scope

`python -m tools.chromie_cli trace view` reads retained files that already exist
under `.chromie/acceptance` or a caller-provided trace root. It does not call
live services, fetch in-memory Agent traces, or turn local artifacts into target
validation.

The first supported schema covers these retained artifact families:

| Family | Files | Producer | Purpose |
|---|---|---|---|
| Session events | `events.jsonl`, other `*.jsonl` files | Host Orchestrator acceptance runners | Correlate VAD, ASR, Router, Agent, Skill Runtime, TTS, playback, cancellation, and fallback log events by session id. |
| Route decision | `route.json` | Text/MuJoCo acceptance runner | Retain Router route, intent, confidence, candidate actions, stage proposals, merge ledger, merged task metadata, and optional post-interrupt review/correction metadata. |
| Interaction response | `interaction_response.json` | Agent `/interaction` response | Retain speech, skill requests, confirmation requirements, interaction id, and response status. |
| Skill Runtime execution | `execution.json` | Host trusted Skill Runtime | Retain interaction-level status, per-skill results, and per-skill trace events. |
| TaskGraph trace | `trace.json` or API-returned trace JSON | Agent TaskGraph service | Retain graph id, graph status, node results, execution events, and deterministic `outcome_summary`. |
| Acceptance summary | `summary.json` | Acceptance runners | Retain run-level pointers and nested route/interaction/execution payloads when present. |

Other JSON files may be scanned only when their top-level keys look trace-like
or when the caller passes `--file`.

## Stable Identifiers

The viewer treats these identifiers as stable correlation keys:

| CLI filter | Artifact keys |
|---|---|
| `--session` | `sid`, `session_id`, `origin_session_id`, `session_ids` |
| `--interaction` | `interaction_id`, `active_interaction_ids` |
| `--graph` | `graph_id`, `active_graph_ids` |
| `--trace` | `trace_id` |

Session event JSONL records should include:

```json
{
  "timestamp_utc": "2026-06-27T00:00:00+00:00",
  "sid": "example-session",
  "elapsed_ms": 12.345,
  "event": "router_done",
  "message": "router_done: route=chat confidence=0.91"
}
```

When a voice session reaches `session_done`, the Orchestrator also emits
workflow evidence:

- `session_workflow`: a compact, bounded breadcrumb chain in JSONL evidence.
- `session_workflow_graph`: a structured graph with `nodes`, `edges`,
  `elapsed_ms`, `delta_from_previous_ms`, and `total_ms`.
- `session_workflow_summary`: one operator-console timing line with the
  slowest graph deltas.

These cover the same per-session stages, such as VAD, ASR, Router, Agent,
fast-first response, Skill Runtime, TTS, playback, and final timing. They are
debug evidence only; they do not authorize or change execution.

TaskGraph traces should follow the Agent `ExecutionTrace` model:

```json
{
  "graph_id": "example-graph",
  "status": "failed",
  "summary": "Planner-provided task summary",
  "outcome_summary": "TaskGraph failed: node submit blocked.",
  "node_results": [
    {
      "node_id": "submit",
      "tool": "soridormi.task.submit",
      "status": "blocked",
      "error": "blocked_subsystem",
      "blocked_by": ["locomotion"]
    }
  ],
  "events": [
    {
      "type": "node_blocked",
      "node_id": "submit",
      "tool": "soridormi.task.submit",
      "message": "locomotion unavailable"
    }
  ]
}
```

Skill Runtime execution artifacts should retain `interaction_id`, `status`,
`results`, and `traces`. Each result may carry `trace_id`; each trace carries
`trace_id`, `interaction_id`, `request_id`, `skill_id`, `provider_id`, `status`,
and ordered events.

## CLI Output

`trace view` emits a schema-versioned result:

```json
{
  "schema_version": 1,
  "source": "scan",
  "trace_root": ".chromie/acceptance",
  "filters": {
    "session": "example-session",
    "interaction": null,
    "graph": null,
    "trace": null
  },
  "artifacts_scanned": 1,
  "artifacts_matched": 1,
  "matched_records": 2,
  "warnings": [],
  "artifacts": []
}
```

Artifacts report their path, kind, record counts, parse errors, discovered
identifiers, and a bounded summary. JSONL artifacts include summarized records;
JSON artifacts include a summarized payload. Use `--limit` to bound records per
artifact.

Supported commands:

```bash
python -m tools.chromie_cli trace view
python -m tools.chromie_cli trace view --session <sid>
python -m tools.chromie_cli trace view --interaction <interaction_id>
python -m tools.chromie_cli trace view --graph <graph_id>
python -m tools.chromie_cli trace view --trace <trace_id>
python -m tools.chromie_cli trace view --trace-root .chromie/acceptance/text-mujoco
python -m tools.chromie_cli trace view --file .chromie/acceptance/text-mujoco/<id>/execution.json
```

Exit codes follow the shared CLI contract:

| Status | Exit code | Meaning |
|---|---:|---|
| `ok` | 0 | At least one retained artifact matched. |
| `warning` | 1 | No artifacts exist, no artifacts match the filters, or non-fatal parse warnings occurred. |
| `failure` | 2 | A caller-provided source file is missing. |
| usage error | 64 | Arguments are invalid. |

## Non-Goals

The trace viewer does not:

- fetch the Agent's process-local retained traces from `/task-graphs/{graph_id}/trace`;
- explain causal responsibility across every subsystem;
- redact or publish trace content;
- certify simulator, microphone, speaker, GPU, or robot evidence;
- replace `scripts/verify_voice_evidence.py`, provider conformance, or release
  verifiers.

`trace explain` remains future work. It should build on these identifiers and
summaries to produce a human-readable account of what was heard, routed,
proposed, authorized, executed, refused, cancelled, timed out, or recovered.
