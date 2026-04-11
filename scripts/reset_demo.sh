#!/usr/bin/env bash
# reset_demo.sh - Resets the NovaOPS demo environment.
# Run every 30 minutes via cron or a systemd timer.
#
# Usage:
#   bash /home/novaops/app/scripts/reset_demo.sh
#
# Cron example (add with: crontab -e -u novaops):
#   */30 * * * * /home/novaops/app/scripts/reset_demo.sh >> /var/log/novaops-demo-reset.log 2>&1

set -euo pipefail

APP_DIR="/home/novaops/app"
VENV="$APP_DIR/.venv/bin/python"
LOG_TAG="novaops-demo-reset"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting demo reset"

# Load environment variables from the app .env file.
if [ -f "$APP_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env"
  set +a
fi

# Verify demo mode is enabled to avoid accidental resets in production.
if [ "${DEMO_MODE:-false}" != "true" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: DEMO_MODE is not true in .env - aborting."
  exit 1
fi

cd "$APP_DIR"
"$VENV" manage.py reset_demo --skip-images

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Demo reset finished"
