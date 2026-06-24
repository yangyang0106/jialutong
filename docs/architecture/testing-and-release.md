# 测试与发布检查

## 后端检查

```bash
cd /Users/ruigu/Documents/home/8888/jialutong/jialutong-server
../../a-stock-assistant/.venv/bin/python -m pytest
```

## 小程序检查

```bash
cd /Users/ruigu/Documents/home/8888/jialutong/jialutong-miniprogram
node -c pages/route/route.js
node -c pages/route-review/route-review.js
node --test tests/*.test.js
/Applications/wechatwebdevtools.app/Contents/MacOS/cli preview --project /Users/ruigu/Documents/home/8888/jialutong/jialutong-miniprogram --qr-format terminal
```

## 真实路线模拟检查

脚本入口：

```bash
cd /Users/ruigu/Documents/home/8888/jialutong/jialutong-miniprogram
JIALUTONG_BASE_URL=http://127.0.0.1:8090 \
JIALUTONG_UPLOAD_TOKEN=change-me \
JIALUTONG_BAIDU_MAP_KEY=你的百度AK \
node scripts/real-route-e2e.js
```

该脚本覆盖：

- 地点搜索。
- 百度路线规划。
- 后端 RouteStep 生成。
- 草稿保存。
- 照片上传。
- 步骤审核。
- 五类语音 TTS。
- 发布路线。
- 模拟 near / arrived / offRoute。
- FOUND / NOT_FOUND / HELP 回流。

## 上架前必须确认

- 小程序端没有测试手机号、测试 token、长期密钥。
- 服务端域名是 HTTPS 公网地址。
- 微信后台配置 request/uploadFile/downloadFile 合法域名。
- `wx.getLocation`、`wx.chooseLocation` 等权限按实际能力开通。
- 生产发布前至少用一条真实路线跑完模拟执行。
