# HTTPS 反向代理

这个目录本身是空的（除了这份 README）——`scripts/setup-https-selfsigned.sh` 或
`scripts/setup-https-letsencrypt.sh` 跑起来之后，会在这里生成 `nginx.conf`、
证书文件这些，同时改写项目根目录的 `docker-compose.yml`，把 `frontend`/`api`/
`postgres`/`redis` 的直接端口暴露收掉，只留 nginx 对外开 80/443。

## 两个脚本选哪个

- **`scripts/setup-https-selfsigned.sh <域名>`**——自签证书，几秒钟搞定，不需要
  真实域名解析，也不需要公网能访问到这台机器。**浏览器会一直提示"不安全"**，
  证书是自己签的，没有任何机构信任它。适合内网测试、还没配好 DNS 之前先跑起来看看。

- **`scripts/setup-https-letsencrypt.sh <域名> [邮箱]`**——真正被浏览器信任的证书，
  免费，但要求：
  1. 域名已经解析到这台机器的公网 IP（脚本会检查一下，不匹配会警告但不会拦截）
  2. 这台机器的 80 端口能被公网访问到（云主机防火墙/安全组要放行；如果是国内
     云主机比如腾讯云/阿里云，还要求这个域名已经完成 ICP 备案，否则云厂商自己
     的网络层就会把流量拦掉，跟这个脚本没关系，得先去控制台完成备案）
  3. 证书 90 天过期，脚本装好后需要你自己配个 cron 定期跑 `scripts/renew-https-certs.sh`
     （脚本跑完最后会打印具体的 crontab 命令）

两个脚本背后改 `docker-compose.yml` 的逻辑是共用的（`scripts/lib/patch_compose_for_https.py`），
已经有测试覆盖（`tests/test_https_setup_scripts.py`），包括专门验证过反复运行不会
把 nginx 服务重复插入两遍。

## 一个容易被忽略但很关键的点：WebSocket

部署进度页面的实时推送走的是 WebSocket（`/api/v1/deployments/{id}/ws`）。这两个
脚本生成的 nginx 配置**都**正确转发了 `Upgrade`/`Connection` 这两个头——如果你
以后自己改这份配置，千万别漏了这两行，漏了不会报错，就是这个页面的进度条永远
不会动，排查起来很反直觉。

## 验证限制

这两个脚本没法在开发这套代码的沙箱环境里跑一次完整的真实验证——那个环境里连
Docker 和 nginx 二进制都装不上（镜像源连不通），更别说去公网申请一张真实的
Let's Encrypt 证书了。已经验证过的部分：`docker-compose.yml` 的字符串替换逻辑
（对着这个项目真实的 compose 文件跑过，包括反复运行的幂等性），shell 语法，
以及 nginx 配置里 WebSocket 头是不是写对了。**没验证过的部分**：nginx 配置文件
本身的语法用真实 nginx 校验过没有、Let's Encrypt 的 HTTP-01 挑战流程真的走一遍
成功没有——这两块只能靠你在真实机器上第一次运行的时候验证。
