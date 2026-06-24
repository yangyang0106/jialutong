# 路线引擎

路线引擎的唯一职责是把地图路线转换成老人可执行的家庭路线资产。

## 输入

- 起点、终点、出行方式。
- 百度路线规划原始返回。
- 家属补充的照片、地标、真人语音。
- AI 生成的建议和文案。

## 输出

- Route。
- RouteStep[]。
- 每步五类语音：enter、repeat、near、arrived、offRoute。
- riskLevel、imageStatus、reviewStatus、requiresFamilyReview 等审核字段。

## 决策点原则

只保留老人真正需要决策或确认的点：

- START
- LEFT / RIGHT / 其他方向变化
- BUS_ON / BUS_OFF
- SUBWAY_IN / SUBWAY_OUT / TRANSFER
- DESTINATION
- 长距离无决策点时插入安心确认点

不按固定距离密集生成锚点。

## 服务端实现位置

- `jialutong-server/app/services/route_engine/baidu_route_parser.py`
- `jialutong-server/app/services/route_engine/decision_point_extractor.py`
- `jialutong-server/app/services/route_engine/route_builder.py`
- `jialutong-server/app/services/route_engine/route_plan_summarizer.py`

## 禁止事项

- 小程序端重新实现路线引擎。
- AI 修改坐标、增删步骤或编造线路站点。
- 未经家属审核自动发布路线。
