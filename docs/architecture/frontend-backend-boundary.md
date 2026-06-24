# 前后端职责边界

## 小程序职责

- 首页展示当前家庭/老人可用的已发布路线。
- 家属端发起地点搜索、路线建议、采集、审核、发布操作。
- 老人端执行路线：语音主导、照片辅助、大按钮操作。
- 开发模式模拟执行路线，用于验证语音、到达、偏航、求助链路。

小程序不负责：

- 解析百度原始路线。
- 提取决策点锚点。
- 判断发布规则。
- 生成路线结构。
- 保存长期敏感 token。

## 后端职责

- 微信登录、session token、familyId 隔离。
- 百度路线规划代理和地点搜索。
- 百度原始路线到 RouteStep 的转换。
- AI 路线顾问、AI 语音文案、AI 采集清单、AI 复盘建议。
- TTS 生成和文件上传。
- 路线审核、发布、禁用、行程结果。

## 当前小程序模块边界

- `utils/route-api.js`：后端路线 API 封装。
- `utils/route-service.js`：页面级路线创建编排，只调用后端 API。
- `utils/elder-route-adapter.js`：把已发布后端路线适配为老人端执行数据。
- `utils/voice-schema.js`：运行时语音字段兼容与五类语音读取。
- `pages/route/route-voice-methods.js`：老人端语音播放状态机。
- `pages/route-review/review-presenter.js`：审核页展示数据整理。

已删除：前端 `utils/route-engine/` 本地兼容实现。
