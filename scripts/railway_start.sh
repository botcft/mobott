#!/usr/bin/env bash
# Railway (and similar) often run only `uvicorn main:app`, which starts the web dashboard
# but does NOT poll Telegram. This repo's conversational bot lives in `main.py` (polling).
set -euo pipefail
PORT="${PORT:-8080}"

if [ "${DISABLE_MO_BOT:-0}" != "1" ]; then
  echo "Starting Telegram bot poller (python main.py) in background..." >&2
  python main.py &
fi

exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
