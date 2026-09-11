# target-node-image-builder：目标集群节点用的操作系统镜像从哪来

这个项目从一开始就有个没人问过的空白：`Metal3MachineTemplate.spec.template.spec.image.url`
（这个后端生成的清单里，Ironic 真正拿去写盘的那个字段）——这个 URL 指向的镜像本身
**从哪来**，这个项目从来没有回答过，一直假设你自己已经有一个。

这个目录回答这个问题，用的是真实、官方的工具——**不是自己现场拼一个构建流程**：
[`kubernetes-sigs/image-builder`](https://github.com/kubernetes-sigs/image-builder)，
Kubernetes SIG Cluster Lifecycle 官方维护、Cluster API 项目自己推荐使用的镜像构建工具
（CAPZ 的官方文档原话："Cluster API uses the Kubernetes Image Builder tools"）。

## 用法

```bash
cd deploy/target-node-image-builder
KUBERNETES_MINOR_VERSION=1.31 ./build-target-node-image.sh
```

跑完之后，`raw` 格式的磁盘镜像和校验和会出现在
`.image-builder-work/image-builder/images/capi/output/` 下面——把这个文件放到
Ironic 能访问到的地方（HTTP 服务起来），`image_url`/`image_checksum` 就填这个。

## 这次开发时，实际验证过什么、没验证过什么

**验证过的**：
- `kubernetes-sigs/image-builder` 仓库真实存在、能 clone 下来
- `packer/raw/raw-ubuntu-2404.json` 这个真实的 build 配置文件，结构对得上——用的是
  真实 Ubuntu 24.04 Server ISO + `autoinstall`（cloud-init 风格的自动化安装），不是
  精简的 debootstrap
- **过程中真的抓到自己写错的一处**：第一版脚本里我写了个 `KUBERNETES_SERIES` 环境
  变量去控制装哪个 K8s 版本——这个变量在真实的 `Makefile` 里根本不存在，是我编的。
  重新查了真实的 `Makefile` 和 `packer/config/kubernetes.json`，确认这其实是一个
  **Packer 变量**（`kubernetes_series`，默认写在配置文件里），真正支持的覆盖方式是
  通过 `PACKER_VAR_FILES` 这个 Make 变量指向一个自定义的 var-file——已经改成这个
  真实、正确的方式，不是留着一个不存在的环境变量误导你

**没有验证过的**（这次是真实的技术限制，不是没做）：
- 真正跑一次 `make build-raw-ubuntu-2404`——这一步需要在 QEMU 里把一个完整的
  Ubuntu Server 安装程序跑起来（不是精简系统，是走真实安装流程），这需要 KVM 加速
  才能在合理时间内跑完；这个开发沙箱反复确认过没有 KVM（`/dev/kvm` 不存在，CPU
  也没有虚拟化扩展位），软件模拟的话慢到不现实
- 光是下载那个 Ubuntu Server 安装 ISO 就有 2.5GB，跟这个项目另一个镜像构建尝试
  （`deploy/ephemeral-node-cloudinit-kubeadm/`）已经记录过的"大文件下载在这个沙箱
  里会被限速到几乎卡死"是同一类问题，大概率会撞上同样的墙
- Packer、Goss 插件、Ansible 这几个工具本身这次也没有在这个沙箱里装、没有验证
  `make deps-raw` 真的能跑通

## 如果你已经有别人构建好的镜像，可以先不自己构建

`kubernetes-sigs/image-builder` 社区里有人已经用这套工具构建好、发布出来的现成镜像
（比如 [osism/k8s-capi-images](https://github.com/osism/k8s-capi-images)），主要是
`qcow2` 格式（给 OpenStack 这类场景用）。如果你要的是 Metal3 的 `raw` 格式，目前
没有找到对应的、已经公开发布好的现成镜像仓库——这也是为什么这次重点是把
**构建流程本身**接进来、而不是找一个能直接用的现成文件。

## 建议

这个脚本本身除了那个已经改正的 `PACKER_VAR_FILES` 修复之外，用的都是官方文档
（<https://image-builder.sigs.k8s.io/capi/capi.html>）里写的真实命令。建议在一台
有 KVM、网络正常的机器上跑（不需要多强的机器，普通带虚拟化支持的服务器/云主机
就够），跑起来卡在哪一步、报什么错，发给我，我可以继续往下排查。
