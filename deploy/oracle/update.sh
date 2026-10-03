#!/usr/bin/env bash
# Update ATIS on the VM: pull the latest code for the deployed branch, rebuild, restart.
#   sudo atis-update              pull + build + restart
#   sudo atis-update --build-only install and build only (used by setup.sh)
# Restarting atis-live during market hours is safe: it resumes without resending alerts.
set -euo pipefail
APP_DIR=/opt/atis
[ "$(id -u)" -eq 0 ] || { echo "run with sudo: sudo atis-update" >&2; exit 1; }
cd "$APP_DIR"

if [ "${1:-}" != --build-only ]; then
  BRANCH="$(git rev-parse --abbrev-ref HEAD)"
  echo "==> pulling $BRANCH"
  git fetch -q origin "$BRANCH"
  git checkout -q -B "$BRANCH" "origin/$BRANCH"
  git log --oneline -1
fi

echo "==> Python package"
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[console]"

echo "==> web UI"
(cd console-ui && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent >/dev/null)
test -f src/atis/console/static/index.html

if [ "${1:-}" != --build-only ]; then
  echo "==> restarting"
  systemctl daemon-reload
  systemctl restart atis-console
  if systemctl is-active -q atis-live; then systemctl restart atis-live; fi
  systemctl --no-pager --lines=0 status atis-console | head -3
fi
