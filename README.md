# 家路通文件与路线配置服务

提供图片/语音上传、路线步骤配置同步，以及完整老人路线的草稿、审核和发布能力。

## 本地启动

```bash
cd jialutong-server
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
JIALUTONG_UPLOAD_TOKEN=local-dev-token \
JIALUTONG_PUBLIC_BASE_URL=http://127.0.0.1:8090 \
JIALUTONG_BAIDU_MAP_KEY=替换为百度地图服务端AK \
uvicorn app.main:app --host 0.0.0.0 --port 8090
```

## 接口

- `GET /api/auth/status`：查询是否已创建家庭账号
- `POST /api/auth/wechat-login`：微信小程序快速登录，服务端用 code 换 openid 并签发家路通 Token
- `POST /api/auth/elder-bind-codes`：为老人档案生成一次性绑定码
- `POST /api/auth/wechat-bind-elder`：老人微信使用绑定码绑定老人档案
- `POST /api/auth/elder-bindings`：已登录用户输入绑定码绑定老人档案
- `POST /api/auth/logout`：退出当前登录态
- `GET /api/auth/me`：查询当前微信账号、家庭身份和老人档案
- `GET /api/auth/emergency-contact`：读取当前家庭和老人档案的默认求助联系人
- `PUT /api/auth/emergency-contact`：家庭管理员保存默认求助联系人
- `POST /api/files`：上传图片或音频
- `DELETE /api/files?url=...`：删除已上传文件
- `GET /api/routes/{route_id}`：获取路线步骤配置
- `PUT /api/routes/{route_id}/steps/{step_no}`：更新步骤配置
- `POST /api/engine/route-plans`：由服务端请求百度地图路线规划
- `POST /api/engine/routes/advise`：根据百度候选路线摘要生成家属路线建议
- `POST /api/engine/places/search`：由服务端搜索百度地图地点
- `POST /api/engine/routes`：保存完整路线草稿
- `POST /api/engine/routes/from-baidu`：由服务端将百度原始路线转换为家路通 RouteStep 并保存草稿
- `GET /api/engine/routes`：获取路线草稿列表
- `GET /api/engine/routes/{route_id}`：获取完整路线
- `PUT /api/engine/routes/{route_id}`：更新未发布路线
- `PUT /api/engine/routes/{route_id}/steps/{step_id}/review`：家属审核锚点
- `POST /api/engine/routes/{route_id}/steps/{step_id}/tts`：为步骤生成腾讯云 TTS 语音
- `POST /api/engine/routes/{route_id}/publish`：校验并发布路线
- `GET /api/engine/elder-routes/{slot}`：获取 `TO_MOM / TO_HOME` 对应的最新已发布路线
- `POST /api/engine/trip-results`：记录 `FOUND / NOT_FOUND / HELP`
- `GET /api/engine/routes/{route_id}/trip-summary`：统计步骤结果
- `GET /files/...`：访问上传后的文件

家属端写接口使用 `Authorization: Bearer <登录后返回的 token>`。
`JIALUTONG_UPLOAD_TOKEN` 仅在显式配置时作为部署脚本和应急管理 Token 兼容保留；未配置时不启用旧 Token 鉴权。不要将它放入小程序代码包。

正式小程序端使用微信快速登录：

- 小程序端调用 `wx.login` 获取一次性 code。
- 服务端调用微信 `jscode2session` 换取 openid。
- 服务端创建或找回家庭、家属账号、默认老人档案与绑定关系。
- 服务端签发家路通 Token；微信 `session_key` 不返回给小程序。

需要在服务端配置：

```bash
JIALUTONG_WECHAT_APPID=微信小程序AppID
JIALUTONG_WECHAT_SECRET=微信小程序AppSecret
```

创建路线时需设置 `elderSlot` 为 `TO_MOM` 或 `TO_HOME`，发布后老人首页对应按钮才会读取该路线。

百度地图服务端 AK 只配置在服务端环境变量 `JIALUTONG_BAIDU_MAP_KEY`，不要放入小程序代码包。
该 AK 必须属于百度地图控制台中的服务端应用，并允许部署服务器的出口 IP；浏览器端 AK 会返回 Referer 校验失败。

腾讯云 TTS 密钥只配置在服务端环境变量 `JIALUTONG_TENCENT_SECRET_ID` 和
`JIALUTONG_TENCENT_SECRET_KEY`。可通过 `JIALUTONG_TENCENT_TTS_REGION` 和
`JIALUTONG_TENCENT_TTS_VOICE_TYPE` 调整地域与音色，严禁将长期密钥放入小程序代码包。

路线顾问通过 OpenAI 兼容接口调用，默认使用 `DEEPSEEK_BASE_URL` 和
`DEEPSEEK_MODEL`。`DEEPSEEK_API_KEY` 只能配置在服务端；无密钥或调用失败时，
接口会推荐百度第一条路线并要求家属人工审核，不影响路线创建。

正式部署必须使用 HTTPS，并将数据目录挂载到持久磁盘或改用对象存储。

生产环境建议使用 `docker-compose.yml` 启动。Caddy 自动提供 HTTPS 并代理到
FastAPI 容器，宿主机的 `8090` 只绑定 `127.0.0.1`，不会直接暴露到公网。
纯 CentOS 7 服务器的完整步骤见
[`deploy/CENTOS7_DEPLOY.md`](deploy/CENTOS7_DEPLOY.md)。

## Docker 部署

```bash
docker build -t jialutong-server .
docker run -d \
  -p 8090:8090 \
  -v jialutong-data:/data \
  -e JIALUTONG_UPLOAD_TOKEN='替换成长随机字符串' \
  -e JIALUTONG_PUBLIC_BASE_URL='https://your-domain.example.com' \
  -e JIALUTONG_BAIDU_MAP_KEY='替换为百度地图服务端AK' \
  jialutong-server
```

在反向代理或云平台上为服务配置 HTTPS。然后将同一域名加入微信公众平台的 `request` 与 `uploadFile` 合法域名。

注意：当前账号体系使用 SQLite 文件 `auth.db` 保存家庭、家属、老人档案、绑定关系和会话，适合 MVP 和小规模内测。公开多家庭产品可继续迁移到 PostgreSQL，并增加家庭邀请、账号锁定和短期上传凭证。
