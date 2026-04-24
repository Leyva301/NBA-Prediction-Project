#!/usr/bin/env bash
# start.sh — CourtIQ local development launcher
# Usage: bash start.sh  (run from the project root)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPONENTS="$SCRIPT_DIR/frontend/src/components"

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
echo "[CourtIQ] Starting Flask API (port 5000)..."
cd "$COMPONENTS"
"$PYTHON" flask_api.py &
FLASK_PID=$!

echo "[CourtIQ] Flask PID: $FLASK_PID — waiting for it to initialize..."
sleep 6

# ── 3. Install Node deps (first run only) ──────────────────────
echo "[CourtIQ] Checking Node.js dependencies..."
npm install --silent

# ── 4. Start Node.js server ────────────────────────────────────
echo "[CourtIQ] Starting Node.js server (port 3000)..."
echo "[CourtIQ] Open http://localhost:3000 in your browser."
npm start
