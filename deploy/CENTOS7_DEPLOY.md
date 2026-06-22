# CentOS 7 部署说明

> CentOS 7 已停止维护。当前服务器仍可用于家路通 MVP，但后续建议迁移到
> Rocky Linux 9、AlmaLinux 9 或 Ubuntu 24.04 LTS。

部署结构：

```text
微信小程序
  -> https://api.jialutong.cloud
  -> Caddy（自动 HTTPS）
  -> FastAPI 容器 api:8090
  -> ./data 持久化目录
```

不需要在宿主机安装 Python、Nginx 或 Certbot。

## 1. 准备 DNS 和防火墙

在域名控制台新增 A 记录：

- 主机记录：`api`
- 记录值：新服务器公网 IPv4

云服务器安全组和 CentOS 防火墙需允许：

- SSH 管理端口
- TCP 80
- TCP 443
- UDP 443（可选，用于 HTTP/3）

不要向公网开放 8090。

## 2. 安装 Docker

以 root 用户执行：

```bash
yum install -y yum-utils git curl
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
docker version
docker compose version
```

如果 Docker Hub 访问超时，腾讯云服务器可增加镜像加速：

```bash
mkdir -p /etc/docker
printf '%s\n' '{"registry-mirrors":["https://mirror.ccs.tencentyun.com"]}' > /etc/docker/daemon.json
systemctl daemon-reload
systemctl restart docker
```

生产 Compose 已为 Python 依赖构建配置国内 PyPI 镜像，避免
`files.pythonhosted.org` 超时。

如果 Docker 官方仓库不再为 CentOS 7 提供可安装包，应停止部署并升级系统，
不要在宿主机上临时拼装过时的 Python/OpenSSL 运行环境。

## 3. 拉取后端

```bash
mkdir -p /opt/jialutong
cd /opt/jialutong
git clone https://github.com/yangyang0106/jialutong.git server
cd server
```

## 4. 配置密钥

```bash
cp .env.production.example .env.production
openssl rand -hex 32
```

编辑 `.env.production`：

- 将随机字符串写入 `JIALUTONG_UPLOAD_TOKEN`。
- 填入百度地图服务端 AK，并在百度控制台允许新服务器出口 IP。
- 填入腾讯云 TTS 密钥。
- 填入阿里百炼 API Key。
- 保持 `JIALUTONG_PUBLIC_BASE_URL=https://api.jialutong.cloud`。

`.env.production` 不得提交到 Git，也不要通过聊天或截图公开。

## 5. 启动

```bash
mkdir -p data
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8090/health
```

DNS 已生效且 80/443 可访问时，Caddy 会自动申请 HTTPS 证书。公网验证：

```bash
curl https://api.jialutong.cloud/health
```

预期响应：

```json
{"status":"ok"}
```

## 6. 查看日志

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 caddy
```

## 7. 更新和备份

```bash
cd /opt/jialutong/server
tar -czf /opt/jialutong/data-$(date +%F-%H%M).tar.gz data
git pull --ff-only
docker compose up -d --build
docker compose ps
```

`data` 目录保存路线 JSON、照片和音频，升级时不能删除。

## 8. 微信公众平台

在微信公众平台配置：

- request 合法域名：`https://api.jialutong.cloud`
- uploadFile 合法域名：`https://api.jialutong.cloud`
- downloadFile 合法域名：`https://api.jialutong.cloud`

完成公网接口验证后，再修改小程序生产环境服务地址。
