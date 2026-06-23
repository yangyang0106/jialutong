const assert = require("node:assert/strict");
const test = require("node:test");

const { buildFamilyRouteFromBaidu } = require("../utils/route-engine/route-builder");
const {
  adaptPublishedRoute,
  adaptRouteForExecution
} = require("../utils/route-engine/elder-route-adapter");
const {
  DECISION_POINT_TYPES,
  RISK_LEVELS,
  VOICE_TYPES
} = require("../utils/route-engine/route-model");
const { normalizeBaiduRoute } = require("../utils/route-engine/baidu-route-parser");
const { calculateDistance } = require("../utils/geo");

function location(latitude, longitude) {
  return { lat: latitude, lng: longitude };
}

const origin = { name: "富友嘉园一期", latitude: 31.25, longitude: 121.32 };
const destination = { name: "彩虹湾墨翠里", latitude: 31.32, longitude: 121.47 };

function walkingStep(instruction, turnType, roadName, start, end, distance = 100) {
  return {
    instruction,
    turn_type: turnType,
    road_name: roadName,
    distance,
    start_location: start,
    end_location: end,
    path: `${start.lng},${start.lat};${end.lng},${end.lat}`
  };
}

function buildWalkingResponse() {
  return {
    status: 0,
    result: {
      routes: [
        {
          distance: 500,
          duration: 480,
          steps: [
            walkingStep("沿丰庄路直行", "直行", "丰庄路", location(31.25, 121.32), location(31.251, 121.321)),
            walkingStep("前方右转进入临洮路", "右转", "临洮路", location(31.251, 121.321), location(31.252, 121.322)),
            walkingStep("继续直行到终点", "直行", "临洮路", location(31.252, 121.322), location(31.32, 121.47), 300)
          ]
        }
      ]
    }
  };
}

function buildTransitResponse(vehicle = "BUS", lineName = "887路") {
  return {
    status: 0,
    result: {
      routes: [
        {
          distance: 4000,
          duration: 2100,
          steps: [
            [
              walkingStep("步行到临洮路站", "直行", "", location(31.25, 121.32), location(31.251, 121.321)),
              {
                instructions: `乘坐${lineName}`,
                distance: 3800,
                start_location: location(31.251, 121.321),
                end_location: location(31.3, 121.45),
                vehicle_info: {
                  type: vehicle,
                  detail: {
                    uid: "line-1",
                    name: lineName,
                    direction: "高境路恒高路方向",
                    stop_num: 6,
                    departure_station: {
                      name: "临洮路站",
                      location: location(31.251, 121.321)
                    },
                    arrive_station: {
                      name: "江湾镇站",
                      location: location(31.3, 121.45)
                    }
                  }
                }
              },
              walkingStep("步行到终点", "直行", "", location(31.3, 121.45), location(31.32, 121.47))
            ]
          ]
        }
      ]
    }
  };
}

test("Baidu walking route keeps only decision points", () => {
  const route = buildFamilyRouteFromBaidu(buildWalkingResponse(), {
    id: "walking-test",
    name: "测试步行路线",
    elderSlot: "TO_MOM",
    origin,
    destination
  });
  assert.deepEqual(
    route.steps.map((step) => step.type),
    [
      DECISION_POINT_TYPES.START,
      DECISION_POINT_TYPES.RIGHT,
      DECISION_POINT_TYPES.STRAIGHT,
      DECISION_POINT_TYPES.DESTINATION
    ]
  );
  assert.equal(route.steps[1].shortAction, "前面右转");
  assert.doesNotMatch(route.steps[1].voice.enterVoice, /右转/);
  assert.match(route.steps[1].voice.nearVoice, /右转/);
  assert.equal(route.sourceProvider, "BAIDU_MAP");
  assert.equal(route.elderSlot, "TO_MOM");
  assert.equal(route.steps[1].voice.voiceType, VOICE_TYPES.SYSTEM);
});

test("destination anchor uses the planned route endpoint instead of a distant POI center", () => {
  const response = buildWalkingResponse();
  const route = buildFamilyRouteFromBaidu(response, {
    id: "destination-endpoint-test",
    name: "终点落点测试",
    origin,
    destination: { ...destination, latitude: 31.4, longitude: 121.6 }
  });
  const last = route.steps[route.steps.length - 1];
  assert.equal(last.type, DECISION_POINT_TYPES.DESTINATION);
  assert.equal(last.location.latitude, 31.32);
  assert.equal(last.location.longitude, 121.47);
});

test("walking decisions that cross a road require family review", () => {
  const response = buildWalkingResponse();
  response.result.routes[0].steps[1].instruction = "过马路后右转进入南崇明路";
  response.result.routes[0].steps[1].road_name = "";
  const route = buildFamilyRouteFromBaidu(response, {
    id: "cross-road-test",
    name: "过马路测试路线",
    origin,
    destination
  });
  const crossingStep = route.steps.find((step) => step.type === DECISION_POINT_TYPES.RIGHT);
  assert.equal(crossingStep.riskLevel, RISK_LEVELS.HIGH);
  assert.equal(crossingStep.requiresFamilyReview, true);
  assert.equal(crossingStep.roadName, "南崇明路");
  assert.equal(crossingStep.title, "右转进入南崇明路");
  assert.equal(crossingStep.shortAction, "过马路右转");
  assert.doesNotMatch(crossingStep.voice.enterVoice, /^请先停一下/);
  assert.match(crossingStep.voice.enterVoice, /过马路的位置停下/);
  assert.doesNotMatch(crossingStep.voice.enterVoice, /右转/);
  assert.match(crossingStep.voice.nearVoice, /过马路，再右转进入南崇明路/);
});

test("walking route recognizes diagonal turns, side guidance and auxiliary roads", () => {
  const response = buildWalkingResponse();
  response.result.routes[0].steps = [
    walkingStep("向右前方转弯", "右前方转弯", "", location(31.25, 121.32), location(31.251, 121.321)),
    walkingStep("靠左继续走", "靠左", "", location(31.251, 121.321), location(31.252, 121.322)),
    walkingStep("进入曹安公路辅路", "", "曹安公路辅路", location(31.252, 121.322), location(31.253, 121.323)),
    walkingStep("到达终点", "直行", "", location(31.253, 121.323), location(31.254, 121.324))
  ];
  const route = buildFamilyRouteFromBaidu(response, {
    id: "advanced-turn-test",
    name: "复杂转向测试",
    origin,
    destination: { ...destination, latitude: 31.254, longitude: 121.324 }
  });
  assert.deepEqual(
    route.steps.slice(1, 4).map((step) => step.type),
    [DECISION_POINT_TYPES.RIGHT, DECISION_POINT_TYPES.LEFT, DECISION_POINT_TYPES.STRAIGHT]
  );
});

test("long walking segment inserts reassurance anchors", () => {
  const response = buildWalkingResponse();
  response.result.routes[0].steps = [
    {
      ...walkingStep(
        "沿曹安公路辅路走900米",
        "直行",
        "曹安公路辅路",
        location(31.25, 121.32),
        location(31.25, 121.33),
        900
      ),
      path: "121.32,31.25;121.324,31.25;121.328,31.25;121.33,31.25"
    }
  ];
  const route = buildFamilyRouteFromBaidu(response, {
    id: "reassurance-test",
    name: "安心点测试",
    origin,
    destination: { ...destination, latitude: 31.25, longitude: 121.33 }
  });
  const reassuranceSteps = route.steps.filter((step) => step.type === DECISION_POINT_TYPES.STRAIGHT);
  assert.ok(reassuranceSteps.length >= 2);
  assert.ok(reassuranceSteps.every((step) => step.riskLevel === RISK_LEVELS.LOW));
});

test("consecutive walking segments cannot leave a gap over 400 meters", () => {
  const response = buildWalkingResponse();
  response.result.routes[0].steps = [
    walkingStep(
      "沿道路直行300米",
      "直行",
      "",
      location(31.25, 121.32),
      location(31.25, 121.3232),
      300
    ),
    walkingStep(
      "继续直行300米",
      "直行",
      "",
      location(31.25, 121.3232),
      location(31.25, 121.3264),
      300
    )
  ];
  const route = buildFamilyRouteFromBaidu(response, {
    id: "walking-gap-test",
    name: "连续步行安心点测试",
    origin,
    destination: { ...destination, latitude: 31.25, longitude: 121.3264 }
  });
  const gaps = route.steps.slice(1).map((step, index) =>
    calculateDistance(
      route.steps[index].location.latitude,
      route.steps[index].location.longitude,
      step.location.latitude,
      step.location.longitude
    )
  );
  assert.ok(Math.max(...gaps) <= 400);
});

test("nearby anchors receive a smaller arrival radius", () => {
  const response = buildWalkingResponse();
  response.result.routes[0].steps[1].end_location = location(31.25105, 121.32105);
  response.result.routes[0].steps[1].path = "121.321,31.251;121.32105,31.25105";
  const route = buildFamilyRouteFromBaidu(response, {
    id: "nearby-anchor-test",
    name: "近锚点测试",
    origin,
    destination
  });
  assert.ok(route.steps.some((step) => step.arriveRadius < 30));
});

test("published engine route adapts to the family navigation runtime", () => {
  const route = buildFamilyRouteFromBaidu(buildWalkingResponse(), {
    id: "published-route",
    name: "去妈妈家",
    elderSlot: "TO_MOM",
    origin,
    destination
  });
  route.status = "PUBLISHED";
  route.steps[1].imageUrl = "https://files.example.com/right-turn.jpg";
  route.steps[1].voice.voiceType = "CUSTOM";
  route.steps[1].voice.audioUrl = "https://files.example.com/right-turn.mp3";
  route.steps[1].voice.enterVoiceType = "CUSTOM";
  route.steps[1].voice.enterAudioUrl = "https://files.example.com/right-turn.mp3";
  const adapted = adaptPublishedRoute(route, "TO_MOM");
  assert.equal(adapted.id, "published-route");
  assert.equal(adapted.slotRouteId, "to-mom");
  assert.equal(adapted.steps[1].direction, "右转");
  assert.equal(adapted.steps[1].distanceTracking, true);
  assert.equal(adapted.steps[1].audio, "https://files.example.com/right-turn.mp3");
});

test("runtime protects legacy system turn voice but preserves family recording", () => {
  const route = buildFamilyRouteFromBaidu(buildWalkingResponse(), {
    id: "legacy-turn-route",
    name: "旧版语音保护测试",
    elderSlot: "TO_MOM",
    origin,
    destination
  });
  const systemTurn = route.steps[1];
  systemTurn.voice.enterVoiceText = "现在右转。";
  systemTurn.voice.enterAudioUrl = "https://files.example.com/unsafe-tts.mp3";
  systemTurn.voice.enterVoiceType = "TTS";
  const customTurn = { ...systemTurn, id: "custom-turn", voice: { ...systemTurn.voice } };
  customTurn.voice.enterVoiceText = "家属录音：现在右转。";
  customTurn.voice.enterAudioUrl = "https://files.example.com/custom.mp3";
  customTurn.voice.enterVoiceType = "CUSTOM";
  customTurn.voice.audioUrl = "https://files.example.com/custom.mp3";
  customTurn.voice.voiceType = "CUSTOM";
  route.steps.splice(2, 0, customTurn);
  const adapted = adaptRouteForExecution(route, "TO_MOM");
  assert.doesNotMatch(adapted.steps[1].voice.enterVoiceText, /右转/);
  assert.equal(adapted.steps[1].voice.enterAudioUrl, "");
  assert.equal(adapted.steps[1].voice.enterVoiceType, "SYSTEM");
  assert.equal(adapted.steps[2].voice.enterVoiceText, "家属录音：现在右转。");
  assert.equal(adapted.steps[2].voice.enterAudioUrl, "https://files.example.com/custom.mp3");
});

test("runtime uses the route endpoint for a legacy distant destination anchor", () => {
  const route = buildFamilyRouteFromBaidu(buildWalkingResponse(), {
    id: "legacy-destination-route",
    name: "旧版终点保护测试",
    origin,
    destination
  });
  const destinationStep = route.steps[route.steps.length - 1];
  destinationStep.location = { latitude: 31.4, longitude: 121.6 };
  const adapted = adaptRouteForExecution(route);
  const last = adapted.steps[adapted.steps.length - 1];
  assert.equal(last.latitude, 31.32);
  assert.equal(last.longitude, 121.47);
});

test("draft engine route can be opened by the development simulator", () => {
  const route = buildFamilyRouteFromBaidu(buildWalkingResponse(), {
    id: "draft-route",
    name: "待审核路线",
    elderSlot: "TO_MOM",
    origin,
    destination
  });
  const adapted = adaptRouteForExecution(route, "TO_MOM");
  assert.equal(adapted.id, "draft-route");
  assert.equal(adapted.steps.length, route.steps.length);
  assert.equal(adaptPublishedRoute(route, "TO_MOM"), null);
});

test("empty published route is not exposed to navigation", () => {
  assert.equal(adaptPublishedRoute({ id: "empty", status: "PUBLISHED", steps: [] }, "TO_MOM"), null);
});

test("Baidu transit route creates bus on and bus off anchors", () => {
  const response = buildTransitResponse();
  const normalized = normalizeBaiduRoute(response);
  const route = buildFamilyRouteFromBaidu(response, {
    id: "bus-test",
    name: "测试公交路线",
    origin,
    destination
  });
  assert.deepEqual(normalized.travelModes, ["WALKING", "BUS"]);
  assert.deepEqual(
    route.steps.map((step) => step.type),
    [
      DECISION_POINT_TYPES.START,
      DECISION_POINT_TYPES.STRAIGHT,
      DECISION_POINT_TYPES.BUS_ON,
      DECISION_POINT_TYPES.BUS_OFF,
      DECISION_POINT_TYPES.STRAIGHT,
      DECISION_POINT_TYPES.DESTINATION
    ]
  );
  assert.equal(route.steps[1].title, "步行到临洮路站");
  assert.equal(route.steps[2].transit.lineName, "887路");
  assert.equal(route.steps[2].transit.direction, "高境路恒高路方向");
  assert.match(route.steps[2].title, /高境路恒高路方向/);
  assert.match(route.steps[2].voice.enterVoice, /开往高境路恒高路方向/);
});

test("Baidu real transit vehicle structure is parsed", () => {
  const response = {
    status: 0,
    result: {
      routes: [
        {
          distance: 3000,
          duration: 900,
          steps: [
            [
              {
                type: 5,
                instruction: "步行200米",
                start_location: location(31.25, 121.32),
                end_location: location(31.251, 121.321),
                path: "121.32,31.25;121.321,31.251",
                vehicle: { type: 0, name: "" }
              }
            ],
            [
              {
                type: 3,
                instruction: "临洮路站乘887路",
                start_location: location(31.251, 121.321),
                end_location: location(31.3, 121.45),
                path: "121.321,31.251;121.45,31.3",
                vehicle: {
                  type: 0,
                  name: "887路",
                  line_id: "bus-887",
                  direct_text: "高境路方向",
                  start_name: "临洮路站",
                  end_name: "江湾镇站",
                  stop_num: 6,
                  start_info: { start_name: "临洮路站", start_location: location(31.251, 121.321) },
                  end_info: { end_name: "江湾镇站", end_location: location(31.3, 121.45) }
                }
              }
            ]
          ]
        }
      ]
    }
  };
  const normalized = normalizeBaiduRoute(response);
  assert.deepEqual(normalized.travelModes, ["WALKING", "BUS"]);
  assert.equal(normalized.segments[1].transit.lineName, "887路");
  assert.equal(normalized.segments[1].transit.getOn.title, "临洮路站");
  assert.equal(normalized.segments[1].transit.getOff.title, "江湾镇站");
});

test("Baidu real subway station names expose access names separately", () => {
  const response = buildTransitResponse("SUBWAY", "地铁12号线");
  const detail = response.result.routes[0].steps[0][1].vehicle_info.detail;
  detail.start_info = {
    start_name: "天潼路站(3口)",
    start_location: location(31.2438, 121.4822)
  };
  detail.end_info = {
    end_name: "金运路站(8口)",
    end_location: location(31.2409, 121.3196)
  };
  delete detail.departure_station;
  delete detail.arrive_station;
  detail.direct_text = "七莘路方向";
  delete detail.direction;

  const normalized = normalizeBaiduRoute(response);
  const transit = normalized.segments[1].transit;
  assert.equal(transit.getOn.title, "天潼路站");
  assert.equal(transit.getOn.accessName, "3口");
  assert.equal(transit.getOff.title, "金运路站");
  assert.equal(transit.getOff.accessName, "8口");
  assert.equal(transit.direction, "七莘路方向");
});

test("Baidu subway anchors are parsed and require family review", () => {
  const response = buildTransitResponse("SUBWAY", "14号线");
  response.result.routes[0].steps[0][0].instruction = "步行到临洮路站，从1号口进站";
  response.result.routes[0].steps[0][2].instruction = "从3号口出站后步行到终点";
  const route = buildFamilyRouteFromBaidu(response, {
    id: "subway-test",
    name: "测试地铁路线",
    origin,
    destination
  });
  assert.deepEqual(
    route.steps.map((step) => step.type),
    [
      DECISION_POINT_TYPES.START,
      DECISION_POINT_TYPES.STRAIGHT,
      DECISION_POINT_TYPES.SUBWAY_IN,
      DECISION_POINT_TYPES.SUBWAY_OUT,
      DECISION_POINT_TYPES.STRAIGHT,
      DECISION_POINT_TYPES.DESTINATION
    ]
  );
  assert.equal(route.steps[2].riskLevel, RISK_LEVELS.HIGH);
  assert.equal(route.steps[2].requiresFamilyReview, true);
  assert.equal(route.steps[2].transit.accessName, "1号口");
  assert.equal(route.steps[3].transit.accessName, "3号口");
  assert.match(route.steps[2].title, /1号口进站/);
  assert.match(route.steps[3].voice.nearVoice, /3号口出站/);
});

test("subway access remains unconfirmed when Baidu does not provide an entrance or exit", () => {
  const route = buildFamilyRouteFromBaidu(buildTransitResponse("SUBWAY", "14号线"), {
    id: "subway-access-review-test",
    name: "地铁口待确认测试",
    origin,
    destination
  });
  const subwayIn = route.steps.find((step) => step.type === DECISION_POINT_TYPES.SUBWAY_IN);
  const subwayOut = route.steps.find((step) => step.type === DECISION_POINT_TYPES.SUBWAY_OUT);
  assert.equal(subwayIn.transit.accessName, "");
  assert.equal(subwayOut.transit.accessName, "");
  assert.match(subwayIn.title, /家属确认的入口/);
  assert.match(subwayOut.title, /家属确认的出口/);
});

test("station transfer does not create an intermediate subway exit", () => {
  const firstLine = buildTransitResponse("SUBWAY", "地铁12号线").result.routes[0].steps[0][1];
  firstLine.vehicle_info.detail.departure_station.name = "天潼路站";
  firstLine.vehicle_info.detail.arrive_station.name = "汉中路站";
  firstLine.vehicle_info.detail.arrive_station.location = location(31.2417, 121.4585);
  firstLine.end_location = location(31.2417, 121.4585);

  const secondLine = JSON.parse(JSON.stringify(firstLine));
  secondLine.vehicle_info.detail.name = "地铁13号线";
  secondLine.vehicle_info.detail.departure_station.name = "汉中路站";
  secondLine.vehicle_info.detail.departure_station.location = location(31.2417, 121.4585);
  secondLine.vehicle_info.detail.arrive_station.name = "金沙江西路站";
  secondLine.vehicle_info.detail.arrive_station.location = location(31.24, 121.34);
  secondLine.start_location = location(31.2417, 121.4585);
  secondLine.end_location = location(31.24, 121.34);

  const response = {
    status: 0,
    result: {
      routes: [
        {
          distance: 12000,
          duration: 2400,
          steps: [
            [
              firstLine,
              {
                instructions: "站内通道换乘 步行200米",
                instruction: "站内通道换乘 步行200米",
                start_location: location(31.2417, 121.4585),
                end_location: location(31.2417, 121.4585),
                path: "121.4585,31.2417;121.4585,31.2417"
              },
              secondLine
            ]
          ]
        }
      ]
    }
  };

  const route = buildFamilyRouteFromBaidu(response, {
    id: "station-transfer-test",
    name: "站内换乘测试",
    origin,
    destination
  });
  assert.deepEqual(
    route.steps.map((step) => step.type),
    [
      DECISION_POINT_TYPES.START,
      DECISION_POINT_TYPES.SUBWAY_IN,
      DECISION_POINT_TYPES.TRANSFER,
      DECISION_POINT_TYPES.SUBWAY_OUT,
      DECISION_POINT_TYPES.DESTINATION
    ]
  );
  assert.match(route.steps[2].title, /在汉中路站内换乘地铁13号线，开往/);
  assert.match(route.steps[2].voice.enterVoice, /不要出站/);
  assert.match(route.steps[2].voice.enterVoice, /开往/);
  assert.equal(
    route.steps.filter((step) => step.type === DECISION_POINT_TYPES.SUBWAY_OUT).length,
    1
  );
});
