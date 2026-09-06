FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# clusterctl -- only actually used by the worker for the (opt-in) pivot
# step (services/pivot.py moving CAPI management from an ephemeral
# bootstrap node to a self-hosting target cluster), but baked into this
# shared image rather than split into an api/worker-specific Dockerfile
# for simplicity; harmless for the api service, which never calls it.
ARG CLUSTERCTL_VERSION=v1.14.0
RUN curl -sL "https://github.com/kubernetes-sigs/cluster-api/releases/download/${CLUSTERCTL_VERSION}/clusterctl-linux-amd64" \
    -o /usr/local/bin/clusterctl \
    && chmod +x /usr/local/bin/clusterctl

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
# Baked into the image so the container is self-contained wherever it
# runs (a Kubernetes Deployment has no host filesystem to volume-mount
# this from, unlike docker-compose's dev-convenience bind mount --
# see yaml_generator.py's _env(), which looks for /templates first and
# only falls back to TEMPLATES_DIR if that path doesn't exist).
COPY templates /templates

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
