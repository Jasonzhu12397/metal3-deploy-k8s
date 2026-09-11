# airgap-bundle-talos：客户环境断网时，Talos 这条路径怎么全部本地化

你说得对——之前 Talos 相关的所有东西（`deploy/ephemeral-node-talos/`、
`templates/capi/providers/talos-metal3.yaml.j2`、`deploy/bootstrap-management-cluster/`）
全部假设能连外网：GitHub release、`ghcr.io`、`registry.k8s.io`、`quay.io`。客户环境
断网的话这些全部会失败。这个目录把整条路径需要的东西分成两类，分别本地化：

1. **容器镜像**——`mirror-images.sh` + `image-list.txt`：用 `skopeo`（真实、标准的
   镜像仓库间复制工具，不需要本地 Docker daemon）把每一个需要的镜像从公网复制到你
   自己的本地镜像仓库
2. **二进制/清单文件/磁盘镜像**——`download-assets.sh`：把 `talosctl`/`clusterctl`
   二进制、Talos 的 PXE 内核+initramfs、Talos 磁盘镜像、CABPT/CACPPT/cert-manager/
   IrSO/BMO 的 YAML 清单，全部下载成本地文件

然后用 `registry-mirror-patch.yaml`（Talos 官方真实支持的 `machine.registries.mirrors`
机制）把每个 Talos 节点的镜像拉取请求重定向到你自己的本地镜像仓库。

## 用法

在一台**能连外网**的机器上（常见叫法是"跳板机"/"堡垒机"，这台机器同时也要能连到
客户那个断网环境）跑：

```bash
cd deploy/airgap-bundle-talos

# 1. 把清单文件里的镜像都同步到你自己的本地仓库
LOCAL_REGISTRY="registry.airgap.local:5000" ./mirror-images.sh

# 2. 把二进制/清单/磁盘镜像都下载下来
./download-assets.sh
```

跑完之后，把 `.bundle/assets/` 整个目录搬到客户那个断网环境里能访问到的地方
（U 盘、内网文件服务器都行），本地起一个 HTTP 服务把它开放出来。

## 然后怎么接到这个项目原本的流程里

- `USAGE.md` 第 1.2 节的 `cluster_spec.image_url` 改成指向你本地文件服务器上的
  `disk-images/metal-amd64.raw.zst`，不再指向 GitHub
- `deploy/ephemeral-node-talos/generate-eph-node-configs.sh` 里下载 PXE 内核/
  initramfs 那两步，改成从你本地文件服务器上的 `pxe/vmlinuz`、`pxe/initramfs.xz`
  拿，不再连 GitHub（这个脚本目前还没有做成"支持本地资源"的参数化版本，需要你
  自己改一下 URL，或者告诉我要不要我把这个也做成可配置的）
- `deploy/bootstrap-management-cluster/setup.sh` 里 `kubectl apply -f <github地址>`
  的地方，全部换成 `kubectl apply -f` 你本地文件服务器上 `manifests/` 目录里对应
  的文件
- 每个 Talos 节点（eph-node 和目标集群节点）的 machine config，用
  `registry-mirror-patch.yaml` 这份真实的 `machine.registries.mirrors` 配置
  合并进去（把 `__LOCAL_REGISTRY_HOST__` 换成你自己本地镜像仓库的真实地址）——
  具体怎么合并，`registry-mirror-patch.yaml` 文件开头的注释里写了两种真实的
  官方方式（`talosctl gen config ... --config-patch @file`，或者对已经在跑的
  节点用 `talosctl patch machineconfig`）

## 这次开发时，实际验证过什么、没验证过什么

这次比之前几次都更进了一步，先说清楚哪些是真的跑通了的：

**真正端到端跑通、验证过的**：
- `download-assets.sh` **真的完整跑通了一次，全部 10 个文件下载成功，没有一步
  失败**——`talosctl`（98MB）、`clusterctl`（35MB）、Talos PXE 内核（21MB）、
  initramfs（78MB）、Talos 磁盘镜像（202MB）、CABPT/CACPPT/cert-manager/IrSO/
  BMO 的清单文件，全部真实下载下来、大小合理
- **过程中真的抓到一个之前几轮工作里一直存在的 bug**：Talos 磁盘镜像的真实文件名
  是 `metal-amd64.raw.zst`（zstd 压缩），不是我之前一直在用的 `metal-amd64.raw.xz`
  （xz 压缩）——Talos 在某个版本之后换了压缩格式，我沿用的是旧文件名，导致
  `templates/capi/providers/talos-metal3.yaml.j2`、`USAGE.md` 第 1.2 节示例、
  还有对应的测试，**这几处之前的 `image_url` 默认值全部是错的、会 404**。已经
  全部改成真实、验证过能下载的 `.raw.zst`，改完之后重新用真实 HTTP 请求确认了
  一遍
- `mirror-images.sh` 的脚本逻辑（解析镜像清单、构造本地仓库目标地址、失败追踪）
  用假的 `skopeo` 命令测过，逻辑是对的
- `image-list.txt` 里的每一个镜像名，都是从真实下载下来的 CABPT/CACPPT/
  cert-manager/BMO/IrSO/CAPI/CAPM3 release 清单里 `grep` 出来的，不是猜的
- `skopeo` 本身真实可以安装、真实可以运行——用它去连 `registry.k8s.io` 的时候，
  报错清楚地显示是这个沙箱自己的网络策略拦截（"Host not in allowlist"），不是
  工具本身坏了

**没有验证过的**：
- `mirror-images.sh` 真正把镜像复制到一个真实的本地仓库——这一步需要真的连上
  `docker.io`/`ghcr.io`/`registry.k8s.io`/`quay.io`，这四个域名在这个沙箱里
  全部被拦截（`host_not_allowed`），一个都连不上，所以真实的镜像复制这一步从
  原理上就没法在这里验证
- `image-list.txt` **不一定是完整的**——Ironic 自己（一旦 IrSO 的 `Ironic` 资源
  真的被 reconcile）还会再跑起 Ironic API/dnsmasq/httpd 这些自己的 Pod，用的是
  它们自己的镜像，这些镜像只有在一个真实、能连网络的管理集群上跑起来之后才能
  观察到是什么——这个沙箱连不上任何镜像仓库，所以这几个镜像从来没有被观察到过，
  没法加进清单里。清单文件自己的注释里写了怎么在真实环境里把这些补全
  （`kubectl get pods ... -o jsonpath=...`）
- `registry.k8s.io`/`docker.io` 这些）会不会正确生效——这个需要真实的 Talos
  节点，任何沙箱都做不到

## 建议

`download-assets.sh` 这部分已经是真金白银跑通验证过的，可以直接用。`mirror-images.sh`
用的是标准、真实的 `skopeo copy` 命令，在一台网络正常的机器上大概率能直接工作——
跑起来如果有具体哪个镜像失败，把报错发给我。
