#!/usr/bin/env bash
# start.sh — CourtIQ local development launcher
# Usage: bash start.sh  (run from the project root)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/backend"
FRONTEND="$SCRIPT_DIR/frontend"

# Kill Flask on exit (Ctrl+C or error)
cleanup() {
  echo ""
  echo "[CourtIQ] Shutting down..."
  if [ -n "$FLASK_PID" ]; then
    kill "$FLASK_PID" 2>/dev/null && echo "[CourtIQ] Flask stopped."
  fi
}
trap cleanup EXIT

# ── 1. Activate venv (create it first if missing) ──────────────
if [ ! -f "$SCRIPT_DIR/venv/Scripts/python" ] && [ ! -f "$SCRIPT_DIR/venv/bin/python" ]; then
  echo "[CourtIQ] No venv found — running setup-venv.sh first..."
  bash "$SCRIPT_DIR/setup-venv.sh"
fi

# Windows Git Bash uses Scripts/, Linux uses bin/
if [ -f "$SCRIPT_DIR/venv/Scripts/python" ]; then
  PYTHON="$SCRIPT_DIR/venv/Scripts/python"
else
  PYTHON="$SCRIPT_DIR/venv/bin/python"
fi

# ── 2. Start Flask API ──────────────────────────────────────────
FLASK_PORT="${FLASK_PORT:-5050}"
export FLASK_PORT
export FLASK_API_URL="${FLASK_API_URL:-http://localhost:$FLASK_PORT}"

echo "[CourtIQ] Starting Flask API (port $FLASK_PORT)..."
cd "$BACKEND"
"$PYTHON" flask_api.py &
FLASK_PID=$!

# Wait until Flask answers (it downloads game logs and trains first).
# Stop here if it crashes, e.g. because the port is already taken.
echo "[CourtIQ] Flask PID: $FLASK_PID — waiting for the model to load..."
until curl -s -o /dev/null "http://localhost:$FLASK_PORT/games/today"; do
  if ! kill -0 "$FLASK_PID" 2>/dev/null; then
    echo "[CourtIQ] ERROR: Flask exited during startup (see the message above)."
    echo "[CourtIQ] If port $FLASK_PORT is in use, run: FLASK_PORT=5051 bash start.sh"
    exit 1
  fi
  sleep 1
done
echo "[CourtIQ] Flask is up."

# ── 3. Install Node deps (first run only) ──────────────────────
echo "[CourtIQ] Checking Node.js dependencies..."
cd "$FRONTEND"
npm install --silent

# ── 4. Start Node.js server ────────────────────────────────────
echo "[CourtIQ] Starting Node.js server (port 3000)..."
echo "[CourtIQ] Open http://localhost:3000 in your browser."
npm start
