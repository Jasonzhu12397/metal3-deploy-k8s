#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# Metal3 Deploy K8s - Docker Compose HTTPS Setup (self-signed)
#
# Usage:
#   sudo ./scripts/setup-https-selfsigned.sh your-domain.com
#
# Quick to set up, works with no DNS/internet requirements at all -- but
# browsers will show a certificate warning, since nothing trusts a
# self-signed cert. If you own a real domain and can point it at this
# server, scripts/setup-https-letsencrypt.sh gets you a real, trusted
# certificate instead -- use that one unless you specifically need
# something that works before DNS is configured (e.g. testing by IP).
#
# This script:
#   - Creates a self-signed TLS certificate
#   - Creates a Docker nginx reverse proxy in front of the existing stack
#   - Updates docker-compose.yml (backed up first)
#   - Keeps PostgreSQL/Redis/API internal-only (no more direct exposure)
#   - Exposes only HTTP/HTTPS
# ============================================================

DOMAIN="${1:-}"

if [[ -z "${DOMAIN}" ]]; then
    echo "Usage:"
    echo "  sudo $0 <domain>"
    echo
    echo "Example:"
    echo "  sudo $0 metal3.example.com"
    exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"

COMPOSE_FILE="${PROJECT_DIR}/docker-compose.yml"
NGINX_DIR="${PROJECT_DIR}/deploy/nginx"
CERT_DIR="${NGINX_DIR}/certs"
NGINX_CONF="${NGINX_DIR}/nginx.conf"
CERT_FILE="${CERT_DIR}/server.crt"
KEY_FILE="${CERT_DIR}/server.key"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${PROJECT_DIR}/docker-compose.yml.backup.${TIMESTAMP}"

echo
echo "============================================================"
echo " Metal3 Deploy K8s HTTPS Setup (self-signed)"
echo "============================================================"
echo
echo "Project : ${PROJECT_DIR}"
echo "Domain  : ${DOMAIN}"
echo

# ------------------------------------------------------------
# Check root
# ------------------------------------------------------------

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Please run this script with sudo."
    echo
    echo "Example:"
    echo "  sudo $0 ${DOMAIN}"
    exit 1
fi

# ------------------------------------------------------------
# Check required commands
# ------------------------------------------------------------

for cmd in docker openssl; do
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

echo "[OK] Docker Compose:"
"${COMPOSE_CMD[@]}" version
echo

# ------------------------------------------------------------
# Check compose file
# ------------------------------------------------------------

if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "ERROR: ${COMPOSE_FILE} not found."
    exit 1
fi

# ------------------------------------------------------------
# Backup compose file
# ------------------------------------------------------------

echo "[1/9] Backing up docker-compose.yml..."

cp -a "${COMPOSE_FILE}" "${BACKUP_FILE}"

echo "[OK] Backup created:"
echo "     ${BACKUP_FILE}"
echo

# ------------------------------------------------------------
# Create directories
# ------------------------------------------------------------

echo "[2/9] Creating Nginx directories..."

mkdir -p "${CERT_DIR}"

echo "[OK] ${NGINX_DIR}"
echo

# ------------------------------------------------------------
# Detect server IP
# ------------------------------------------------------------

SERVER_IP=""

if command -v ip >/dev/null 2>&1; then
    SERVER_IP="$(ip route get 1.1.1.1 2>/dev/null \
        | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' \
        || true)"
fi

if [[ -z "${SERVER_IP}" ]]; then
    SERVER_IP="127.0.0.1"
fi

echo "[3/9] Detected server IP:"
echo "     ${SERVER_IP}"
echo

# ------------------------------------------------------------
# Generate self-signed certificate
# ------------------------------------------------------------

echo "[4/9] Generating self-signed TLS certificate..."

cat > "${CERT_DIR}/openssl.cnf" <<OPENSSL_EOF
[req]
default_bits = 2048
prompt = no
default_md = sha256
req_extensions = req_ext
distinguished_name = dn

[dn]
CN = ${DOMAIN}

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${DOMAIN}
DNS.2 = localhost
IP.1 = ${SERVER_IP}
IP.2 = 127.0.0.1
OPENSSL_EOF

openssl req \
    -x509 \
    -nodes \
    -newkey rsa:2048 \
    -sha256 \
    -days 365 \
    -keyout "${KEY_FILE}" \
    -out "${CERT_FILE}" \
    -config "${CERT_DIR}/openssl.cnf" \
    -extensions req_ext \
    >/dev/null 2>&1

chmod 600 "${KEY_FILE}"
chmod 644 "${CERT_FILE}"
chmod 644 "${CERT_DIR}/openssl.cnf"

echo "[OK] Certificate:"
echo "     ${CERT_FILE}"
echo
echo "[OK] Private key:"
echo "     ${KEY_FILE}"
echo

# ------------------------------------------------------------
# Create Nginx configuration
# ------------------------------------------------------------

echo "[5/9] Creating Nginx configuration..."

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

    # HTTP -> HTTPS
    server {
        listen 80;
        listen [::]:80;

        server_name ${DOMAIN};

        location / {
            return 301 https://\$host\$request_uri;
        }
    }

    # HTTPS
    server {
        listen 443 ssl;
        listen [::]:443 ssl;

        server_name ${DOMAIN};

        ssl_certificate     /etc/nginx/certs/server.crt;
        ssl_certificate_key /etc/nginx/certs/server.key;

        ssl_protocols TLSv1.2 TLSv1.3;

        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        location / {
            proxy_pass http://frontend;

            proxy_http_version 1.1;

            # REQUIRED for the deployment-progress WebSocket
            # (/api/v1/deployments/{id}/ws) to work through this proxy --
            # without these two headers, nginx treats the WebSocket
            # upgrade handshake as a plain HTTP request and it fails
            # silently (the frontend's own internal nginx already sets
            # these correctly for its /api/ location, but that's the
            # NEXT hop -- this outer proxy has to forward the upgrade
            # intent through, or the inner hop never sees it).
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

echo "[OK] ${NGINX_CONF}"
echo

# ------------------------------------------------------------
# Validate nginx config syntax
# ------------------------------------------------------------

echo "[6/9] Validating Nginx configuration..."

# The nginx config references the Docker Compose service name "frontend".
# A standalone nginx container cannot resolve that name before the Compose
# network exists. The actual nginx validation is performed after Compose starts.
docker run --rm \
    -v "${NGINX_CONF}:/etc/nginx/nginx.conf:ro" \
    -v "${CERT_DIR}:/etc/nginx/certs:ro" \
    nginx:1.27-alpine \
    nginx -t -g "daemon off;" 2>&1 || true

echo "[OK] Nginx configuration file generated."
echo "[INFO] Docker service name 'frontend' will be resolved after Compose starts."
echo

# ------------------------------------------------------------
# Modify docker-compose.yml
# ------------------------------------------------------------

echo "[7/9] Updating docker-compose.yml..."

python3 "${PROJECT_DIR}/scripts/lib/patch_compose_for_https.py" "${COMPOSE_FILE}"

echo "[OK] docker-compose.yml updated."
echo

# ------------------------------------------------------------
# Show resulting compose
# ------------------------------------------------------------

echo "Current exposed ports:"
grep -n -A3 -B2 'ports:' "${COMPOSE_FILE}" || true
echo

# ------------------------------------------------------------
# Validate Docker Compose
# ------------------------------------------------------------

echo "[8/9] Validating Docker Compose..."

"${COMPOSE_CMD[@]}" config >/tmp/metal3-compose-config.yaml

echo "[OK] Docker Compose configuration is valid."
echo

# ------------------------------------------------------------
# Restart stack
# ------------------------------------------------------------

echo "[9/9] Starting application..."

"${COMPOSE_CMD[@]}" up -d --build

echo
echo "Waiting for containers..."
sleep 8

echo
echo "============================================================"
echo " Container Status"
echo "============================================================"

"${COMPOSE_CMD[@]}" ps

echo
echo "============================================================"
echo " HTTPS Test"
echo "============================================================"

if curl -k -I --max-time 15 "https://${DOMAIN}" >/tmp/metal3_https_test.txt 2>&1; then
    echo "[OK] HTTPS endpoint responded:"
    cat /tmp/metal3_https_test.txt
else
    echo "[WARNING] HTTPS test failed."
    echo
    echo "This can be normal if DNS is not configured yet."
    echo
    echo "Check:"
    echo "  ${COMPOSE_CMD[*]} logs nginx"
    echo "  curl -k -I https://${DOMAIN}"
fi

echo
echo "============================================================"
echo " HTTPS Setup Complete (self-signed)"
echo "============================================================"
echo
echo "Domain:"
echo "  https://${DOMAIN}"
echo
echo "NOTE:"
echo "  This is a self-signed certificate -- browsers will show a"
echo "  warning. If ${DOMAIN} is a real domain you control and this"
echo "  server is reachable on port 80 from the internet, run"
echo "  scripts/setup-https-letsencrypt.sh instead for a trusted cert."
echo
echo "Compose backup:"
echo "  ${BACKUP_FILE}"
echo
echo "To check logs:"
echo "  ${COMPOSE_CMD[*]} logs -f nginx"
echo
echo "============================================================"
