const SLOT_ROUTE_IDS = Object.freeze({
  TO_MOM: "to-mom",
  TO_HOME: "to-home"
});

const TYPE_MODES = Object.freeze({
  START: "步行",
  STRAIGHT: "步行",
  LEFT: "步行",
  RIGHT: "步行",
  BUS_ON: "公交",
  BUS_OFF: "公交",
  SUBWAY_IN: "地铁",
  SUBWAY_OUT: "地铁",
  TRANSFER: "地铁换乘",
  DESTINATION: "步行"
});

const TYPE_DIRECTIONS = Object.freeze({
  LEFT: "左转",
  STRAIGHT: "直走",
  RIGHT: "右转",
  BUS_ON: "上车",
  BUS_OFF: "下车",
  SUBWAY_IN: "进站",
  SUBWAY_OUT: "出站",
  TRANSFER: "换乘",
  DESTINATION: "到达"
});

const LOCATION_TYPES = new Set(["START", "STRAIGHT", "LEFT", "RIGHT", "DESTINATION"]);
const { calculateDistance, normalizePolyline } = require("../geo");
const { listVoiceMoments, normalizeVoiceConfig } = require("./voice-schema");

function protectLegacyTurnVoice(step, inputVoice) {
  if (step.type !== "LEFT" && step.type !== "RIGHT") return inputVoice;
  let voice = inputVoice;
  const safeTexts = {
    enter: "请先继续往前走，暂时不用转弯。",
    repeat: "请继续往前走，我会提醒您转弯。"
  };
  Object.entries(safeTexts).forEach(([moment, text]) => {
    const typeField = `${moment}VoiceType`;
    if (voice[typeField] === "CUSTOM") return;
    voice = {
      ...voice,
      [`${moment}VoiceText`]: text,
      [`${moment}AudioUrl`]: "",
      [typeField]: "SYSTEM"
    };
    if (moment === "enter") voice = { ...voice, enterVoice: text, audioUrl: "", voiceType: "SYSTEM" };
    if (moment === "repeat") voice = { ...voice, repeatVoice: text };
  });
  return voice;
}

function adaptStep(step) {
  const location = step.location || {};
  let voice = normalizeVoiceConfig(step.voice || {}, step.shortAction || step.title || "");
  voice = protectLegacyTurnVoice(step, voice);
  let latitude = location.latitude == null ? null : Number(location.latitude);
  let longitude = location.longitude == null ? null : Number(location.longitude);
  const pathPolyline = step.source && step.source.polyline || [];
  const pathPoints = normalizePolyline(pathPolyline);
  const pathEnd = pathPoints[pathPoints.length - 1];
  if (
    step.type === "DESTINATION" &&
    pathEnd &&
    latitude != null &&
    longitude != null &&
    calculateDistance(latitude, longitude, pathEnd.latitude, pathEnd.longitude) > 60
  ) {
    latitude = pathEnd.latitude;
    longitude = pathEnd.longitude;
  }
  const distanceTracking =
    LOCATION_TYPES.has(step.type) && latitude != null && longitude != null;
  const voiceText = voice.enterVoice || step.title || step.shortAction || "";

  return {
    stepNo: Number(step.stepNo) || 0,
    engineStepId: step.id || "",
    type: step.type,
    mode: TYPE_MODES[step.type] || "步行",
    title: step.title || step.shortAction || "继续前往",
    desc: voiceText,
    shortAction: step.shortAction || TYPE_DIRECTIONS[step.type] || step.title || "继续前往",
    voiceText,
    nearVoice: voice.nearVoice || "",
    repeatVoice: voice.repeatVoice || voiceText,
    arrivedVoice: voice.arrivedVoiceText,
    offRouteVoice: voice.offRouteVoiceText,
    voiceMoments: listVoiceMoments(voice, voiceText),
    voice,
    image: step.imageUrl || "",
    imageUrl: step.imageUrl || "",
    audio: voice.audioUrl || "",
    latitude,
    longitude,
    direction: step.direction || TYPE_DIRECTIONS[step.type] || "",
    landmarkHint: step.landmarkHint || "",
    pathPolyline,
    arriveRadius: Number(step.arriveRadius) || 30,
    showDirectionDistance: Number(step.showDirectionDistance) || 30,
    verificationRequired: false,
    distanceTracking,
    riskLevel: step.riskLevel || "LOW",
    warning: step.riskLevel === "HIGH" ? "请停一下，确认安全后再继续。" : "",
    transit: step.transit || null
  };
}

function adaptRouteForExecution(route, slot) {
  if (!route || !route.steps || !route.steps.length) return null;
  return {
    id: route.id,
    slotRouteId: SLOT_ROUTE_IDS[slot] || "",
    engineRouteId: route.id,
    elderSlot: slot || route.elderSlot || null,
    name: route.name,
    origin: route.origin,
    destination: route.destination,
    demoData: false,
    published: true,
    sourcePolyline: route.sourcePolyline || [],
    steps: (route.steps || []).map(adaptStep)
  };
}

function adaptPublishedRoute(route, slot) {
  if (!route || route.status !== "PUBLISHED") return null;
  return adaptRouteForExecution(route, slot);
}

module.exports = {
  SLOT_ROUTE_IDS,
  adaptPublishedRoute,
  adaptRouteForExecution,
  adaptStep
};
