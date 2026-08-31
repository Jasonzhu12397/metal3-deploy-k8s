#!/usr/bin/env bash
set -Eeuo pipefail

# Renews the Let's Encrypt cert obtained by setup-https-letsencrypt.sh and
# reloads nginx so it picks up the renewed files. Certbot only actually
# renews within ~30 days of expiry (safe to run this often -- it's a
# no-op otherwise), so a daily cron entry is fine:
#
#   crontab -e
#   0 3 * * * /path/to/metal3-deploy-k8s-backend/scripts/renew-https-certs.sh >> /var/log/metal3-cert-renew.log 2>&1
#
# The certbot service in docker-compose.yml (added by
# setup-https-letsencrypt.sh) also loops on its own every 12h as a second
# line of defense, but a real cron entry running this script is easier to
# see/debug when something goes wrong than a container loop's logs.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "ERROR: docker compose / docker-compose not found." >&2
    exit 1
fi

echo "[$(date -Is)] Checking for certificate renewal..."
"${COMPOSE_CMD[@]}" run --rm certbot renew --webroot -w /var/www/certbot

echo "[$(date -Is)] Reloading nginx..."
"${COMPOSE_CMD[@]}" exec nginx nginx -s reload || "${COMPOSE_CMD[@]}" restart nginx

echo "[$(date -Is)] Done."
