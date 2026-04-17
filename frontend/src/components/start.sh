#!/bin/bash

VENV_PATH="./venv"
FLASK_SCRIPT="flask_api.py"

cleanup() {
  echo ""
  echo "[CourtIQ] Shutting down..."
  kill $FLASK_PID 2>/dev/null
  kill $NODE_PID 2>/dev/null
  wait $FLASK_PID 2>/dev/null
  wait $NODE_PID 2>/dev/null
  echo "[CourtIQ] All servers stopped."
  exit 0
}
trap cleanup SIGINT SIGTERM

source $VENV_PATH/bin/activate

# Start Flask — write output to log file instead of piping (piping loses the PID)
echo "[CourtIQ] Starting Flask..."
python $FLASK_SCRIPT > flask.log 2>&1 &
FLASK_PID=$!
echo "[CourtIQ] Flask PID: $FLASK_PID"

echo "[CourtIQ] Waiting for model to train..."
sleep 15

echo "[CourtIQ] Starting Node..."
npm start > node.log 2>&1 &
NODE_PID=$!
echo "[CourtIQ] Node PID: $NODE_PID"

echo "[CourtIQ] Both running. Ctrl+C to stop both."
echo "[CourtIQ] Watching logs — tail -f flask.log or tail -f node.log"

# Keep alive and print both logs to terminal
tail -f flask.log node.log &
TAIL_PID=$!

wait $NODE_PID
cleanup