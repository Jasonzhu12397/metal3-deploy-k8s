# capd-quickstart：只用容器证明这套平台真的能部署、管理 Kubernetes

跟 `../fake-bmc/` 的关系：`fake-bmc` 证明的是"BareMetalHost 注册/探测这条链路对不对"，
不会真的装出一个系统。这里证明的是更进一步的东西——**一个真实的、能被 `kubectl` 连上的
Kubernetes API server**，完全通过这个项目自己的 API 走一遍"建集群 → 触发部署 → 等它跑完"
流程部署出来，不物理机、不用云账号、不用 VMware，只靠这台机器上的 Docker。

用的是 [Cluster API Provider Docker（CAPD）](https://cluster-api.sigs.k8s.io/)——
Cluster API 项目自己维护、自己在用来测试 Cluster API 本身的官方 provider，每个"节点"
就是管理集群上的一个容器（用 `kindest/node` 镜像，跟 [kind](https://kind.sigs.k8s.io/)
是同一套机制）。**这是官方自己写明的开发/测试用途 provider，不是这个项目的判断，不要
用于生产。**

## 跑起来

```bash
cd deploy/testing/capd-quickstart
./setup.sh
```

会依次做这些事（每一步都有编号输出，方便看到卡在哪）：

1. 建 CAPD 需要的 `kind` Docker 网络
2. 用 [kind](https://kind.sigs.k8s.io/) 建一个"管理集群"
3. 在管理集群上装 Cluster API 核心组件 + CAPD（`clusterctl init --infrastructure docker`）
4. 把这个项目自己的 docker-compose 栈起来，指向这个管理集群
5. **调用这个项目真实的 API**（不是绕过去直接 kubectl apply）创建一个
   `infrastructure_provider=docker` 的集群
6. 触发部署
7. 轮询部署状态直到完成（第一次跑会拉 `kindest/node` 镜像，可能要几分钟）
8. 从管理集群上取出新建集群自己的 kubeconfig（CAPI 标准约定：
   `<集群名>-kubeconfig` 这个 Secret），对着**新集群**跑 `kubectl get nodes`

第 8 步是真正的证明——如果这一步能看到真实的、Ready 的节点，说明整条链路
（这个后端 → CAPI 清单渲染 → CAPD 实际把节点跑起来 → 一个真实的 kube-apiserver
在应答请求）是通的。

跑完清理：

```bash
./teardown.sh
```

## 前置条件

- Docker（且 daemon 能连上，`docker info` 不报错）
- [kind](https://kind.sigs.k8s.io/) —— 脚本会在缺失时打印安装命令
- [clusterctl](https://cluster-api.sigs.k8s.io/user/quick-start.html#install-clusterctl)
- `kubectl`、`jq`、`curl`

## 这次开发时，实际验证过什么、没验证过什么

如实说清楚，不然这份文档本身就是不诚实的：

**验证过的**（这个环境里没有 Docker，没法起真正的容器集群，但下面这些是真查证/真跑过的）：
- `kind`、`clusterctl` 是真实下载、真实能跑的二进制（`kind version`/`clusterctl version` 都执行成功过）
- `clusterctl config repositories` 确认 `docker` 确实是 clusterctl 内置注册的 InfrastructureProvider，不是编的
- `templates/capi/providers/docker.yaml.j2` 这个模板本身：用真实 Jinja2 + YAML 解析验证过单节点和带 worker pool 两种场景（见 `tests/test_capd_provider.py`），字段结构（Cluster → DockerCluster → DockerMachineTemplate → KubeadmControlPlane）是对照多个独立的、当前的官方文档核实过的，不是凭记忆写的
- `setup.sh` 的前置条件检查逻辑：真的跑过，确认它能正确识别出缺 Docker 并给出清晰的报错和退出码
- 部署流水线本身处理"云 provider、没有物理主机要等"这条路径（`hosts: []` 直接跳过 `APPLYING_BMH`/`WAITING_FOR_HOSTS`）：这条路径 openstack/vsphere/kubevirt 已经在用，docker provider 复用的是完全相同的代码路径（`infrastructure_provider != METAL3` 就走 `CloudPlannerService`），不是新写的分支

**没有验证过的**（这个环境本身没有 Docker，物理上做不到）：
- `kind create cluster` 真的建出一个管理集群
- CAPD 真的把容器拉起来、跑出一个可用的 K8s 节点
- 第 8 步真的 `kubectl get nodes` 看到 Ready 状态

这几步只能靠你在有 Docker 的机器上第一次跑 `./setup.sh` 的时候验证。如果卡住了，
把卡在哪一步（脚本会打印 `[N/8]`）和报错发给我。
