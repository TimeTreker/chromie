#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="${CHROMIE_VOICE_MUJOCO_STATE_DIR:-$ROOT_DIR/.chromie/voice-mujoco}"
EVIDENCE_ROOT="$STATE_DIR/text-cases"
MCP_URL="${SORIDORMI_MCP_URL:-http://127.0.0.1:${SORIDORMI_MCP_PORT:-8000}${SORIDORMI_MCP_PATH:-/mcp}}"
SPEAKER_FLAG=--speaker
PREVIEW_ONLY=0
AUTO_CONFIRM=1
SKILL_TIMEOUT_S="${CHROMIE_VOICE_MUJOCO_SKILL_TIMEOUT_S:-120}"
EXPECT_ROUTE=()
EXPECT_NO_SKILLS=()
EXPECT_SKILL=()
EXPECT_ARGS=()
TEXT=""

usage() {
  cat <<'USAGE'
Usage: ./scripts/run_voice_mujoco_text_case.sh [options] "text request"

Run a no-microphone text -> Chromie -> Soridormi/MuJoCo diagnostic case
against an already-started voice-MuJoCo stack.

Examples:
  ./scripts/run_voice_mujoco_text_case.sh "Please walk forward for ten seconds." --no-speaker
  ./scripts/run_voice_mujoco_text_case.sh "Please blink your eyes." --speaker

Regression assertion example:
  ./scripts/run_voice_mujoco_text_case.sh "Please nod twice." --speaker
  ./scripts/run_voice_mujoco_text_case.sh "Please nod twice." --no-speaker --expect-skill soridormi.nod_yes

Options:
  --mcp-url URL              Soridormi MCP URL; default: http://127.0.0.1:8000/mcp
  --speaker                  Play Chromie TTS through configured speaker; default
  --no-speaker               Headless check without speaker playback
  --preview-only             Route and validate without executing Soridormi skills
  --no-auto-confirm-sim      Do not auto-confirm simulator skills
  --skill-timeout-s SECONDS  Per-Soridormi-skill timeout; default: 120
  --expect-route ROUTE       Post-run assertion for Router route: chat, deep_thought,
                             robot_action, tool, memory, clarify, interrupt,
                             or ignore
  --expect-no-skills         Post-run assertion for no Soridormi skill emission
  --expect-skill SKILL_ID    Post-run assertion for the exact planned skill sequence
  --expect-arg I:KEY=VALUE   Post-run assertion for an emitted skill argument
  -h, --help                 Show this help
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --mcp-url) MCP_URL="${2:?--mcp-url requires a URL}"; shift 2 ;;
    --speaker) SPEAKER_FLAG=--speaker; shift ;;
    --no-speaker) SPEAKER_FLAG=--no-speaker; shift ;;
    --preview-only) PREVIEW_ONLY=1; shift ;;
    --no-auto-confirm-sim) AUTO_CONFIRM=0; shift ;;
    --skill-timeout-s) SKILL_TIMEOUT_S="${2:?--skill-timeout-s requires seconds}"; shift 2 ;;
    --expect-route) EXPECT_ROUTE+=(--expect-route "${2:?--expect-route requires a route}"); shift 2 ;;
    --expect-no-skills) EXPECT_NO_SKILLS+=(--expect-no-skills); shift ;;
    --expect-skill) EXPECT_SKILL+=(--expect-skill "${2:?--expect-skill requires a skill id}"); shift 2 ;;
    --expect-arg) EXPECT_ARGS+=(--expect-arg "${2:?--expect-arg requires I:KEY=VALUE}"); shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *)
      if [ -z "$TEXT" ]; then
        TEXT="$1"
        shift
      else
        echo "[voice-mujoco-text][error] Multiple text requests supplied." >&2
        usage >&2
        exit 2
      fi
      ;;
  esac
done

if [ -z "$TEXT" ]; then
  echo "[voice-mujoco-text][error] Text request is required." >&2
  usage >&2
  exit 2
fi

if [ "${#EXPECT_ROUTE[@]}" -eq 0 ] \
  && [ "${#EXPECT_NO_SKILLS[@]}" -eq 0 ] \
  && [ "${#EXPECT_SKILL[@]}" -eq 0 ] \
  && [ "${#EXPECT_ARGS[@]}" -eq 0 ]; then
  echo "[voice-mujoco-text] Natural input mode: no --expect-* assertions supplied; Chromie will infer route and skills from the text." >&2
else
  echo "[voice-mujoco-text] Assertion mode: --expect-* flags validate the output after Chromie has already planned from the text." >&2
fi

mkdir -p "$EVIDENCE_ROOT"

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
    echo "[voice-mujoco-text][error] conda not found; set CHROMIE_PYTHON to a Python with orchestrator dependencies." >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  source "$CONDA_BASE/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV_NAME"
  PYTHON_BIN="$(command -v python)"
fi

args=(
  --soridormi-mcp-url "$MCP_URL"
  --manifest capabilities/soridormi.json
  "$SPEAKER_FLAG"
  --require-speech
  --skill-timeout-s "$SKILL_TIMEOUT_S"
)
if [ "$PREVIEW_ONLY" = "1" ]; then args+=(--preview-only); fi
if [ "$AUTO_CONFIRM" = "1" ]; then
  args+=(--auto-confirm-sim)
else
  args+=(--no-auto-confirm-sim)
fi
args+=("${EXPECT_ROUTE[@]}" "${EXPECT_NO_SKILLS[@]}" "${EXPECT_SKILL[@]}" "${EXPECT_ARGS[@]}" "$TEXT")

"$PYTHON_BIN" scripts/interaction_text_mujoco_check.py "${args[@]}"
