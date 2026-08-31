#!/usr/bin/env bash
set -euo pipefail

echo "== metal3-deploy-k8s-backend :: install =="

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env

  # Auto-generate real secrets instead of leaving placeholder text for
  # someone to fill in by hand -- this is the *correct* place for "the
  # system generates it automatically" to happen: a local file that
  # never enters git and never enters the application's own database
  # (see README's "BMC credential storage" section for why the key can
  # never live next to the data it protects, no matter how that data is
  # stored). "Automatic" and "in the database" are different asks --
  # this satisfies the first without breaking the second.
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
  if [ -z "$PYTHON_BIN" ]; then
    echo "python3 not found -- can't auto-generate SECRET_KEY/BMC_ENCRYPTION_KEY." >&2
    echo "Install python3 and re-run, or fill both values into .env by hand." >&2
  else
    SECRET_KEY="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(32))')"
    sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env && rm -f .env.bak
    echo "Generated SECRET_KEY."

    if "$PYTHON_BIN" -c 'import cryptography' >/dev/null 2>&1; then
      BMC_KEY="$("$PYTHON_BIN" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
      sed -i.bak "s|^BMC_ENCRYPTION_KEY=.*|BMC_ENCRYPTION_KEY=${BMC_KEY}|" .env && rm -f .env.bak
      echo "Generated BMC_ENCRYPTION_KEY."
    else
      echo "python's 'cryptography' package isn't installed here -- BMC_ENCRYPTION_KEY" >&2
      echo "left blank. Run this to generate one and paste it into .env yourself:" >&2
      echo "  pip install cryptography --break-system-packages" >&2
      echo '  python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"' >&2
    fi
  fi

  echo "Created .env with generated secrets. ADMIN_PASSWORD is left blank on"
  echo "purpose -- a random one gets generated and printed once to the api"
  echo "container's logs on first startup (docker compose logs api)."
fi

mkdir -p deploy/kubeconfig
echo "Place your management-cluster kubeconfig at deploy/kubeconfig/config"

echo "Building images..."
docker compose build

echo "Done. Run ./scripts/start.sh to bring the stack up."
