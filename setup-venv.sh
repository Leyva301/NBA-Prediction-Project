#!/usr/bin/env bash
# setup-venv.sh — Create the Python virtual environment on any machine.
#
# Run this once after cloning or pulling on a new machine (local or flip).
# It creates a venv/ folder and installs all Python dependencies into it.
#
# Usage:
#   bash setup-venv.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[CourtIQ] Creating Python virtual environment..."
python3 -m venv "$SCRIPT_DIR/venv"

echo "[CourtIQ] Installing dependencies from requirements.txt..."
# Windows Git Bash uses Scripts/, Linux/macOS use bin/
if [ -f "$SCRIPT_DIR/venv/Scripts/python" ]; then
  PYTHON="$SCRIPT_DIR/venv/Scripts/python"
else
  PYTHON="$SCRIPT_DIR/venv/bin/python"
fi
"$PYTHON" -m pip install --upgrade pip -q
"$PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "[CourtIQ] venv ready. Packages installed:"
"$PYTHON" -m pip list --format=columns | grep -E "pandas|numpy|nba.api|scikit|flask|scipy"
echo ""
echo "[CourtIQ] Done. You can now run:"
echo "  bash start.sh        (local)"
echo "  bash start-flip.sh   (flip server)"
