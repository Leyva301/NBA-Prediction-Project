#!/usr/bin/env bash
# start-flip.sh — CourtIQ launcher for OSU flip servers
#
# Run this ON the flip server after cloning/pulling the repo.
# Both servers run in the background via nohup so they survive logout.
#
# Usage (on the flip server):
#   bash start-flip.sh           → start both servers
#   bash start-flip.sh stop      → kill both servers
#   bash start-flip.sh status    → show running processes
#   bash start-flip.sh logs      → tail both log files

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPONENTS="$SCRIPT_DIR/frontend/src/components"
FLASK_LOG="$COMPONENTS/flask.log"
NODE_LOG="$COMPONENTS/node.log"
PID_FILE="$SCRIPT_DIR/.courtiq.pids"

# ── STOP ──────────────────────────────────────────────────────────
if [ "$1" = "stop" ]; then
  if [ -f "$PID_FILE" ]; then
    while read -r pid; do
      kill "$pid" 2>/dev/null && echo "Killed PID $pid" || echo "PID $pid already gone"
    done < "$PID_FILE"
    rm "$PID_FILE"
    echo "[CourtIQ] Servers stopped."
  else
    echo "[CourtIQ] No PID file found. Trying pkill..."
    pkill -f "flask_api.py" 2>/dev/null || true
    pkill -f "server.js"   2>/dev/null || true
    echo "[CourtIQ] Done."
  fi
  exit 0
fi

# ── STATUS ────────────────────────────────────────────────────────
if [ "$1" = "status" ]; then
  echo "=== Flask (flask_api.py) ==="
  pgrep -af "flask_api.py" || echo "  Not running"
  echo ""
  echo "=== Node (server.js) ==="
  pgrep -af "server.js" || echo "  Not running"
  exit 0
fi

# ── LOGS ──────────────────────────────────────────────────────────
if [ "$1" = "logs" ]; then
  tail -f "$FLASK_LOG" "$NODE_LOG"
  exit 0
fi

# ── START ─────────────────────────────────────────────────────────

# Kill any existing instances first
pkill -f "flask_api.py" 2>/dev/null || true
pkill -f "server.js"   2>/dev/null || true
sleep 1

# ── Activate venv (create it first if missing) ────────────────────
if [ ! -f "$SCRIPT_DIR/venv/bin/python" ]; then
  echo "[CourtIQ] No venv found — running setup-venv.sh..."
  bash "$SCRIPT_DIR/setup-venv.sh"
fi
PYTHON="$SCRIPT_DIR/venv/bin/python"

echo "[CourtIQ] Starting Flask API in background (port 5000)..."
cd "$COMPONENTS"
nohup "$PYTHON" flask_api.py > "$FLASK_LOG" 2>&1 &
FLASK_PID=$!

echo "[CourtIQ] Waiting for model to load (~20s — fetches NBA season data on startup)..."
sleep 20

echo "[CourtIQ] Installing Node.js dependencies..."
npm install --silent

echo "[CourtIQ] Starting Node.js server in background (port 3000)..."
nohup node server.js > "$NODE_LOG" 2>&1 &
NODE_PID=$!

# Save PIDs so stop command works
echo "$FLASK_PID" >  "$PID_FILE"
echo "$NODE_PID"  >> "$PID_FILE"

sleep 2

# Confirm both are still alive
if kill -0 "$FLASK_PID" 2>/dev/null && kill -0 "$NODE_PID" 2>/dev/null; then
  FLIP_HOST=$(hostname)
  echo ""
  echo "================================================"
  echo " [CourtIQ] Both servers are running!"
  echo " Frontend : http://$FLIP_HOST:3000"
  echo " Flask API: http://$FLIP_HOST:5000"
  echo " Flask PID: $FLASK_PID  |  Node PID: $NODE_PID"
  echo ""
  echo " Logs : bash start-flip.sh logs"
  echo " Stop : bash start-flip.sh stop"
  echo "================================================"
else
  echo "[CourtIQ] ERROR: One or both servers failed to start."
  echo "Check logs:"
  echo "  $FLASK_LOG"
  echo "  $NODE_LOG"
  exit 1
fi
