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
"$SCRIPT_DIR/venv/bin/pip" install --upgrade pip -q
"$SCRIPT_DIR/venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "[CourtIQ] venv ready. Packages installed:"
"$SCRIPT_DIR/venv/bin/pip" list --format=columns | grep -E "pandas|numpy|nba.api|scikit|flask|scipy"
echo ""
echo "[CourtIQ] Done. You can now run:"
echo "  bash start.sh        (local)"
echo "  bash start-flip.sh   (flip server)"
