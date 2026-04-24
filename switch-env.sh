#!/usr/bin/env bash
# switch-env.sh — Toggle CourtIQ between local and flip hosting
#
# Usage:
#   bash switch-env.sh local          → sets FLASK_API_URL to localhost:5000
#   bash switch-env.sh flip <flipX>   → sets FLASK_API_URL to flipX.engr.oregonstate.edu:5000
#
# Examples:
#   bash switch-env.sh local
#   bash switch-env.sh flip flip3

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DEST="$SCRIPT_DIR/frontend/src/components/.env"

MODE="$1"
FLIP_HOST="$2"

if [ "$MODE" = "local" ]; then
  cp "$SCRIPT_DIR/env.local" "$ENV_DEST"
  echo "[CourtIQ] Environment set to LOCAL."
  echo "  Flask API → http://localhost:5000"
  echo "  Frontend  → http://localhost:3000"
  echo ""
  echo "  Run with: bash start.sh"

elif [ "$MODE" = "flip" ]; then
  if [ -z "$FLIP_HOST" ]; then
    echo "Error: please specify which flip server, e.g.:"
    echo "  bash switch-env.sh flip flip3"
    exit 1
  fi

  cp "$SCRIPT_DIR/env.flip" "$ENV_DEST"
  # Replace the placeholder flipX with the actual host
  sed -i "s/flipX/$FLIP_HOST/g" "$ENV_DEST"

  echo "[CourtIQ] Environment set to FLIP ($FLIP_HOST)."
  echo "  Flask API → http://$FLIP_HOST.engr.oregonstate.edu:5000"
  echo "  Frontend  → http://$FLIP_HOST.engr.oregonstate.edu:3000"
  echo ""
  echo "  Next steps:"
  echo "    1. Push your changes to GitHub"
  echo "    2. SSH into $FLIP_HOST and git pull"
  echo "    3. Run: bash start-flip.sh"

else
  echo "Usage:"
  echo "  bash switch-env.sh local"
  echo "  bash switch-env.sh flip <flipX>"
  exit 1
fi
