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

# kubectl + helm -- used by the worker for services/addons.py's addon
# installer (kubectl apply for manifest-style addons like KubeVirt, helm
# upgrade --install for chart-style addons like Kube-OVN). Real,
# official install methods (dl.k8s.io / get.helm.sh, the same sources
# their own docs point at) -- NOT verified as actually downloading
# successfully in the sandbox this project was developed in, unlike
# clusterctl/kind/k3s above: both dl.k8s.io and get.helm.sh were outside
# that sandbox's network allowlist, a constraint specific to that
# environment, not a statement about whether these URLs are correct.
ARG KUBECTL_VERSION=v1.31.4
RUN curl -sL "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    -o /usr/local/bin/kubectl \
    && chmod +x /usr/local/bin/kubectl
ARG HELM_VERSION=v3.21.4
RUN curl -sL "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" \
    | tar -xz -C /tmp \
    && mv /tmp/linux-amd64/helm /usr/local/bin/helm \
    && chmod +x /usr/local/bin/helm \
    && rm -rf /tmp/linux-amd64

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
