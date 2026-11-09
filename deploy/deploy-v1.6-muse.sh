#!/usr/bin/env bash
# TAPAS Growth Autopilot V1.6 — guarded deployment helper
# Run this ON the Muse VM from the backend checkout. No credentials are embedded.
set -Eeuo pipefail

BRANCH="${BRANCH:-feature/v1.6-publishing-growth-integrations}"
SERVICE_NAME="${SERVICE_NAME:-}"
REPO_DIR="$(pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-$HOME/tapas-backups}"
VENV="${VENV:-.venv}"

fail(){ echo "ERROR: $*" >&2; exit 1; }
[[ -d .git ]] || fail "Run from the tapas-social-backend Git checkout."
[[ -f requirements.txt ]] || fail "requirements.txt not found; wrong directory?"
mkdir -p "$BACKUP_DIR"

echo "== 1/6 Backup current checkout (excluding virtualenv/cache) =="
tar --exclude='.git' --exclude='.venv' --exclude='venv' --exclude='__pycache__' \
  -czf "$BACKUP_DIR/tapas-backend-$STAMP.tgz" .
echo "Backup: $BACKUP_DIR/tapas-backend-$STAMP.tgz"

echo "== 2/6 Preserve environment file =="
if [[ -f .env ]]; then cp -p .env "$BACKUP_DIR/.env-$STAMP"; echo "Saved .env backup."; else echo "No .env found (will not create one)."; fi

echo "== 3/6 Fetch and switch to V1.6 branch =="
git fetch origin
git switch "$BRANCH" 2>/dev/null || git switch -c "$BRANCH" --track "origin/$BRANCH"
git pull --ff-only origin "$BRANCH"
echo "Checked out: $(git rev-parse --short HEAD)"

echo "== 4/6 Install dependencies and run tests =="
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/pip" install -r requirements.txt
"$VENV/bin/python" -m compileall -q server.py services
"$VENV/bin/python" -m pytest -q

echo "== 5/6 Restart only if an explicit service name is supplied =="
if [[ -n "$SERVICE_NAME" ]]; then
  command -v systemctl >/dev/null || fail "systemctl unavailable; use your VM's service manager."
  sudo systemctl restart "$SERVICE_NAME"
  sudo systemctl --no-pager --full status "$SERVICE_NAME"
else
  echo "SERVICE_NAME unset: skipping restart. Configure the actual service/launcher first."
fi

echo "== 6/6 Health verification =="
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/health}"
if command -v curl >/dev/null; then
  curl --fail --silent --show-error "$HEALTH_URL" || {
    echo "Health endpoint failed. Inspect service logs; do not assume deployment is live." >&2
    exit 2
  }
  echo "Health endpoint responded: $HEALTH_URL"
else
  echo "curl unavailable; verify health manually at $HEALTH_URL"
fi

echo "Deployment script completed. Confirm app version, scheduler, integrations, and logs separately."
