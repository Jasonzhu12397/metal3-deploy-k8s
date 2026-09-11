# golden-image-target-node：给 target 集群节点用的预烘焙镜像

## 先说清楚这个是不是必须的

**默认情况下，这个项目根本不需要自定义镜像。** 标准做法是：Ironic 写一份官方的
Ubuntu/CentOS 云镜像（这些镜像自带 cloud-init）到硬盘，CABPK（Cluster API 的
kubeadm bootstrap 组件）生成一份 cloud-init 数据（真实网络配置、真实的
`kubeadm init`/`kubeadm join` 命令），节点启动时联网装 kubeadm/kubelet/containerd、
跑 kubeadm 命令自己变成集群节点——这是整个 CAPI+kubeadm 生态默认设计的工作方式，
不用维护自定义镜像。

**这个目录要解决的是另一个场景**：如果你的生产网络是受限的（节点在 provisioning
的时候连不上 `pkgs.k8s.io`/公网 apt 源/容器镜像仓库——这跟这个项目自己开发过程中
反复撞到的沙箱网络限制是同一类问题，只是发生在你的生产网络而不是这里），那就需要
提前把 kubeadm/kubelet/containerd 这些包**烘焙进镜像本身**，节点启动时不需要再
联网装。

跟 `deploy/ephemeral-node-cloudinit-kubeadm/` 的关键区别：那边是给 eph-node 用的
**live/内存启动**镜像；这个是给 target 集群节点用的**真实装到硬盘、带 GRUB 引导**
的镜像——target 节点是要长期跑下去的，不能是内存里的临时状态。

## 用法

```bash
cd deploy/golden-image-target-node
./build-golden-image.sh
```

跑完之后压缩镜像（`xz -T0 golden-image.raw`），放到 Ironic 能访问到的地方，
建集群的时候把 `spec.image_url`/`spec.image_checksum` 指过去就行——具体这两个字段
放在请求体的什么位置，见 `USAGE.md` 第 1 节的建集群示例。

## 这次开发时，实际验证过什么、没验证过什么

跟 `deploy/ephemeral-node-cloudinit-kubeadm/` 撞到的是**同一个、已经确认过的沙箱
网络限制**，这次又实测复现了一遍，不是新问题：

**验证过的**：
- `debootstrap` 在这个沙箱里应用过 User-Agent 修复之后（见
  `ephemeral-node-cloudinit-kubeadm/README.md` 里那个发现）能真正连上
  `archive.ubuntu.com`、验证签名、开始下载包
- 这次实测又跑到了 12MB 左右（比上次那次的约 10MB 略多，说明这个限制不是每次
  卡在完全一样的字节数，是真的不稳定，不是某个固定的硬编码上限）

**没有验证过的**：
- **具体的 `.deb` 包文件下载，这次又一次卡死在几分钟内、个位数到十几 MB 的进度上，
  彻底没有恢复** ——跟上次构建 eph-node 镜像时遇到的问题一模一样，这次相当于又
  完整复现确认了一遍这个限制是真实存在、可重复的，不是那次的偶然状况
- 因为 `debootstrap` 没跑完，后面所有步骤——chroot 装包（containerd/cloud-init/
  kubeadm/kubelet/GRUB）、`parted` 分区、`mkfs.ext4` 格式化、`grub-install` 装
  引导——**这次同样一步都没有机会真正跑通验证过**，脚本本身是按真实、标准的 Linux
  磁盘镜像制作流程写的（`debootstrap` → chroot 装包 → `losetup` 挂 loop 设备 →
  分区格式化 → 拷贝根文件系统 → `grub-install`，都是业界标准做法，不是我编的），
  但从 `debootstrap` 卡住那一刻起，后面的每一步都是"写完了、没测过"
- `kubeadm`/`kubelet`/`kubectl` 的官方源 `pkgs.k8s.io` 在这个沙箱里是彻底拦截
  （不是慢，是打不开），这一步无论 `debootstrap` 跑不跑得完，在这个沙箱里都过不去

## 建议

这个脚本用的每一条命令都是真实、标准、在正常网络环境下会工作的做法。如果你有一台
网络正常的真实服务器或者云主机，建议直接在那上面跑一遍，大概率不会撞上这个沙箱
特有的下载卡死问题。跑起来卡在哪一步、报什么错，发给我，我可以继续排查。

如果你的生产网络本身没有受限（能正常访问 `pkgs.k8s.io`、公网 apt 源），其实
**不需要用这个脚本**——直接用官方 Ubuntu 云镜像 + 标准 cloud-init 流程就够了，
这个目录只是为了"网络受限场景"这个特定需求准备的，不是默认必须的东西。
