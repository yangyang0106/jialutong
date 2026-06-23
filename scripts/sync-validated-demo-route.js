const fs = require("node:fs");
const path = require("node:path");

const SOURCE_ROUTE_ID = "e2e-fuyou-lintao-walk-v5";
const root = path.resolve(__dirname, "../..");
const sourcePath = path.join(root, "jialutong-server/data/engine-routes.json");
const targetPath = path.join(__dirname, "../data/routes.js");

function readSourceRoute() {
  const stored = JSON.parse(fs.readFileSync(sourcePath, "utf8"));
  const routes = Array.isArray(stored) ? stored : stored.routes || Object.values(stored);
  const route = routes.find((item) => item.id === SOURCE_ROUTE_ID);
  if (!route) throw new Error(`找不到已验证演示路线：${SOURCE_ROUTE_ID}`);
  return route;
}

function directionFor(type) {
  return {
    LEFT: "左转",
    RIGHT: "右转",
    STRAIGHT: "直走",
    DESTINATION: "到达"
  }[type] || "";
}

function adaptStep(step) {
  const voice = step.voice || {};
  return {
    stepNo: step.stepNo,
    engineStepId: step.id,
    type: step.type,
    mode: "步行",
    title: step.title,
    desc: voice.enterVoiceText,
    shortAction: step.shortAction,
    voiceText: voice.enterVoiceText,
    nearVoice: voice.nearVoiceText,
    repeatVoice: voice.repeatVoiceText,
    arrivedVoice: voice.arrivedVoiceText,
    offRouteVoice: voice.offRouteVoiceText,
    voice,
    image: step.imageUrl,
    imageUrl: step.imageUrl,
    audio: voice.enterAudioUrl,
    latitude: step.location.latitude,
    longitude: step.location.longitude,
    direction: step.direction || directionFor(step.type),
    landmarkHint: step.landmarkHint || "",
    pathPolyline: step.source && step.source.polyline || [],
    arriveRadius: step.arriveRadius,
    showDirectionDistance: step.showDirectionDistance,
    verificationRequired: false,
    distanceTracking: true,
    riskLevel: step.riskLevel,
    warning: step.riskLevel === "HIGH" ? "请停一下，确认安全后再继续。" : ""
  };
}

function createDemoRoute(source) {
  return {
    id: "to-mom",
    engineRouteId: source.id,
    name: "去临洮路站",
    demoData: true,
    published: true,
    origin: source.origin,
    destination: source.destination,
    sourcePolyline: source.sourcePolyline,
    steps: source.steps.map(adaptStep)
  };
}

const demoRoute = createDemoRoute(readSourceRoute());
const output = `// 由 scripts/sync-validated-demo-route.js 从已完成端到端模拟的路线生成。
// 图片为测试坐标图，仅供演示执行流程，不可替代家属实景照片。
const routes = {
  validatedDemo: ${JSON.stringify(demoRoute, null, 2)}
};

function getRouteById(id) {
  return Object.values(routes).find((route) => route.id === id);
}

module.exports = {
  routes,
  getRouteById
};
`;

fs.writeFileSync(targetPath, output);
console.log(`已同步 ${demoRoute.steps.length} 个已验证演示锚点到 ${targetPath}`);
