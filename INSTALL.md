# 安装手册 (INSTALL)

本手册说明如何把 `metal3-deploy-k8s-backend` 跑起来，两条路选一条：

1. **docker-compose，跑在管理集群外面的另一台机器上**——本手册接下来的内容，适合本地开发/测试。这条路需要手动把管理集群的 kubeconfig 拿到本地（见第 4 节，以及为什么这一步**没法自动化**）。
2. **直接部署进管理集群内部（in-cluster，推荐用于实际环境）**——不需要 kubeconfig，Pod 用自己的 ServiceAccount 自动认证。这条路走 `deploy/k8s/README.md`，完整的 Deployment/RBAC/ConfigMap/Secret 清单都在那。**如果你打算长期在真实环境跑这套系统，建议直接跳过本手册剩下的部分，去看 `deploy/k8s/README.md`。**

这份安装手册跟你选哪个 `infrastructure_provider`（metal3/openstack/vsphere/kubevirt）无关——安装步骤是一样的，区别只在建集群之后你怎么用（见 USAGE.md）。如果要部署到 OpenStack/vSphere/KubeVirt，额外要做的是：在管理集群上先装好对应的 CAPI provider（CAPO/CAPV/CAPK）和它需要的凭证 Secret（比如 OpenStack 的 `clouds.yaml`、vCenter 的用户名密码），这些不归这个后端管——它只负责渲染引用这些 Secret 名字的 YAML，不负责创建凭证本身。

---

## 1. 前置条件

| 依赖 | 版本 | 说明 |
|---|---|---|
| Docker | 24+ | 跑 postgres/redis/api/worker |
| Docker Compose | v2 (`docker compose`, 不是 `docker-compose`) | |
| 一个可达的 metal3 管理集群 kubeconfig | - | **只有走 docker-compose 这条路才需要**。本项目不负责把 baremetal-operator/Ironic/CAPI 装进管理集群，只负责调用它们的 API——kubeconfig 本质是"怎么连到一个已经存在的集群"的凭证，这个集群不存在，kubeconfig 就生成不出来，所以这一步没法自动化。如果你是走 in-cluster 部署（见 `deploy/k8s/README.md`），完全不需要这个，跳过 |
| （可选）Python 3.12 + pip | - | 只有想不用 Docker、本地直接跑/跑测试时才需要 |

管理集群上需要已经装好：
- `baremetal-operator`（提供 `BareMetalHost` CRD，`metal3.io/v1alpha1`）
- `cluster-api` 核心 + `cluster-api-provider-metal3`（提供 `Cluster`/`Metal3Cluster`/`KubeadmControlPlane`/`Metal3MachineTemplate` 等 CRD）
- Ironic（baremetal-operator 依赖它做硬件 inspection）

这几个组件的安装本身超出本项目范围，按 [metal3-io 官方文档](https://book.metal3.io/) 装即可，这个后端只是在它们之上做编排。

---

## 2. 解压项目

```bash
unzip metal3-deploy-k8s-backend.zip
cd metal3-deploy-k8s-backend
```

目录结构：

```
backend/          FastAPI + Celery 源码
frontend/         React + Vite + TypeScript 前端控制台
deploy/           docker-compose 引用的配套文件（postgres/redis 配置、kubeconfig 挂载点）
templates/        渲染 bmh.yaml / 集群配置 / 网络策略 的 Jinja2 模板
scripts/          install.sh / start.sh
tests/            pytest 测试
.env.example      环境变量模板
docker-compose.yml
Makefile
```

---

## 3. 配置环境变量

```bash
cp .env.example .env
```

打开 `.env` 编辑，关键项：

```ini
# 随便一个足够随机的字符串，用于 JWT 签名（如果你接了认证）
SECRET_KEY=换成一个长随机字符串

# 管理集群 kubeconfig 在容器里的路径 —— 不用改，docker-compose 会把
# deploy/kubeconfig/config 挂载到这个路径
MGMT_KUBECONFIG_PATH=/secrets/kubeconfig/config

# BareMetalHost / Cluster 等资源所在的命名空间
CAPI_NAMESPACE=metal3

# 等 BMH 变成 available 的超时时间（秒）
BMH_READY_TIMEOUT=1800
# 等控制面 Ready 的超时时间（秒）
CLUSTER_PROVISION_TIMEOUT=7200
```

> ⚠️ **不要**把 SSH 私钥、集群 CA 私钥、LDAP 密码这类东西写进 `.env`——这些不归这个项目管，`.env` 只放这个服务自己的配置。
>
> **BMC 密码是个例外，现在会加密存进这个服务自己的数据库**（不是明文，也不是 base64——base64 不是加密，任何人拿到密文一行代码就能还原，等于没锁；这里用的是 Fernet 对称加密，需要单独管理的密钥才能解密），这样注册过一次的物理机，之后要重建被删掉的 Kubernetes Secret 时不用再重新输一遍密码。加密密钥必须单独设置：

```bash
# 生成一个密钥（只需要生成一次，之后所有物理机的 BMC 密码都用这一把密钥加密）
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把生成的值填进 `.env` 的 `BMC_ENCRYPTION_KEY`。**这把密钥本身才是真正敏感的东西**——它不能跟它加密出来的数据存在一起，丢了这把密钥，之前存的所有 BMC 密码就永久解不出来了（没有后门，这是设计上的），生产环境应该用 Vault/K8s Secret/KMS 管理，不是明文 `.env`。没设置这把密钥也不会导致注册主机失败——BMH 和 Kubernetes Secret 照常创建，只是这个服务自己数据库里那份"方便以后重建 Secret 用"的备份不会存，属于优雅降级。

---

## 4. 放置管理集群 kubeconfig（仅 docker-compose 这条路需要）

**这一步没法自动生成**——kubeconfig 是"怎么连到一个已存在的集群"的凭证，管理集群不存在，这份文件就生成不出来。它是 eph 节点跑 `kubeadm init` 时的副产物（通常在那台机器上的 `/etc/kubernetes/admin.conf`），需要你手动从那台机器上取出来。如果这一步让你觉得别扭，说明你可能更适合走 in-cluster 部署（`deploy/k8s/README.md`）——那条路完全不需要这个文件，Pod 用自己的 ServiceAccount 自动认证。

```bash
mkdir -p deploy/kubeconfig
cp /path/to/your/mgmt-cluster-kubeconfig deploy/kubeconfig/config
```

这个文件不会被提交到 git（`.gitignore` 里已经排除了 `deploy/kubeconfig/config`）。

验证这份 kubeconfig 至少有权限：
- 读写 `metal3.io/v1alpha1` 的 `baremetalhosts`（及其所在 namespace 的 `secrets`）
- 读写 `cluster.x-k8s.io/v1beta1`、`infrastructure.cluster.x-k8s.io/v1beta1`、`controlplane.cluster.x-k8s.io/v1beta1`、`bootstrap.cluster.x-k8s.io/v1beta1` 下的资源

```bash
KUBECONFIG=deploy/kubeconfig/config kubectl auth can-i create baremetalhosts.metal3.io -n metal3
KUBECONFIG=deploy/kubeconfig/config kubectl auth can-i create clusters.cluster.x-k8s.io -n metal3
```

---

## 5. 构建 & 启动

```bash
./scripts/install.sh   # 首次运行：生成 .env（如果还没有）、docker compose build
./scripts/start.sh      # docker compose up -d，然后 tail api/worker 日志
```

`install.sh` / `start.sh` 内部就是：

```bash
docker compose build
docker compose up -d
```

启动的容器：

| 服务 | 作用 |
|---|---|
| `postgres` | 存 Cluster / BareMetalHost / HardwareAsset / Deployment 等元数据 |
| `redis` | Celery broker + result backend |
| `api` | FastAPI，监听 `:8000` |
| `worker` | Celery worker，实际跑部署任务 |
| `frontend` | React 控制台，nginx 监听 `:80`（宿主机映射到 `:8080`），同源反向代理 `/api` 到 `api` 服务，浏览器不需要单独配置后端地址 |

---

## 5.5 想用域名 + HTTPS 访问（可选）

默认的 `docker compose up` 只是把 `frontend` 直接映射到宿主机 `:8080`，走的是明文
HTTP，`postgres`/`redis`/`api` 的端口也是直接暴露在宿主机上的——本地测试没问题，
但要给别人访问、或者绑了域名，就不该这么裸奔。

```bash
# 自签证书，几秒钟搞定，浏览器会提示"不安全"，适合内网/临时测试
sudo ./scripts/setup-https-selfsigned.sh 你的域名

# 真正被信任的证书（Let's Encrypt），要求域名已解析到这台机器、80 端口公网可达
sudo ./scripts/setup-https-letsencrypt.sh 你的域名 你的邮箱
```

两个脚本都会把 `postgres`/`redis`/`api` 的直接端口暴露收掉，只留 nginx 对外开
80/443，`frontend`/`api` 继续通过 Docker 内部网络访问。详细说明、Let's Encrypt
需要的前置条件（国内云主机的 ICP 备案要求、证书续期）、以及这两个脚本目前还没
在什么环境下验证过，见 `deploy/nginx/README.md`。

---

## 6. 验证安装

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}

curl http://localhost:8000/readyz
# {"status":"ready"}
```

打开控制台（KubeSphere 风格的管理界面，集群/硬件资产/部署都在这里操作）：

```
http://localhost:8080
```

**第一次打开会跳到登录页。** 找管理员账号密码：

```bash
docker compose logs api | grep -A3 "Seeded initial admin account"
```

- 如果你在 `.env` 里设置了 `ADMIN_PASSWORD`，用户名是 `ADMIN_USERNAME`（默认 `admin`），密码就是你设的那个。
- 如果没设置，服务第一次启动时会随机生成一个密码，**只在启动日志里打印一次**，不会存在任何文件里——上面这条命令就是用来找它的。登进去之后建议尽快把密码改掉——目前前端还没做"修改密码"的界面，直接调接口即可：
  ```bash
  curl -X POST http://localhost:8000/api/v1/auth/change-password \
    -H "Authorization: Bearer <登录后拿到的 access_token>" \
    -H "Content-Type: application/json" \
    -d '{"current_password": "刚才那个随机密码", "new_password": "换成你自己的"}'
  ```

这套账号密码是先能用的最简版本（细节见 README 的「Auth」一节），后面要接你们现有的 LDAP/Dex 时，换掉 `backend/app/services/auth.py` 和 `api/auth.py` 就行，前端不用大改。

打开交互式 API 文档（前端还没覆盖到的接口，可以直接在这里点着试——注意大部分接口现在需要先在 `/auth/login` 拿到 token，点右上角的 Authorize 按钮填进去）：

```
http://localhost:8000/docs
```

看 worker 有没有正常连上 Redis：

```bash
docker compose logs -f worker
# 应该看到 celery@... ready. 之类的输出，没有连接报错
```

---

## 7. 本地开发模式（不走 Docker，可选）

如果你想直接改代码、跑测试，不想每次都重建镜像：

```bash
cd backend
pip install -r requirements.txt --break-system-packages   # 或用 venv
```

跑测试（不需要真实数据库/管理集群，测试用 sqlite + 纯函数验证）：

```bash
pip install pytest aiosqlite --break-system-packages
cd ..
python -m pytest tests -v
```

本地起服务（需要本机有 postgres/redis，或者把 `.env` 里的 `DATABASE_URL`/`REDIS_URL` 指到 docker-compose 起的那两个容器的暴露端口 `localhost:5432`/`localhost:6379`）：

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

另开一个终端跑 worker：

```bash
cd backend
celery -A app.tasks.deployment_tasks.celery_app worker --loglevel=INFO
```

再开一个终端跑前端（Vite dev server，热更新，`vite.config.ts` 里配置了 `/api`、`/healthz`、`/readyz` 自动代理到 `localhost:8000`，不用额外配置）：

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173
```

如果后端不是跑在本机 `8000` 端口（比如你把它跑在别的机器上），设置代理目标再启动：

```bash
VITE_API_PROXY_TARGET=http://192.168.1.50:8000 npm run dev
```

---

## 8. 常见问题

**`readyz`/`healthz` 正常，但调用需要访问管理集群的接口（比如注册 BMH）报错连接失败**
检查 `deploy/kubeconfig/config` 是不是真的挂进容器了：
```bash
docker compose exec api cat /secrets/kubeconfig/config | head -5
```
如果是空文件/文件不存在，说明 kubeconfig 没放对地方，回第 4 步。

**postgres 容器起不来 / api 一直重启**
```bash
docker compose logs postgres
```
常见是端口 5432 已经被本机别的 postgres 占用，改 `docker-compose.yml` 里 `postgres` 的端口映射（比如改成 `"5433:5432"`）。

**celery worker 起来了但任务一直 pending**
确认 `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` 在 `api` 和 `worker` 两个容器里指向同一个 redis（docker-compose 里默认是同一个，如果你手动改过要保持一致）。

**想清空重来**
```bash
docker compose down -v   # -v 会连数据卷一起删，postgres 数据也没了
```

---

## 8.5 没有真实物理机，想测试完整流程怎么办

两条路，看你的环境有没有嵌套虚拟化：

- **`deploy/testing/fake-bmc/`（推荐，不需要 KVM/嵌套虚拟化）**——用 [sushy-tools](https://opendev.org/openstack/sushy-tools) 的 `--fake` 驱动模式，一个轻量容器直接在内存里模拟 N 台服务器的开关机/PXE 状态，不需要背后真的有虚拟机。云主机（腾讯云/阿里云这类共享云主机大多不支持嵌套虚拟化）、Hyper-V/VMware 里开不了嵌套虚拟化的场景，用这条路。局限是不会真的装系统，但注册/探测/开关机这套状态机能完整走一遍，测这个项目本身的代码/UI 对不对已经够用。详细步骤见 `deploy/testing/fake-bmc/README.md`。
- **`deploy/testing/vm-bmc/`（需要 Linux + KVM）**——用真实 libvirt 虚拟机，能看到真实系统被装起来，但需要嵌套虚拟化。如果你是在 Hyper-V 的 Linux VM 里跑，要先在 Windows 主机上给这台 VM 开嵌套虚拟化，文档里写了具体命令。详细步骤见 `deploy/testing/vm-bmc/README.md`。

两条路背后都是同一个 Redfish 模拟器（sushy-tools），都跟 metal3-io 官方自己测试用的方法（`metal3-dev-env`）是一回事，区别只是要不要真的起虚拟机。

---

## 9. 生产化建议（超出本手册范围，但值得记一下）

- 数据库迁移：目前 `init_db()` 用的是 SQLAlchemy 的 `create_all()`，够开发用；生产环境建议接入 Alembic（`requirements.txt` 里已经有这个包）做版本化迁移。
- 密钥管理：`.env` 里的 `SECRET_KEY`、`ADMIN_PASSWORD`，生产环境应该走 Vault / Kubernetes Secret / SOPS，不是明文 `.env` 文件。`SECRET_KEY` 换掉之后，之前签发的所有 token 会立刻失效（相当于全员强制重新登录），这是预期行为。
- 把 `api`/`worker` 部署进管理集群内部而不是 docker-compose 的话，直接用 `deploy/k8s/`——里面有完整的 Deployment/Service/RBAC/ConfigMap/Secret 清单和一份说明（`deploy/k8s/README.md`），RBAC 是照着代码实际会调用哪些 API group/kind 精确对出来的，不是拍脑袋给的 `cluster-admin`。
- 现在这套鉴权是"先能用"的最简版本：一张 `users` 表 + bcrypt 密码 + JWT，没有 SSO、没有 MFA、没有账号锁定策略、没有密码复杂度校验。真正接入生产环境前应该换成真实身份源——既然你们现有系统里已经有 Dex+LDAP，最省事的路大概率是把 `services/auth.py`/`api/auth.py` 换成 OIDC 对接 Dex，而不是继续维护这套独立账号体系。前端的 `lib/auth.tsx`/token 校验机制不用大改，因为无论 token 从哪发的，走的都是同一套 JWT bearer 流程。
- 如果前端要单独部署（不通过 docker-compose 的 nginx 反代），构建时设置 `VITE_API_BASE_URL` 指向后端的真实地址，并且给后端 `CORS_ORIGINS` 加上前端的域名。
