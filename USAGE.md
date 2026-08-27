# 使用手册 (USAGE)

在 `INSTALL.md` 把服务跑起来之后，这份手册讲怎么用。所有例子都是实打实能跑的 `curl`，字段名跟代码里的 Pydantic schema 一一对应（`backend/app/schemas/`）。也可以直接打开 `http://localhost:8000/docs` 用 Swagger UI 点着试，效果一样。

**现在所有接口（除了 `/healthz`、`/readyz`、`/auth/login`）都要带 token 了。** 先登录拿 token：

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "你的密码"}' | jq -r .access_token)
```

下面所有 `curl` 例子都要加上 `-H "Authorization: Bearer $TOKEN"`，为了不让每条命令都写一遍，后面就省略了——记得自己加上，不然全都是 `401`。token 默认 1 小时过期（`ACCESS_TOKEN_EXPIRE_MINUTES`），过期了重新登录一次就行。

**现在也有网页控制台了**（`http://localhost:8080`，见 `frontend/`）：登录后，新建集群、注册主机、把硬件拖进节点池并拖动滑块设置 CPU 预留（带实时核心分配预览图）、发起部署看实时进度，这些都能直接点。下面这份手册仍然按 API 调用顺序写，一是给还没做完的操作（比如批量导入）留参考，二是方便你们接自动化脚本；控制台背后调的就是这些接口，字段一一对应。

下面按真实操作顺序走一遍完整流程：**建集群 → 注册物理机 → 从 Ironic 同步硬件信息 → 把硬件分配到 pool（含 CPU 预留）→ 生成三份 YAML → 触发部署 → 看进度**。

---

## 0. 整体顺序一览

```
POST /clusters                          先定义要建的集群（名字、CIDR、控制面数量等）
POST /baremetalhosts                    注册物理机（写 BMC 凭证，Ironic 开始 inspect）
   ↓ 等 Ironic inspect 完
POST /hardware-assets/{id}/sync-from-ironic   把探测到的 CPU/内存/网卡/磁盘同步进来
PATCH /hardware-assets/{id}             （如果自动识别的网卡/磁盘角色不对，手动改）
POST /clusters/{id}/pools/{pool}/assign 把资产分配进某个 pool，设置 CPU 预留/大页
POST /clusters/{id}/manifests/generate  生成 bmh.yaml / 集群配置 / 网络策略（纯预览，不 apply）
POST /deployments                       真正开始部署（apply 到管理集群 + 跑 Celery 任务）
WS   /deployments/{id}/ws               订阅进度
```

---

## 1. 创建集群定义

**这一步先决定部署目标（`infrastructure_provider`）。** 默认是 `metal3`（裸金属，走下面第 2-5 步的硬件选择流程）。如果目标是 OpenStack/vSphere/KubeVirt，流程不一样，直接跳到本节末尾的"云 provider 建集群"，不需要走硬件资产那一套。

```bash
curl -s -X POST http://localhost:8000/api/v1/clusters \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pk-cnis-pcg",
    "namespace": "metal3",
    "control_plane_count": 3,
    "control_plane_endpoint": "10.138.165.27",
    "spec": {
      "pod_cidr": "192.168.0.0/16",
      "service_cidr": "10.96.0.0/12",
      "k8s_version": "v1.29.0"
    }
  }'
```

返回里的 `id` 后面全流程都要用，记下来：

```bash
CLUSTER_ID=$(curl -s -X POST http://localhost:8000/api/v1/clusters -H "Content-Type: application/json" -d '{...同上...}' | jq -r .id)
```

> `worker_pools` 这里先不用填 —— pool 的组成是后面靠"分配硬件资产"动态长出来的，不是在建集群时一次性写死。（这条只对 `metal3` provider 成立——云 provider 见下面。）

查看/更新/删除：

```bash
curl -s http://localhost:8000/api/v1/clusters                 # 列表
curl -s http://localhost:8000/api/v1/clusters/$CLUSTER_ID      # 详情
curl -s -X PATCH http://localhost:8000/api/v1/clusters/$CLUSTER_ID \
  -H "Content-Type: application/json" -d '{"control_plane_endpoint": "10.138.165.28"}'
```

### 1.1 云 provider 建集群（OpenStack / vSphere / KubeVirt）

跟 metal3 最大的区别：**没有物理硬件可选**，worker 池的 `flavor`/`image` 得在建集群的时候就直接写死，不走后面第 2-4 步。少了 `control_plane_flavor`/`control_plane_image`（或者某个 worker 池少了 `flavor`/`image`）会直接 `422`。

```bash
# OpenStack 例子
curl -s -X POST http://localhost:8000/api/v1/clusters \
  -H "Content-Type: application/json" \
  -d '{
    "name": "openstack-demo",
    "infrastructure_provider": "openstack",
    "control_plane_count": 3,
    "control_plane_endpoint": "10.0.0.100",
    "control_plane_flavor": "m1.large",
    "control_plane_image": "ubuntu-22.04",
    "worker_pools": [
      {"name": "pool1", "count": 3, "flavor": "m1.xlarge", "image": "ubuntu-22.04"}
    ],
    "spec": {
      "openstack": {"cloud_name": "mycloud", "external_network_id": "ext-net-uuid"}
    }
  }'
```

`vsphere`/`kubevirt`结构一样，`spec` 里换成对应的键：

```bash
# vSphere: spec.vsphere = {server, datacenter, datastore, network, resource_pool?, folder?, clone_mode?}
# KubeVirt: spec.kubevirt = {storage_class_name, control_plane_service_type?}
```

建完之后直接跳到 **第 5 步生成 YAML**（会自动只渲染 `cluster_config_yaml`，`bmh_yaml`是空字符串——云 provider 没有物理机）和 **第 6 步触发部署**。第 2/3/4 步（注册 BMH、同步硬件、分配到 pool）对云 provider 集群没有意义，调用 `/pools/{pool}/assign` 会直接收到 `409`。

⚠️ **老实说明一下限制**：OpenStack/vSphere/KubeVirt 这三份模板里的字段名是照 CAPO/CAPV/CAPK 常见的 CRD 结构写的，但这几个 provider 的 CRD 在不同版本间会变，这里没有真实的 OpenStack/vSphere/KubeVirt 环境能验证渲染出来的 YAML 真的能拉起一个健康集群——渲染逻辑和整条 orchestration 状态机是测过的（见 `tests/test_cloud_providers.py`），但"这些字段名对不对"这件事需要你们自己对着 `kubectl explain <kind>.spec...`（在装了对应 CAPI provider 的管理集群上）核对一遍。相比之下 metal3 那条路径是照着更接近真实的 Ironic/baremetal-operator 数据格式测过的，可信度更高。

---

## 2. 注册物理机（BareMetalHost）

（本节及第 3、4 步只适用于 `metal3` provider——云 provider 请看上面 1.1 节，跳到第 5 步。）

这次请求里的 BMC 凭证会立刻写成 Kubernetes Secret（Metal3 真正读密码的地方），同时**加密后**存进这个服务自己的数据库（需要提前在 `.env` 设置 `BMC_ENCRYPTION_KEY`，见 INSTALL.md）——这样以后要重建被误删的 Secret，不用再让人把密码重新输一遍。加密用的是 Fernet 对称加密，不是明文也不是 base64；接口永远不会把密码（不管是明文还是密文）返回给调用方，`GET /hardware-assets` 只会告诉你 `has_bmc_credentials: true/false`。

```bash
curl -s -X POST http://localhost:8000/api/v1/baremetalhosts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "pk-dell8-1-1-sd001-wp01",
    "node_pool_name": "pool1",
    "bmc_address": "sdi+netconf://172.18.37.1/pk-cnis-pcg-tenant/1001",
    "boot_mac_address": "b4:e9:b8:08:37:c2",
    "credentials": {
      "username": "换成真实用户名",
      "password": "换成真实密码"
    },
    "online": false,
    "disable_certificate_verification": true
  }'
```

一批机器可以用批量接口，body 是同样结构的数组包一层 `hosts`：

```bash
curl -s -X POST http://localhost:8000/api/v1/baremetalhosts/bulk-import \
  -H "Content-Type: application/json" \
  -d '{"hosts": [ {...host1...}, {...host2...} ]}'
```

查状态 / 开关机：

```bash
curl -s http://localhost:8000/api/v1/baremetalhosts/pk-dell8-1-1-sd001-wp01/status
curl -s -X POST "http://localhost:8000/api/v1/baremetalhosts/pk-dell8-1-1-sd001-wp01/power?online=true"
```

BMH apply 之后，baremetal-operator 会驱动 Ironic 去做硬件 inspection，这一步在管理集群那边跑，跟本服务无关，正常几分钟能跑完。可以用 `status` 接口轮询，直到 `provisioning.state` 变成 `inspecting` 之后再变成 `available`。

---

## 3. 把探测到的硬件同步成 HardwareAsset

**这一步是关键**：不需要手填 CPU 型号/网卡 PCI 地址/磁盘型号，直接从 Ironic 的探测结果拉。

第 2 步注册 BMH 的时候，系统已经自动帮你建好了对应的 `HardwareAsset` 壳子（`bmc_address`/`boot_mac_address`/`node_pool_name` 是从 BMH 注册请求里带过来的 —— 这几项本来就不是 Ironic 探测出来的，没必要让你重复填一遍）。直接按名字查出它的 id 就行，不用再手动 `POST /hardware-assets`：

```bash
ASSET_ID=$(curl -s http://localhost:8000/api/v1/hardware-assets | jq -r '.[] | select(.name=="pk-dell8-1-1-sd001-wp01") | .id')
```

（如果你想在物理机还没接进 BMH 流程之前就先规划硬件——比如提前建库存、还没决定 BMC 地址——`POST /hardware-assets` 这个手动建壳子的接口仍然保留，见文末"手动登记硬件"。）

等 BMH inspection 完成后，同步硬件信息：

```bash
curl -s -X POST http://localhost:8000/api/v1/hardware-assets/$ASSET_ID/sync-from-ironic
```

这一步内部做的事：读 `BareMetalHost.status.hardware`（CPU 型号/核数、内存、网卡列表、磁盘列表），映射进 `HardwareAsset`，状态改成 `available`。

**注意一个限制**：`BMH.status.hardware` 本身不带网卡的 PCI 地址和 NUMA 编号，只有网卡名（`kernel_name`）。如果你要精确控制哪张网卡走 bond_control、哪张走 SR-IOV，需要把 Ironic 原始 introspection 数据（`ironic-python-agent` 的 `inventory`，通常从 Ironic API `GET /v1/introspection/{uuid}/data` 拿，或者你们 inspection webhook 存下来的那份）一起传进去：

```bash
curl -s -X POST http://localhost:8000/api/v1/hardware-assets/$ASSET_ID/sync-from-ironic \
  -H "Content-Type: application/json" \
  -d '{"ironic_inventory": <把那份 inventory JSON 整个贴进来>}'
```

传了 `ironic_inventory` 之后，`nics[*].pci_address` / `nics[*].numa_node` 就会被正确填上，后面生成网络配置才有意义。

查一下同步结果：

```bash
curl -s http://localhost:8000/api/v1/hardware-assets/$ASSET_ID | jq
```

大概长这样（示意）：

```json
{
  "id": "...",
  "name": "pk-dell8-1-1-sd001-wp01",
  "status": "available",
  "cpu_sockets": 2,
  "cpu_cores_per_socket": 32,
  "cpu_threads_per_core": 2,
  "memory_gb": 256,
  "nics": [
    {"pci_address": "0000:02:00.0", "kernel_name": "eno1", "role": "unassigned", ...},
    {"pci_address": "0000:02:00.1", "kernel_name": "eno2", "role": "unassigned", ...},
    {"pci_address": "0000:37:00.0", "kernel_name": "enp55s0f0np0", "role": "unassigned", ...},
    {"pci_address": "0000:37:00.1", "kernel_name": "enp55s0f1np1", "role": "unassigned", ...}
  ],
  "disks": [
    {"model": "Dell BOSS-N1", "role": "unassigned", ...},
    {"model": "Dell Ent NVMe CM7 U.2 3.2TB", "role": "unassigned", ...}
  ]
}
```

### 3.1 修正网卡/磁盘角色（如果需要）

同步回来的 `role` 全是 `unassigned`。如果不手动指定，后面生成配置时会用一个位置启发式规则（第 1-2 张网卡当 control、第 3-4 张当 data、第 5-6 张当 storage、其余当 SR-IOV），**但生产环境建议明确指定**，用 `PATCH` 改：

```bash
curl -s -X PATCH http://localhost:8000/api/v1/hardware-assets/$ASSET_ID \
  -H "Content-Type: application/json" \
  -d '{
    "nics": [
      {"pci_address": "0000:02:00.0", "kernel_name": "eno1", "role": "control"},
      {"pci_address": "0000:02:00.1", "kernel_name": "eno2", "role": "control"},
      {"pci_address": "0000:37:00.0", "kernel_name": "enp55s0f0np0", "role": "data"},
      {"pci_address": "0000:37:00.1", "kernel_name": "enp55s0f1np1", "role": "data"}
    ],
    "disks": [
      {"model": "Dell BOSS-N1", "media_type": "ssd", "role": "os"},
      {"model": "Dell Ent NVMe CM7 U.2 3.2TB", "media_type": "nvme", "size_gb": 3200, "role": "ceph_osd"}
    ]
  }'
```

`role` 可选值：
- 网卡：`control`（走 bond_control，active-backup）/ `data`（走 bond_data，LACP 802.3ad）/ `storage`（走 bond_storage，LACP）/ `sriov`（独立网口，给 DPDK/高吞吐 pool 用）
- 磁盘：`os` / `ceph_osd` / `ceph_journal` / `local_storage`

### 3.2 查库存

给（未来的）前端资产选择界面用的接口：

```bash
curl -s "http://localhost:8000/api/v1/hardware-assets?status=available"
curl -s "http://localhost:8000/api/v1/hardware-assets?unassigned_only=true"
curl -s "http://localhost:8000/api/v1/hardware-assets?min_memory_gb=128"
```

对每台物理机重复第 2-3 步（注册 BMH → 建资产壳子 → 同步 → 修角色），把整个机房的库存都建起来。

### 3.3 BMC 凭证：手动设置 / 重建 Secret

大多数情况下不需要手动管这块——第 2 步注册 BMH 的时候凭证已经自动加密存好了。这两个接口是给补录/修复用的：

**手动给一个已存在的资产设置/更新 BMC 凭证**（比如这台资产不是通过 `POST /baremetalhosts` 注册的，是走"手动登记硬件"那条路建的）：

```bash
curl -s -X POST http://localhost:8000/api/v1/hardware-assets/$ASSET_ID/bmc-credentials \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "真实密码"}'
```

这个接口会同时做两件事：加密存进数据库、立刻写一份 Kubernetes Secret（跟注册 BMH 时的行为一致，两条路径不会存出两份不一样的密码）。

**重建 Kubernetes Secret**（Secret 被误删、namespace 重建过、或者你就是不确定现在是不是同步的）：

```bash
curl -s -X POST http://localhost:8000/api/v1/hardware-assets/$ASSET_ID/resync-bmc-secret
```

这个接口从数据库解密出密码，重新写一次 Secret，**响应里不会包含密码本身**——只会确认"写成功了"。如果报 `409`，说明这个资产本来就没存过凭证（比如注册的时候还没设 `BMC_ENCRYPTION_KEY`）；报 `500` 且提示解密失败，通常是密钥被换掉了但数据库里的密文还是旧密钥加密的（换密钥的正确流程见 README 的"BMC credential storage"一节，别直接把 `BMC_ENCRYPTION_KEY` 硬改，那样之前存的密码全部读不出来）。

---

## 4. 把资产分配到集群的 pool 里（这一步做 CPU 预留）

这是"选硬件部署"的核心动作：从库存里挑几台机器，丢进某个 pool，同时决定**每个 socket 预留几个核给系统用**（DPDK/CNF 场景下这个特别关键）。

```bash
curl -s -X POST "http://localhost:8000/api/v1/clusters/$CLUSTER_ID/pools/pool1/assign" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_ids": ["'"$ASSET_ID"'"],
    "role": "worker",
    "reserved_cores_per_socket": 4,
    "cpu_manager_policy": "static",
    "topology_manager_policy": "single-numa-node",
    "isolation_interrupts": true,
    "hugepage_type": "1GB",
    "hugepage_count_1gb": 16
  }'
```

返回里会直接给出算好的 `computed_reserved_cpus` 和 `computed_isolated_cpu_count`，不用自己拿计算器算超线程配对：

```json
[
  {
    "id": "...",
    "pool_name": "pool1",
    "asset_id": "...",
    "reserved_cores_per_socket": 4,
    "computed_reserved_cpus": "0,64,1,65,2,66,3,67,32,96,33,97,34,98,35,99",
    "computed_isolated_cpu_count": 112
  }
]
```

（这个换算规则：物理核按 socket 连续编号，超线程兄弟核 = 物理核号 + 总物理核数；每个 socket 预留前 N 个物理核 + 它们的兄弟核。跟你们现网配置里 `pk-cnis-pcg-secret`/`ccdadm-config.yaml` 里手写的 `reserved_cpus` 是同一套规则，算出来的结果完全一致。）

查看某个集群目前每个 pool 的组成：

```bash
curl -s "http://localhost:8000/api/v1/clusters/$CLUSTER_ID/pools" | jq
```

从 pool 里撤掉一台机器（资产状态会变回 `available`，可以重新分配）：

```bash
curl -s -X DELETE "http://localhost:8000/api/v1/clusters/$CLUSTER_ID/pools/pool1/assets/$ASSET_ID"
```

重复这一步，把 control-plane 池（`role: "control-plane"`，通常不用设 `reserved_cores_per_socket`/hugepage）和各个 worker 池都建起来。

---

## 5. 生成 YAML（先预览，不 apply）

所有分配完成后，一次性把三份东西渲染出来看看对不对：

```bash
curl -s -X POST "http://localhost:8000/api/v1/clusters/$CLUSTER_ID/manifests/generate" | jq -r
```

返回结构：

```json
{
  "bmh_yaml": "apiVersion: metal3.io/v1alpha1\nkind: BareMetalHost\n...",
  "cluster_config_yaml": "apiVersion: cluster.x-k8s.io/v1beta1\nkind: Cluster\n...",
  "network_policies": {
    "pool1/pk-dell8-1-1-sd001-wp01": "interfaces:\n  - name: 0000:02:00.0\n..."
  },
  "eph_net_yaml": null
}
```

想直接存文件看：

```bash
curl -s -X POST "http://localhost:8000/api/v1/clusters/$CLUSTER_ID/manifests/generate" \
  | jq -r '.bmh_yaml' > /tmp/bmh.yaml
```

如果这一步报 `422`，说明某个 pool 里的资产缺东西（比如没设 `bmc_address`，或者 CPU 拓扑是 0）；报 `409` 说明这个集群还没往任何 pool 分配过硬件（先做第 4 步）。

> 这一步只是渲染，**不会**改动管理集群上的任何资源。真正 apply 是下一步 `POST /deployments`。

如果你不想走"资产库存"这条完整链路，只是想临时渲染一份 YAML 看格式（比如调试模板），还有一组更底层的接口，直接传结构化 JSON，不依赖数据库里的资产/集群记录：

```bash
curl -s -X POST http://localhost:8000/api/v1/manifests/bmh \
  -H "Content-Type: application/json" \
  -d '{"hosts": [{"name": "test", "node_pool_name": "pool1", "bmc_address": "...", "secret_ref": "test-bmc-secret", "boot_mac_address": "aa:bb:cc:dd:ee:ff"}]}'
```

---

## 6. 触发真正的部署

```bash
DEPLOYMENT_ID=$(curl -s -X POST http://localhost:8000/api/v1/deployments \
  -H "Content-Type: application/json" \
  -d '{"cluster_id": "'"$CLUSTER_ID"'", "regenerate_manifests": true}' | jq -r .id)
```

这会往 Celery 丢一个任务，worker 按顺序执行（对应 `models/deployment.py` 里的 `DeploymentPhase`）：

```
queued
→ generating_manifests          渲染并校验清单
→ bootstrapping_ephemeral_node  确认能连上管理集群（eph 节点自身的 PXE 引导不归本服务管，见下方说明）
→ applying_bmh                  确认已注册的 BMH
→ waiting_for_hosts             轮询 BMH 状态直到 available（超时看 .env 里 BMH_READY_TIMEOUT）
→ applying_cluster               apply Cluster/Metal3Cluster/KubeadmControlPlane/MachineDeployment
→ waiting_for_control_plane      轮询直到 ControlPlaneReady（超时看 CLUSTER_PROVISION_TIMEOUT）
→ installing_addons              预留的扩展点，addon 安装逻辑要自己接
→ complete / failed
```

> **eph 节点本身的 PXE/SDI3 引导**这一步（对应你们现有流程里 `ccdadm cluster bootstrap` 那条命令）环境相关性太强，这个服务假设它已经跑完，`MGMT_KUBECONFIG_PATH` 已经指向那个跑起来的单节点管理集群。这个服务接手的是"管理集群已经可访问"之后的事。

查当前状态：

```bash
curl -s http://localhost:8000/api/v1/deployments/$DEPLOYMENT_ID | jq
```

失败了看 `error_message` 字段。

---

## 7. 订阅实时进度（WebSocket）

命令行用 `websocat`（或者随便一个 WS 客户端）：

```bash
websocat "ws://localhost:8000/api/v1/deployments/$DEPLOYMENT_ID/ws"
```

会收到一串 JSON 事件：

```json
{"phase": "waiting_for_hosts", "message": "polling BMH state"}
{"phase": "applying_cluster", "message": "applying Cluster API resources"}
{"phase": "waiting_for_control_plane", "message": "waiting for KubeadmControlPlane to report Ready"}
{"phase": "complete", "message": "deployment complete"}
```

前端要接的话就是照这个格式，`onmessage` 里 `JSON.parse` 完直接更新进度条/时间线组件。

---

## 8. 电源管理

单独开关某台机器（不走 deployment 流程）：

```bash
curl -s -X POST http://localhost:8000/api/v1/bmc/pk-dell8-1-1-sd001-wp01/power/on
curl -s -X POST http://localhost:8000/api/v1/bmc/pk-dell8-1-1-sd001-wp01/power/off
curl -s -X POST http://localhost:8000/api/v1/bmc/pk-dell8-1-1-sd001-wp01/power/reboot
```

底层还是走 `BareMetalHost.spec.online`，Metal3 的 baremetal-operator 负责真正调 BMC，这层只是改期望状态，不直接连 BMC。

---

## 9. 查某个集群的 Machine 列表

集群 apply 之后，CAPI 会为每个 pool 拉起对应数量的 `Machine`：

```bash
curl -s "http://localhost:8000/api/v1/machines?cluster_name=pk-cnis-pcg&namespace=metal3"
```

---

## 10. 完整脚本示例（单节点 pool，从零到生成 YAML）

把上面串起来，方便直接复制改：

```bash
#!/usr/bin/env bash
set -euo pipefail
API=http://localhost:8000/api/v1

CLUSTER_ID=$(curl -s -X POST $API/clusters -H "Content-Type: application/json" -d '{
  "name": "demo-cluster", "namespace": "metal3", "control_plane_count": 3,
  "control_plane_endpoint": "10.0.0.10"
}' | jq -r .id)
echo "cluster: $CLUSTER_ID"

curl -s -X POST $API/baremetalhosts -H "Content-Type: application/json" -d '{
  "name": "worker-01", "node_pool_name": "pool1",
  "bmc_address": "redfish://192.168.1.10/redfish/v1/Systems/1",
  "boot_mac_address": "aa:bb:cc:dd:ee:01",
  "credentials": {"username": "admin", "password": "CHANGE_ME"}
}'

ASSET_ID=$(curl -s $API/hardware-assets | jq -r '.[] | select(.name=="worker-01") | .id')

# 等 Ironic inspect 完再跑：
curl -s -X POST $API/hardware-assets/$ASSET_ID/sync-from-ironic

curl -s -X POST $API/clusters/$CLUSTER_ID/pools/pool1/assign \
  -H "Content-Type: application/json" -d '{
    "asset_ids": ["'"$ASSET_ID"'"],
    "reserved_cores_per_socket": 4,
    "hugepage_count_1gb": 16
  }'

curl -s -X POST $API/clusters/$CLUSTER_ID/manifests/generate | jq -r '.cluster_config_yaml'
```

---

## 附：手动登记硬件（不经过 BMH 注册流程）

如果要在物理机还没接进 Metal3/Ironic 流程之前先做规划（比如库存管理、提前排产），可以直接手建一个 `HardwareAsset`，不需要先有 BMH：

```bash
curl -s -X POST http://localhost:8000/api/v1/hardware-assets \
  -H "Content-Type: application/json" \
  -d '{
    "name": "future-node-01",
    "vendor": "Dell", "model": "PowerEdge R660",
    "cpu_sockets": 2, "cpu_cores_per_socket": 32, "cpu_threads_per_core": 2,
    "memory_gb": 256
  }'
```

注意：这样手建的资产要走 `POST /clusters/{id}/manifests/generate` 生成 `bmh.yaml`，必须自己后续用 `PATCH /hardware-assets/{id}` 把 `bmc_address`/`boot_mac_address` 补上（正常流程下这两项是第 2 步注册 BMH 时自动带上的，手建的资产没有这一步）。

---

## 常见报错对照表

| 报错 | 原因 | 处理 |
|---|---|---|
| `401 Not authenticated` | 忘了带 `Authorization: Bearer <token>` | 先 `POST /auth/login` 拿 token |
| `401 Invalid or expired token` | token 过期（默认 1 小时）或者 `SECRET_KEY` 被改过 | 重新登录一次 |
| `409 Cluster 'xxx' already exists` | 集群名重复 | 换名字或先 `GET /clusters` 确认是不是已经建过 |
| `404 BareMetalHost not found`（开关机时） | BMH 还没 apply 成功，或名字打错 | 先 `GET /baremetalhosts/{name}/status` 确认存在 |
| `409 ... status.hardware yet -- inspection incomplete`（sync-from-ironic 时） | Ironic 还没跑完 inspection | 等一会再试，或去管理集群上 `kubectl describe bmh` 看 inspection 卡在哪 |
| `409 Asset 'xxx' is not available`（assign 时） | 这台机器已经被分到别的集群/pool 了 | 先在原 pool 里 `DELETE` 释放，或换一台 |
| `409 No hardware assigned to any pool yet`（generate 时） | 还没做第 4 步 | 先 `POST /pools/{pool}/assign` |
| `422`（generate 时） | pool 里某台资产缺 `bmc_address`/`boot_mac_address`，或 CPU 拓扑没同步到 | 回去检查该资产 `GET /hardware-assets/{id}` |
| `422`（云 provider 建集群时） | 没填 `control_plane_flavor`/`control_plane_image`，或某个 worker 池没填 `flavor`/`image` | 云 provider 没有物理硬件可选，机器规格必须在建集群时直接声明 |
| `409 ... there's no physical hardware to assign`（云 provider 调 `/pools/{pool}/assign` 时） | 对非 metal3 集群调用了硬件分配接口 | 云 provider 的 worker 池在建集群时就定好了，改配置需要重建集群 |
