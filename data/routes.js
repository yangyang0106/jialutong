// 路线主干按高德地图方案整理。
// 步行/骑行段必须由家属陪同实地采集：每次转弯、过红绿灯和进出站均单独作为一步。
// 未确认锚点不会开启距离判断，避免向老人提供错误方向。
function buildSteps(steps) {
  return steps.map((step, index) => ({
    stepNo: index + 1,
    image: "",
    audio: "",
    direction: "",
    warning: step.mode === "公交" ? "在这里等车，不要跟陌生人离开。" : "",
    distanceTracking: step.latitude != null && step.longitude != null && !step.verificationRequired,
    ...step
  }));
}

const routes = {
  toMom: {
    id: "to-mom",
    name: "去彩虹湾墨翠里",
    steps: buildSteps([
      {
        mode: "步行或骑行",
        title: "从富友嘉园一期出门",
        desc: "到小区门口后停下。请看实地照片，确认出门后是左转还是右转。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "小区门口转弯",
        desc: "待家属使用高德地图并实地确认：在小区门口左转或右转。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "前往临洮路站的第一个路口",
        desc: "待家属实地确认路口名称、红绿灯位置和转弯方向。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "前往临洮路站的第二个路口",
        desc: "待家属实地确认路口名称、红绿灯位置和转弯方向。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "到达临洮路地铁站入口",
        desc: "到达家属确认的临洮路站入口。骑车时请先停好车，再进入地铁站。",
        verificationRequired: true
      },
      {
        mode: "地铁",
        title: "乘坐 14 号线",
        desc: "在临洮路站乘坐 14 号线，方向为桂桥路方向，到曹杨路站下车。",
        distanceTracking: false
      },
      {
        mode: "地铁换乘",
        title: "曹杨路站换乘 3 号线",
        desc: "在曹杨路站按照站内指示换乘 3 号线，方向为江杨北路方向。",
        distanceTracking: false
      },
      {
        mode: "地铁",
        title: "江湾镇站下车",
        desc: "乘坐 3 号线到江湾镇站下车，从家属确认的出口出站。",
        verificationRequired: true
      },
      {
        mode: "步行",
        title: "从江湾镇站走到 887 路车站",
        desc: "待家属确认地铁出口、887 路上车站名称，以及每一个转弯点。",
        verificationRequired: true
      },
      {
        mode: "公交",
        title: "乘坐 887 路",
        desc: "乘坐开往高境路恒高路方向的 887 路，到家属确认的下车站下车。",
        distanceTracking: false
      },
      {
        mode: "步行",
        title: "下车后走到第一个路口",
        desc: "待家属实地确认下车站、路口名称、红绿灯位置和转弯方向。",
        verificationRequired: true
      },
      {
        mode: "步行",
        title: "从路口走向墨翠里",
        desc: "待家属实地确认左转或右转，并补充醒目的建筑物照片。",
        verificationRequired: true
      },
      {
        mode: "步行",
        title: "到达彩虹湾墨翠里",
        desc: "到达家属确认的墨翠里入口后，再点击完成。",
        verificationRequired: true
      }
    ])
  },
  toHome: {
    id: "to-home",
    name: "回富友嘉园一期",
    steps: buildSteps([
      {
        mode: "步行",
        title: "从彩虹湾墨翠里出门",
        desc: "到家属确认的墨翠里入口后停下，确认出门后的转弯方向。",
        verificationRequired: true
      },
      {
        mode: "步行",
        title: "走到 887 路车站",
        desc: "待家属实地确认每一个转弯点、红绿灯和 887 路上车站名称。",
        verificationRequired: true
      },
      {
        mode: "公交",
        title: "乘坐 887 路",
        desc: "乘坐开往逸仙路场中路方向的 887 路，到家属确认的下车站下车。",
        distanceTracking: false
      },
      {
        mode: "步行",
        title: "从 887 路车站走到江湾镇站",
        desc: "待家属确认每一个转弯点和江湾镇站入口。",
        verificationRequired: true
      },
      {
        mode: "地铁",
        title: "乘坐 3 号线",
        desc: "在江湾镇站乘坐 3 号线，方向为上海南站方向，到曹杨路站下车。",
        distanceTracking: false
      },
      {
        mode: "地铁换乘",
        title: "曹杨路站换乘 14 号线",
        desc: "在曹杨路站按照站内指示换乘 14 号线，方向为封浜方向。",
        distanceTracking: false
      },
      {
        mode: "地铁",
        title: "临洮路站下车",
        desc: "在临洮路站下车，从家属确认的出口出站。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "从临洮路站前往第一个路口",
        desc: "待家属实地确认路口名称、红绿灯位置和转弯方向。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "继续前往富友嘉园一期",
        desc: "待家属实地确认后续每一个转弯点，并补充醒目的建筑物照片。",
        verificationRequired: true
      },
      {
        mode: "步行或骑行",
        title: "到达富友嘉园一期",
        desc: "到达家属确认的小区入口后，再点击完成。",
        verificationRequired: true
      }
    ])
  }
};

function getRouteById(id) {
  return Object.values(routes).find((route) => route.id === id);
}

module.exports = {
  routes,
  getRouteById
};
