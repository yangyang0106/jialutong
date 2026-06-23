# 家路通路线引擎

本目录负责把百度地图原始路线转换成经过家属审核后才能发布的家人路线。

## 转换流程

```text
百度地图响应
→ baidu-route-parser 标准化
→ decision-point-extractor 提取决策点
→ voice-generator 生成三层语音
→ review 生成审核阻断项
→ 家路通服务端 家属确认并发布
→ elder-route-adapter 转为家人导航页运行数据
→ elder-route-loader 远程读取并缓存，固定 JSON 断网兜底
```

## 当前 MVP 支持

- 步行路线解析
- 公交路线解析
- `START / STRAIGHT / LEFT / RIGHT / BUS_ON / BUS_OFF / SUBWAY_IN / SUBWAY_OUT / TRANSFER / DESTINATION`
- 连续直行压缩
- 三层语音文案
- 风险等级和家属审核
- 高风险步骤家属实拍照片校验
- `FOUND / NOT_FOUND / HELP` 出行结果
- `TO_MOM / TO_HOME` 家人首页按钮位置绑定（仅为历史兼容字段，不代表固定目的地）
- 已发布路线接入家人端与离线缓存

## 入口

- 从百度响应构建路线：`buildFamilyRouteFromBaidu`
- 创建并保存路线草稿：`createAndSaveRouteDraft`
- 家属确认步骤：调用路线步骤审核接口
- 发布路线：调用路线发布接口
- 家人端读取已发布路线：`loadElderRoute`

## 发布到家人首页

创建路线时必须选择首页显示位置。内部仍使用历史字段，但页面不展示固定目的地：

- `TO_MOM`：首页按钮 1
- `TO_HOME`：首页按钮 2

首页按钮文字使用家属创建时填写的自定义路线名称，例如“去医院”“去菜场”“去女儿家”。家人端只读取对应首页位置下最新发布的路线。远程服务不可用时，优先使用上次缓存，缓存也不存在时使用 `data/routes.js` 固定路线。
