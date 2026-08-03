#!/usr/bin/env bash
#
# Redeploy JOBZY on the production server.
# Run as root on the server itself:
#
#   bash /opt/jobzy/app/deploy.sh
#
# Pulls the latest main, installs any new dependencies, applies migrations,
# refreshes static files and restarts the service.

set -euo pipefail

APP_DIR=/opt/jobzy/app
VENV=/opt/jobzy/venv
APP_USER=jobzy

echo "==> Fetching latest code"
cd "$APP_DIR"
git fetch --all --quiet
git reset --hard origin/main --quiet
git log --oneline -1

echo "==> Installing dependencies"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r requirements.txt

echo "==> Applying migrations"
sudo -u "$APP_USER" "$VENV/bin/python" manage.py migrate --noinput

echo "==> Collecting static files"
sudo -u "$APP_USER" "$VENV/bin/python" manage.py collectstatic --noinput >/dev/null
echo "static files collected"

echo "==> Fixing ownership"
chown -R "$APP_USER:$APP_USER" /opt/jobzy /var/www/jobzy
chmod 600 "$APP_DIR/.env"

echo "==> Restarting services"
systemctl restart jobzy
sleep 4
systemctl is-active jobzy

echo "==> Smoke test"
curl -sf -o /dev/null -w "swagger: HTTP %{http_code}\n" https://62-238-33-236.sslip.io/swagger/
echo "Deploy complete."
