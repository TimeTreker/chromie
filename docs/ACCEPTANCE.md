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

At the current working revision this runs 170 current tests and 20 legacy Agent
tests.
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

Probe the live MCP endpoint before execution. Prefer the Agent container so
the probe uses the same MCP SDK and dependency versions as the deployed Agent:

```bash
./scripts/build_runtime_env.sh
docker compose --env-file .env.runtime up -d chromie-agent
docker compose --env-file .env.runtime exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

`docker-compose.yml` maps `host.docker.internal` to the Linux host gateway for
`chromie-agent`. When Soridormi runs in the same Docker network, pass its
service hostname instead. A host-side probe remains available for development
after installing `agent/requirements.txt`.

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

## Level D - legacy target runner

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

## Alpha voice acceptance modes

The scripts, environment variables, and evidence directory retain the
historical `m13` identifier for compatibility.

## Provider fault matrix

The Chromie-side provider matrix runs without Docker, audio devices, a live MCP
endpoint, or MuJoCo:

```bash
python scripts/provider_fault_matrix.py
```

It executes 16 versioned deterministic scenarios for provider restart, skill
unavailability, jitter, plan, safety-monitor status loss, execution, timeout,
disconnect, malformed-result, runtime-cancellation, and operator-cancellation
behavior. Each result compares the interaction terminal state, body-skill
terminal state, reason code, user-facing speech, and exact tool-call sequence.
Use `--scenarios` for a subset and `--output` to retain a machine-readable JSON
summary. This is automated contract evidence, not live simulator or hardware
validation.

The matrix also records total scenario and terminal latency. Defaults require
each scenario to finish within 1000 ms, timeout terminal handling within 500
ms, and operator cancellation terminal handling within 250 ms. Override these
with `--max-scenario-ms`, `--max-timeout-terminal-ms`, and
`--max-cancel-terminal-ms` for a declared target environment. A threshold
violation fails the matrix and is retained in the JSON result.

After every scenario, the runner reads `soridormi.robot.get_status`. A scenario
passes only when the status call succeeds, `active_task` is empty, and
`emergency_stop` is explicitly false. The retained result includes the complete
high-level status snapshot and aggregate safe-idle count.

The shared provider conformance suite verifies the same high-level contract for
`sim`, a recommendation-only `hardware_shadow` skeleton, and a no-motion
`hardware_dry_run` skeleton:

```bash
python scripts/provider_conformance.py
```

It checks the versioned catalog, opaque plan identity, safety monitor,
authorized explicit completion, cancellation, provider status, safe idle, and
rejection of low-level device fields. It refuses real `hardware` mode. When a
safe live endpoint is available, use `--live` with one explicit safe
`--profile` and configure `SORIDORMI_MCP_URL`.

Multi-profile output includes a parity result. Profile-specific checks such as
the declared mode, recommendation-only shadow proof, and dry-run no-motion
proof are compared separately. All shared checks must have the same names and
pass/fail outcomes. Versioned traces retain each high-level call, arguments,
authorization context, and normalized outcome; parity also requires the shared
trace sequence and terminal statuses to match. Use `--output` to retain the
replayable JSON evidence. Compare separately retained live runs without making
new provider calls:

```bash
python scripts/provider_conformance.py --compare \
  evidence/provider-sim.json \
  evidence/provider-shadow.json \
  evidence/provider-dry-run.json \
  --output evidence/provider-parity.json
```

The hardware selection requirements and rejection conditions are maintained in
the [Reference Robot Commissioning Checklist](ROBOT_COMMISSIONING.md).

Before starting target services, check whether the pinned Soridormi manifest
declares every required safe mode and the test-only fault-injection contract:

```bash
python scripts/verify_provider_readiness.py preflight \
  --manifest capabilities/soridormi.json
```

The fault-injection declaration lives under
`metadata.provider_readiness.fault_injection`. It names test-only
`configure_tool` and `clear_tool` capabilities, which must be
`llm_visible=false`, plus the supported versioned scenario IDs. The checked-in
manifest currently fails this preflight because the pinned upstream revision
does not yet declare hardware shadow or live fault injection.

Retained target evidence uses one directory containing:

- `metadata.json` with target, endpoint, exact Chromie and Soridormi revisions,
  clean-worktree state, and `status=passed`;
- one live conformance JSON file for each safe profile;
- the offline profile parity result;
- a live 16-scenario fault-matrix result; and
- reviewed `operator-notes.md`.

Verify it with:

```bash
python scripts/verify_provider_readiness.py verify \
  evidence/provider-readiness/<run-id> \
  --require-clean \
  --write-report evidence/provider-readiness/<run-id>/verification.json
```

The verifier rejects local-stub conformance output, missing profiles or
scenarios, version drift, threshold violations, unsafe-idle results, dirty
revisions when required, and missing operator review.

`scripts/m13_voice_acceptance.py` has three explicit modes. All three retain
correlated JSONL events, exact revisions, redacted configuration, generated or
captured audio, Orchestrator logs, and per-case checks.

| Mode | Input path | Operator interaction | What it proves | Release-closing |
|---|---|---|---|---:|
| `synthetic` (default) | Chromie TTS WAV -> framed Orchestrator stdin -> VAD -> ASR | None | Reproducible speech/control-plane/Skill Runtime regression | No |
| `virtual-mic` | Chromie TTS WAV -> Pulse/PipeWire null sink monitor -> normal host capture -> VAD -> ASR | None | Host audio-device capture plus the automated control path | No |
| `supervised` | Real microphone -> normal host capture -> VAD -> ASR | Audible/visual verdict after machine checks pass | Reference-host microphone, speaker, pronunciation, and observed simulator behavior | Yes |

The automatic modes intentionally use response playback `discard` mode. Audio
is paced in real time, so `playback_start`, barge-in, cancellation, and stale
playback checks still execute without requiring a physical speaker or risking
speaker-to-microphone feedback.

### Automatic synthetic acceptance

Start the five Chromie services and a supervised MuJoCo-backed Soridormi MCP
endpoint. Check all prerequisites before creating an evidence bundle:

```bash
python scripts/m13_voice_acceptance.py \
  --preflight-only \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The preflight checks the generated-runtime script, Docker CLI and daemon,
automatic Python runtime, TTS startup plan, and the external Soridormi endpoint
and repository. It does not start services or create evidence. Once it reports
`Overall: ready`, run:

```bash
python scripts/m13_voice_acceptance.py \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner generates each unique test utterance once through the existing TTS
WebSocket service and stores it under:

```text
.chromie/acceptance/m13/<id>/generated-input/
```

It then injects a private framed PCM16 stream through the Orchestrator process's
stdin. No network injection endpoint is opened. The Orchestrator resamples the
packet, feeds normal VAD frames, sends the resulting utterance to ASR, and uses
the same Router, Agent, Skill Runtime, TTS, and Soridormi paths as a microphone
session.

This mode is the recommended first run because it removes pronunciation,
microphone selection, room noise, and operator timing from the result. It is
also intentionally optimistic: Chromie's TTS voice is generally easier for its
ASR to recognize than arbitrary human speech.

Verify automatic evidence with:

```bash
python scripts/verify_m13_evidence.py --allow-automated \
  .chromie/acceptance/m13/<id>
```

The verifier reports the bundle as valid automated evidence but
`release_eligible=false`.

### Automatic virtual-microphone acceptance

`virtual-mic` mode requires PulseAudio or PipeWire. It uses `pactl`/`paplay`
when available and otherwise falls back to native
`pw-cli`/`pw-cat`/`pw-dump` tools:

```bash
python scripts/m13_voice_acceptance.py \
  --mode virtual-mic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner creates a temporary null sink named `chromie_m13_test` by default,
sets its monitor as `PULSE_SOURCE` for the Orchestrator, plays each generated WAV
into that sink, and unloads the module during cleanup. Override the sink name
with `--virtual-mic-sink` when needed.

This mode exercises normal `sounddevice` capture, sample-rate conversion, host
buffering, VAD, and ASR. It still does not prove a physical microphone or
speaker.

### Final supervised acceptance

Commit the candidate revision first, then run:

```bash
python scripts/m13_voice_acceptance.py \
  --mode supervised \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

For each utterance the runner displays a countdown and `SPEAK NOW`, waits for
`asr_final`, shows expected and recognized text, and prints the current
session's Router, interaction, skill, playback, cancellation, and completion
events. It asks for an audible/visual operator verdict only after all machine
checks pass. Missing ASR or required runtime events automatically fail the case.

Only a clean, passing `supervised` bundle can satisfy the release verifier:

```bash
python scripts/verify_m13_evidence.py --require-clean \
  .chromie/acceptance/m13/<id>
```

The host runner uses `ORCH_RUNTIME_OVERRIDE_FILE` and does not edit the
operator's `.env.local` or generated `.env.runtime`. The Soridormi capability
probe runs inside `chromie-agent` by default; host-loopback endpoints are
translated to `host.docker.internal` only for that container command.

### Shared controls

```text
--cases all|speech-only,speech-skill,...
--asr-timeout-s 20
--asr-retries 1
--case-timeout-s 60
--continue-after-failure
--tts-url ws://127.0.0.1:5000
--tts-speaker-id default
```

A command-only rehearsal remains non-evidence:

```bash
python scripts/m13_voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

## Alpha microphone acceptance matrix

Run from the repository root with the structured path enabled and a live
MuJoCo-backed Soridormi endpoint. All three modes execute these cases in the
order below; only `supervised` adds physical audio and operator observations.

| Case | User input | Required evidence |
|---|---|---|
| Speech only | General question | ASR final text, interaction ID, speech request, TTS request ID, audible output, no body skill. |
| Speech plus body skill | “Nod” or equivalent, then “Yes” | Action-specific prompt, exact request fingerprint, approval event, live catalog import, plan/monitor/execute results, safe idle. |
| Refusal | Valid body request, then “No thanks” | Bound denial event, no remote physical execution, user-facing speech. |
| Barge-in | Interrupt while speaking | Playback generation cancelled and no duplicate stale speech. |
| Body cancellation | Confirm, then interrupt a cancellable simulated skill | Bound approval, provider cancel invoked, execution marked cancelled, safe idle verified. |
| Stop/emergency | Explicit stop during active work | Deterministic operational route, active work stopped, retained safety state and recovery notes. |
| Follow-up | Context-dependent second utterance | Same conversation ID when policy requires, bounded history, correct reference resolution. |

For every case retain:

- repository and Soridormi revisions;
- `.env.runtime` profile name without secrets;
- audio device names, sample rates, and VAD thresholds;
- Router decision, Agent/interaction metadata, skill results, and correlated IDs;
- confirmation ID, exact request fingerprint, expiry, and approval or denial;
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
- Do not publish the alpha from text-input acceptance alone.
- Do not publish logs containing execution tokens or private environment data.
- Record failure evidence as well as successful reruns; otherwise regressions are
  difficult to diagnose.
