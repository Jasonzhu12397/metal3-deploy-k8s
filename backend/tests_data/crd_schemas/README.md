# Real upstream CRD schemas, snapshotted for schema validation tests

These are the actual `CustomResourceDefinition` YAML files from the real
upstream projects -- not hand-written approximations. `tests/test_manifest_schema_validation.py`
extracts each one's `openAPIV3Schema` and validates every manifest this
project's `YamlGeneratorService` actually renders against it, catching
things no amount of "is this valid YAML" testing ever would.

## Version status (as of 2026-09-03)

This project's templates target the **v1beta2** Cluster API contract for
every CAPI-core resource (`Cluster`, `KubeadmControlPlane`,
`MachineDeployment`, `KubeadmConfigTemplate`) across all 5 infrastructure
providers -- `v1beta1` on these types was marked `deprecated: true` as of
CAPI v1.11.0 (storage version moved to `v1beta2`). This was a real
migration, not a version-string find-and-replace: v1beta2 restructured
`infrastructureRef`/`controlPlaneRef`/`configRef` from
`{apiVersion, kind, name}` to `{apiGroup, kind, name}` (no version at
all -- the controller looks it up from the target CRD's own contract
labels), and `kubeletExtraArgs`/`apiServer.extraArgs` from a map to a
list of `{name, value}` objects. See
`templates/capi/cluster-template.yaml.j2`'s header comment for the full
detail.

Per-provider status for the provider-*specific* resources (as opposed to
the CAPI-core resources shared by all 5, which are ALL on v1beta2 now):

| Provider | Infra-specific resources | Version used | Why |
|---|---|---|---|
| Metal3 | `Metal3Cluster`, `Metal3MachineTemplate` | **v1beta2** | CAPM3 v1.13.x moved to v1beta2; verified field-level changes (`noCloudProvider`->`cloudProviderEnabled`, `format`->`diskFormat`, `checksum` became required) against the real v1.13.2 CRD. |
| Docker (CAPD) | `DockerCluster`, `DockerMachineTemplate` | **v1beta2** | Ships in the same repo/release as CAPI core; v1beta2 confirmed served+storage at the same v1.11.0 tag used for CAPI core. |
| OpenStack (CAPO) | `OpenStackCluster`, `OpenStackMachineTemplate` | v1beta1 (deliberately kept) | CAPO's own v1beta2 types are newer and still stabilizing (dual v1beta1/v1beta2 support with conversion webhooks as of recent CAPO releases). v1beta1 confirmed `served: true, storage: true` at CAPO v0.11.3 -- still the broadly-compatible choice. |
| vSphere (CAPV) | `VSphereCluster`, `VSphereMachineTemplate` | v1beta1 (deliberately kept) | CAPV's v1beta2 only landed in CAPV v1.16; the v1.13-v1.15 line (what most current installs run) is still v1beta1. Confirmed `served: true, storage: true` at CAPV v1.13.0. |
| KubeVirt (CAPK) | `KubevirtCluster`, `KubevirtMachineTemplate` | v1alpha1 (no migration exists) | CAPK has never had a v1beta1/v1beta2 for its own types -- confirmed only `v1alpha1` is served at the latest stable CAPK release (v0.1.10). Nothing to migrate to. |

`BareMetalHost` (`metal3.io/v1alpha1`) has never changed API versions in
Metal3's history and isn't affected by any of this.

## Where these came from

| File | Fetched from |
|---|---|
| `cluster.yaml` | `kubernetes-sigs/cluster-api` @ `v1.11.0`, `config/crd/bases/cluster.x-k8s.io_clusters.yaml` |
| `machinedeployment.yaml` | same repo/tag, `cluster.x-k8s.io_machinedeployments.yaml` |
| `kubeadmcontrolplane.yaml` | same repo/tag, `controlplane/kubeadm/config/crd/bases/controlplane.cluster.x-k8s.io_kubeadmcontrolplanes.yaml` |
| `kubeadmconfigtemplate.yaml` | same repo/tag, `bootstrap/kubeadm/config/crd/bases/bootstrap.cluster.x-k8s.io_kubeadmconfigtemplates.yaml` |
| `dockercluster.yaml` | same repo/tag, `test/infrastructure/docker/config/crd/bases/infrastructure.cluster.x-k8s.io_dockerclusters.yaml` |
| `dockermachinetemplate.yaml` | same repo/tag, `infrastructure.cluster.x-k8s.io_dockermachinetemplates.yaml` |
| `metal3cluster.yaml` | `metal3-io/cluster-api-provider-metal3` @ `v1.13.2`, `config/crd/bases/infrastructure.cluster.x-k8s.io_metal3clusters.yaml` |
| `metal3machinetemplate.yaml` | same repo/tag, `infrastructure.cluster.x-k8s.io_metal3machinetemplates.yaml` |
| `baremetalhost.yaml` | `metal3-io/baremetal-operator` @ `main`, `config/base/crds/bases/metal3.io_baremetalhosts.yaml` |
| `openstackcluster.yaml` | `kubernetes-sigs/cluster-api-provider-openstack` @ `v0.11.3`, `config/crd/bases/infrastructure.cluster.x-k8s.io_openstackclusters.yaml` |
| `openstackmachinetemplate.yaml` | same repo/tag, `infrastructure.cluster.x-k8s.io_openstackmachinetemplates.yaml` |
| `vspherecluster.yaml` | `kubernetes-sigs/cluster-api-provider-vsphere` @ `v1.13.0`, `config/default/crd/bases/infrastructure.cluster.x-k8s.io_vsphereclusters.yaml` |
| `vspheremachinetemplate.yaml` | same repo/tag, `infrastructure.cluster.x-k8s.io_vspheremachinetemplates.yaml` |

KubevirtCluster/KubevirtMachineTemplate schemas are NOT snapshotted here
-- since they're v1alpha1 with no v1beta1/v1beta2 alternative, and this
project's kubevirt.yaml.j2 template was never validated against them
even before this migration (only the shared CAPI-core parts of that
template are covered by these tests). Fetchable at
`kubernetes-sigs/cluster-api-provider-kubevirt` @ `v0.1.10`,
`config/crd/bases/infrastructure.cluster.x-k8s.io_kubevirtclusters.yaml`
if that coverage gets added later.

## Refreshing these

Upstream schemas change (new fields, new enum values, new required
fields, and -- as this migration itself demonstrates -- entire contract
versions). Re-download periodically, or when a validation failure looks
like it might be about a schema change rather than a real bug:

```bash
curl -sL "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api/v1.11.0/config/crd/bases/cluster.x-k8s.io_clusters.yaml" -o cluster.yaml
# ...same pattern for the others, see the table above for exact repo/tag/path
```

CRD paths move between releases (baremetal-operator's have before;
CAPV's `config/default/crd/bases/` vs. the more common
`config/crd/bases/` is one example already hit while building this) --
if a URL 404s, check the repo's current directory structure and Makefile
(`grep -i crd Makefile` usually reveals the real path) rather than
assuming the file was removed.

## Talos Linux provider CRDs (added later)

| File | Fetched from |
|---|---|
| `talos-bootstrap.yaml` | `siderolabs/cluster-api-bootstrap-provider-talos` @ `v0.6.5`, `bootstrap-components.yaml` release asset |
| `talos-controlplane.yaml` | `siderolabs/cluster-api-control-plane-provider-talos` @ `v0.5.7`, `control-plane-components.yaml` release asset |

Unlike every other CRD in this directory, these are only served at
`v1alpha3` -- confirmed against the real files, not an oversight. Talos's
own CAPI provider pair hasn't moved to v1beta1/v1beta2 the way core CAPI
and CAPM3 have; there's nothing newer to pin to yet. See
`templates/capi/providers/talos-metal3.yaml.j2`'s own header comment for
what this means for how references to these two types are structured.
