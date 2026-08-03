#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
WORK="$ROOT/.chromie/debug/debug_bundle_$STAMP"
ARCHIVE="$HOME/Downloads/chromie_debug_bundle_$STAMP.tar.gz"

mkdir -p "$WORK"

cd "$ROOT"

git rev-parse HEAD > "$WORK/git_commit.txt" 2>/dev/null || true
git status --short > "$WORK/git_status.txt" 2>/dev/null || true

cp .chromie/runtime_profile.json "$WORK/" 2>/dev/null || true
cp .env "$WORK/env.txt" 2>/dev/null || true
cp .env.runtime "$WORK/env.runtime.txt" 2>/dev/null || true
cp .chromie/experience/episodes.jsonl "$WORK/episodes.jsonl" 2>/dev/null || true

docker compose ps > "$WORK/docker_ps.txt" 2>&1 || true
docker compose logs --tail=5000 > "$WORK/docker_compose.log" 2>&1 || true
docker compose logs chromie-agent --tail=5000 > "$WORK/chromie-agent.log" 2>&1 || true
docker compose logs chromie-orchestrator --tail=5000 > "$WORK/orchestrator.log" 2>&1 || true

python --version > "$WORK/python.txt" 2>&1 || true

curl -s http://127.0.0.1:8092/health > "$WORK/agent_health.json" || true
curl -s http://127.0.0.1:8092/openapi.json > "$WORK/openapi.json" || true

grep -R \
  -e "goal" \
  -e "continuity" \
  -e "association" \
  -e "planner" \
  -e "missing_ability" \
  -e "capability" \
  .chromie \
  > "$WORK/cognitive_keywords.log" 2>/dev/null || true

tar czf "$ARCHIVE" -C "$(dirname "$WORK")" "$(basename "$WORK")"

echo "Debug bundle created:"
echo "$ARCHIVE"
