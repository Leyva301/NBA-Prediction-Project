#!/bin/bash

# Kill both servers when you hit Ctrl+C
cleanup() {
  echo ""
  echo "Shutting down..."
  kill $FLASK_PID $NODE_PID 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "[1/2] Starting Flask API..."
python3 "$ROOT/backend/app/main.py" &
FLASK_PID=$!

echo "[2/2] Starting Express server..."
node "$ROOT/frontend/src/components/server.js" &
NODE_PID=$!

echo ""
echo "CourtIQ running at http://localhost:3000"
echo "Flask API running at http://localhost:5001"
echo "Press Ctrl+C to stop both."
echo ""

wait $FLASK_PID $NODE_PID
