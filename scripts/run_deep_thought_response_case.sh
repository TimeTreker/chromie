#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MCP_URL="${SORIDORMI_MCP_URL:-http://127.0.0.1:${SORIDORMI_MCP_PORT:-8000}${SORIDORMI_MCP_PATH:-/mcp}}"
SPEAKER_FLAG=--no-speaker
TIMEOUT_S="${CHROMIE_DEEP_THOUGHT_TIMEOUT_S:-120}"
REQUIRE_BODY_CUE=--require-body-cue
REQUIRE_BODY_CUE_COMPLETED=--require-body-cue-completed
REQUIRE_AGENT_SUCCESS=--require-agent-success
MIN_SCHEDULED_TTS="${CHROMIE_DEEP_THOUGHT_MIN_TTS:-2}"
EVIDENCE_DIR=()
TEXT=""

usage() {
  cat <<'USAGE'
Usage: ./scripts/run_deep_thought_response_case.sh [options] ["text request"]

Run a no-microphone deep_thought response scenario against an already-started
Chromie + Soridormi/MuJoCo stack.

Default scenario:
  User asks a complicated planning request.
  Chromie routes deep_thought.
  Chromie says a short "let me think" acknowledgement.
  Chromie launches the simulator-safe thinking pose.
  The deepthinking Agent returns a final spoken response.

Examples:
  ./scripts/start_voice_mujoco.sh --build
  ./scripts/run_deep_thought_response_case.sh
  ./scripts/run_deep_thought_response_case.sh --speaker "请认真思考一下，帮我拆分实现 social.look_at_user 能力的任务：路由触发、能力注册表映射、Soridormi 技能绑定和测试。"

Options:
  --mcp-url URL                     Soridormi MCP URL; default: http://127.0.0.1:8000/mcp
  --speaker                         Play Chromie TTS through configured speaker
  --no-speaker                      Headless check without speaker playback; default
  --timeout-s SECONDS               Wait timeout; default: 120
  --evidence-dir DIR                Write evidence into this directory
  --no-require-body-cue             Do not fail if thinking pose is not launched
  --no-require-body-cue-completed   Do not fail if thinking pose does not complete
  --no-require-agent-success        Allow direct-LLM fallback if Agent is stale/down
  --min-scheduled-tts N             Minimum scheduled TTS items; default: 2
  -h, --help                        Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mcp-url) MCP_URL="${2:?--mcp-url requires a URL}"; shift 2 ;;
    --speaker) SPEAKER_FLAG=--speaker; shift ;;
    --no-speaker) SPEAKER_FLAG=--no-speaker; shift ;;
    --timeout-s) TIMEOUT_S="${2:?--timeout-s requires seconds}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR=(--evidence-dir "${2:?--evidence-dir requires a directory}"); shift 2 ;;
    --no-require-body-cue) REQUIRE_BODY_CUE=--no-require-body-cue; shift ;;
    --no-require-body-cue-completed) REQUIRE_BODY_CUE_COMPLETED=--no-require-body-cue-completed; shift ;;
    --no-require-agent-success) REQUIRE_AGENT_SUCCESS=--no-require-agent-success; shift ;;
    --min-scheduled-tts) MIN_SCHEDULED_TTS="${2:?--min-scheduled-tts requires an integer}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [ -z "$TEXT" ]; then
        TEXT="$1"
        shift
      else
        echo "[deep-thought-response][error] Multiple text requests supplied." >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

PYTHON_BIN="${CHROMIE_PYTHON:-}"
if [ -z "$PYTHON_BIN" ]; then
  CONDA_ENV_NAME="${CONDA_ENV_NAME:-${CHROMIE_CONDA_ENV:-Chromie}}"
  if command -v conda >/dev/null 2>&1; then
    CONDA_BASE="$(conda info --base)"
  elif [ -x "$HOME/miniconda3/bin/conda" ]; then
    CONDA_BASE="$HOME/miniconda3"
  elif [ -x "$HOME/anaconda3/bin/conda" ]; then
    CONDA_BASE="$HOME/anaconda3"
  else
    echo "[deep-thought-response][error] conda not found; set CHROMIE_PYTHON to a Python with orchestrator dependencies." >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source "$CONDA_BASE/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV_NAME"
  PYTHON_BIN="$(command -v python)"
fi

args=(
  --soridormi-mcp-url "$MCP_URL"
  "$SPEAKER_FLAG"
  --timeout-s "$TIMEOUT_S"
  "$REQUIRE_BODY_CUE"
  "$REQUIRE_BODY_CUE_COMPLETED"
  "$REQUIRE_AGENT_SUCCESS"
  --min-scheduled-tts "$MIN_SCHEDULED_TTS"
  "${EVIDENCE_DIR[@]}"
)
if [ -n "$TEXT" ]; then
  args+=("$TEXT")
fi

"$PYTHON_BIN" scripts/deep_thought_response_check.py "${args[@]}"
