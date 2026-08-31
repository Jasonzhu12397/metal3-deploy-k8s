#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Metal3 Deploy K8s - Docker Compose HTTPS Setup (Let's Encrypt)
#
# Usage:
#   sudo ./scripts/setup-https-letsencrypt.sh your-domain.com [email]
#
# Requires, before you run this:
#   - A real domain (e.g. metal3.top) with an A record pointing at this
#     server's public IP -- Let's Encrypt validates ownership by fetching
#     a file from http://<domain>/.well-known/acme-challenge/... over the
#     public internet, so DNS must already resolve correctly and port 80
#     must be reachable from the internet (not blocked by a firewall,
#     cloud security group, or -- if you're on a mainland China cloud
#     provider -- not blocked for lack of ICP备案).
#   - Port 80 and 443 free on this host (nothing else bound to them).
#
# This bootstraps in two phases because nginx can't start with a
# certificate config pointing at files that don't exist yet:
#   Phase 1: nginx serves plain HTTP only, with just enough config to
#            answer the ACME HTTP-01 challenge. certbot runs against it
#            and obtains the real certificate.
#   Phase 2: nginx gets the full HTTP(redirect)+HTTPS config, now that
#            the certificate files actually exist, and reloads.
#
# Renewal: Let's Encrypt certs expire every 90 days. Add a cron entry
# for scripts/renew-https-certs.sh (see that script's own header).
# ============================================================

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [[ -z "${DOMAIN}" ]]; then
    echo "Usage:"
    echo "  sudo $0 <domain> [email]"
    echo
    echo "Example:"
    echo "  sudo $0 metal3.top admin@metal3.top"
    echo
    echo "The email is optional but recommended -- Let's Encrypt uses it"
    echo "for expiry notices if renewal ever fails silently."
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
NGINX_DIR="${PROJECT_DIR}/deploy/nginx"
NGINX_CONF="${NGINX_DIR}/nginx.conf"
CERTBOT_WEBROOT="${NGINX_DIR}/certbot-webroot"
LETSENCRYPT_DIR="${NGINX_DIR}/letsencrypt"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${PROJECT_DIR}/docker-compose.yml.backup.${TIMESTAMP}"

echo
echo "============================================================"
echo " Metal3 Deploy K8s HTTPS Setup (Let's Encrypt)"
echo "============================================================"
echo
echo "Project : ${PROJECT_DIR}"
echo "Domain  : ${DOMAIN}"
echo "Email   : ${EMAIL:-<none -- --register-unsafely-without-email>}"
echo

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Please run this script with sudo."
    exit 1
fi

for cmd in docker openssl curl; do
    if ! command -v "${cmd}" >/dev/null 2>&1; then
        echo "ERROR: ${cmd} is not installed."
        exit 1
    fi
done

if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD=(docker-compose)
else
    echo "ERROR: docker compose / docker-compose not found."
    exit 1
fi

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "ERROR: ${COMPOSE_FILE} not found."
    exit 1
fi

# ------------------------------------------------------------
# Sanity check: does the domain actually resolve to this host?
# Not a hard blocker (DNS can be slow to propagate, or you might be
# behind a load balancer/NAT doing the actual public-facing termination)
# -- just a heads-up before spending a Let's Encrypt rate-limit attempt.
# ------------------------------------------------------------

echo "[1/10] Checking DNS resolution for ${DOMAIN}..."
RESOLVED_IP="$(getent hosts "${DOMAIN}" 2>/dev/null | awk '{print $1}' | head -1 || true)"
SERVER_IP="$(curl -s --max-time 5 https://api.ipify.org || true)"
if [[ -n "${RESOLVED_IP}" && -n "${SERVER_IP}" && "${RESOLVED_IP}" != "${SERVER_IP}" ]]; then
    echo "[WARNING] ${DOMAIN} resolves to ${RESOLVED_IP}, but this server's public IP looks like ${SERVER_IP}."
    echo "          Let's Encrypt's validation request comes from the public internet, not from this"
    echo "          machine -- if these don't match, the challenge will fail. Continuing anyway in case"
    echo "          this check itself is wrong (e.g. multiple public IPs, CDN in front)."
elif [[ -z "${RESOLVED_IP}" ]]; then
    echo "[WARNING] ${DOMAIN} doesn't resolve at all yet from here. DNS may still be propagating."
else
    echo "[OK] ${DOMAIN} resolves to ${RESOLVED_IP}, matching this server's apparent public IP."
fi
echo

echo "[2/10] Backing up docker-compose.yml..."
cp -a "${COMPOSE_FILE}" "${BACKUP_FILE}"
echo "[OK] Backup created: ${BACKUP_FILE}"
echo

echo "[3/10] Creating Nginx/certbot directories..."
mkdir -p "${CERTBOT_WEBROOT}" "${LETSENCRYPT_DIR}"
echo "[OK] ${NGINX_DIR}"
echo

# ------------------------------------------------------------
# Phase 1: HTTP-only nginx config, just enough to answer the
# ACME challenge. No certificate reference at all yet.
# ------------------------------------------------------------

echo "[4/10] Writing phase-1 (HTTP-only) Nginx config..."

cat > "${NGINX_CONF}" <<NGINX_EOF
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;

    server {
        listen 80;
        listen [::]:80;
        server_name ${DOMAIN};

        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 200 'metal3-deploy-k8s-backend: waiting for TLS certificate...';
            add_header Content-Type text/plain;
        }
    }
}
NGINX_EOF

echo "[OK] ${NGINX_CONF} (phase 1)"
echo

# ------------------------------------------------------------
# Patch docker-compose.yml: strip direct port exposure, add nginx
# (mounting the certbot webroot + letsencrypt dirs too, unlike the
# self-signed version) and a one-shot certbot service.
# ------------------------------------------------------------

echo "[5/10] Updating docker-compose.yml..."

python3 - "${COMPOSE_FILE}" "${PROJECT_DIR}" <<'PY'
import sys
from pathlib import Path

compose_file = Path(sys.argv[1])
project_dir = Path(sys.argv[2])
sys.path.insert(0, str(project_dir / "scripts" / "lib"))
from patch_compose_for_https import patch  # noqa: E402

nginx_service = '''
  nginx:
    image: nginx:1.27-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./deploy/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./deploy/nginx/letsencrypt:/etc/letsencrypt:ro
      - ./deploy/nginx/certbot-webroot:/var/www/certbot:ro
    depends_on:
      - frontend

  certbot:
    image: certbot/certbot:latest
    volumes:
      - ./deploy/nginx/letsencrypt:/etc/letsencrypt
      - ./deploy/nginx/certbot-webroot:/var/www/certbot
    entrypoint: ["sh", "-c", "trap exit TERM; while :; do sleep 12h & wait $${!}; certbot renew --webroot -w /var/www/certbot --quiet; done"]
'''
patch(compose_file, nginx_service)
PY

echo "[OK] docker-compose.yml updated."
echo
echo "Current exposed ports:"
grep -n -A3 -B2 'ports:' "${COMPOSE_FILE}" || true
echo

echo "[6/10] Validating Docker Compose..."
"${COMPOSE_CMD[@]}" config >/tmp/metal3-compose-config.yaml
echo "[OK] Docker Compose configuration is valid."
echo

# ------------------------------------------------------------
# Bring up nginx (phase 1) + the rest of the stack, so certbot's
# HTTP-01 challenge has something to answer it on port 80.
# ------------------------------------------------------------

echo "[7/10] Starting stack with phase-1 (HTTP-only) Nginx..."
"${COMPOSE_CMD[@]}" up -d --build
sleep 5
echo "[OK] Stack is up."
echo

# ------------------------------------------------------------
# Obtain the certificate.
# ------------------------------------------------------------

echo "[8/10] Requesting certificate from Let's Encrypt..."

EMAIL_ARG=(--register-unsafely-without-email)
if [[ -n "${EMAIL}" ]]; then
    EMAIL_ARG=(--email "${EMAIL}" --no-eff-email)
fi

"${COMPOSE_CMD[@]}" run --rm certbot \
    certonly --webroot -w /var/www/certbot \
    -d "${DOMAIN}" \
    "${EMAIL_ARG[@]}" \
    --agree-tos \
    --non-interactive

if [[ ! -f "${LETSENCRYPT_DIR}/live/${DOMAIN}/fullchain.pem" ]]; then
    echo
    echo "[ERROR] Certificate was not issued -- check the certbot output above."
    echo "Common causes: DNS not pointing here yet, port 80 not reachable from the"
    echo "internet (firewall / cloud security group / ICP备案 block on a mainland"
    echo "China host), or Let's Encrypt rate limits from too many recent attempts"
    echo "for this domain."
    echo
    echo "docker-compose.yml has already been modified -- restore from the backup"
    echo "if you need to roll back:"
    echo "  cp ${BACKUP_FILE} ${COMPOSE_FILE}"
    exit 1
fi

echo "[OK] Certificate obtained: ${LETSENCRYPT_DIR}/live/${DOMAIN}/fullchain.pem"
echo

# ------------------------------------------------------------
# Phase 2: full HTTP(redirect)+HTTPS config, now that the
# certificate actually exists.
# ------------------------------------------------------------

echo "[9/10] Writing phase-2 (HTTPS) Nginx config..."

cat > "${NGINX_CONF}" <<NGINX_EOF
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    client_max_body_size 100m;

    upstream frontend {
        server frontend:80;
    }

    server {
        listen 80;
        listen [::]:80;
        server_name ${DOMAIN};

        # Keep serving the ACME challenge over plain HTTP even after
        # switching to HTTPS -- certbot renew (run periodically by the
        # certbot service's loop, see docker-compose.yml) re-validates
        # this way every ~60 days.
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        location / {
            return 301 https://\$host\$request_uri;
        }
    }

    server {
        listen 443 ssl;
        listen [::]:443 ssl;
        server_name ${DOMAIN};

        ssl_certificate     /etc/letsencrypt/live/${DOMAIN}/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/${DOMAIN}/privkey.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;

            # REQUIRED for the deployment-progress WebSocket
            # (/api/v1/deployments/{id}/ws) -- see setup-https-selfsigned.sh's
            # copy of this same comment for the full explanation.
            proxy_set_header Upgrade \$http_upgrade;
            proxy_set_header Connection "upgrade";

            proxy_set_header Host \$host;
            proxy_set_header X-Real-IP \$remote_addr;
            proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto https;

            proxy_connect_timeout 60s;
            proxy_send_timeout 300s;
            proxy_read_timeout 300s;
        }
    }
}
NGINX_EOF

echo "[OK] ${NGINX_CONF} (phase 2)"
echo

echo "[10/10] Reloading Nginx with the real certificate..."
"${COMPOSE_CMD[@]}" restart nginx
sleep 3
echo "[OK] Nginx reloaded."
echo

echo "============================================================"
echo " HTTPS Test"
echo "============================================================"
if curl -I --max-time 15 "https://${DOMAIN}" >/tmp/metal3_https_test.txt 2>&1; then
    echo "[OK] HTTPS endpoint responded (real, trusted certificate -- no -k needed):"
    cat /tmp/metal3_https_test.txt
else
    echo "[WARNING] HTTPS test failed -- check: ${COMPOSE_CMD[*]} logs nginx"
fi

echo
echo "============================================================"
echo " HTTPS Setup Complete (Let's Encrypt)"
echo "============================================================"
echo
echo "  https://${DOMAIN}"
echo
echo "Certificate expires in ~90 days. Set up automatic renewal:"
echo "  crontab -e"
echo "  # add: 0 3 * * * $(cd "${PROJECT_DIR}" && pwd)/scripts/renew-https-certs.sh"
echo
echo "(The certbot container in docker-compose.yml also runs its own renewal"
echo "loop every 12h as a second line of defense, but a real cron entry"
echo "running scripts/renew-https-certs.sh is the more visible/debuggable path.)"
echo
echo "Compose backup: ${BACKUP_FILE}"
echo "============================================================"
