#!/usr/bin/env bash
#
# Launch the Zinvest Django backend under Gunicorn, behind Nginx (local dev).
# Nginx proxies to the unix socket this creates (see deploy/nginx/zinvest.loc.conf).
#
#   ./deploy/run-backend.sh
#
# Ctrl-C to stop. On a crash the stale socket is removed on the next start.
set -euo pipefail

PROJECT="/Users/abdulaziz/Website/Zinvest"
BACKEND="$PROJECT/backend"
SOCK="$BACKEND/zinvest.sock"

# --- Config injected here so it works regardless of the .env file -----------
# (settings.py reads these from the environment; env vars win over any .env.)
export GUNICORN_BIND="unix:$SOCK"
export ALLOWED_HOSTS="localhost,127.0.0.1,zinvest.loc,api.zinvest.loc,dashboard.zinvest.loc"
export FORWARDED_ALLOW_IPS="127.0.0.1"
# DEBUG defaults to True in settings.py -> stays on SQLite, plain-HTTP cookies OK.

# --- Activate venv & run ----------------------------------------------------
source "$BACKEND/.venv/bin/activate"
cd "$BACKEND"

# Remove a stale socket left by a previous crash so Nginx doesn't 502.
rm -f "$SOCK"

echo "→ Gunicorn binding $SOCK  (workers: 3)"
exec gunicorn config.wsgi:application -c gunicorn.conf.py --workers 3
