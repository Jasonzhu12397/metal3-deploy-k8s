# 纯容器测试环境（不需要 KVM/嵌套虚拟化）

跟 `../vm-bmc/` 目标一样——不用真实物理机就把 `BareMetalHost` 注册 → Ironic 探测 →
供电/PXE 这条链路跑通——但这条路**不需要 libvirt/KVM，不需要嵌套虚拟化**，一个
轻量 Docker 容器就够。如果你是在云主机（腾讯云/阿里云这类共享云主机很多不支持
嵌套虚拟化）或者 Hyper-V VM 里但没法开嵌套虚拟化，这条路比 `../vm-bmc/` 现实得多。

## 原理

sushy-tools（跟 `../vm-bmc/` 用的是同一个 OpenStack 官方 Redfish 模拟器）自带一个
`--fake` 驱动模式：不需要背后有真实虚拟机，直接在内存里模拟 N 台"服务器"的开关机
状态、启动方式（PXE/硬盘）——这些正是 Ironic 真正需要通过 Redfish 协议操作的东西。
**这套东西已经在这个项目的沙箱环境里真实跑通验证过**（起 fake BMC → 起真实后端
[K8s 层 mock 掉] → 调用注册脚本 → 确认 3 台机器真的进了数据库，字段完全正确），
不是只测了语法。

局限：fake 驱动不会真的执行 PXE 安装——它能让 Ironic 完整走完注册/探测/开关机这套
状态机，但没有真实系统会被装上。如果你需要看到一个真实 OS 被装起来，最终还是要
`../vm-bmc/`（真实 VM）或者真实物理机。作为"我的后端代码/UI 到底对不对"的测试，
这一层已经足够——它能验证的东西比很多人以为的多。

## 跑起来

```bash
cd deploy/testing/fake-bmc

# 1. 生成 3 台 fake BMC 的配置（数量随便改 --count）
python3 generate_fake_nodes.py --count 3
# 生成 sushy-fake.conf（sushy-emulator 用）和 test_nodes.json（注册脚本用）

# 2. 起容器
docker compose up -d --build
# 监听在宿主机的 8001 端口（docker-compose.yml 里映射的）

# 3. 注册进这个项目的后端（跟 ../vm-bmc/ 完全一样的脚本和参数）
python3 register_with_backend.py \
  --api-base http://localhost:8000 \
  --admin-password "你的后端登录密码" \
  --sushy-host <这台机器能被后端访问到的地址，同机就填 127.0.0.1> \
  --sushy-port 8001 \
  --bmc-username admin \
  --bmc-password password
```

跑完之后，控制台「裸金属主机」页面应该能看到这几台——从这里开始走的就是这个项目
正常的注册/探测/分配/生成清单流程，跟真实物理机完全一样的接口和数据库记录。

## 收尾

```bash
docker compose down
rm -f sushy-fake.conf test_nodes.json
```

## 排查

- **`docker compose up` 报端口冲突**：改 `docker-compose.yml` 里 `"8001:8000"` 左边那个宿主机端口。
- **注册时报 `Connection refused`**：确认 `--sushy-port` 跟 `docker-compose.yml` 里映射的宿主机端口一致（不是容器内部那个 `8000`）。
- **多次测试之间数据"串"了**（比如改了 `--count` 但看到的还是上次的数量）：这是 sushy-tools fake 驱动会把状态持久化在容器内 `/tmp/sushy-emulator` 的缘故——`docker compose down` 会连容器一起删掉，天然是干净的；如果你手动 `docker compose restart`（不是 `down` 再 `up`）状态就会保留，想要干净重来用 `down`。
