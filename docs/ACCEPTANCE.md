# Acceptance and Evidence

This document centralizes validation that was previously scattered across
milestones and component notes.

## Evidence levels

| Level | Environment | What it proves |
|---|---|---|
| A | GPU-free automated tests | Contracts, policy, scheduling, fallback, and deterministic behavior. |
| B | Deployed local services | Container health, HTTP/WebSocket interfaces, model presence, and control-plane round trips. |
| C | Live simulator / MCP | Cross-project capability compatibility, named-skill execution, cancellation, and safe idle recovery. |
| D | Target GPU/audio/hardware | Real latency, device behavior, hardware safety, recovery, and release supportability. |

A higher level does not replace lower-level regression tests.

## Current evidence summary

| Area | A | B | C | D |
|---|:---:|:---:|:---:|:---:|
| Router/Agent contracts | Yes | Smoke tooling | Not required | Target run open |
| Interaction contracts and Skill Runtime | Yes | Text path | Live MuJoCo path | Full microphone matrix open |
| TaskGraph read/planning execution | Yes | Endpoint tooling | Soridormi acceptance | Target retention open |
| Guarded cancellation and emergency fallback | Yes | Acceptance tooling | Runtime-backed path available | Supervised hardware evidence open |
| ASR/TTS GPU use | Limited | GPU smoke tooling | Not applicable | Retained target run open |
| Audio devices and barge-in | Partial | Manual host run | Can pair with sim | Retained matrix open |

## Level A — automated suite

```bash
./scripts/run_tests.sh
```

At the verified snapshot this runs 138 current tests and 20 legacy Agent tests.
It also runs the documentation consistency checker.

## Level B — deployed service checks

```bash
./scripts/start_services.sh
docker compose --env-file .env.runtime ps
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:8092/health
curl -fsS http://127.0.0.1:11434/api/tags
./scripts/verify_tts_gpu.sh
```

For a complete GPU smoke pass:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

This checks host/container GPU visibility, Compose health, Router-to-Agent
round trip, ASR/TTS WebSockets, Ollama generation, model GPU placement, and
optional non-empty TTS PCM generation. It does not evaluate microphone or
speaker quality.

## Level C — Soridormi contract and simulator

Probe the live MCP endpoint before execution:

```bash
export SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
PYTHONPATH=agent python -m app.probe_capabilities \
  --manifest capabilities/soridormi.json
```

Run safe status and zero-motion planning:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json
```

Require a ready runtime-backed simulator endpoint:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --runtime-preflight \
  --expected-backend runtime \
  --expected-mode sim
```

Exercise the structured text-to-named-skill path:

```bash
PYTHONPATH=. python scripts/interaction_text_acceptance.py nod
```

Optional cancellation:

```bash
PYTHONPATH=. python scripts/interaction_text_acceptance.py nod \
  --cancel-after-s 0.2
```

The text acceptance path uses deterministic routing, the current Agent runtime,
native Interaction output, the trusted Skill Runtime, and the live
Soridormi MCP provider. It schedules speech through a test scheduler rather
than a speaker device.

## Guarded and recovery acceptance

Against a disposable Soridormi dry-run process:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --guarded-dry-run
```

Add `--exercise-emergency-stop` only when the process may be restarted. The
command intentionally leaves emergency stop active.

Against a supervised runtime-backed endpoint:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --exercise-runtime-cancellation
```

This dispatches a long zero-velocity plan, cancels it, requires the emergency
fallback, and verifies retained e-stop state. Complete Soridormi’s recovery
procedure before further motion.

## Level D — M3/M5 target runner

```bash
SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 \
  ./scripts/m5_target_acceptance.sh
```

Evidence is written under:

```text
.chromie/acceptance/<UTC acceptance id>/
```

The runner records runtime preflight, GPU smoke output, cancellation/recovery
output, and `summary.env`. It intentionally ends with Soridormi emergency
stopped. A passing command is not complete until the operator records recovery
and safe-idle confirmation.

A command-only rehearsal is available:

```bash
SUPERVISED_ACCEPTANCE=1 M5_DRY_RUN=1 \
  SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  ./scripts/m5_target_acceptance.sh
```

## M13 guided microphone acceptance

The repository includes an operator-guided runner. It starts the host
Orchestrator with late-bound acceptance overrides, keeps native output and
validation fallback settings explicit, and records:

- exact Chromie and pinned Soridormi revisions;
- a redacted `.env.runtime` snapshot;
- audio-device discovery and Compose state;
- correlated JSONL session events from `SessionTracker`;
- Orchestrator logs and optional raw input/output recordings;
- automated event checks plus an operator verdict and notes for every case.

Commit the candidate revision first, then run from the repository root against a
supervised MuJoCo-backed Soridormi endpoint. The runner rejects a dirty worktree
by default; `--allow-dirty` is only for exploratory evidence and cannot satisfy
a clean release gate.

```bash
python scripts/m13_voice_acceptance.py \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

Omit `--start-services` when the five Chromie containers are already healthy.
The runner uses `ORCH_RUNTIME_OVERRIDE_FILE` so it does not edit `.env.local` or
`.env.runtime`. Evidence is written under:

```text
.chromie/acceptance/m13/<UTC acceptance id>/
```

A command-only rehearsal is available and must never be counted as target
evidence:

```bash
python scripts/m13_voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

After all cases pass, verify the bundle mechanically:

```bash
python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<UTC acceptance id>
```

The verifier requires all seven cases, nonempty correlated events, native mode,
Soridormi skills enabled, fallback disabled, exact revisions, and passing
operator/automated verdicts. Human review is still required for audible quality,
simulator safe idle, recovery notes, and privacy.

## M13 microphone acceptance matrix

Run from the repository root with the structured path enabled and a live
MuJoCo-backed Soridormi endpoint. The guided runner presents these cases in the
order below.

| Case | User input | Required evidence |
|---|---|---|
| Speech only | General question | ASR final text, interaction ID, speech request, TTS request ID, audible output, no body skill. |
| Speech plus body skill | “Nod” or equivalent | Speech and named skill, live catalog import, plan/monitor/execute results, safe idle. |
| Refusal | Invalid/unavailable or unconfirmed skill | No remote physical execution, clear refusal reason, user-facing speech. |
| Barge-in | Interrupt while speaking | Playback generation cancelled and no duplicate stale speech. |
| Body cancellation | Interrupt a cancellable simulated skill | Provider cancel invoked, execution marked cancelled, safe idle verified. |
| Stop/emergency | Explicit stop during active work | Deterministic operational route, active work stopped, retained safety state and recovery notes. |
| Follow-up | Context-dependent second utterance | Same conversation ID when policy requires, bounded history, correct reference resolution. |

For every case retain:

- repository and Soridormi revisions;
- `.env.runtime` profile name without secrets;
- audio device names, sample rates, and VAD thresholds;
- Router decision, Agent/interaction metadata, skill results, and correlated IDs;
- timing logs and operator pass/fail notes;
- simulator/hardware state before and after the case;
- recovery confirmation when stop or emergency behavior is exercised.


## Structured event evidence

Set `ORCH_EVENT_LOG_PATH` to append one JSON object per session event. The
acceptance runner configures this automatically. Each record contains a UTC
timestamp, session ID, elapsed milliseconds, event name, and rendered message.
Evidence writing is best-effort and cannot crash the realtime loop.

Do not place event logs in the repository or publish them without review; ASR
text and operator-visible context may contain private speech.

## Pass/fail discipline

- Do not count a dry run as simulator or hardware evidence.
- Do not count a simulator exemption as hardware confirmation.
- Do not mark M13 closed from text-input acceptance alone.
- Do not publish logs containing execution tokens or private environment data.
- Record failure evidence as well as successful reruns; otherwise regressions are
  difficult to diagnose.
