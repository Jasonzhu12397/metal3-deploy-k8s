# bootstrap-management-cluster：装出这个平台假设已经存在的那个"管理集群"

这个项目从一开始就有个明确的边界：它假设 Ironic + baremetal-operator + Cluster API + CAPM3
**已经**跑在某个"管理集群"上，本身不负责装这些。这条边界写在项目自己的文档里,
不是藏着不说。

这个目录做的事：把这条边界往前推一段，自动化装出这个"管理集群"本身——用的是
[Metal3 官方现在（2026 年）真实的、当前有效的 quick-start 流程](https://book.metal3.io/quick-start)，
不是我自己编的简化版。具体来说：

1. 一个 Kubernetes 集群作为管理集群底座——如果你已经有一个，直接用（官方文档原话：
   "If you already have a Kubernetes cluster that you want to use, go ahead and use that"）；
   如果没有，脚本会下载 [k3s](https://k3s.io/)（单个静态二进制，自带 kube-apiserver +
   etcd + controller-manager + scheduler + kubelet，不需要 Docker）起一个。
2. `clusterctl init --infrastructure=metal3 --ipam=metal3`——装 Cluster API 核心组件 +
   CAPM3，顺带自动装好 cert-manager。
3. [Ironic Standalone Operator (IrSO)](https://github.com/metal3-io/ironic-standalone-operator)——
   用官方发布的合并清单（`install.yaml`），不需要本地 Go/kustomize 编译。
4. [Baremetal Operator (BMO)](https://github.com/metal3-io/baremetal-operator)——同样用官方发布的合并清单。
5. 一个最小化的 `Ironic` 自定义资源——`networking` 字段留空，**故意不帮你猜网络配置**。

## 用法

```bash
cd deploy/bootstrap-management-cluster
./setup.sh
```

跑完之后，把生成的 kubeconfig（脚本最后会打印路径）设成这个项目后端的
`MGMT_KUBECONFIG_PATH`，这个平台自己的 API/Worker 就能开始通过这个管理集群
去操作硬件资产、生成清单、发起部署了——衔接的正是本项目 README 里"这一步假设已经
装好"的那个前提。

## 跑完之后你必须自己做的事——这些没法用脚本替你决定

**网络配置**——`kubectl edit ironic -n baremetal-operator-system ironic`，把
`spec.networking` 填成你自己环境真实的 DHCP 网段、网卡、PXE 相关配置。这个脚本
故意留空，不是漏做：Ironic 的 DHCP 配置一旦猜错，轻则 PXE 起不来，重则**把一个不相关的
网段搞挂**（DHCP 服务器抢地址是真实会发生的生产事故）。具体要填哪些字段，参考
[IrSO 官方文档](https://github.com/metal3-io/ironic-standalone-operator) 和你自己的
网络拓扑，这里没法替你决定。

**确认 Ironic 真的能连到你的 BMC，物理机真的能 PXE 到 Ironic**——这个只能在你自己的
真实网络环境里验证，脚本做不到，任何脚本都做不到。

## 这次开发时，实际验证过什么、没验证过什么

如实说清楚：

**验证过的**：
- 完整脚本的第 1 步（起一个真实的、可用 `kubectl` 连上去的 k3s 管理集群）——真的跑过，
  跟这个项目其他地方（`deploy/testing/live-apply-test.sh`）验证过的是同一套机制
- IrSO、BMO 的官方发布清单 URL 是真实存在的、能下载到的，`kubectl apply` 之后确实创建出
  了正确结构的 K8s 对象（Deployment、CRD、Webhook 等），不是编的 URL
- 步骤依赖顺序是对的——实测过跳过 cert-manager 直接装 IrSO 会报错（`Certificate`/`Issuer`
  这两个 cert-manager CRD 类型不存在），验证了"IrSO 必须在 cert-manager 装完之后装"这个
  顺序是真实存在的依赖，不是我猜的
- `Ironic` 自定义资源的 schema：`spec` 底下没有必填字段，所以`networking: {}`这个最小化写法
  是 schema 层面合法的

**没有验证过的**（这次开发环境的真实限制，不是设计问题）：
- `clusterctl init` 完整跑通——这次撞上了 GitHub API 限流（这个项目开发过程中查了太多次
  未认证的 GitHub API，额度用完了），没能在这次开发环境里跑到底
- cert-manager/CAPI/CAPM3/IrSO/BMO 这些控制器的 Pod 真的达到 Running 状态——这次开发环境
  磁盘空间紧张，触发了 `disk-pressure` 污点，Pod 卡在 Pending 调度不上去，这也是开发环境
  本身的资源限制，不是脚本逻辑的问题
- Ironic 真实连到 BMC、物理机真实 PXE 成功——这个前面说过，任何脚本环境都验证不了，
  必须在你自己的真实网络里跑

这几步只能靠你在自己的真实环境里跑 `./setup.sh` 的时候验证。如果卡住了，把卡在哪一步
和报错发给我。
