#!/usr/bin/env bash
# Chromie comprehensive deterministic + hybrid E2E qualification collector.
#
# This runner preserves the existing test architecture:
#   1. exact source/unit/module/contract checks;
#   2. maintained deterministic behavior scenarios;
#   3. bilingual generated-speech closed-loop E2E scenarios;
#   4. semantic-review bundles for meaning-based judgments;
#   5. correlated host, Docker, GPU, audio, and runtime evidence.
#
# It never asks the operator to speak. With --capture acoustic, Chromie's own
# TTS is played through the speaker and recorded by the physical microphone.
# Every phase is fail-soft so a failed check still leaves an uploadable archive.
set -uo pipefail

SCRIPT_VERSION="1.5.2"
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
DEFAULT_REPO_DIR="$(cd "$(dirname "$SCRIPT_PATH")/../.." && pwd)"
REPO_DIR="$DEFAULT_REPO_DIR"
DOWNLOAD_DIR="$HOME/Downloads"
CAPTURE_MODE="auto"
LANGUAGES="zh,en"
ALLOW_DIRTY=0
STOP_SERVICES=0
SKIP_SOURCE=0
SKIP_DETERMINISTIC=0
SKIP_SERVICES=0
SKIP_CLOSED_LOOP=0
SKIP_SYNTHETIC=0
SKIP_GPU_LOAD=0
DRY_RUN=0
COLLECT_ONLY=0
STRICT_EXIT=0
SOURCE_TIMEOUT_S=2400
BENCHMARK_TIMEOUT_S=1800
SERVICE_TIMEOUT_S=900
E2E_TIMEOUT_S=2400
GPU_LOAD_REQUESTS=20
TTS_REPEAT=8
DOCKER_LOG_SINCE=""
SEMANTIC_REVIEWERS=""
SEMANTIC_REVIEWER_IDS=()
SANITIZE_ARCHIVE=0
SANITIZE_EXCLUDE_AUDIO=0

usage() {
  cat <<'USAGE'
Usage: scripts/qualification/run_comprehensive_test.sh [options]

Runs Chromie's complete source, deterministic benchmark, service/GPU, bilingual
closed-loop, and semantic-evidence collection flow. No operator speech is used.

Options:
  --repo PATH                 Chromie repository root (default: this checkout)
  --downloads PATH            Archive destination (default: ~/Downloads)
  --capture MODE              auto, monitor, or acoustic (default: auto)
  --languages LIST            Closed-loop languages (default: zh,en)
  --allow-dirty               Run from a dirty worktree, but mark it unqualified
  --stop-services             Stop Compose services after evidence collection
  --dry-run                   Validate inputs and print the execution plan only
  --collect-only              Collect current host/container evidence without running tests
  --strict-exit               Retain the archive but exit nonzero unless the run passed
  --ci                        Alias for --strict-exit
  --skip-source               Skip revision-bound source/unit qualification
  --skip-deterministic        Skip benchmark contracts and deterministic scenarios
  --skip-services             Skip Docker/GPU/TTS and all live E2E phases
  --skip-closed-loop          Skip bilingual playback-capture/ASR E2E
  --skip-synthetic            Skip the retained synthetic voice-acceptance suite
  --skip-gpu-load             Skip shared-GPU contention tests
  --source-timeout SECONDS    Source qualification timeout (default: 2400)
  --benchmark-timeout SECONDS Deterministic benchmark timeout (default: 1800)
  --e2e-timeout SECONDS       Per closed-loop run timeout (default: 2400)
  --tts-repeat N              TTS benchmark repetitions (default: 8)
  --gpu-load-requests N       Ollama requests during contention (default: 20)
  --semantic-reviewers PATH   Opt in to external multi-LLM semantic adjudication
  --semantic-reviewer ID      Select one configured reviewer (repeatable)
  --sanitize-archive          Also create a credential- and identity-redacted upload copy
  --sanitize-exclude-audio    Exclude audio from the sanitized upload copy
  -h, --help                  Show this help

Output:
  ~/Downloads/chromie-comprehensive-<revision>-<UTC_RUN_ID>.tar.gz
  ~/Downloads/chromie-comprehensive-<revision>-<UTC_RUN_ID>.tar.gz.sha256

Review the archive with a chosen LLM/human or use --semantic-reviewers for an
independent model ensemble. Inspect it first because logs may contain private content.
USAGE
}

while (($#)); do
  case "$1" in
    --repo) REPO_DIR="${2:?--repo needs a path}"; shift 2 ;;
    --downloads) DOWNLOAD_DIR="${2:?--downloads needs a path}"; shift 2 ;;
    --capture) CAPTURE_MODE="${2:?--capture needs auto, monitor, or acoustic}"; shift 2 ;;
    --languages) LANGUAGES="${2:?--languages needs a comma-separated list}"; shift 2 ;;
    --allow-dirty) ALLOW_DIRTY=1; shift ;;
    --stop-services) STOP_SERVICES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --collect-only) COLLECT_ONLY=1; shift ;;
    --strict-exit|--ci) STRICT_EXIT=1; shift ;;
    --skip-source) SKIP_SOURCE=1; shift ;;
    --skip-deterministic) SKIP_DETERMINISTIC=1; shift ;;
    --skip-services) SKIP_SERVICES=1; shift ;;
    --skip-closed-loop) SKIP_CLOSED_LOOP=1; shift ;;
    --skip-synthetic) SKIP_SYNTHETIC=1; shift ;;
    --skip-gpu-load) SKIP_GPU_LOAD=1; shift ;;
    --source-timeout) SOURCE_TIMEOUT_S="${2:?--source-timeout needs seconds}"; shift 2 ;;
    --benchmark-timeout) BENCHMARK_TIMEOUT_S="${2:?--benchmark-timeout needs seconds}"; shift 2 ;;
    --e2e-timeout) E2E_TIMEOUT_S="${2:?--e2e-timeout needs seconds}"; shift 2 ;;
    --tts-repeat) TTS_REPEAT="${2:?--tts-repeat needs a number}"; shift 2 ;;
    --gpu-load-requests) GPU_LOAD_REQUESTS="${2:?--gpu-load-requests needs a number}"; shift 2 ;;
    --semantic-reviewers) SEMANTIC_REVIEWERS="${2:?--semantic-reviewers needs a path}"; shift 2 ;;
    --semantic-reviewer) SEMANTIC_REVIEWER_IDS+=("${2:?--semantic-reviewer needs an id}"); shift 2 ;;
    --sanitize-archive) SANITIZE_ARCHIVE=1; shift ;;
    --sanitize-exclude-audio) SANITIZE_ARCHIVE=1; SANITIZE_EXCLUDE_AUDIO=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[comprehensive][error] Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$CAPTURE_MODE" in
  auto|monitor|acoustic) ;;
  *) echo "[comprehensive][error] --capture must be auto, monitor, or acoustic" >&2; exit 2 ;;
esac

for numeric in SOURCE_TIMEOUT_S BENCHMARK_TIMEOUT_S E2E_TIMEOUT_S TTS_REPEAT GPU_LOAD_REQUESTS; do
  value="${!numeric}"
  [[ "$value" =~ ^[0-9]+$ ]] || {
    echo "[comprehensive][error] $numeric must be a non-negative integer" >&2
    exit 2
  }
done

REPO_DIR="$(cd "$REPO_DIR" 2>/dev/null && pwd)" || {
  echo "[comprehensive][error] Repository directory does not exist: $REPO_DIR" >&2
  exit 2
}
cd "$REPO_DIR"
mkdir -p "$DOWNLOAD_DIR"

if ((${#SEMANTIC_REVIEWER_IDS[@]} > 0)) && [[ -z "$SEMANTIC_REVIEWERS" ]]; then
  echo "[comprehensive][error] --semantic-reviewer requires --semantic-reviewers" >&2
  exit 2
fi

if [[ -n "$SEMANTIC_REVIEWERS" ]]; then
  if [[ "$SEMANTIC_REVIEWERS" != /* ]]; then
    SEMANTIC_REVIEWERS="$REPO_DIR/$SEMANTIC_REVIEWERS"
  fi
  [[ -f "$SEMANTIC_REVIEWERS" ]] || {
    echo "[comprehensive][error] Semantic reviewer config not found: $SEMANTIC_REVIEWERS" >&2
    exit 2
  }
fi

required_files=(
  scripts/run_source_qualification.py
  scripts/build_runtime_env.sh
  scripts/start_services.sh
  scripts/gpu_smoke_test.sh
  scripts/verify_tts_gpu.sh
  scripts/benchmark_tts.py
  scripts/closed_loop_e2e.py
  scripts/voice_acceptance.py
  benchmarks/manifests/closed_loop_e2e_v1.json
  benchmarks/manifests/fault_injection_v1.json
)
for required in "${required_files[@]}"; do
  [[ -e "$required" ]] || {
    echo "[comprehensive][error] Missing repository file: $required" >&2
    exit 2
  }
done

print_plan() {
  cat <<EOF
Chromie comprehensive qualification plan

Repository:       $REPO_DIR
Capture mode:     $CAPTURE_MODE
Languages:        $LANGUAGES
Allow dirty:      $ALLOW_DIRTY
Collect only:     $COLLECT_ONLY
Strict exit:      $STRICT_EXIT
Semantic judges:  ${SEMANTIC_REVIEWERS:-disabled}
Sanitized copy:   $SANITIZE_ARCHIVE
Exclude audio:    $SANITIZE_EXCLUDE_AUDIO

Phases:
  0. Record revision, host, audio, Docker, GPU, and runner identity.
  1. Run revision-bound source qualification and maintained deterministic tests.
  2. Validate benchmark inventory/contracts, run deterministic scenarios, and inject controlled provider faults.
  3. Build/start maintained services and run GPU/TTS health checks.
  4. Run bilingual generated-speech closed-loop E2E and package semantic evidence.
  5. Repeat TTS and workflow E2E under bounded shared-GPU load.
  6. Optionally run independent configured LLM judges and aggregate consensus.
  7. Collect all program/container logs, artifacts, hashes, and the raw local archive.
  8. Optionally create a separate sanitized upload archive without modifying raw evidence.

Objective fixtures, contracts, and invariants remain deterministic truth.
Semantic dimensions remain pending retained LLM or human adjudication.
No operator voice or pronunciation judgment is required.
EOF
}

if (( DRY_RUN == 1 )); then
  print_plan
  exit 0
fi

if (( COLLECT_ONLY == 1 )); then
  SKIP_SOURCE=1
  SKIP_DETERMINISTIC=1
  SKIP_SERVICES=1
  SKIP_CLOSED_LOOP=1
  SKIP_SYNTHETIC=1
  SKIP_GPU_LOAD=1
fi

CONDA_ENV_NAME="${CHROMIE_CONDA_ENV:-Chromie}"
if command -v conda >/dev/null 2>&1 \
   && conda env list 2>/dev/null | awk '{print $1}' | grep -Fxq "$CONDA_ENV_NAME"; then
  PYTHON_CMD=(conda run --no-capture-output -n "$CONDA_ENV_NAME" python)
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD=(python)
else
  PYTHON_CMD=(python3)
fi

RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
STARTED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DOCKER_LOG_SINCE="$STARTED_UTC"
REVISION="$(git rev-parse HEAD 2>/dev/null || printf 'unknown')"
REV_SHORT="${REVISION:0:12}"
RESULT_REL=".chromie/comprehensive/$RUN_ID"
RESULT_ROOT="$REPO_DIR/$RESULT_REL"
LOG_ROOT="$RESULT_ROOT/logs"
BENCH_ROOT="$RESULT_ROOT/benchmarks"
E2E_ROOT="$RESULT_ROOT/e2e"
SYSTEM_ROOT="$RESULT_ROOT/system"
CONTAINER_ROOT="$RESULT_ROOT/containers"
mkdir -p "$LOG_ROOT" "$BENCH_ROOT" "$E2E_ROOT" "$SYSTEM_ROOT" "$CONTAINER_ROOT"
cp "$SCRIPT_PATH" "$SYSTEM_ROOT/run_comprehensive_test.sh"
sha256sum "$SYSTEM_ROOT/run_comprehensive_test.sh" > "$SYSTEM_ROOT/run_comprehensive_test.sh.sha256"
CHECKS_TSV="$RESULT_ROOT/checks.tsv"
printf 'phase\tcheck\tstatus\texit_code\tstarted_utc\tcompleted_utc\tlog\n' > "$CHECKS_TSV"

GPU_MONITOR_PID=""
DOCKER_EVENTS_PID=""
OLLAMA_LOAD_PID=""
SERVICES_STARTED=0

cleanup_background() {
  local pid
  for pid in "$OLLAMA_LOAD_PID" "$GPU_MONITOR_PID" "$DOCKER_EVENTS_PID"; do
    [[ -n "$pid" ]] || continue
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  done
  OLLAMA_LOAD_PID=""
  GPU_MONITOR_PID=""
  DOCKER_EVENTS_PID=""
}
trap cleanup_background EXIT INT TERM

safe_name() {
  printf '%s' "$1" | tr ' /:' '___' | tr -cd '[:alnum:]_.-'
}

record_result() {
  local phase="$1" label="$2" code="$3" started="$4" completed="$5" log="$6"
  local status="PASS"
  case "$code" in
    0) status="PASS" ;;
    124|137) status="TIMEOUT" ;;
    200) status="SKIP" ;;
    *) status="FAIL" ;;
  esac
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$phase" "$label" "$status" "$code" "$started" "$completed" "$log" >> "$CHECKS_TSV"
  printf '[comprehensive][%s][%s] %s (exit=%s)\n' "$phase" "$status" "$label" "$code"
}

record_skip() {
  local phase="$1" label="$2" reason="$3"
  local now file
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  file="$LOG_ROOT/$(safe_name "$phase-$label").log"
  printf '%s\n' "$reason" > "$file"
  record_result "$phase" "$label" 200 "$now" "$now" "${file#$RESULT_ROOT/}"
}

run_capture() {
  local phase="$1" label="$2" timeout_s="$3"; shift 3
  local file command_file started completed code
  file="$LOG_ROOT/$(safe_name "$phase-$label").log"
  command_file="$file.command"
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '%q ' "$@" > "$command_file"
  printf '\n' >> "$command_file"
  echo
  echo "========================================================================"
  echo "[comprehensive][$phase] $label"
  echo "[comprehensive] command: $(cat "$command_file")"
  echo "========================================================================"
  set +e
  if (( timeout_s > 0 )) && command -v timeout >/dev/null 2>&1; then
    timeout --signal=TERM --kill-after=30s "${timeout_s}s" "$@" 2>&1 | tee "$file"
    code=${PIPESTATUS[0]}
  else
    "$@" 2>&1 | tee "$file"
    code=${PIPESTATUS[0]}
  fi
  completed="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  record_result "$phase" "$label" "$code" "$started" "$completed" "${file#$RESULT_ROOT/}"
  return 0
}

run_shell_capture() {
  local phase="$1" label="$2" timeout_s="$3" shell_command="$4"
  run_capture "$phase" "$label" "$timeout_s" bash -lc "$shell_command"
}

write_redacted_env() {
  local source="$1" target="$2"
  python3 - "$source" "$target" <<'PY'
from pathlib import Path
import re
import sys

source, target = map(Path, sys.argv[1:])
sensitive = re.compile(
    r"(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|AUTH|CREDENTIAL|PRIVATE_KEY|COOKIE)",
    re.I,
)
rows = []
for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
    if "=" in raw:
        key, _ = raw.split("=", 1)
        if sensitive.search(key):
            raw = f"{key}=<redacted>"
    rows.append(raw)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("\n".join(rows) + "\n", encoding="utf-8")
PY
}

cat > "$RESULT_ROOT/run.env" <<EOF
script_version=$SCRIPT_VERSION
runner_path=scripts/qualification/run_comprehensive_test.sh
runner_sha256=$(sha256sum "$SCRIPT_PATH" | awk '{print $1}')
run_id=$RUN_ID
started_utc=$STARTED_UTC
repository=$REPO_DIR
revision=$REVISION
capture_mode=$CAPTURE_MODE
languages=$LANGUAGES
python_command=$(printf '%q ' "${PYTHON_CMD[@]}")
human_voice_required=false
operator_pronunciation_graded=false
collect_only=$COLLECT_ONLY
semantic_reviewers_config=${SEMANTIC_REVIEWERS:-disabled}
semantic_reviewer_ids=$(IFS=,; echo "${SEMANTIC_REVIEWER_IDS[*]}")
EOF

# ---------------------------------------------------------------------------
# Phase 0: immutable identity and host inventory.
# ---------------------------------------------------------------------------
run_capture identity "git status" 60 git status --short
run_capture identity "git revision" 60 git rev-parse HEAD
run_capture identity "git commit" 60 git log -1 --decorate --stat --oneline
run_capture identity "git diff check" 60 git diff --check
run_capture system "uname" 60 uname -a
run_shell_capture system "os release" 60 "cat /etc/os-release 2>/dev/null || true"
run_shell_capture system "cpu and memory" 60 "lscpu 2>/dev/null || true; echo; free -h 2>/dev/null || true; echo; df -h '$REPO_DIR' 2>/dev/null || true"
run_capture system "python version" 60 "${PYTHON_CMD[@]}" --version
run_capture system "python packages" 180 "${PYTHON_CMD[@]}" -m pip freeze
run_capture system "docker version" 120 docker version
run_capture system "docker info" 120 docker info
run_capture system "nvidia smi" 120 nvidia-smi
run_shell_capture system "nvidia query" 120 "nvidia-smi --query-gpu=timestamp,name,driver_version,compute_cap,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw --format=csv"
run_shell_capture system "audio inventory" 120 "command -v wpctl >/dev/null && wpctl status || true; echo '--- pactl info ---'; command -v pactl >/dev/null && pactl info || true; echo '--- sources ---'; command -v pactl >/dev/null && pactl list short sources || true; echo '--- sinks ---'; command -v pactl >/dev/null && pactl list short sinks || true; echo '--- ALSA playback ---'; command -v aplay >/dev/null && aplay -l || true; echo '--- ALSA capture ---'; command -v arecord >/dev/null && arecord -l || true"
run_capture system "sounddevice inventory" 120 "${PYTHON_CMD[@]}" -m sounddevice

DIRTY=0
[[ -z "$(git status --porcelain 2>/dev/null)" ]] || DIRTY=1
if (( DIRTY == 1 )); then
  record_result identity "clean worktree requirement" 3 "$STARTED_UTC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "logs/identity-git_status.log"
  cat > "$RESULT_ROOT/DIRTY_WORKTREE.txt" <<EOF
The worktree was dirty. Collection continued so failures remain diagnosable, but
this run cannot establish revision-bound qualification. Re-run from a clean,
committed checkout for an authoritative comparison.

allow_dirty=$ALLOW_DIRTY
EOF
else
  record_result identity "clean worktree requirement" 0 "$STARTED_UTC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "logs/identity-git_status.log"
fi

# Start run-wide telemetry before tests/services.
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi \
    --query-gpu=timestamp,utilization.gpu,utilization.memory,memory.used,memory.total,temperature.gpu,power.draw \
    --format=csv -l 1 > "$SYSTEM_ROOT/gpu-periodic.csv" 2>&1 &
  GPU_MONITOR_PID=$!
fi
if command -v docker >/dev/null 2>&1; then
  docker events --since "$STARTED_UTC" --format '{{json .}}' \
    > "$CONTAINER_ROOT/docker-events.jsonl" 2>&1 &
  DOCKER_EVENTS_PID=$!
fi

# ---------------------------------------------------------------------------
# Phase 1: revision-bound source, unit, typing, policy, and docs gates.
# ---------------------------------------------------------------------------
if (( SKIP_SOURCE == 0 )); then
  source_args=("${PYTHON_CMD[@]}" scripts/run_source_qualification.py
    --output "$RESULT_ROOT/source-qualification.json")
  (( ALLOW_DIRTY == 1 )) && source_args+=(--allow-dirty)
  run_capture source "revision-bound source qualification" "$SOURCE_TIMEOUT_S" "${source_args[@]}"
else
  record_skip source "revision-bound source qualification" "Skipped by --skip-source."
fi

# ---------------------------------------------------------------------------
# Phase 2: benchmark framework and maintained deterministic scenarios.
# ---------------------------------------------------------------------------
if (( SKIP_DETERMINISTIC == 0 )); then
  run_capture deterministic "benchmark unit tests" "$BENCHMARK_TIMEOUT_S" \
    "${PYTHON_CMD[@]}" -m pytest -q benchmarks/tests
  run_capture deterministic "benchmark inventory check" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.inventory.core --check
  run_capture deterministic "benchmark inventory materialization" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.inventory.core \
    --output "$BENCH_ROOT/existing-scenarios.json" \
    --coverage-output "$BENCH_ROOT/inventory-coverage.json"
  run_capture deterministic "normalized scenario check" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.adapters.normalize --check
  run_capture deterministic "normalized scenario materialization" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.adapters.normalize \
    --inventory "$BENCH_ROOT/existing-scenarios.json" \
    --output "$BENCH_ROOT/normalized-scenarios.json"
  run_capture deterministic "scenario migration parity" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.scenarios check \
    --output "$BENCH_ROOT/scenario-migration.json"
  run_capture deterministic "e2e profile contracts" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.e2e.validate --check
  run_capture deterministic "stress workload contracts" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.stress.validate --check
  run_capture deterministic "social attention dataset" 300 \
    "${PYTHON_CMD[@]}" -m benchmarks.datasets.social_attention.validate --check
  mkdir -p "$BENCH_ROOT/behavior-reports"
  run_capture deterministic "all maintained deterministic scenarios" "$BENCHMARK_TIMEOUT_S" \
    "${PYTHON_CMD[@]}" -m benchmarks.scenarios run \
    --report-dir "$BENCH_ROOT/behavior-reports" --json
  run_capture deterministic "provider client fault injection" "$BENCHMARK_TIMEOUT_S" \
    "${PYTHON_CMD[@]}" -m benchmarks.faults run \
    --manifest benchmarks/manifests/fault_injection_v1.json \
    --output "$BENCH_ROOT/fault-injection.json"
else
  record_skip deterministic "benchmark framework and scenarios" "Skipped by --skip-deterministic."
fi

# ---------------------------------------------------------------------------
# Phase 3: build/start maintained services and run service/GPU checks.
# ---------------------------------------------------------------------------
if (( SKIP_SERVICES == 0 )); then
  run_capture services "build runtime environment" "$SERVICE_TIMEOUT_S" ./scripts/build_runtime_env.sh
  run_capture services "build and start services" "$SERVICE_TIMEOUT_S" \
    env BUILD=1 ./scripts/start_services.sh
  SERVICES_STARTED=1

  if [[ -f .env.runtime ]]; then
    write_redacted_env .env.runtime "$SYSTEM_ROOT/env.runtime.redacted"
  fi
  if [[ -f .chromie/runtime_profile.json ]]; then
    cp .chromie/runtime_profile.json "$SYSTEM_ROOT/runtime-profile.json"
  fi

  run_shell_capture services "compose status" 180 "docker compose --env-file .env.runtime -f docker-compose.yml ps"
  run_shell_capture services "compose services and images" 180 "docker compose --env-file .env.runtime -f docker-compose.yml config --services; echo '--- images ---'; docker compose --env-file .env.runtime -f docker-compose.yml config --images"
  run_shell_capture services "container state snapshot" 180 "for id in \$(docker compose --env-file .env.runtime -f docker-compose.yml ps -q); do docker inspect --format '{{json .State}}' \"\$id\"; done"

  run_shell_capture hardware "gpu smoke current contract" "$SERVICE_TIMEOUT_S" \
    "START_SERVICES=0 RUN_TTS_SYNTHESIS=1 RUN_OLLAMA_GENERATE=1 ./scripts/gpu_smoke_test.sh"
  run_capture hardware "verify TTS GPU" "$SERVICE_TIMEOUT_S" ./scripts/verify_tts_gpu.sh
  run_capture hardware "TTS idle benchmark" "$SERVICE_TIMEOUT_S" \
    "${PYTHON_CMD[@]}" scripts/benchmark_tts.py \
    --warmup 1 --repeat "$TTS_REPEAT" --output "$RESULT_ROOT/tts-idle.json"
else
  record_skip services "service and hardware phases" "Skipped by --skip-services."
  SKIP_CLOSED_LOOP=1
  SKIP_SYNTHETIC=1
  SKIP_GPU_LOAD=1
fi

# ---------------------------------------------------------------------------
# Phase 4: bilingual generated-speech closed-loop E2E and review evidence.
# ---------------------------------------------------------------------------
if (( SKIP_CLOSED_LOOP == 0 )); then
  mkdir -p "$E2E_ROOT/closed-loop-idle"
  run_capture e2e "bilingual closed-loop idle" "$E2E_TIMEOUT_S" \
    "${PYTHON_CMD[@]}" scripts/closed_loop_e2e.py \
    --languages "$LANGUAGES" \
    --capture "$CAPTURE_MODE" \
    --output-dir "$E2E_ROOT/closed-loop-idle"
else
  record_skip e2e "bilingual closed-loop idle" "Skipped by option or service phase."
fi

# Preserve the previously maintained synthetic acceptance framework instead of
# replacing it with the new closed-loop runner.
if (( SKIP_SYNTHETIC == 0 )); then
  SYNTH_ID="comprehensive-synthetic-$RUN_ID"
  SYNTH_ROOT="$E2E_ROOT/voice-synthetic"
  synth_args=(env BUILD=0 "${PYTHON_CMD[@]}" scripts/voice_acceptance.py
    --mode synthetic
    --cases speech-only,barge-in,follow-up
    --evidence-root "$SYNTH_ROOT"
    --acceptance-id "$SYNTH_ID"
    --operator "${USER:-automatic}"
    --start-services
    --continue-after-failure)
  (( ALLOW_DIRTY == 1 )) && synth_args+=(--allow-dirty)
  run_capture e2e "retained synthetic voice acceptance" "$E2E_TIMEOUT_S" "${synth_args[@]}"
else
  record_skip e2e "retained synthetic voice acceptance" "Skipped by option or service phase."
fi

# ---------------------------------------------------------------------------
# Phase 5: shared-GPU contention, including a full workflow playback capture.
# ---------------------------------------------------------------------------
if (( SKIP_GPU_LOAD == 0 )); then
  if [[ -f .env.runtime ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env.runtime
    set +a
  fi
  LOAD_MODEL="${AGENT_MODEL:-${AGENT_FAST_PLANNER_MODEL:-qwen3:4b}}"
  LOAD_LOG="$LOG_ROOT/gpu_load-ollama_background.log"
  (
    set -e
    for index in $(seq 1 "$GPU_LOAD_REQUESTS"); do
      curl -fsS http://127.0.0.1:11434/api/generate \
        -H 'Content-Type: application/json' \
        -d "{\"model\":\"$LOAD_MODEL\",\"prompt\":\"Give one concise family scheduling suggestion number $index.\",\"stream\":false,\"options\":{\"num_predict\":256}}" \
        >/dev/null
    done
  ) > "$LOAD_LOG" 2>&1 &
  OLLAMA_LOAD_PID=$!

  run_capture gpu_load "TTS benchmark under shared GPU load" "$SERVICE_TIMEOUT_S" \
    "${PYTHON_CMD[@]}" scripts/benchmark_tts.py \
    --warmup 1 --repeat "$TTS_REPEAT" --output "$RESULT_ROOT/tts-shared-gpu.json"

  if (( SKIP_CLOSED_LOOP == 0 )); then
    mkdir -p "$E2E_ROOT/closed-loop-gpu-load"
    run_capture gpu_load "workflow closed-loop under shared GPU load" "$E2E_TIMEOUT_S" \
      "${PYTHON_CMD[@]}" scripts/closed_loop_e2e.py \
      --languages "$LANGUAGES" \
      --workflow-only \
      --capture "$CAPTURE_MODE" \
      --output-dir "$E2E_ROOT/closed-loop-gpu-load"
  fi

  set +e
  wait "$OLLAMA_LOAD_PID"
  load_code=$?
  OLLAMA_LOAD_PID=""
  load_started="$STARTED_UTC"
  load_completed="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  record_result gpu_load "Ollama background load" "$load_code" "$load_started" "$load_completed" "${LOAD_LOG#$RESULT_ROOT/}"

  python3 - "$RESULT_ROOT/tts-idle.json" "$RESULT_ROOT/tts-shared-gpu.json" "$RESULT_ROOT/tts-comparison.json" <<'PY' || true
import json
from pathlib import Path
import sys

idle_path, load_path, output_path = map(Path, sys.argv[1:])
if not idle_path.exists() or not load_path.exists():
    raise SystemExit(0)
idle = json.loads(idle_path.read_text(encoding="utf-8"))
load = json.loads(load_path.read_text(encoding="utf-8"))
idle_summary = idle.get("summary", {})
load_summary = load.get("summary", {})
keys = (
    "median_first_binary_seconds",
    "median_total_seconds",
    "median_generate_seconds",
    "median_realtime_factor",
    "generation_limit_reached_count",
)
delta = {}
for key in keys:
    a = idle_summary.get(key)
    b = load_summary.get(key)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        delta[key] = round(b - a, 6)
output_path.write_text(
    json.dumps({"idle": idle_summary, "shared_gpu": load_summary, "delta": delta}, indent=2) + "\n",
    encoding="utf-8",
)
PY
else
  record_skip gpu_load "shared-GPU contention" "Skipped by option or service phase."
fi

# ---------------------------------------------------------------------------
# Phase 6: optional independent multi-LLM semantic adjudication.
# ---------------------------------------------------------------------------
if [[ -n "$SEMANTIC_REVIEWERS" ]]; then
  cp "$SEMANTIC_REVIEWERS" "$SYSTEM_ROOT/semantic-reviewers.json"
  sha256sum "$SYSTEM_ROOT/semantic-reviewers.json" \
    > "$SYSTEM_ROOT/semantic-reviewers.json.sha256"
  review_bundle_count=0
  while IFS= read -r review_bundle; do
    [[ -n "$review_bundle" ]] || continue
    review_bundle_count=$((review_bundle_count + 1))
    review_name="$(safe_name "$(basename "$(dirname "$review_bundle")")")"
    review_output="$RESULT_ROOT/semantic-judgments/$review_name"
    judge_args=("${PYTHON_CMD[@]}" -m benchmarks.review judge
      --bundle "$review_bundle"
      --reviewers "$SEMANTIC_REVIEWERS"
      --output-dir "$review_output")
    for reviewer_id in "${SEMANTIC_REVIEWER_IDS[@]}"; do
      judge_args+=(--reviewer "$reviewer_id")
    done
    run_capture semantic_review "multi-LLM review $review_name" "$E2E_TIMEOUT_S" \
      "${judge_args[@]}"
  done < <(find "$E2E_ROOT" -type f -name 'semantic-review-bundle.json' -print | sort)
  if (( review_bundle_count == 0 )); then
    record_skip semantic_review "multi-LLM semantic adjudication" \
      "No semantic-review-bundle.json was produced by the selected E2E phases."
  fi
else
  record_skip semantic_review "multi-LLM semantic adjudication" \
    "No --semantic-reviewers configuration was supplied; retained bundles remain available for manual review."
fi

# ---------------------------------------------------------------------------
# Phase 7: complete correlated process/container evidence for this run window.
# ---------------------------------------------------------------------------
run_shell_capture collection "final process snapshot" 120 "ps -eo pid,ppid,etimes,%cpu,%mem,stat,comm,args --sort=-%cpu | head -300"
run_shell_capture collection "final GPU snapshot" 120 "nvidia-smi || true"
if command -v docker >/dev/null 2>&1 && [[ -f .env.runtime ]]; then
  run_shell_capture collection "final compose status" 180 "docker compose --env-file .env.runtime -f docker-compose.yml ps"
  run_shell_capture collection "Docker stats" 180 "docker stats --no-stream --no-trunc || true"
else
  record_skip collection "final compose status" "Docker or .env.runtime is unavailable."
  record_skip collection "Docker stats" "Docker or .env.runtime is unavailable."
fi

if command -v docker >/dev/null 2>&1 && [[ -f .env.runtime ]]; then
  docker compose --env-file .env.runtime -f docker-compose.yml logs \
    --no-color --timestamps --since "$DOCKER_LOG_SINCE" \
    > "$CONTAINER_ROOT/compose-all.log" 2>&1
  compose_log_code=$?
  record_result collection "all Compose logs" "$compose_log_code" "$STARTED_UTC" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "containers/compose-all.log"

  docker compose --env-file .env.runtime -f docker-compose.yml config --services \
    > "$CONTAINER_ROOT/services.txt" 2>/dev/null || true
  while IFS= read -r service; do
    [[ -n "$service" ]] || continue
    safe_service="$(safe_name "$service")"
    docker compose --env-file .env.runtime -f docker-compose.yml logs \
      --no-color --timestamps --since "$DOCKER_LOG_SINCE" "$service" \
      > "$CONTAINER_ROOT/$safe_service.log" 2>&1 || true
  done < "$CONTAINER_ROOT/services.txt"

  : > "$CONTAINER_ROOT/container-states.jsonl"
  while IFS= read -r container_id; do
    [[ -n "$container_id" ]] || continue
    docker inspect --format '{{json .State}}' "$container_id" \
      >> "$CONTAINER_ROOT/container-states.jsonl" 2>/dev/null || true
  done < <(docker compose --env-file .env.runtime -f docker-compose.yml ps -q 2>/dev/null)
fi

if [[ -n "$GPU_MONITOR_PID" ]]; then
  kill "$GPU_MONITOR_PID" 2>/dev/null || true
  wait "$GPU_MONITOR_PID" 2>/dev/null || true
  GPU_MONITOR_PID=""
fi
if [[ -n "$DOCKER_EVENTS_PID" ]]; then
  kill "$DOCKER_EVENTS_PID" 2>/dev/null || true
  wait "$DOCKER_EVENTS_PID" 2>/dev/null || true
  DOCKER_EVENTS_PID=""
fi

if (( STOP_SERVICES == 1 && SERVICES_STARTED == 1 )); then
  run_shell_capture services "stop services" 600 "docker compose --env-file .env.runtime -f docker-compose.yml down"
fi

COMPLETED_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat > "$RESULT_ROOT/UPLOAD_ME.txt" <<EOF
Chromie comprehensive qualification evidence

Run ID:        $RUN_ID
Revision:      $REVISION
Started UTC:   $STARTED_UTC
Completed UTC: $COMPLETED_UTC
Capture mode:  $CAPTURE_MODE
Languages:     $LANGUAGES

This bundle contains deterministic test truth, generated-speech closed-loop
evidence, semantic-review inputs, host program logs, Docker logs, GPU telemetry,
audio captures, ASR transcripts, and source/runtime identity.

No operator voice or pronunciation judgment was used.

Review the complete archive with one model or use --semantic-reviewers to run
independent API judges. Semantic-review scenarios must be judged from retained
evidence; deterministic failures remain failures and cannot be overridden by
semantic review or consensus.

Privacy: review the archive before uploading. ASR, conversation, and container
logs may contain private content. Secret-like values from .env.runtime are
redacted, but arbitrary program logs cannot be guaranteed secret-free.
EOF

# Convert the append-only check ledger into a machine-readable collection report.
SEMANTIC_REVIEWERS_ENABLED=0
[[ -n "$SEMANTIC_REVIEWERS" ]] && SEMANTIC_REVIEWERS_ENABLED=1

python3 - "$RESULT_ROOT" "$REVISION" "$STARTED_UTC" "$COMPLETED_UTC" "$CAPTURE_MODE" "$LANGUAGES" "$ALLOW_DIRTY" "$SCRIPT_VERSION" "$COLLECT_ONLY" "$STRICT_EXIT" "$SEMANTIC_REVIEWERS_ENABLED" <<'PY'
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
revision, started, completed, capture, languages = sys.argv[2:7]
allow_dirty = sys.argv[7] == "1"
script_version = sys.argv[8]
collect_only = sys.argv[9] == "1"
strict_exit = sys.argv[10] == "1"
semantic_reviewers_enabled = sys.argv[11] == "1"
checks = []
with (root / "checks.tsv").open(encoding="utf-8", newline="") as handle:
    for row in csv.DictReader(handle, delimiter="\t"):
        try:
            row["exit_code"] = int(row["exit_code"])
        except (TypeError, ValueError):
            pass
        checks.append(row)
counts = {status: sum(1 for row in checks if row["status"] == status) for status in ("PASS", "FAIL", "TIMEOUT", "SKIP")}
closed_loop = []
for summary_path in sorted((root / "e2e").glob("**/summary.json")):
    try:
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
    except Exception as exc:
        closed_loop.append({"path": str(summary_path.relative_to(root)), "parse_error": str(exc)})
        continue
    closed_loop.append(
        {
            "path": str(summary_path.relative_to(root)),
            "collection_succeeded": payload.get("collection_succeeded"),
            "mechanical_passed": payload.get("mechanical_passed"),
            "semantic_review_pending": payload.get("semantic_review_pending"),
            "transport": payload.get("transport_summary"),
            "workflow": payload.get("workflow_summary"),
        }
    )
semantic_judgments = []
for judge_path in sorted((root / "semantic-judgments").glob("**/judge-report.json")):
    try:
        payload = json.loads(judge_path.read_text(encoding="utf-8"))
    except Exception as exc:
        semantic_judgments.append(
            {"path": str(judge_path.relative_to(root)), "parse_error": str(exc)}
        )
        continue
    semantic_judgments.append(
        {
            "path": str(judge_path.relative_to(root)),
            "complete": payload.get("complete"),
            "selected_reviewers": payload.get("selected_reviewers"),
            "reviewers": payload.get("reviewers"),
            "consensus": payload.get("consensus"),
        }
    )
hard_failure = counts["FAIL"] > 0 or counts["TIMEOUT"] > 0
closed_loop_failure = any(
    bool(item.get("parse_error")) or item.get("mechanical_passed") is False
    for item in closed_loop
)
semantic_pending = any(
    item.get("semantic_review_pending") is True for item in closed_loop
)
review_infrastructure_failed = any(
    bool(item.get("parse_error")) or item.get("complete") is False
    for item in semantic_judgments
)
semantic_review_complete = (
    not semantic_pending
    or (
        semantic_reviewers_enabled
        and bool(semantic_judgments)
        and not review_infrastructure_failed
        and all(item.get("complete") is True for item in semantic_judgments)
    )
)
if collect_only:
    overall_status = "collection_only"
elif hard_failure or closed_loop_failure:
    overall_status = "failed"
elif allow_dirty or counts["SKIP"] > 0 or not semantic_review_complete:
    overall_status = "incomplete"
else:
    overall_status = "passed"

report = {
    "schema_version": 2,
    "runner": "scripts/qualification/run_comprehensive_test.sh",
    "runner_version": script_version,
    "revision": revision,
    "started_utc": started,
    "completed_utc": completed,
    "capture_mode": capture,
    "languages": [item.strip() for item in languages.split(",") if item.strip()],
    "human_voice_required": False,
    "operator_pronunciation_graded": False,
    "allow_dirty": allow_dirty,
    "collect_only": collect_only,
    "strict_exit": strict_exit,
    "overall_status": overall_status,
    "semantic_review_complete": semantic_review_complete,
    "review_infrastructure_failed": review_infrastructure_failed,
    "counts": counts,
    "checks": checks,
    "closed_loop_runs": closed_loop,
    "semantic_judgments": semantic_judgments,
    "semantic_truth_source": "configured_multi_llm_ensemble_or_external_llm_or_human_review",
    "deterministic_truth_source": "declared_fixtures_contracts_and_invariants",
    "release_qualified": False,
}
(root / "collection-report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

# Hash every retained artifact except the index itself. This makes partial or
# accidentally modified uploads visible during later analysis.
records = []
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.name == "artifact-index.json":
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    records.append(
        {
            "path": str(path.relative_to(root)),
            "size": path.stat().st_size,
            "sha256": digest.hexdigest(),
        }
    )
(root / "artifact-index.json").write_text(
    json.dumps({"schema_version": 1, "artifacts": records}, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

PASS_COUNT="$(awk -F '\t' 'NR>1 && $3=="PASS" {n++} END {print n+0}' "$CHECKS_TSV")"
FAIL_COUNT="$(awk -F '\t' 'NR>1 && $3=="FAIL" {n++} END {print n+0}' "$CHECKS_TSV")"
TIMEOUT_COUNT="$(awk -F '\t' 'NR>1 && $3=="TIMEOUT" {n++} END {print n+0}' "$CHECKS_TSV")"
SKIP_COUNT="$(awk -F '\t' 'NR>1 && $3=="SKIP" {n++} END {print n+0}' "$CHECKS_TSV")"

ARCHIVE="$DOWNLOAD_DIR/chromie-comprehensive-$REV_SHORT-$RUN_ID.tar.gz"
tar -czf "$ARCHIVE" -C "$REPO_DIR" "$RESULT_REL"
sha256sum "$ARCHIVE" | tee "$ARCHIVE.sha256"

SANITIZED_ARCHIVE=""
SANITIZE_STATUS=0
if (( SANITIZE_ARCHIVE == 1 )); then
  SANITIZED_ARCHIVE="$DOWNLOAD_DIR/chromie-comprehensive-$REV_SHORT-$RUN_ID-sanitized.tar.gz"
  sanitize_args=("${PYTHON_CMD[@]}" -m benchmarks.evidence sanitize
    --input "$RESULT_ROOT"
    --output "$SANITIZED_ARCHIVE")
  (( SANITIZE_EXCLUDE_AUDIO == 1 )) && sanitize_args+=(--exclude-audio)
  "${sanitize_args[@]}" > "$RESULT_ROOT/logs/evidence-sanitization.log" 2>&1 || SANITIZE_STATUS=$?
fi

trap - EXIT INT TERM
cleanup_background

echo
echo "========================================================================"
echo "Chromie comprehensive collection complete"
echo "  Revision:       $REVISION"
echo "  Passed checks:  $PASS_COUNT"
echo "  Failed checks:  $FAIL_COUNT"
echo "  Timed out:      $TIMEOUT_COUNT"
echo "  Skipped:        $SKIP_COUNT"
echo "  Evidence root:  $RESULT_ROOT"
echo "  Archive:        $ARCHIVE"
echo "  Checksum:       $ARCHIVE.sha256"
if [[ -n "$SANITIZED_ARCHIVE" ]]; then
  echo "  Sanitized:      $SANITIZED_ARCHIVE"
  echo "  Sanitized sum:  $SANITIZED_ARCHIVE.sha256"
  echo "  Sanitize exit:  $SANITIZE_STATUS"
fi
echo "========================================================================"
OVERALL_STATUS="$(python3 - "$RESULT_ROOT/collection-report.json" <<'PY_STATUS'
import json
from pathlib import Path
import sys
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["overall_status"])
PY_STATUS
)"

echo "  Overall status: $OVERALL_STATUS"
if (( STRICT_EXIT == 1 )) && { [[ "$OVERALL_STATUS" != "passed" ]] || (( SANITIZE_STATUS != 0 )); }; then
  echo "The archive was retained, but strict mode is failing this run." >&2
  exit 1
fi

echo "The archive was retained. Fail-soft mode does not convert failed checks into a pass."
exit 0
