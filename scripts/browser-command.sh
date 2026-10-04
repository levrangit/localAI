#!/usr/bin/env bash
set -euo pipefail
if [[ $# -lt 1 ]]; then
  echo "usage: $0 ACTION [TEXT]" >&2
  exit 2
fi
ACTION="$1"
TEXT="${2:-}"
PAYLOAD=$(python3 - "$ACTION" "$TEXT" <<'PY'
import json, sys
print(json.dumps({"action": sys.argv[1], "text": sys.argv[2]}, ensure_ascii=False))
PY
)
RESPONSE=$(curl -fsS -X POST http://127.0.0.1:8765/command -H 'Content-Type: application/json' -d "$PAYLOAD")
ID=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$RESPONSE")
for _ in $(seq 1 100); do
  RESULT=$(curl -sS "http://127.0.0.1:8765/result/$ID" || true)
  if [[ "$RESULT" != *"result_not_ready"* ]]; then
    printf '%s\n' "$RESULT"
    exit 0
  fi
  sleep 0.1
done
echo '{"ok":false,"error":"timeout"}'
exit 1
