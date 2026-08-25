#!/usr/bin/env bash
set -euo pipefail

echo "== metal3-deploy-k8s-backend :: install =="

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required but not installed." >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example -- edit it before starting the stack."
fi

mkdir -p deploy/kubeconfig
echo "Place your management-cluster kubeconfig at deploy/kubeconfig/config"

echo "Building images..."
docker compose build

echo "Done. Run ./scripts/start.sh to bring the stack up."
