# metal3-deploy-k8s-backend

Automation layer on top of Cluster API, built to replace shell-script-driven
deployment (`ccdadm cluster bootstrap` + hand-edited `bmh.yaml` /
`k8s-config.yaml` / `eph-net.yaml`) with an API + async task pipeline, plus
a React console (`frontend/`) driving it.

**Supports four Cluster API infrastructure providers**, selected per-cluster
via `infrastructure_provider`:

| Provider | Upstream CAPI project | What it targets |
|---|---|---|
| `metal3` (default) | **[metal3-io](https://github.com/metal3-io)** (baremetal-operator + Ironic + CAPM3) | bare metal, via the hardware-asset picker flow below |
| `openstack` | Cluster API Provider OpenStack (CAPO) | VMs on an existing OpenStack cloud |
| `vsphere` | Cluster API Provider vSphere (CAPV) | VMs on vCenter |
| `kubevirt` | Cluster API Provider KubeVirt (CAPK) | VMs as KubeVirt VirtualMachines inside an existing (KubeVirt-enabled) management cluster -- the generic answer for "any KVM/libvirt substrate" |

Only `metal3` has real physical hardware to pick (NIC PCI addresses, CPU
topology, disk roles) -- the other three are VM-based, so their worker
pools are just `{name, count, flavor, image}` declared directly at cluster
creation, no asset picker involved. See `templates/capi/providers/*.yaml.j2`
for what each one renders, and their NOTE comments for the very real
caveat that CAPO/CAPV/CAPK's CRD fields shift between versions and this
project has no live OpenStack/vSphere/KubeVirt cluster to validate
against -- only the `metal3` path has been exercised against anything
resembling real infrastructure semantics (Ironic's actual data shapes,
etc.); the other three are verified for correct manifest structure and
API wiring (see `tests/test_cloud_providers.py`), not verified to
actually bring up a healthy cluster on real OpenStack/vSphere/KubeVirt.

What upstream project each metal3-path service wraps:

| This service | Upstream metal3-io component |
|---|---|
| `services/metal3.py` | **baremetal-operator** (`BareMetalHost` CRD) -- registration, power state, and reading Ironic's inspection results off `status.hardware` |
| `services/introspection.py` | **Ironic** -- turns its inspection/introspection data into structured hardware inventory instead of the operator reading it off a dashboard |
| `services/capi.py` | **Cluster API** generically -- `render_manifests`/`apply_cluster` don't know or care which provider they're rendering for, see `services/yaml_generator.PROVIDER_TEMPLATES` |
| `services/asset_planner.py` + `cpu_topology.py` | not upstream -- this project's own layer that turns *picked hardware* into the manifests CAPM3 needs (NIC PCI addresses -> bond config, CPU topology -> `reserved-cpus` string, disks -> root device hints / Ceph OSD filters) |
| `services/cloud_planner.py` | not upstream -- the equivalent layer for the three VM-based providers, much simpler since there's no physical hardware to reconcile |

### Hardware-driven manifest generation (metal3 provider -- no hand-typed YAML)

1. A `BareMetalHost` gets created (via `POST /baremetalhosts`) and Ironic inspects it.
2. `POST /hardware-assets/{id}/sync-from-ironic` pulls the inspected CPU/RAM/NIC/disk data off `BMH.status.hardware` into a `HardwareAsset` row. Pass Ironic's raw introspection `inventory` too if you have it (webhook/API), since `status.hardware` alone doesn't include NIC PCI address or NUMA node, and the network/CPU config genuinely needs those.
3. In the console (or via the API), an operator picks assets from that inventory and assigns them to a cluster's pool via `POST /clusters/{id}/pools/{pool}/assign`, choosing: role (control-plane/worker), **cores reserved per socket** (this is what "CPU 预留" turns into), hugepage size/count, and NIC role overrides if the auto-detected bonding grouping is wrong.
4. `POST /clusters/{id}/manifests/generate` renders `bmh.yaml`, the CAPI `k8s-config.yaml`-equivalent, and per-node NIC bonding policy -- all derived from the picked hardware, with zero hand-typed PCI addresses or `reserved_cpus` strings.

`reserved_cpus` is computed from the asset's real socket/core/thread topology (`services/cpu_topology.py`) using the same hyperthread-sibling-pairing convention as the existing production config -- e.g. 2 sockets × 32 cores × SMT2, reserving 4 cores/socket, reproduces `0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99` exactly (see `tests/test_asset_planner.py`).

**Assigning a role="control-plane" pool with exactly one asset and no
worker pools is a genuine single-node target cluster**: `control_plane_count`
gets derived from the actual assignment (not whatever the cluster was
created with), and the control-plane's `NoSchedule` taint is automatically
dropped so the one node can run workloads too. This is the "PXE-booted
ephemeral node bootstraps a single-node management cluster, which deploys
the target cluster" flow -- see `tests/test_asset_planner.py`'s
control-plane tests and `tests/test_deployment_tasks.py` for the full
orchestration run.

It also still exposes:

* Jinja2 templates (`/templates`) rendering `bmh.yaml` / cluster config / network policy from structured input directly, for cases where you don't want to go through the asset-picker flow
* services that apply the rendered manifests to the management cluster via the Kubernetes API (not `kubectl apply -f`)
* a Celery worker that drives a deployment through its phases and streams progress over a WebSocket

## ⚠️ Before you do anything else: secrets

If you're bootstrapping this from existing `bmhosts.yaml`/cluster-config-style
files that already have real BMC credentials, SSH private keys, a
cluster CA private key, LDAP bind passwords, or console password
hashes baked in, treat all of that as **compromised the moment it left
its original, access-controlled location** -- pasted into a chat,
committed to a repo, attached to a ticket, whatever.

Before this project (or any tooling) touches files like that:

1. **Rotate every credential in them.**
2. Never commit them, or a `.env` with real values, to git. This repo's `.gitignore`-worthy paths: `.env`, `deploy/kubeconfig/config`, any `*.pem`/`*-key`.
3. **BMC passwords are stored encrypted in this app's own database** (Fernet symmetric encryption, `services/crypto.py`) so an operator can recreate a deleted/rotated Kubernetes Secret without re-typing the password (`POST /hardware-assets/{id}/resync-bmc-secret`). This is NOT the same as storing them in plaintext or base64: the encryption key (`BMC_ENCRYPTION_KEY`) lives outside this database entirely (env var / mounted Secret), and no API response ever returns the password, encrypted or plain -- only a `has_bmc_credentials` boolean. SSH private keys and any cluster CA private key are a different matter and are NOT covered by this mechanism -- don't extend it to those without separately deciding that's the right call.
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
6. `installing_addons` – extension point for Helm/kubectl-driven addons (calico, ceph, bgp-lb, apigateway, pm, dex, ...)
7. `complete` / `failed`

Progress is broadcast over `GET /api/v1/deployments/{id}/ws`.

## Quick start

**Two deployment models** -- pick one:

- **In-cluster (recommended for real use)**: run the api/worker as pods inside the management cluster itself, authenticating via the pod's own ServiceAccount -- no kubeconfig file needed anywhere. See **[deploy/k8s/README.md](./deploy/k8s/README.md)**.
- **docker-compose (local dev/test)**: runs on a separate host, needs a kubeconfig for the management cluster copied in manually (this can't be automated -- a kubeconfig only exists once a real cluster does):

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
- **应用目录 App Catalog** — reference catalog of this platform's addons (calico/ceph/bgp-lb/apigateway/pm/dex/...); Ingress has been dropped in favor of the Gateway API. Cross-referenced against a selected cluster's configured addons

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to localhost:8000
```

Or via docker-compose (see below) at `http://localhost:8080`, reverse-proxied through nginx to the API on the same origin.

## Key endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/clusters` | Define a target cluster spec (set `infrastructure_provider` here: `metal3`\|`openstack`\|`vsphere`\|`kubevirt`) |
| POST | `/api/v1/baremetalhosts` | Register one BMH (writes BMC creds to a k8s Secret) -- metal3 only |
| POST | `/api/v1/baremetalhosts/bulk-import` | Register many hosts at once |
| POST | `/api/v1/baremetalhosts/{name}/power?online=true` | Power on/off via Metal3 |
| POST | `/api/v1/manifests/bmh` | Render `bmh.yaml` from JSON, without applying it |
| POST | `/api/v1/manifests/cluster-config` | Render CAPI `k8s-config.yaml`-equivalent for any provider |
| POST | `/api/v1/manifests/eph-net` | Render the ephemeral node's `eph-net.yaml`-equivalent |
| GET | `/api/v1/deployments?cluster_id=` | List deployments, optionally filtered by cluster |
| POST | `/api/v1/deployments` | Kick off a full cluster deployment (branches by provider internally) |
| WS | `/api/v1/deployments/{id}/ws` | Live progress stream |
| POST | `/api/v1/hardware-assets/{id}/sync-from-ironic` | Pull CPU/RAM/NIC/disk data from an inspected BMH -- metal3 only |
| GET | `/api/v1/hardware-assets?status=available` | Inventory for the asset picker UI -- metal3 only |
| PATCH | `/api/v1/hardware-assets/{id}` | Correct NIC/disk role assignment -- metal3 only |
| POST | `/api/v1/clusters/{id}/pools/{pool}/assign` | Assign picked hardware to a pool + set CPU reservation/hugepages -- metal3 only, `409`s for other providers |
| GET | `/api/v1/clusters/{id}/pools` | Current pool composition + computed `reserved_cpus` per asset -- metal3 only |
| POST | `/api/v1/clusters/{id}/manifests/generate` | Render manifests: bmh.yaml/cluster-config/network-policies from assigned hardware (metal3), or just cluster-config from declared flavor/image (other providers) |
| GET | `/api/v1/addons/catalog` | Full addon catalog (calico, kube-ovn, ceph, kubevirt, apigateway, ...) |
| POST/DELETE | `/api/v1/clusters/{id}/addons/{name}/enable`\|`disable` | Toggle an addon for a cluster |

## What's stubbed vs. real

Real: FastAPI app, DB models/migrations via `create_all`, k8s client wrapper,
BMH/CAPI manifest generation and apply logic (all four providers), Celery
task skeleton, tests for manifest rendering, a working React frontend
wired to all of the above, and username/password auth end-to-end (JWT
bearer tokens, bcrypt password hashes, a seeded admin account, and a real
login screen -- verified against a live backend, not just built).

**Verified vs. structurally-present-but-unvalidated, honestly:** the
`metal3` provider's manifest generation and orchestration state machine
have been run end-to-end repeatedly against realistic mocked K8s/Ironic
responses, including the single-node control-plane case. The `openstack`/
`vsphere`/`kubevirt` providers are verified the same way for API
contract + orchestration state machine + manifest *structure* (right
Kinds, right replica counts, `tests/test_cloud_providers.py`), but there's
no real OpenStack/vSphere/KubeVirt cluster in this environment to confirm
the manifests actually bring up a healthy cluster -- CAPO/CAPV/CAPK's
exact CRD field names shift between provider versions, so treat those
three templates as a correct starting skeleton to validate against
`kubectl explain <kind>.spec...` on your actual management cluster, not
as pre-verified production output the way the metal3 path is.

## Auth

Deliberately minimal on purpose: one flat `users` table, bcrypt-hashed
passwords, JWT bearer tokens (`core/security.py`), no SSO/MFA/lockout
policies. Every route except `/healthz`, `/readyz`, and `POST /auth/login`
requires a valid token; the frontend redirects to `/login` if it doesn't
have one and drops back to it on any `401` from the API.

The first admin account is seeded automatically on first startup (see
`services/auth.ensure_seed_admin`) -- set `ADMIN_PASSWORD` in `.env` to
control it, or leave it unset and read the generated password once from
`docker compose logs api`. Change it via `POST /api/v1/auth/change-password`
once logged in.

This is explicitly a placeholder for when you actually need real SSO --
swap `services/auth.py` + `api/auth.py` for your IdP (this platform's own
Dex/LDAP is a natural fit, since it already exists in the addon catalog)
when this stops being "internal test environment only". The JWT session
mechanism (`core/security.py`, the frontend's `lib/auth.tsx`) stays the
same either way -- only how the token gets issued changes.

Intentionally still left as extension points (environment-specific, can't
be guessed generically): the ephemeral node's own PXE/SDI3 bootstrap
sequence, and the addon-install step.

## BMC credential storage

**This is a login password (hashed, one-way, never recovered) vs. a BMC
password (has to come back out as plaintext eventually, because this app
hands it to Kubernetes as a Secret value) are fundamentally different
problems, using fundamentally different primitives.** BMC credentials are
encrypted with Fernet (`services/crypto.py`, `cryptography.fernet`) --
*not* hashed, and definitely not base64 (base64 is an encoding with no
key at all; anyone with the ciphertext reverses it in one line, no secret
required -- it provides zero confidentiality and should never be
mistaken for encryption).

- `BMC_ENCRYPTION_KEY` must be set outside this database (env var /
  mounted Secret / KMS). Generate one with:
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- Registering a BMH (`POST /baremetalhosts`) encrypts and stores the
  password automatically alongside writing the Kubernetes Secret (which
  is still what baremetal-operator actually reads from -- this database
  is not a second live copy Ironic depends on, it's how *this app* can
  recreate that Secret later without asking anyone to re-type the
  password).
- No API response, ever, contains the plaintext password or the
  ciphertext -- `HardwareAssetRead` only exposes `has_bmc_credentials: bool`.
  `POST /hardware-assets/{id}/resync-bmc-secret` decrypts server-side and
  re-writes the Secret; the password itself never travels back to the
  caller.
- `BMC_ENCRYPTION_KEY` is comma-separatable for key rotation (newest
  first) -- see `services/crypto.rotate_key` and its docstring for the
  actual rotation procedure. Losing the key entirely means every
  previously-encrypted credential becomes permanently unrecoverable by
  design; there is no backdoor.

## Tests

```bash
pip install -r backend/requirements.txt pytest httpx aiosqlite ruff
make test
```
