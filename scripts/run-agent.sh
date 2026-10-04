#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/run"
if [[ -f "$ROOT/run/browser-agent.pid" ]] && kill -0 "$(cat "$ROOT/run/browser-agent.pid")" 2>/dev/null; then
  echo "browser-agent already running: PID $(cat "$ROOT/run/browser-agent.pid")"
  exit 0
fi
nohup python3 -m browser_agent.server >"$ROOT/run/browser-agent.log" 2>&1 &
echo $! >"$ROOT/run/browser-agent.pid"
sleep 0.5
curl -fsS http://127.0.0.1:8765/health
echo
echo "Browser agent started."
echo "Load extension: $ROOT/browser_extension/manifest.json"
