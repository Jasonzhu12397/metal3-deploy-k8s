# ephemeral-node-talos：用真正的 live OS（Talos Linux）实现 eph-node

这个目录解决的是这个项目从第一次提交就写在 `deployment_tasks.py` 文档注释里、但从来没
真正实现过的那一步："bootstrap the ephemeral (PXE, in-memory) node as the temporary
CAPI management cluster"。

**明确不是 Docker，也不是 k3s**：

- Talos 直接用 containerd，从架构上就没有 Docker daemon
- Talos 跑的是原生上游 Kubernetes 组件，不是 k3s 发行版——这次实测生成的配置里
  kubelet 镜像是 `ghcr.io/siderolabs/kubelet:v1.12.x`，不是任何 k3s 相关的镜像
- Talos 节点第一次从网络启动、还没有配置的时候，会自动进入官方叫做
  "maintenance mode" 的状态——**这本身就是"活的、内存运行、等待指令"的live OS 状态**，
  不需要额外发明什么机制去模拟这个效果

## 完整流程

```
PXE 启动裸机                          （你自己的 DHCP/TFTP/HTTP 基础设施）
    │
    ▼
Talos 进入 maintenance mode          （节点已经在跑，纯内存，等配置）
    │  talosctl apply-config --insecure
    ▼
Talos 应用控制面配置
    │  talosctl bootstrap
    ▼
这一台机器现在是一个真实的、在跑的单节点 Kubernetes 集群   ← 这就是 "eph-node"
    │  talosctl kubeconfig
    ▼
把这个 kubeconfig 交给 deploy/bootstrap-management-cluster/setup.sh
    │  （那个脚本本来就支持"已经有集群就直接用"这条路径）
    ▼
eph-node 上装好 CAPI + CAPM3 + Ironic + BMO
    │
    ▼
用这个 eph-node 去 provision 目标集群的控制面（走这个项目本身的部署流程）
    │
    ▼
目标集群控制面起来之后，用 services/pivot.py（clusterctl move）
把 CAPI 管理权从 eph-node 迁移到目标集群自己身上
    │
    ▼
eph-node 完成使命——它本来就是"ephemeral"的，可以关机/重装
```

## 用法

```bash
cd deploy/ephemeral-node-talos
CONTROL_PLANE_ENDPOINT="https://<这台裸机自己的IP>:6443" ./generate-eph-node-configs.sh
```

脚本会做到这些：下载真实的 Talos 内核+initramfs（官方 GitHub release）、下载真实的
`talosctl`、真的跑 `talosctl gen config` 生成控制面配置。跑完之后会打印剩下几步
真实、当前有效的官方命令（推配置、bootstrap、拿 kubeconfig），这几步需要真实的联网
裸机才能执行，脚本本身没法替你跑。

## `controlplane.yaml` 生成出来长什么样、要改哪几个字段

`talosctl gen config` 生成的是一份**注释非常详细**的真实配置（下面是真的跑出来的
结构，密钥/证书内容替换成了占位符，其他都是原样）：

```yaml
version: v1alpha1
debug: false
persist: true
machine:
    type: controlplane
    token: <真实 token，自动生成，不用你管>
    ca:
        crt: <真实 CA 证书，自动生成>
        key: <真实 CA 私钥，自动生成>
    kubelet:
        image: ghcr.io/siderolabs/kubelet:v1.35.8
    network: {}          # ← 网络配置，见下面
    install:
        disk: /dev/sda    # ← 装系统的磁盘，见下面
        image: ghcr.io/siderolabs/installer:v1.12.12
cluster:
    ...                   # 集群级配置（Pod/Service CIDR、token 等），一般不用改
```

**默认生成出来的配置，`machine.network` 是空的**——意味着走 DHCP。如果你的
eph-node 需要固定 IP（大多数生产场景都需要），要自己在 `network:` 底下加：

```yaml
machine:
    network:
        hostname: eph-node
        interfaces:
            - interface: eth0          # 换成这台机器真实的网卡名
              addresses:
                - 192.0.2.50/24        # 换成这台机器真实要用的静态 IP
              routes:
                - network: 0.0.0.0/0
                  gateway: 192.0.2.1   # 换成真实网关
```

**同样故意不帮你把这几个值填进 `generate-eph-node-configs.sh` 自动生成的文件里**——
网卡名、IP、网关是你自己网络环境的事，跟这个项目其他地方（`bootstrap-management-cluster/`
的 `Ironic.spec.networking`、`ephemeral-node-cloudinit-kubeadm/` 的 `network-config.yaml`）
是同一个原则：脚本生成的是"骨架"，网络这一段必须你自己核对着改，改错一个网卡名或者
IP 冲突，代价是真实网络故障。

**`machine.install.disk` 也要核对**——默认写的是 `/dev/sda`，如果这台机器的系统盘
设备名不是这个（比如 NVMe 盘会是 `/dev/nvme0n1`），必须改成真实的，装错盘是真实的
数据风险。

改完之后重新跑：

```bash
talosctl apply-config --insecure --nodes <IP> --file controlplane.yaml
```

如果这台机器已经 bootstrap 过、想改配置，要换成不带 `--insecure` 的
`talosctl apply-config --nodes <IP> --file controlplane.yaml`（这时候节点已经有
自己的证书了，走的是认证过的 API，不是 maintenance mode 那个不认证的临时接口）。

## 这次开发时，实际验证过什么、没验证过什么

如实说清楚，跟这个项目其他地方的诚实标准一样：

**验证过的**（真的跑了，不是看文档编的）：
- `talosctl` 二进制真实存在、能下载、能跑（`talosctl version --client` 有正确输出）
- Talos 官方 release 的内核（`vmlinuz-amd64`，21MB）和 initramfs
  （`initramfs-amd64.xz`，78MB）真实存在、能下载，大小是合理的真实 Linux 内核体积，
  不是空文件或者错误页面
- `talosctl gen config` 真的跑通了，生成的 `controlplane.yaml`/`talosconfig` 是
  真实的、包含真实 PKI 证书和 token 的配置文件，这一步是纯本地密码学计算和 YAML 生成，
  不需要网络也不需要真实节点，所以能在这个沙箱里完整验证

**没有验证过的**（这几步需要真实的、联网的物理机，任何沙箱都做不到）：
- 真实裸机 PXE 启动、真的进入 maintenance mode
- `talosctl apply-config --insecure` 真的把配置推给一台正在监听的真实机器
- `talosctl bootstrap` 真的把这台机器变成一个健康的单节点 K8s 集群
- 拿到的 kubeconfig 真的能给 `bootstrap-management-cluster/setup.sh` 用起来
  （这一步本身也有它自己没验证过的部分，见那个目录的 README——容器镜像仓库在这个
  开发沙箱里被拦截，`bootstrap-management-cluster/` 的这一层从原理上就没法在这里
  验证到底，不是这次的新问题，是同一个环境限制）

这几步必须由你在真实网络环境里跑通。如果卡住了，把卡在哪一步、`talosctl` 的报错
发给我，我可以帮你看是配置问题还是网络问题。
