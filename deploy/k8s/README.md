# In-cluster deployment (recommended)

Runs the API/worker as pods **inside the management cluster itself**
(the one running Metal3 + Cluster API), authenticating with this pod's own
ServiceAccount instead of a mounted kubeconfig file. This is the
deployment model this project actually recommends -- see the root
`INSTALL.md` for why a mounted-kubeconfig setup (docker-compose, running
this on some other host) can't be made "automatic": a kubeconfig only
exists once a real cluster does, so something manual (or separately
automated, outside this project's scope) always has to produce one for
any *external* deployment. In-cluster sidesteps that entirely.

## What's here

| File | Purpose |
|---|---|
| `namespace.yaml` | Only needed if `metal3` namespace doesn't already exist |
| `serviceaccount.yaml` | Identity the pods run as |
| `rbac.yaml` | Role + RoleBinding, scoped to exactly the API groups/kinds this code calls (BareMetalHost, Cluster API core + Metal3/OpenStack/vSphere/KubeVirt infrastructure providers, Secrets) -- not a blanket `edit`/`cluster-admin` grant |
| `configmap.yaml` | Non-secret settings |
| `secret.yaml.example` | Template for `SECRET_KEY`/`ADMIN_PASSWORD`/`DATABASE_URL`/etc -- `generate-secret.sh` fills this in for you |
| `generate-secret.sh` | Generates `secret.yaml` from the template with real, random `SECRET_KEY`/`BMC_ENCRYPTION_KEY`/`POSTGRES_PASSWORD` values -- nothing to hand-type or think up |
| `deployment-api.yaml` | The FastAPI service + its ClusterIP Service |
| `deployment-worker.yaml` | The Celery worker (same image, different command) |
| `postgres.yaml` / `redis.yaml` | Optional dev-grade fallback if you don't already have managed Postgres/Redis reachable from this cluster |
| `kustomization.yaml` | Ties the above together (minus `secret.yaml`, applied separately) |

## Build and push the image

The Dockerfile's build context is the **project root** (not `backend/`)
because it bakes `templates/` into the image too -- a Kubernetes
Deployment has no host filesystem to volume-mount that from the way
docker-compose's dev setup does:

```bash
cd metal3-deploy-k8s-backend   # project root
docker build -f backend/Dockerfile -t <your-registry>/metal3-deploy-api:latest .
docker push <your-registry>/metal3-deploy-api:latest
```

If you're running the addon catalog's `cr-registry` (in-cluster OCI
registry) on this same platform, that's a natural place to push to --
just make sure the node/pod can actually resolve and pull from it.

Then point both `deployment-api.yaml` and `deployment-worker.yaml`'s
`image:` field at what you pushed (same image, different `command:` for
the worker).

## Apply

```bash
kubectl apply -k deploy/k8s/          # namespace, RBAC, configmap, deployments
./deploy/k8s/generate-secret.sh       # writes secret.yaml with real, random secrets already filled in
kubectl apply -f deploy/k8s/secret.yaml
kubectl rollout restart deployment/metal3-deploy-api deployment/metal3-deploy-worker -n metal3
```

If you already have managed Postgres/Redis, remove `postgres.yaml` /
`redis.yaml` from `kustomization.yaml`'s `resources:` list first and point
`DATABASE_URL`/`REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` in
`secret.yaml` at your real endpoints instead.

## Verify

```bash
kubectl get pods -n metal3 -l app=metal3-deploy-api
kubectl logs -n metal3 deploy/metal3-deploy-api | grep -A5 "Seeded initial admin"
kubectl exec -n metal3 deploy/metal3-deploy-api -- curl -s localhost:8000/readyz
```

No kubeconfig file anywhere in this flow -- the pod authenticates as
itself. If you get `403 Forbidden` errors calling the Kubernetes API
(visible in `kubectl logs`), it means some CRD this code needs isn't
covered by `rbac.yaml` -- most likely because you're using an
infrastructure provider (or a CAPI/Metal3 version) whose CRD group/kind
doesn't match what's listed there. Add it and re-apply.

## Exposing the API/console outside the cluster

`deployment-api.yaml`'s Service is `ClusterIP` (internal only) on
purpose -- how you expose it (Ingress-replacement Gateway API route,
NodePort, LoadBalancer, port-forward for testing) depends on what's
already running on your management cluster and is left to you rather than
guessed at here. `kubectl port-forward -n metal3 svc/metal3-deploy-api 8000:8000`
is the fastest way to poke at it while setting this up.
