# 虚拟 BMC 测试环境

不用真实物理机，就能把 `BareMetalHost` 注册 → Ironic 探测 → 供电/PXE → provisioning 这一整条链路跑一遍。做法跟 metal3-io 官方自己的 CI（`metal3-dev-env` 项目）一样：用 libvirt 虚拟机假装成物理服务器，配合 [sushy-tools](https://opendev.org/openstack/sushy-tools)（OpenStack 官方的 Redfish 模拟器）把每台虚拟机包装成一个真正的 Redfish BMC endpoint。Ironic 发出的每一条 Redfish 指令（开机、关机、设置下次启动走网络卡）都会被 sushy-tools 转译成真实的 `virsh` 操作——对 Ironic 来说，跟操作一台真实的 iDRAC/iLO 没有区别。

**⚠️ 老实话说在前面**：这几个脚本是在一个完全没有 KVM/libvirt 的沙箱环境里写出来的，逻辑跟着 sushy-tools/metal3-dev-env 的标准做法走，Python 语法和 HTTP 调用逻辑都测过（见 `tests/test_dev_vm_bmc_registration.py`），但 `create_test_nodes.py` 里实际调 `virt-install`/`virsh` 那部分，我这边**没有条件跑起来验证过**。你在真实 Linux 环境里第一次跑，大概率要根据你的 libvirt 版本/网络配置调一下参数，不要指望复制粘贴就零错误。

## 前置条件

你现在这台 `ccdadm` 是 Windows 11 Hyper-V 里的 Linux VM——**这套东西要装在这台 Linux VM 里面**，属于嵌套虚拟化（VM 里面再跑 VM）。先确认这条件满足：

1. **在 Windows 11 主机上**（不是在 Linux VM 里面），用管理员 PowerShell，VM 先关机，然后：
   ```powershell
   Set-VMProcessor -VMName <你的VM名字> -ExposeVirtualizationExtensions $true
   ```
   开机后，进 Linux VM 确认：
   ```bash
   egrep -c '(vmx|svm)' /proc/cpuinfo   # 非 0 才说明虚拟化指令集对 VM 可见
   ls /dev/kvm                          # 存在才说明 KVM 能用
   ```
   任何一条不满足，libvirt 建的虚拟机会跑得极慢（纯软件模拟）甚至直接报错，不是这几个脚本的问题，先把这层打通。

2. 装依赖（Debian/Ubuntu 系为例，其他发行版换成对应包管理器）：
   ```bash
   sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients virtinst bridge-utils apache2-utils
   sudo usermod -aG libvirt $(whoami)   # 重新登录一次让组权限生效
   ```

3. Python 依赖：
   ```bash
   cd deploy/testing/vm-bmc
   pip install -r requirements.txt --break-system-packages
   ```

4. 一个 libvirt 网络，给虚拟机的启动网卡用，这个网络要能被你管理集群那边的 Ironic PXE/DHCP 服务覆盖到（或者你专门为测试搭一个隔离的 PXE 环境——这部分网络怎么接到你现有的 Ironic provisioning 网段，环境相关性太强，这里没法替你决定，需要你自己对着 `infra.networks.ccdprovsp`那类配置想清楚）。最简单起步：直接用 libvirt 默认的 `default` 网络（NAT），先验证流程通不通，再考虑接生产网络。

## 跑起来

```bash
cd deploy/testing/vm-bmc

# 1. 建 3 台"裸机"（只建虚拟机定义，不装系统，保持关机状态）
python3 create_test_nodes.py --count 3 --network default --pool default
# 输出 test_nodes.json，里面是每台机器的 name/libvirt_uuid/boot_mac_address

# 2. 给 sushy-emulator 生成一个 BMC 账号密码（htpasswd 格式）
htpasswd -cb /etc/sushy/htpasswd admin '设一个密码'

# 3. 启动 sushy-emulator（前台跑方便看日志，也可以丢进 systemd/tmux）
sushy-emulator --config ./sushy-emulator.conf

# 4. 另开一个终端，把这 3 台虚拟机注册进这个后端
#    --admin-password 是你登录这个后端控制台的密码（不是 BMC 密码）
#    --bmc-password 是上一步 htpasswd 设的那个密码
python3 register_with_backend.py \
  --api-base http://localhost:8000 \
  --admin-password "你的后端登录密码" \
  --bmc-password "你的sushy密码"
```

跑完之后，去控制台的「裸金属主机」页面应该能看到这 3 台——从这一步开始，走的就是这个项目正常的流程：等 Ironic inspection 完成、同步硬件信息、分配到节点池、生成 YAML、触发部署，跟真实物理机完全一样，只是背后是虚拟机在跑。

## 收尾

```bash
./teardown.sh metal3-test-node default
```

会把所有名字匹配 `metal3-test-node*` 的虚拟机连磁盘一起销毁，不会动你手动建的其他虚拟机。

## 排查

- **`virt-install` 报错找不到 `default` 网络/存储池**：`virsh net-list --all`、`virsh pool-list --all` 先确认这两个默认资源存在且是 active 状态，很多 libvirt 装完默认不会自动 `virsh net-start default`。
- **sushy-emulator 起不来**：先直接跑 `sushy-emulator --config ./sushy-emulator.conf`（不要丢后台），看具体报错——大概率是 `qemu:///system` 连不上（当前用户没在 `libvirt` 组，或者没重新登录生效)。
- **Ironic 一直连不上这个虚拟 BMC**：确认 sushy-emulator 监听的地址/端口，管理集群那边的 Ironic 网络能不能路由到——如果 sushy-emulator 跑在这台 Linux VM 上，而 Ironic 跑在别的管理集群，两边网络要能互通，`register_with_backend.py --sushy-host` 要填 Ironic 那边真正能访问到的地址，不能填 `127.0.0.1`。
