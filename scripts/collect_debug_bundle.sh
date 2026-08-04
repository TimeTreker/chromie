#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="$ROOT/.chromie/debug/debug_bundle_$STAMP"
DOWNLOADS="$HOME/Downloads"
ARCHIVE="$DOWNLOADS/chromie_debug_bundle_$STAMP.tar.gz"

mkdir -p "$WORK" "$DOWNLOADS"
cd "$ROOT"

copy_tail() {
  local source="$1"
  local destination="$2"
  local lines="${3:-5000}"
  if [[ -f "$source" ]]; then
    tail -n "$lines" "$source" > "$WORK/$destination"
  fi
}

safe_filename() {
  printf '%s' "$1" | tr -c '[:alnum:]_.-' '_'
}

collect_container_diagnostics() {
  local container="$1"
  local prefix
  prefix="$(safe_filename "$container")"

  docker logs --timestamps --tail=5000 "$container" \
    > "$WORK/${prefix}.docker.log" 2>&1 || true
  docker inspect --format 'Name={{.Name}}
Id={{.Id}}
Image={{.Config.Image}}
Created={{.Created}}
Status={{.State.Status}}
Running={{.State.Running}}
ExitCode={{.State.ExitCode}}
Error={{.State.Error}}
StartedAt={{.State.StartedAt}}
FinishedAt={{.State.FinishedAt}}
RestartCount={{.RestartCount}}
Health={{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}
ComposeProject={{with .Config.Labels}}{{index . "com.docker.compose.project"}}{{end}}
ComposeService={{with .Config.Labels}}{{index . "com.docker.compose.service"}}{{end}}
ComposeWorkingDir={{with .Config.Labels}}{{index . "com.docker.compose.project.working_dir"}}{{end}}' \
    "$container" > "$WORK/${prefix}.docker.inspect.txt" 2>&1 || true
  docker port "$container" > "$WORK/${prefix}.docker.ports.txt" 2>&1 || true
}

collect_soridormi_docker_logs() {
  local containers="$WORK/soridormi_docker_containers.txt"

  {
    docker ps -a --filter name=soridormi --format '{{.Names}}' 2>/dev/null || true
    if docker inspect soridormi-runtime-mcp >/dev/null 2>&1; then
      printf '%s\n' soridormi-runtime-mcp
    fi
  } | awk 'NF && !seen[$0]++' > "$containers"

  if [[ ! -s "$containers" ]]; then
    printf '%s\n' \
      'No Soridormi Docker container was found. The paired launcher log may still be available.' \
      > "$containers"
    return 0
  fi

  while IFS= read -r container; do
    [[ -n "$container" ]] || continue
    collect_container_diagnostics "$container"
  done < "$containers"
}

sanitize_env() {
  local source="$1"
  local destination="$2"
  [[ -f "$source" ]] || return 0
  python - "$source" "$WORK/$destination" <<'PY'
from pathlib import Path
import re
import sys

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
sensitive = re.compile(
    r"(?:TOKEN|SECRET|PASSWORD|PASSWD|API[_-]?KEY|AUTH|COOKIE|CREDENTIAL|PRIVATE[_-]?KEY|ACCESS[_-]?KEY)",
    re.IGNORECASE,
)
lines = []
for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
    stripped = raw.strip()
    prefix = ""
    candidate = stripped
    if candidate.startswith("export "):
        prefix = "export "
        candidate = candidate[7:].lstrip()
    if "=" not in candidate or candidate.startswith("#"):
        lines.append(raw)
        continue
    key, value = candidate.split("=", 1)
    if sensitive.search(key):
        lines.append(f"{prefix}{key}=<redacted>")
    else:
        lines.append(raw)
destination.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
}

git rev-parse HEAD > "$WORK/git_commit.txt" 2>/dev/null || true
git status --short > "$WORK/git_status.txt" 2>/dev/null || true
git log -n 20 --oneline > "$WORK/git_log.txt" 2>/dev/null || true
python --version > "$WORK/python.txt" 2>&1 || true

cp .chromie/runtime_profile.json "$WORK/runtime_profile.json" 2>/dev/null || true
sanitize_env .env env.redacted.txt
sanitize_env .env.runtime env.runtime.redacted.txt
sanitize_env .chromie/voice-runtime/orchestrator.env orchestrator.env.redacted.txt
sanitize_env .chromie/voice-mujoco/run.env voice_mujoco_run.env.redacted.txt

copy_tail .chromie/experience/episodes.jsonl episodes.tail.jsonl 200
copy_tail .chromie/experience/experience.jsonl experience.tail.jsonl 500
copy_tail .chromie/experience/mind_update_proposals.jsonl mind_update_proposals.tail.jsonl 200
copy_tail .chromie/evidence/cognitive-runtime/events.jsonl cognitive_runtime_events.tail.jsonl 1000
copy_tail .chromie/voice-runtime/orchestrator-events.jsonl orchestrator_events.tail.jsonl 1000
copy_tail .chromie/voice-mujoco/logs/orchestrator-events.jsonl voice_mujoco_orchestrator_events.tail.jsonl 1000
copy_tail .chromie/voice-mujoco/logs/chromie.log chromie-launcher.log 5000
copy_tail .chromie/voice-mujoco/logs/soridormi.log soridormi-launcher.log 5000
copy_tail .chromie/voice-mujoco/logs/soridormi-runtime-mcp.compose.log soridormi-runtime-mcp.compose.previous.log 5000

docker compose ps > "$WORK/docker_ps.txt" 2>&1 || true
docker compose config --services > "$WORK/docker_services.txt" 2>&1 || true
docker compose logs --tail=5000 > "$WORK/docker_compose.log" 2>&1 || true
docker compose logs chromie-agent --tail=5000 > "$WORK/chromie-agent.log" 2>&1 || true
docker compose ls --all > "$WORK/docker_compose_projects.txt" 2>&1 || true
docker ps -a --no-trunc \
  --format 'table {{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Labels}}' \
  > "$WORK/docker_containers.txt" 2>&1 || true
collect_soridormi_docker_logs

ps -ef > "$WORK/processes.txt" 2>&1 || true
ss -ltnp > "$WORK/listening_ports.txt" 2>&1 || true
curl -fsS http://127.0.0.1:8092/health > "$WORK/agent_health.json" 2>/dev/null || true
curl -fsS http://127.0.0.1:8092/openapi.json > "$WORK/openapi.json" 2>/dev/null || true

{
  for file in \
    "$WORK/chromie-agent.log" \
    "$WORK/docker_compose.log" \
    "$WORK/cognitive_runtime_events.tail.jsonl" \
    "$WORK/episodes.tail.jsonl" \
    "$WORK/soridormi-launcher.log" \
    "$WORK"/soridormi-*.docker.log \
    "$WORK"/soridormi-*.compose*.log; do
    [[ -f "$file" ]] || continue
    grep -Ei "goal|continuity|association|planner|missing_ability|capability|soridormi|mcp|motion|provider" "$file" || true
  done
} > "$WORK/cognitive_trace.txt"

cat > "$WORK/README.txt" <<EOF2
Chromie debug bundle
Created: $(date --iso-8601=seconds 2>/dev/null || date)
Git commit: $(git rev-parse HEAD 2>/dev/null || echo unknown)

Collect this bundle immediately after reproducing the problem while services are
still running. Environment files are included only in redacted form.

When the paired voice-to-MuJoCo launcher has been used, this bundle also includes
its Chromie and Soridormi launcher logs. Fresh Docker logs, state, and published
ports are collected for every container whose name contains "soridormi",
including stopped containers retained by Docker.
EOF2

tar -czf "$ARCHIVE" -C "$(dirname "$WORK")" "$(basename "$WORK")"
printf 'Debug bundle created:\n%s\n' "$ARCHIVE"
