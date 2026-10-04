set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 ACTION [--tab N] [TEXT]" >&2
  exit 2
fi

ACTION="$1"
shift
TAB=""
if [[ "${1:-}" == "--tab" ]]; then
  TAB="${2:-}"
  if [[ -z "$TAB" ]]; then
    echo "--tab requires a number" >&2
    exit 2
  fi
  shift 2
fi

TEXT="${1:-}"

PAYLOAD=$(python3 - "$ACTION" "$TAB" "$TEXT" <<'PY'
import json
import sys

action, tab, text = sys.argv[1], sys.argv[2], sys.argv[3]
payload = {"action": action, "text": text}
if tab:
    payload["tab"] = int(tab)
print(json.dumps(payload, ensure_ascii=False))
PY
)

RESPONSE=$(curl -fsS -X POST http://127.0.0.1:8765/command   -H 'Content-Type: application/json'   -d "$PAYLOAD")

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
