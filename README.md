# metal3-deploy-k8s-backend

Automation layer on top of the upstream **[metal3-io](https://github.com/metal3-io)**
stack (baremetal-operator + Ironic + Cluster API Provider Metal3), built to
replace shell-script-driven deployment (`ccdadm cluster bootstrap` +
hand-edited `bmh.yaml` / `k8s-config.yaml` / `eph-net.yaml`) with an API +
async task pipeline. This is the **backend only** -- it's designed to be
driven by a frontend (asset picker, pool builder, deployment dashboard)
that doesn't exist yet.

What upstream project each service wraps:

| This service | Upstream metal3-io component |
|---|---|
| `services/metal3.py` | **baremetal-operator** (`BareMetalHost` CRD) -- registration, power state, and reading Ironic's inspection results off `status.hardware` |
| `services/introspection.py` | **Ironic** -- turns its inspection/introspection data into structured hardware inventory instead of the operator reading it off a dashboard |
| `services/capi.py` | **Cluster API Provider Metal3 (CAPM3)** -- `Cluster` / `Metal3Cluster` / `KubeadmControlPlane` / `Metal3MachineTemplate` / `MachineDeployment` |
| `services/asset_planner.py` + `cpu_topology.py` | not upstream -- this project's own layer that turns *picked hardware* into the manifests those CRDs need (NIC PCI addresses -> bond config, CPU topology -> `reserved-cpus` string, disks -> root device hints / Ceph OSD filters) |

### Hardware-driven manifest generation (no more hand-typed YAML)

1. A `BareMetalHost` gets created (via `POST /baremetalhosts`) and Ironic inspects it.
2. `POST /hardware-assets/{id}/sync-from-ironic` pulls the inspected CPU/RAM/NIC/disk data off `BMH.status.hardware` into a `HardwareAsset` row. Pass Ironic's raw introspection `inventory` too if you have it (webhook/API), since `status.hardware` alone doesn't include NIC PCI address or NUMA node, and the network/CPU config genuinely needs those.
3. In the (future) frontend, an operator picks assets from that inventory and assigns them to a cluster's pool via `POST /clusters/{id}/pools/{pool}/assign`, choosing: role (control-plane/worker), **cores reserved per socket** (this is what "CPU 预留" turns into), hugepage size/count, and NIC role overrides if the auto-detected bonding grouping is wrong.
4. `POST /clusters/{id}/manifests/generate` renders `bmh.yaml`, the CAPI `k8s-config.yaml`-equivalent, and per-node NIC bonding policy -- all derived from the picked hardware, with zero hand-typed PCI addresses or `reserved_cpus` strings.

`reserved_cpus` is computed from the asset's real socket/core/thread topology (`services/cpu_topology.py`) using the same hyperthread-sibling-pairing convention as the existing production config -- e.g. 2 sockets × 32 cores × SMT2, reserving 4 cores/socket, reproduces `0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99` exactly (see `tests/test_asset_planner.py`).

It also still exposes:

* Jinja2 templates (`/templates`) rendering `bmh.yaml` / cluster config / network policy from structured input directly, for cases where you don't want to go through the asset-picker flow
* services that apply the rendered manifests to the management cluster via the Kubernetes API (not `kubectl apply -f`)
* a Celery worker that drives a deployment through its phases and streams progress over a WebSocket

## ⚠️ Before you do anything else: secrets

The files you're using as source material (`bmh.yaml`/`bmhosts.yaml`,
`k8s-config.yaml`/`ccdadm-config.yaml`) contain **live secrets** --
SSH private keys, the cluster's CA private key, an LDAP bind password,
a console password hash, registry/webhook passwords, etc.

Before this project (or any tooling) touches these files:

1. **Rotate every credential in them.** Anything that has ever been pasted into a chat, ticket, or repo should be treated as compromised.
2. Never commit them, or a `.env` with real values, to git. This repo's `.gitignore`-worthy paths: `.env`, `deploy/kubeconfig/config`, any `*.pem`/`*-key`.
3. This service intentionally never stores BMC/SSH/CA secrets in its own database -- it only stores a *reference* (a Kubernetes Secret name). Keep it that way if you extend it.
4. Use a real secret manager (Vault, SOPS + git, k8s External Secrets, etc.) for anything currently living as plaintext in your YAML files.

## Architecture

```
FastAPI (backend/app)
 ├─ api/            HTTP + WebSocket routes
 ├─ core/           config, db session, auth, logging
 ├─ models/         SQLAlchemy models (Cluster, BareMetalHost, Machine, Deployment,
 │                HardwareAsset, NodePoolAssignment)
 ├─ schemas/        Pydantic request/response models
 ├─ services/
 │   ├─ kubernetes.py   generic k8s client wrapper (Secrets + Custom Objects)
 │   ├─ bmc.py           BMC credential -> k8s Secret handling
 │   ├─ metal3.py        BareMetalHost lifecycle (register/power/import)
 │   ├─ capi.py          Cluster API + Metal3 CRs for the target cluster
 │   ├─ introspection.py  Ironic hardware data -> HardwareAsset fields
 │   ├─ cpu_topology.py   reserved-cpus / hugepage math from socket/core topology
 │   ├─ asset_planner.py  HardwareAsset + NodePoolAssignment -> rendered YAML bundle
 │   └─ yaml_generator.py Jinja2 rendering of bmh.yaml / k8s-config.yaml / eph-net.yaml
 ├─ tasks/          Celery task orchestrating a full deployment
 └─ websocket/      broadcasts deployment progress to connected clients

templates/          the Jinja2 sources for the three YAML artefacts
deploy/             docker-compose asset references, postgres init, redis conf, kubeconfig mount point
scripts/            install.sh / start.sh
frontend/           React + Vite + TypeScript console (see "Frontend" below)
```

### Deployment flow (`POST /api/v1/deployments`)

1. `generating_manifests` – validate/render Cluster API manifests from the cluster spec
2. `bootstrapping_ephemeral_node` – assumes the ephemeral PXE node's single-node management cluster (Metal3 + CAPI) is already reachable via `MGMT_KUBECONFIG_PATH` (that bootstrap itself is SDI3/netconf + kubeadm territory and out of scope for this service today)
3. `applying_bmh` / `waiting_for_hosts` – confirms registered `BareMetalHost` objects reach `available`
4. `applying_cluster` – applies `Cluster` / `Metal3Cluster` / `KubeadmControlPlane` / `Metal3MachineTemplate` / `MachineDeployment`
5. `waiting_for_control_plane` – polls the CAPI `Cluster` status for `ControlPlaneReady`
6. `installing_addons` – extension point for Helm/kubectl-driven addons (calico, ceph, ecfe, apigateway, pm, dex, ...)
7. `complete` / `failed`

Progress is broadcast over `GET /api/v1/deployments/{id}/ws`.

## Quick start

```bash
cp .env.example .env            # edit values
./scripts/install.sh
# put your management-cluster kubeconfig at deploy/kubeconfig/config
./scripts/start.sh
# API docs:  http://localhost:8000/docs
# Console:   http://localhost:8080
```

For step-by-step setup see **[INSTALL.md](./INSTALL.md)**; for a full
API walkthrough (register hardware, assign it to pools with CPU
reservation, generate manifests, deploy, watch progress) see
**[USAGE.md](./USAGE.md)**. Both are written in Chinese for this team.

## Frontend

`frontend/` is a real React + Vite + TypeScript console (KubeSphere-style:
dark sidebar nav, card dashboard, resource tables, an app-catalog page),
built directly against the API above:

- **概览 Dashboard** — cluster/asset/deployment counts, recent activity
- **集群管理 Clusters** — create clusters; detail page with 节点池/清单/部署 tabs
- **硬件资产 Hardware Assets** — rack-view or table view of inventory; a drawer to sync from Ironic and fix NIC/disk roles; the pool-assignment modal renders a live **CPU core map** (a literal reserved-vs-isolated core grid, computed client-side with the same math as `cpu_topology.py`) as you drag the reserved-cores-per-socket slider
- **裸金属主机 Bare Metal Hosts** — register BMHs, power on/off
- **部署任务 Deployments** — trigger a deployment, watch phases update live over the WebSocket
- **应用目录 App Catalog** — reference catalog of this platform's addons (calico/ceph/ecfe/apigateway/pm/dex/...); Ingress has been dropped in favor of the Gateway API. Cross-referenced against a selected cluster's configured addons

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
```

Or via docker-compose (see below) at `http://localhost:8080`, reverse-proxied through nginx to the API on the same origin.

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/clusters` | Define a target cluster spec |
| POST | `/api/v1/baremetalhosts` | Register one BMH (writes BMC creds to a k8s Secret) |
| POST | `/api/v1/baremetalhosts/bulk-import` | Register many hosts at once |
| POST | `/api/v1/baremetalhosts/{name}/power?online=true` | Power on/off via Metal3 |
| POST | `/api/v1/manifests/bmh` | Render `bmh.yaml` from JSON, without applying it |
| POST | `/api/v1/manifests/cluster-config` | Render CAPI/Metal3 `k8s-config.yaml`-equivalent |
| POST | `/api/v1/manifests/eph-net` | Render the ephemeral node's `eph-net.yaml`-equivalent |
| GET | `/api/v1/deployments?cluster_id=` | List deployments, optionally filtered by cluster |
| POST | `/api/v1/deployments` | Kick off a full cluster deployment |
| WS | `/api/v1/deployments/{id}/ws` | Live progress stream |
| POST | `/api/v1/hardware-assets/{id}/sync-from-ironic` | Pull CPU/RAM/NIC/disk data from an inspected BMH |
| GET | `/api/v1/hardware-assets?status=available` | Inventory for the asset picker UI |
| PATCH | `/api/v1/hardware-assets/{id}` | Correct NIC/disk role assignment |
| POST | `/api/v1/clusters/{id}/pools/{pool}/assign` | Assign picked hardware to a pool + set CPU reservation/hugepages |
| GET | `/api/v1/clusters/{id}/pools` | Current pool composition + computed `reserved_cpus` per asset |
| POST | `/api/v1/clusters/{id}/manifests/generate` | Render bmh.yaml/cluster-config/network-policies from assigned hardware |

## What's stubbed vs. real

Real: FastAPI app, DB models/migrations via `create_all`, k8s client wrapper,
BMH/CAPI manifest generation and apply logic, Celery task skeleton, tests
for manifest rendering, and a working React frontend wired to all of the
above (verified end-to-end against a live backend, not just built).

Intentionally left as extension points (environment-specific, can't be
guessed generically): the ephemeral node's own PXE/SDI3 bootstrap sequence,
the addon-install step, and auth wiring to your real IdP (LDAP/Dex) --
there's currently no login screen because nothing in the API enforces auth
yet either; add both together.

## Tests

```bash
pip install -r backend/requirements.txt pytest httpx aiosqlite ruff
make test
```
