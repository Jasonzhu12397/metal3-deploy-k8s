#!/usr/bin/env bash
# Generates deploy/k8s/secret.yaml from secret.yaml.example with real,
# random SECRET_KEY/BMC_ENCRYPTION_KEY/POSTGRES_PASSWORD values already
# filled in -- so nobody has to hand-type or think up secrets. The
# generated file stays a plain local file (gitignored) and gets applied
# straight to the cluster as a real Kubernetes Secret; nothing here ever
# writes a key into this application's own database (see the README's
# "BMC credential storage" section for why that specific combination
# would defeat the whole point of encrypting anything).
set -euo pipefail

cd "$(dirname "$0")"

if [ -f secret.yaml ]; then
  echo "secret.yaml already exists -- not overwriting. Delete it first if you want to regenerate." >&2
  exit 1
fi

PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "python3 is required to generate secrets." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c 'import cryptography' >/dev/null 2>&1; then
  echo "python's 'cryptography' package is required. Install it and re-run:" >&2
  echo "  pip install cryptography --break-system-packages" >&2
  exit 1
fi

SECRET_KEY="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(32))')"
BMC_ENCRYPTION_KEY="$("$PYTHON_BIN" -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
POSTGRES_PASSWORD="$("$PYTHON_BIN" -c 'import secrets; print(secrets.token_urlsafe(24))')"

cp secret.yaml.example secret.yaml
sed -i.bak \
  -e "s|REPLACE_WITH_A_LONG_RANDOM_VALUE|${SECRET_KEY}|" \
  -e "s|REPLACE_WITH_A_GENERATED_FERNET_KEY|${BMC_ENCRYPTION_KEY}|" \
  -e "s|REPLACE_WITH_A_STRONG_PASSWORD|${POSTGRES_PASSWORD}|g" \
  secret.yaml
rm -f secret.yaml.bak

echo "Generated deploy/k8s/secret.yaml with real SECRET_KEY/BMC_ENCRYPTION_KEY/POSTGRES_PASSWORD values."
echo "ADMIN_PASSWORD is left blank on purpose -- a random one gets generated and printed"
echo "once to the api pod's logs on first startup:"
echo "  kubectl logs -n metal3 deploy/metal3-deploy-api | grep -A3 'Seeded initial admin'"
echo ""
echo "If you're using a managed Postgres instead of postgres.yaml's fallback, edit"
echo "DATABASE_URL in secret.yaml to point at it instead (the generated POSTGRES_PASSWORD"
echo "is only wired up for the self-contained fallback)."
echo ""
echo "Next: kubectl apply -f secret.yaml"
