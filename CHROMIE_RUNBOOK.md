# Chromie Operations Runbook

This runbook contains commands and recovery procedures. Use
[Current Implementation Status](docs/STATUS.md) for claims about completion and
[Configuration Reference](docs/CONFIGURATION.md) for variable semantics.

Run commands from the repository root unless stated otherwise.

## 1. Inspect configuration

```bash
cp -n .env.local.example .env.local
./scripts/show_profile.sh
python -m tools.chromie_cli status
python -m tools.chromie_cli config show
python -m tools.chromie_cli config validate
python -m tools.chromie_cli doctor
python -m tools.chromie_cli capability check
python -m tools.chromie_cli trace view
python -m tools.chromie_cli evidence bundle
```

Generated files:

```text
.env.runtime
.env
.chromie/system_info.env
.chromie/runtime_profile.json
```

Do not hand-edit generated files. Hardware profile selection is automatic; do
not set `CHROMIE_HARDWARE_PROFILE` in `.env.local` or on a launcher command.

## 1.1 Launcher layers

`./scripts/start_services.sh` is the low-level Docker service launcher. It first
refreshes hardware detection and `.env.runtime`, validates Compose, builds or
starts ASR, TTS, Ollama, Router, and Agent, and then verifies that containers
and the TTS CUDA build match the detected profile. It does not start the host
Orchestrator and does not assume Soridormi is running.

`./scripts/start_chromie.sh` is the operator launcher. It expects Soridormi MCP
to already be reachable, writes the Chromie/Soridormi runtime overrides, starts
the Docker services through `start_services.sh`, probes Soridormi capabilities,
and then starts the host Orchestrator. Use `--no-orchestrator --keep-services`
when you only want the service/MCP attachment for text diagnostics or another
already-running Orchestrator.

## 2. Start Docker services

First build:

```bash
BUILD=1 ./scripts/start_services.sh
```

Normal start:

```bash
./scripts/start_services.sh
```

Clean rebuild:

```bash
REBUILD_NO_CACHE=1 ./scripts/start_services.sh
```

Stop services:

```bash
./scripts/compose.sh down
```

## 3. Prepare Ollama

```bash
./scripts/compose.sh exec chromie-llm ollama list
./scripts/list_runtime_ollama_models.sh

# Pull every distinct model selected by the detected profile.
while IFS= read -r model; do
  ./scripts/compose.sh exec chromie-llm ollama pull "$model"
done < <(./scripts/list_runtime_ollama_models.sh)

./scripts/warm_ollama.sh
```

`start_chromie.sh` and `start_orchestrator.sh` warm the complete active model
inventory automatically. A missing profile model stops startup before a live
interaction can reach that stage.

## 4. Configure and start host audio

```bash
conda create -n Chromie python=3.11 -y
conda activate Chromie
./scripts/install_orchestrator_deps.sh
cp -n orchestrator/.env.local.example orchestrator/.env.local
python orchestrator/list_devices.py
```

Set `ORCH_INPUT_DEVICE` and `ORCH_OUTPUT_DEVICE`, then start:

```bash
./scripts/start_orchestrator.sh
```

Manual launch, after dependencies are installed:

```bash
./scripts/build_runtime_env.sh
python -m orchestrator.orchestrator
```

Do not launch from inside `orchestrator/`; repository-relative imports and paths
assume the project root.

## 5. Select the interaction mode

### Compatibility voice path

Use this only for explicit rollback or compatibility diagnostics:

```env
ORCH_ENABLE_ROUTER=1
ORCH_ENABLE_AGENT=1
ORCH_ENABLE_INTERACTION_RESPONSE=0
ORCH_COGNITIVE_RUNTIME_MODE=off
```

### Structured speech-only path

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=0
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat
```

### Structured MuJoCo path

```env
ORCH_ENABLE_INTERACTION_RESPONSE=1
ORCH_ENABLE_SORIDORMI_SKILLS=1
ORCH_AUTO_CONFIRM_SIM_SKILLS=1
ORCH_COGNITIVE_RUNTIME_MODE=apply
ORCH_COGNITIVE_APPLY_LANES=chat,robot_action
ORCH_SORIDORMI_MANIFEST=capabilities/soridormi.json
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

Restart the Orchestrator after changing host feature gates.


## 5.1 Start the complete voice-to-MuJoCo path

Start Soridormi's simulator and runtime MCP first. Then, from the Chromie
repository root, run:

```bash
./scripts/start_chromie.sh
```

The launcher uses the same `.env.runtime` and Compose image definitions as the
normal service scripts. It enables structured InteractionResponse, Soridormi
named skills, physical microphone input, and speaker output without redefining
image tags. Use `--require-confirmation` to require spoken confirmation for all
simulator skills, or `--build` to rebuild repository-owned service images.

## 5.2 Text-to-MuJoCo without microphone or ASR

For route, goal-driven planning, Skill Runtime, speaker, and live MuJoCo checks without
microphone capture or ASR, start Soridormi first:

```bash
cd ../soridormi
./scripts/run_sim_server.sh --backend mujoco --profile open_duck_forward --no-viewer
```

In another terminal:

```bash
cd ../soridormi
docker compose -f compose.sim.yaml --profile mcp-runtime up -d --no-build mcp-runtime
```

Start the Chromie services with the Soridormi manifest mounted into the Agent:

```bash
cd ../chromie
mkdir -p .chromie/text-mujoco
cat > .chromie/text-mujoco/compose.soridormi.yaml <<'EOF'
services:
  chromie-agent:
    environment:
      AGENT_CAPABILITY_MANIFESTS: /app/capabilities/soridormi.json
      SORIDORMI_MCP_URL: http://host.docker.internal:8000/mcp
      AGENT_INTERACTION_OUTPUT_MODE: native
      AGENT_NATIVE_INTERACTION_FALLBACK: "0"
  chromie-router:
    environment:
      ROUTER_CAPABILITY_MATCH_LIMIT: "16"
EOF
CHROMIE_COMPOSE_OVERRIDE_FILES=.chromie/text-mujoco/compose.soridormi.yaml \
  ./scripts/start_services.sh
```

Then run the text check. This commands MuJoCo through Soridormi and speaks
Chromie's response through the configured speaker:

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

Use `--no-speaker` for headless automation. The runner sets a 120s per-skill
diagnostic timeout for live simulator checks; pass `--skill-timeout-s 0` to use
catalog/default timeouts unchanged. Evidence is written under
`.chromie/acceptance/text-mujoco/<id>/`. The summary records exact source,
manifest, and semantic-runtime provenance. This is the current cognitive
text-to-MuJoCo path; it is not supervised microphone evidence and does not prove
physical audio-device quality. Use `--no-cognitive-runtime` only for an
explicitly labelled legacy compatibility diagnosis.

For behavior-quality text probes without executing robot motion, run the
general ability live-text preview:

```bash
python scripts/general_ability_acceptance.py \
  --mode live-text \
  --goal-driven-runtime apply \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

This checks representative ability-class probes through Router and the
goal-driven runtime in preview mode and writes evidence under
`.chromie/acceptance/general-ability/<id>/`. Add `--execute` only for a
supervised simulator run.

## 6. Health checks

```bash
./scripts/compose.sh ps
curl -fsS http://127.0.0.1:8091/health | python -m json.tool
curl -fsS http://127.0.0.1:8091/routes | python -m json.tool
curl -fsS http://127.0.0.1:8092/health | python -m json.tool
curl -fsS http://127.0.0.1:8092/capabilities | python -m json.tool
curl -fsS http://127.0.0.1:11434/api/tags | python -m json.tool
```

TaskGraph dry-run, trace, and scheduler diagnostics require a bearer token. Use
the configured diagnostics token, or the execution token when the diagnostics
token is blank:

```bash
TASK_GRAPH_TOKEN="${AGENT_TASK_GRAPH_DIAGNOSTICS_TOKEN:-${AGENT_TASK_GRAPH_EXECUTION_TOKEN:-}}"
test -n "$TASK_GRAPH_TOKEN"
curl -fsS \
  -H "Authorization: Bearer $TASK_GRAPH_TOKEN" \
  http://127.0.0.1:8092/task-graphs/scheduler/status | python -m json.tool
```

When neither token is configured, diagnostic endpoints intentionally return
HTTP 503.

## 7. Automated tests

```bash
./scripts/run_tests.sh
```

Documentation-only check:

```bash
python scripts/check_docs.py
```

## 8. GPU and TTS verification

```bash
./scripts/verify_tts_gpu.sh
./scripts/gpu_smoke_test.sh
```

Start existing images and generate real TTS audio:

```bash
START_SERVICES=1 RUN_TTS_SYNTHESIS=1 ./scripts/gpu_smoke_test.sh
```

Dry-run the planned checks:

```bash
DRY_RUN=1 ./scripts/gpu_smoke_test.sh
```

A dry run is not target evidence.

## 9. Soridormi capability checks

Set the live endpoint:

```bash
export SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp
```

Probe schema compatibility in the deployed Agent environment:

```bash
./scripts/build_runtime_env.sh
./scripts/compose.sh up -d chromie-agent
./scripts/compose.sh exec -T \
  -e SORIDORMI_MCP_URL=http://host.docker.internal:8000/mcp \
  chromie-agent \
  python -m app.probe_capabilities \
  --manifest /app/capabilities/soridormi.json
```

The Agent service has `host.docker.internal:host-gateway` configured for Linux.
Use a Docker service hostname instead when Soridormi is attached to the same
network.

List the active Agent registry:

```bash
PYTHONPATH=agent python -m app.list_capabilities \
  --manifest capabilities/soridormi.json
```

Generate LLM-visible context:

```bash
PYTHONPATH=agent python -m app.list_capabilities \
  --manifest capabilities/soridormi.json \
  --llm-context --language en
```

Safe status and zero-motion planning acceptance:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json
```

Runtime-backed simulator preflight:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --runtime-preflight \
  --expected-backend runtime \
  --expected-mode sim
```

## 10. Structured text acceptance

Use the general ability preview for behavior claims:

```bash
python scripts/general_ability_acceptance.py --mode live-text \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp
```

Use `scripts/interaction_text_mujoco_check.py --no-speaker` when the claim
requires retained text-to-simulator evidence. These paths do not use the
microphone or physical speaker.

## 11. Guarded recovery acceptance

Disposable Soridormi dry-run process:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --guarded-dry-run
```

Only add `--exercise-emergency-stop` when the process may be restarted.

Supervised runtime cancellation:

```bash
PYTHONPATH=agent python -m app.soridormi_acceptance \
  --manifest capabilities/soridormi.json \
  --exercise-runtime-cancellation
```

This intentionally leaves Soridormi emergency-stopped. Follow the Soridormi
recovery procedure and verify ready/safe-idle state before further motion.

## 12. Legacy target evidence

```bash
SUPERVISED_ACCEPTANCE=1 START_SERVICES=1 \
  ./scripts/run_supervised_target_acceptance.sh
```

Evidence appears under `.chromie/acceptance/<id>/`. The runner combines runtime
preflight, GPU smoke, and cancellation/emergency fallback. After it passes,
record the recovery result; the script itself leaves e-stop active.

Command rehearsal:

```bash
SUPERVISED_ACCEPTANCE=1 TARGET_ACCEPTANCE_DRY_RUN=1 \
  SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
  ./scripts/run_supervised_target_acceptance.sh
```

## 13. Alpha voice acceptance

Use the functional voice acceptance commands for new evidence. Historical
Historical text-to-MuJoCo evidence remains documented separately.

Before live simulator work, run the dependency-free provider fault matrix:

```bash
python scripts/provider_fault_matrix.py
```

To retain a focused replayable summary:

```bash
python scripts/provider_fault_matrix.py \
  --scenarios monitor_refused,execute_timeout,operator_cancel \
  --max-cancel-terminal-ms 250 \
  --output .chromie/provider-fault-matrix.json
```

The JSON summary includes status and reason distributions, maximum elapsed
time, maximum terminal latency, active thresholds, and per-scenario threshold
violations. Declare tighter target thresholds explicitly rather than changing
the scenario semantics. Every scenario also ends with
`soridormi.robot.get_status`; a non-empty `active_task`, active emergency stop,
or failed status read fails the matrix.

Run the live form serially against a dedicated no-motion Soridormi endpoint;
do not run conformance concurrently because fault configuration is endpoint
state:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
python scripts/provider_fault_matrix.py --live \
  --manifest capabilities/soridormi.json \
  --output .chromie/provider-readiness/fault-matrix.json
```

Run the provider-neutral conformance contract against both local no-motion
profiles:

```bash
python scripts/provider_conformance.py
```

The live form is restricted to one explicit safe profile:

```bash
SORIDORMI_MCP_URL=http://127.0.0.1:8000/mcp \
python scripts/provider_conformance.py --live --profile sim
```

Run the automatic synthetic matrix first. It generates input WAV files with the
existing TTS service and injects them through the Orchestrator's private stdin
audio path, so the test still crosses VAD, ASR, Router, goal-driven Agent
planning/composition, Skill Runtime, response TTS, and Soridormi without relying
on a person speaking:

```bash
python scripts/voice_acceptance.py \
  --preflight-only \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

This reports all local blockers without starting services or creating an
evidence directory. After it reports `Overall: ready`, run:

```bash
python scripts/voice_acceptance.py \
  --mode synthetic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The run is fully automatic. The terminal displays generated fixture paths, ASR
transcripts, Router results, proposed skill IDs, skill results, and final case
verdicts. Validate this regression evidence with:

```bash
python scripts/verify_voice_evidence.py --allow-automated \
  .chromie/acceptance/voice/<id>
```

To include the host audio-device capture path without using a physical
microphone, run:

```bash
python scripts/voice_acceptance.py \
  --mode virtual-mic \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

The runner uses `pactl`/`paplay` when available or native
`pw-cli`/`pw-cat`/`pw-dump` on PipeWire. It creates a temporary null sink, uses
its monitor as the input source, and removes it during cleanup. If a PulseAudio
run was killed before cleanup, unload the stale module with
`pactl list short modules` followed by `pactl unload-module <id>`.

For a later claim that includes human microphone/speaker operation, commit the
committed revision and run the real reference-host matrix:

```bash
python scripts/voice_acceptance.py \
  --mode supervised \
  --soridormi-mcp-url http://127.0.0.1:8000/mcp \
  --soridormi-repo ../soridormi \
  --start-services
```

In supervised mode, press Enter once when ready, wait for `SPEAK NOW`, and speak
the displayed phrase. The runner prints the ASR result and session-scoped
pipeline trace. It asks for an audible/visual verdict only after all automated
checks pass. Verify human voice-device evidence without `--allow-automated`:

```bash
python scripts/verify_voice_evidence.py --require-clean \
  .chromie/acceptance/voice/<id>
```

Automatic bundles do not prove a real microphone, speaker, human pronunciation,
room conditions, or operator-observed simulator safety. They therefore cannot
close a human voice-device claim. The current development compatibility policy accepts clean current-revision
`synthetic`, `virtual-mic`, or `acoustic` voice evidence for bounded
engineering review. It does not turn those modes into human voice-device
evidence; see `docs/RELEASE.md`.

## 14. Logs

```bash
./scripts/compose.sh logs -f chromie-asr
./scripts/compose.sh logs -f chromie-router
./scripts/compose.sh logs -f chromie-agent
./scripts/compose.sh logs -f chromie-llm
./scripts/compose.sh logs -f chromie-tts
```

Useful Agent inspection:

```bash
curl -fsS http://127.0.0.1:8092/health | python -m json.tool
curl -fsS 'http://127.0.0.1:8092/capabilities/llm-context?language=en' \
  | python -m json.tool
```

## 15. Common recovery

### Duplicate replies

Verify only one Orchestrator owns the microphone:

```bash
pgrep -af 'orchestrator\.orchestrator'
```

The normal startup script uses `/tmp/chromie-orchestrator.lock`.

### TTS produces no audio

- Inspect `chromie-tts` logs.
- Verify `TTS_MAX_LENGTH` is a generation budget, not a character limit.
- Use `TTS_MAX_TEXT_CHARS` to shorten speech.
- Run `./scripts/verify_tts_gpu.sh`.

### TTS speaks only the first words

- Compare `tts_schedule` text with `tts_server_metrics` audio duration. If the
  full text was scheduled but only about one second of audio was returned, the
  TTS model—not playback—truncated the waveform.
- Inspect `prompt_tokens`, `generated_tokens`, `headroom`, and `limit_reached` in
  `chromie-tts` logs. `limit_reached=true` means the prompt plus generated audio
  tokens exhausted `TTS_MAX_LENGTH`.
- The maintained RTX 4090 Laptop profile uses
  `TTS_CONTEXT_SIZE=4096` and `TTS_MAX_LENGTH=4096`. Rebuild `.env.runtime` and
  recreate `chromie-tts` after changing the profile.
- Run `python scripts/benchmark_tts.py --repeat 2 --warmup 1`; the benchmark
  fails when any case reaches the generation limit.

### Compare or diagnose TTS providers

- Confirm the selected service exposes `provider_contract_version=1`, a
  software-license declaration, and immutable licensed
  `provider.model_artifacts` in its `health` response.
- The maintained `chromie-tts` image must report
  `TTS_PROVIDER=fun-cosyvoice3-0.5b`; an unknown or image-mismatched value is a
  startup error, not a fallback. Oute and Qwen are separate explicit services.
- Validate the common matrix before a live run:
  `python scripts/tts_provider_ab.py --check`.
- Compare at least two isolated endpoints with identical inputs:

  ```bash
  TTS_AB_REFERENCE_DIR=.chromie/private/tts-voice \
  TTS_AB_SKIP_REFERENCE_GENERATION=1 \
  ./scripts/run_tts_candidate_ab.sh
  ```

- Review `result.json`, every WAV, and `listening-review.json`. A fast automated run is not a Mandarin listening verdict.
- If interruption recovery fails, inspect the provider cancellation mode,
  worker/process lifecycle, active GPU work, and whether stale PCM appeared in
  the recovery request. Host barge-in policy remains in the Orchestrator.

### Named skill fails before execution

- Confirm `ORCH_ENABLE_SORIDORMI_SKILLS=1`.
- Confirm `SORIDORMI_MCP_URL` is exported where the manifest is loaded.
- Run the capability probe.
- Compare live tool schemas to the pinned manifest revision.

### Emergency stop remains active

This is expected after cancellation/emergency acceptance. Do not bypass it in
Chromie. Follow Soridormi’s recovery process, then re-run status/preflight.
