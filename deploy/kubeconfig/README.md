Place the management-cluster kubeconfig here as `config` (never commit a
real one). `docker-compose.yml` mounts this directory read-only into the
api/worker containers at `/secrets/kubeconfig`.
