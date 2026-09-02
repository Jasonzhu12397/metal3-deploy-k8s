# Real upstream CRD schemas, snapshotted for schema validation tests

These are the actual `CustomResourceDefinition` YAML files from the real
upstream projects -- not hand-written approximations. `tests/test_manifest_schema_validation.py`
extracts each one's `openAPIV3Schema` and validates every manifest this
project's `YamlGeneratorService` actually renders against it, catching
things no amount of "is this valid YAML" testing ever would (e.g. a
field with the right name but wrong type, or a value that's `null` when
Kubernetes actually requires a string there).

## Where these came from (as of 2026-09-02)

Kubernetes-native (CAPI core) resources are `deprecated: true` at
`v1beta1` as of CAPI v1.11.0 (`v1beta2` is now the storage/primary
version) -- these were fetched at `v1beta1` because that's what this
project's templates currently target and what real CAPI/CAPM3 installs
still `served: true` at that version as of the CAPM3 compatibility
matrix checked the same day (CAPM3 v1.12.x pairs with CAPI v1beta1;
CAPM3 v1.13.x has moved to v1beta2). Migrating this project's templates
to v1beta2 is tracked separately -- see README's "Known API version debt"
section.

| File | Fetched from |
|---|---|
| `cluster.yaml` | `kubernetes-sigs/cluster-api` @ `v1.11.0`, `config/crd/bases/cluster.x-k8s.io_clusters.yaml` |
| `machinedeployment.yaml` | same repo/tag, `cluster.x-k8s.io_machinedeployments.yaml` |
| `kubeadmcontrolplane.yaml` | same repo/tag, `controlplane/kubeadm/config/crd/bases/controlplane.cluster.x-k8s.io_kubeadmcontrolplanes.yaml` |
| `kubeadmconfigtemplate.yaml` | same repo/tag, `bootstrap/kubeadm/config/crd/bases/bootstrap.cluster.x-k8s.io_kubeadmconfigtemplates.yaml` |
| `metal3cluster.yaml` | `metal3-io/cluster-api-provider-metal3` @ `main`, `config/crd/bases/infrastructure.cluster.x-k8s.io_metal3clusters.yaml` |
| `metal3machinetemplate.yaml` | same repo, `infrastructure.cluster.x-k8s.io_metal3machinetemplates.yaml` |
| `baremetalhost.yaml` | `metal3-io/baremetal-operator` @ `main`, `config/base/crds/bases/metal3.io_baremetalhosts.yaml` |

## Refreshing these

Upstream schemas change (new fields, new enum values, new required
fields). Re-download periodically, or when a validation failure looks
like it might be about a schema change rather than a real bug:

```bash
curl -sL "https://raw.githubusercontent.com/kubernetes-sigs/cluster-api/v1.11.0/config/crd/bases/cluster.x-k8s.io_clusters.yaml" -o cluster.yaml
# ...same pattern for the others, see the table above for exact paths
```

Metal3's CRD paths in particular have moved before (baremetal-operator's
CRDs used to live at a different path than `config/base/crds/bases/`) --
if a URL 404s, check the repo's current directory structure rather than
assuming the file was removed.
