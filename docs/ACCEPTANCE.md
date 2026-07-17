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
| Router/Agent contracts | Yes | RTX smoke passed | Not required | Physical audio review open |
| Interaction contracts and Skill Runtime | Yes | Text path | Historical legacy live-MuJoCo closure passed; current goal-driven rerun open | Physical audio open separately |
| TaskGraph read/planning execution | Yes | Endpoint tooling | Soridormi acceptance | Target retention open |
| Guarded cancellation and emergency fallback | Yes | Acceptance tooling | Runtime-backed path available | Supervised hardware evidence open |
| ASR/TTS GPU use | Limited | GPU smoke tooling | Not applicable | RTX 5090 smoke passed 21/21 |
| Audio devices and barge-in | Partial | Manual host run | Can pair with sim | PipeWire virtual-mic 7/7 passed; physical microphone/speaker open |

Retained reference-host evidence from June 14 and June 17, 2026:

| Evidence ID | Revision | Result | Scope |
|---|---|---|---|
| GPU `20260614T130944Z` | `280c36a` | 21 passed, 0 failed | RTX 5090 service/GPU smoke, Ollama GPU placement, ASR/TTS health, generated PCM |
| M13 `20260614T132934Z` | `f0e22ba` | 7/7 passed | Synthetic framed PCM through VAD, ASR, Router, Agent, Skill Runtime, TTS, and MuJoCo |
| M13 `20260614T133155Z` | `f0e22ba` | 7/7 passed | PipeWire virtual-microphone capture through the same interaction and MuJoCo path |
| M13 `20260617T075825Z` | `4604a03` | 7/7 passed | Clean synthetic framed PCM through VAD, ASR, Router, Agent live Soridormi catalog, host confirmation, Skill Runtime, TTS, and MuJoCo |
| Text-MuJoCo `20260617T081411Z` | `857c15f` | passed | Direct text input through Router, Agent `/interaction`, host Skill Runtime, live Soridormi MCP, ordered walk/nod/turn execution, and safe-idle status |

The retained M13 automated bundles are historical evidence for their recorded
revisions and legacy semantic path; they are not current goal-driven validation.
They can be inspected by supplying their recorded revisions through the
verifier's `--expected-*` options. The verifier defaults to the current source
and therefore rejects them as release evidence for a newer revision. They report
they are not eligible for a human physical voice-device claim. The retained
Text-MuJoCo bundle closes the historical M13 text interaction scope. It
intentionally skips microphone and ASR and therefore does not prove physical
audio-device quality.

## Level A — automated suite

```bash
./scripts/run_tests.sh
```

This runs the documentation consistency checker, all current `unittest` cases
discovered under `tests/`, and the dependency-light legacy Agent tests. Report
the exact command output when making a claim; do not use a stale hardcoded test
count as evidence.

If the host Python environment is intentionally minimal, install the declared
host test dependency set while running the gate:

```bash
INSTALL_TEST_DEPS=1 ./scripts/run_tests.sh
```

You can also run the same gate in the service dependency envelope:

```bash
./scripts/compose.sh run --rm --no-deps \
  -v "$PWD:/workspace" -w /workspace \
  chromie-agent ./scripts/run_tests.sh
```

For roadmap-aligned module and combination checks, use:

```bash
python scripts/test_matrix.py --list
python scripts/test_matrix.py router
python scripts/test_matrix.py behavior
python scripts/test_matrix.py general-ability
python scripts/test_matrix.py asr tts router
python scripts/test_matrix.py local-modules
python scripts/test_matrix.py voice-mujoco-sim
```

This runner is a Level A convenience layer over existing tests. It lets modules
be tested independently or in declared combinations, but it does not replace the
canonical `./scripts/run_tests.sh` gate and it does not create GPU, microphone,
MuJoCo, or hardware evidence.

`scripts/scenario_runner.py` remains as a low-level deterministic scenario
engine for fixture authoring and focused debugging. It is not the preferred
behavior-quality gate. New user-visible behavior claims should use the general
ability acceptance layer below so the report names the protected ability class
and evidence level.

The committed fixtures live under [`../scenarios/`](../scenarios/). Each file
contains one deterministic scenario and expectation set. The runner writes a
timestamped `summary.json` with pass/fail details and, when a baseline is
provided, lists regressions, improvements, new cases, and removed cases. These
reports are Level A automated evidence only; they do not prove live service,
GPU, microphone, speaker, simulator, or robot behavior.
Interaction fixtures may opt into host response preparation to assert
preflight, proposal-ledger, revision/supersede, and correction metadata without
executing live TTS, simulator, or hardware side effects.

For claim-oriented behavior coverage, run the general ability acceptance layer:

```bash
python scripts/general_ability_acceptance.py --mode check
python scripts/general_ability_acceptance.py --mode level-a
python scripts/general_ability_acceptance.py --mode level-a \
  --ability-class deterministic_safety_controls
```

The manifest lives at
[`../scenarios/general_ability_acceptance.json`](../scenarios/general_ability_acceptance.json).
It groups representative scenario files by the general ability class they
protect: robust intent understanding, stable capability grounding, natural
uncertainty handling, composable action planning, truthful embodied speech,
tool/conversation lane discipline, deterministic safety controls, and evidence
claim discipline, plus multi-goal daily-life planning. The runner writes evidence summaries under
`.chromie/acceptance/general-ability/` unless `--no-write` is supplied.

A passing `--mode level-a` run is still Level A deterministic evidence only. It
does not prove live services, microphone/speaker behavior, simulator execution,
or physical robot behavior. When it fails, the retained summary marks
`root_cause_report_required=true`; the next patch must identify the earliest
wrong boundary before changing prompts or wording.

Against deployed services, the same manifest can run live text probes:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi
```

Use `--execute` only for supervised simulator runs. Live text preview checks the
Router, Agent, and Soridormi status/preflight boundary but does not execute
motion; live text execution can support a Level C simulator claim only when the
summary shows successful Skill Runtime execution and safe idle. Neither mode is
microphone, speaker, or physical hardware evidence.
`--soridormi-repo` records a declared paired checkout for diagnostic
provenance; it does not prove which source revision is executing behind the MCP
endpoint.

The RTX 5090 and RTX 4090 Laptop hardware profiles currently use qualification
time budgets: 120 seconds per Agent cognitive stage, 150 seconds per host stage,
and 900 seconds for the complete cognitive pipeline. The live runner therefore
defaults to a 1200-second outer case timeout. Do not reduce these values while
validating LLM capability and end-to-end architecture; optimize latency only
after retaining successful warm-run evidence.

The reconstruction design and staged implementation plan are maintained in
[General Ability Test Reconstruction](GENERAL_ABILITY_TEST_RECONSTRUCTION.md).

To grow the scenario library, use the authoring helper:

```bash
python scripts/scenario_author.py new --suite router --id draft_case \
  --text "Hello Chromie."
python scripts/scenario_author.py edit --suite router --id draft_case
python scripts/scenario_author.py validate-all
python scripts/scenario_author.py prompt --suite interaction --count 20
```

The prompt command is for generating reviewed candidate JSON with an LLM; the
LLM is not used as the pass/fail judge during regression runs.

## Model-assisted routing guardrails

The fast Router model is accepted only as an advisory semantic classifier.
Level A routing evidence must continue to prove:

- deterministic stop, cancel, emergency, ignore, silence, and unusable-audio
  paths do not depend on model output;
- model routes are bounded by capability-catalog candidates and schema
  finalization;
- low-confidence, ambiguous, unsupported, or unavailable routes clarify, refuse,
  ignore, or fall back safely;
- native InteractionRuntime and the host Skill Runtime re-resolve capabilities
  before execution;
- Soridormi task preview, refusal, events, cancellation, and safe-idle status
  remain authoritative for embodied goals.

See
[Model-Assisted Routing Guardrails](MODEL_ASSISTED_ROUTING_GUARDRAILS.md).

## Level B — deployed service checks

```bash
./scripts/start_services.sh
./scripts/compose.sh ps
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

ASR backend migration work starts at Level A with backend-selection and
fail-closed tests, then Level B service health that reports `backend`, `mode`,
`model`, and `model_revision`. A backend benchmark is not release readiness by
itself. Changing the supported default requires retained evidence for
recognition quality, latency, resource use, timeout/fallback clarity, and
unchanged stop, cancel, emergency, silence, unusable-audio, confirmation, and
barge-in semantics. The staged criteria are maintained in
[ASR Backend Migration Plan](ASR_BACKEND_MIGRATION.md).

## Level C — Soridormi contract and simulator

Probe the live MCP endpoint before execution. Prefer the Agent container so
the probe uses the same MCP SDK and dependency versions as the deployed Agent:

```bash
./scripts/build_runtime_env.sh
./scripts/compose.sh up -d chromie-agent
./scripts/compose.sh exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

`docker-compose.yml` maps `host.docker.internal` to the Linux host gateway for
`chromie-agent`. When Soridormi runs in the same Docker network, pass its
service hostname instead. A host-side probe remains available for development
after installing `agent/requirements.txt`.

The general probe verifies the complete manifest by default. M13 voice
acceptance adds `--exclude-effect test_control` because its production
voice-to-simulator path does not depend on hidden fault-injection controls.
Provider-readiness evidence continues to require those controls separately.

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

The older single-skill text acceptance command has been removed because it used
a fixture-like legacy Agent result and could be mistaken for acceptance
evidence. Use the general ability runner for behavior claims and
`interaction_text_mujoco_check.py` for retained text-to-simulator evidence.

The old standalone text skill sweep has been removed because it can overstate
coverage and has been observed to fail unclearly when live inventory or service
calls hang. Add representative live text probes to
[`../scenarios/general_ability_acceptance.json`](../scenarios/general_ability_acceptance.json)
instead.

For a deployed text-to-MuJoCo check that skips microphone and ASR while keeping
Router, the goal-driven runtime, the host trusted Skill Runtime, live Soridormi
MCP, and optional real speaker playback, start Chromie with the Soridormi
manifest loaded and run:

```bash
python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --no-speaker
```

That command is the natural no-microphone rehearsal: Chromie infers the route,
speech, and skills from the text exactly as it would after ASR. Add
`--expect-*` flags only when you want a regression assertion after planning:

```bash
python scripts/interaction_text_mujoco_check.py \
  "walk ahead at 0.2 speed for 10 seconds and then nod your head twice, then turn left" \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --expect-skill soridormi.walk_velocity \
  --expect-skill soridormi.nod_yes \
  --expect-skill soridormi.turn_in_place \
  --expect-arg 0:vx_mps=0.2 \
  --expect-arg 0:duration_s=10 \
  --expect-arg 1:count=2 \
  --expect-arg 2:yaw_radps=-0.12
```

This runner defaults to the maintained goal-driven path; use
`--no-cognitive-runtime` only for an explicitly labelled compatibility run. It
writes `route.json`, `interaction_response.json`,
`execution.json`, status snapshots, session events, recordings when enabled,
and `summary.json` under `.chromie/acceptance/text-mujoco/<id>/`. The summary
records the Chromie checkout revision/version/clean state, Soridormi manifest,
the user-supplied declared paired checkout and its clean state, selected
semantic path, and apply lanes. `--soridormi-repo` does not prove which source
the MCP endpoint executes. Target validation additionally requires an
endpoint-reported Soridormi source revision matching the clean paired checkout
and manifest; the current runner records no such endpoint revision, so its new
summaries remain diagnostic. It fails if
Skill Runtime execution fails, if the simulator does not return to safe idle,
or, when assertion flags are supplied, if the ordered Soridormi skills or
expected arguments do not match. Use `--no-speaker` for headless automation;
otherwise Chromie schedules TTS through the configured output device. The
runner uses a 120s per-Soridormi-skill diagnostic timeout by default; pass
`--skill-timeout-s 0` to use catalog/default timeouts unchanged. It prints
compact debug lines for route, staged task list, skills, speech count, and
errors before the JSON summary. The runner refuses non-`sim` Soridormi modes
unless `--allow-non-sim` is supplied under separate supervision.

Use `--reject-internal-speech` when investigating planner/TTS leakage. For the
known ASR-style walk typo regression, run:

```bash
python scripts/interaction_text_mujoco_check.py \
  "Wal forward for 15 seconds, quickly." \
  --cognitive-runtime \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --preview-only \
  --no-speaker \
  --expect-skill soridormi.walk_forward \
  --reject-internal-speech
```

That preview-only check fails if no walking skill is emitted or if spoken text
contains internal labels such as `Task Split`, `Key Risk`, `Next Step`, or
model-facing `soridormi.*` skill IDs. It still writes `route.json`,
`interaction_response.json`, session events, and `summary.json` for diagnosis.

The retained `20260617T081411Z` text bundle is historical M13 `/interaction`
closure evidence. It does not contain the provenance or cognitive status needed
to validate the current goal-driven path. Produce a new clean goal-driven bundle
when the claim includes the current semantic-authority boundary.

The old standalone text scenario suite has been removed for behavior claims.
Its useful cases are represented by the general ability manifest so failures
are reported by ability class rather than as a flat list of examples. Use:

```bash
conda run -n Chromie python scripts/general_ability_acceptance.py \
  --mode live-text \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

That command is preview-only and headless by default. Use `--execute` only for
supervised simulator execution.

## Task-agent bridge acceptance

Against a live Soridormi endpoint that exposes the no-motion task API, run:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --task-agent-bridge
```

This probes the manifest endpoint, calls `soridormi.task.get_capabilities`,
requires `task_api_no_motion=true` and at least one declared task type before
any preview or submit call, previews a structured task goal, submits it with a
Chromie-owned `client_task_ref`, and monitors `soridormi.task.events` until a
terminal no-motion completion. It fails if Soridormi does not declare the
no-motion task contract, if preview would create a persistent task, if submit
does not return a `task_id`, or if terminal monitoring does not end
`safe_idle=true`.

Use `--task-goal-json` to supply another structured task goal. This acceptance
mode is contract evidence only; it does not authorize or prove physical motion.

## High-level task enrichment acceptance

When Soridormi adds a high-level task type, Chromie acceptance should treat it
as routable only after the authoritative manifest and live endpoint expose the
contract and the no-motion or simulator evidence passes. Near-term task types
are:

- `navigate_to_location`;
- `approach_target`;
- `look_at_target`;
- `perform_gesture`;
- `recover_safe_idle`.

For each task type, retain evidence for manifest probing, task capability
inspection, preview, submit, event monitoring, terminal state, safe idle,
cancellation where applicable, refusal or blocked-subsystem behavior, and
Chromie user-facing routing/reporting. Unsupported task types must remain
structured refusals or clarifications. Do not treat a task as physical
completion unless Soridormi returns retained simulator or commissioned hardware
execution evidence for that exact path.

Motion-control model training is not an acceptance shortcut. It requires a
selected simulator or robot target, calibration and telemetry, task-level
metrics, and Soridormi-owned safety envelopes.

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
  ./scripts/run_supervised_target_acceptance.sh
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
SUPERVISED_ACCEPTANCE=1 TARGET_ACCEPTANCE_DRY_RUN=1 \
  SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  ./scripts/run_supervised_target_acceptance.sh
```

## Voice audio acceptance modes

New voice evidence uses functional script names and the
`.chromie/acceptance/voice/` directory. Historical M13 text evidence remains
documented separately.

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

Against a Soridormi endpoint that declares hidden test controls, run the same
matrix through the real MCP transport:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
python scripts/provider_fault_matrix.py --live \
  --manifest capabilities/soridormi.json \
  --output .chromie/provider-readiness/fault-matrix.json
```

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
manifest is pinned to a Soridormi revision that declares all three safe modes
and the hidden live fault-injection contract.

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

## Reference robot candidate preflight

Physical pilot preparation uses a separate machine-readable candidate record:

```bash
python scripts/verify_robot_candidate.py \
  .chromie/commissioning/reference_robot_candidate.json \
  --evidence-root .chromie/commissioning \
  --verify-evidence-files \
  --write-report .chromie/commissioning/candidate-verification.json
```

The report separates structural validity, readiness for no-motion review, and
selection for the pilot. Missing identity, unpinned revisions, absent
emergency-stop evidence, missing calibration hashes, unspecified limits or
exclusions, invalid timestamps, and unknown fields all fail closed. Candidate
selection never authorizes physical motion. With `--verify-evidence-files`, the
verifier also requires referenced procedure and safety files to exist and
remain inside the evidence root, requires the provider manifest's
`metadata.upstream_commit` to match `revisions.soridormi`, and requires
calibration artifact SHA-256 values to match.

`scripts/voice_acceptance.py` has four explicit modes. All four retain
correlated JSONL events, exact revisions, redacted configuration, generated or
captured audio, Orchestrator logs, and per-case checks.

| Mode | Input path | Operator interaction | What it proves | Human voice-device closure |
|---|---|---|---|---:|
| `synthetic` (default) | Chromie TTS WAV -> framed Orchestrator stdin -> VAD -> ASR | None | Reproducible speech/control-plane/Skill Runtime regression | No |
| `virtual-mic` | Chromie TTS WAV -> Pulse/PipeWire null sink monitor -> normal host capture -> VAD -> ASR | None | Host audio-device capture plus the automated control path | No |
| `acoustic` | Chromie TTS WAV -> host output -> configured host input device -> VAD -> ASR | None | Repeatable host audio-device path for generated speech; physical evidence when bound to a real speaker/microphone pair | No |
| `supervised` | Real microphone -> normal host capture -> VAD -> ASR | Audible/visual verdict after machine checks pass | Reference-host microphone, speaker, pronunciation, and observed simulator behavior | Yes, for physical voice-device release claims |

The `synthetic` and `virtual-mic` modes intentionally use response playback
`discard` mode. Audio is paced in real time, so `playback_start`, barge-in,
cancellation, and stale playback checks still execute without requiring a
physical speaker or risking speaker-to-microphone feedback. The `acoustic`
mode uses host playback and configured input-device capture, so it is useful
for low-cost microphone/speaker regression when bound to real devices, but it
proves generated speech rather than arbitrary human pronunciation.

The current narrowed `0.0.1` compatibility policy lists `synthetic`,
`virtual-mic`, and `acoustic` as eligible generated-speech modes. That policy
does not turn them into human voice-device evidence. Before a bundle can enter
policy evaluation, the verifier also requires the goal-driven acceptance
override, correlated applied `chat` and `robot_action` cognitive events,
exclusive Soridormi `sim` provider events, clean matching checkouts, and an
endpoint-reported Soridormi revision. The current runner records only a
`declared_paired_checkout`, so it cannot yet produce a policy-ready bundle.

Use `scripts/interaction_text_mujoco_check.py` when the goal is to skip both
microphone and ASR but still hear Chromie through the speaker. Use
`synthetic` M13 mode when the goal is to skip only the microphone: generated
Chromie TTS audio is injected as input and still passes through VAD and ASR.

### Automatic synthetic acceptance

Start the five Chromie services and a supervised MuJoCo-backed Soridormi MCP
endpoint. Check all prerequisites before creating an evidence bundle:

```bash
python scripts/voice_acceptance.py \
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
python scripts/voice_acceptance.py \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner generates each unique test utterance once through the existing TTS
WebSocket service and stores it under:

```text
.chromie/acceptance/voice/<id>/generated-input/
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
python scripts/verify_voice_evidence.py --allow-automated \
  .chromie/acceptance/voice/<id>
```

When its recorded Chromie version/revision and Soridormi manifest and declared
paired-checkout revisions match the current clean source, the verifier may
report passing diagnostic automated evidence. It sets
`policy_evaluation_ready=true` only when the endpoint also reports the matching
executing Soridormi revision. The current runner/endpoint path does not provide
that binding, while
`human_voice_device_claim_eligible=false` remains reserved for clean supervised
evidence. Release preparation separately applies the narrowed compatibility
policy's accepted modes. Historical inspection requires explicit
`--expected-*` values and does not transfer evidence to a newer build.

The retained reference-host synthetic run is `20260614T132934Z`; all seven
cases passed at Chromie revision `f0e22ba`.

### Automatic virtual-microphone acceptance

`virtual-mic` mode requires PulseAudio or PipeWire. It uses `pactl`/`paplay`
when available and otherwise falls back to native
`pw-cli`/`pw-cat`/`pw-dump` tools:

```bash
python scripts/voice_acceptance.py \
  --mode virtual-mic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner creates a temporary null sink named `chromie_voice_test` by default,
sets its monitor as `PULSE_SOURCE` for the Orchestrator, plays each generated WAV
into that sink, and unloads the module during cleanup. Override the sink name
with `--virtual-mic-sink` when needed.

This mode exercises normal `sounddevice` capture, sample-rate conversion, host
buffering, VAD, and ASR. It still does not prove a physical microphone or
speaker.

The retained PipeWire run is `20260614T133155Z`; all seven cases passed at
Chromie revision `f0e22ba`.

### Automatic acoustic acceptance

Use `acoustic` mode when the goal is to test the reference host's configured
speaker/input-device loop without requiring a human to speak all seven cases:

```bash
ORCH_INPUT_DEVICE=0 ORCH_OUTPUT_DEVICE=16 ORCH_INPUT_GAIN=80 \
python scripts/voice_acceptance.py \
  --mode acoustic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner generates each prompt with Chromie TTS, plays it through the
host audio player, and waits for the normal Orchestrator microphone path to
capture and recognize it. The default player is `auto`, which prefers
`pw-play`, then `paplay`, then `aplay`, and falls back to `sounddevice`.
Tune `ORCH_INPUT_DEVICE`, `ORCH_OUTPUT_DEVICE`, `ORCH_INPUT_GAIN`,
`--acoustic-playback-gain`, `--acoustic-player`, and
`--acoustic-output-target` for the host room and device levels. Chromie's own
responses use paced discard playback by default to avoid echoing confirmation
prompts back through host input bridges; use
`--acoustic-response-output-mode device` only when the selected input is a real
microphone path that tolerates response playback. This is target audio-path
evidence for generated speech, not a human pronunciation or
operator-observation claim; treat it as physical microphone evidence only when
the recorded `ORCH_INPUT_DEVICE` is known to be the real microphone path.

### Physical audio supervised acceptance

Commit the candidate revision first, then run:

```bash
python scripts/voice_acceptance.py \
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

Only a clean, passing `supervised` bundle can satisfy a human-supervised
voice-device release verifier:

```bash
python scripts/verify_voice_evidence.py --require-clean \
  .chromie/acceptance/voice/<id>
```

The host runner uses `ORCH_RUNTIME_OVERRIDE_FILE` and does not edit the
operator's `.env.local` or generated `.env.runtime`. The Soridormi capability
probe runs inside `chromie-agent` by default; host-loopback endpoints are
translated to `host.docker.internal` only for that container command.

This supervised mode is not required for M13 text interaction closure. Use it
when the claim being tested includes real microphone recognition, real speaker
playback, and operator-observed behavior.

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
python scripts/voice_acceptance.py --dry-run \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

## Voice and MuJoCo acceptance matrix

Run from the repository root with the structured path enabled and a live
MuJoCo-backed Soridormi endpoint. All four modes execute these cases in the
order below; only `acoustic` and `supervised` use a physical host audio path,
and only `supervised` adds human speech and operator observations.

| Case | User input | Required evidence |
|---|---|---|
| Speech only | General question | ASR final text, prepared speech with zero body skills, correlated TTS schedule, playback start/end, and clean session completion. Audible output is additionally judged only when the selected mode uses a physical output device. |
| Speech plus body skill | “Nod” or equivalent, then “Yes” | Exact nod/count proposal; request-bound confirmation prompt scheduled and fully played before approval; requested, approved, and authorized events bound by confirmation ID and fingerprint; completed skill result; safe idle. |
| Refusal | Valid body request, then “No thanks” | Requested, denied, and rejected events bound by confirmation ID and fingerprint; no Soridormi result; completed denial speech output. |
| Barge-in | Interrupt while speaking | Active old-session playback linked to the new interrupt session, deterministic interrupt route, and no old-session playback after interruption completes. |
| Body cancellation | Confirm, then interrupt a cancellable simulated skill | Bound approval, host-observed Skill Runtime cancellation, host interruption completion, and post-cancellation safe-idle/no-active-task status. This does not claim a provider cancel RPC unless a provider event explicitly records one. |
| Stop/emergency | Explicit stop during active work | Deterministic operational route linked to the active prior session, with no later old-session output or completed work. |
| Follow-up | “Remember … blue,” then ask for the color | Same conversation ID, both intended ASR utterances, and completed second-response output containing `blue`. |

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
- Do not publish a MuJoCo-executor release from text-input acceptance alone.
- Do not publish logs containing execution tokens or private environment data.
- Record failure evidence as well as successful reruns; otherwise regressions are
  difficult to diagnose.
