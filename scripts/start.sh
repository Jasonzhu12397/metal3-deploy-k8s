#!/usr/bin/env bash
set -euo pipefail

docker compose up -d
echo "API:      http://localhost:8000/docs"
echo "Health:   http://localhost:8000/healthz"
docker compose logs -f api worker
