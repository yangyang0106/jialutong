const { DECISION_POINT_TYPES, RISK_LEVELS, VOICE_TYPES } = require("./route-model");

function isRoadCrossing(step) {
  return /过马路|穿过马路|横穿|人行横道|红绿灯/.test(
    step.source && step.source.instruction || ""
  );
}

function turnVoice(step, direction) {
  const target = step.roadName ? `${direction}进入${step.roadName}` : direction;
  const landmark = step.landmarkHint ? `看到${step.landmarkHint}后，` : "";
  if (isRoadCrossing(step)) {
    return {
      enterVoice: `请往前走，${landmark}到前面过马路的位置停下。`,
      nearVoice: `快到路口了，${landmark}请先停一下，确认安全后过马路，再${target}。`,
      repeatVoice: "请继续往前走，我会提醒您转弯。"
    };
  }
  return {
    enterVoice: `请往前走，${landmark}暂时不用转弯。`,
    nearVoice: `快到了，${landmark}请${target}。`,
    repeatVoice: "请继续往前走，我会提醒您转弯。"
  };
}

function directionVoice(direction) {
  if (!direction) return "";
  return /^开往/.test(direction) ? `，${direction}` : `，开往${direction}`;
}

function generateBaseVoice(step, destinationName) {
  const transit = step.transit || {};
  const transitDirection = directionVoice(transit.direction);
  const entrance = transit.accessName || "家人确认过的入口";
  const exit = transit.accessName || "家人确认过的出口";
  switch (step.type) {
    case DECISION_POINT_TYPES.START:
      return {
        enterVoice: `现在带您去${destinationName}，请先从这里出发。`,
        nearVoice: "已经准备好了，请看照片确认方向。",
        repeatVoice: "请按照照片中的方向继续走。"
      };
    case DECISION_POINT_TYPES.LEFT:
      return turnVoice(step, "左转");
    case DECISION_POINT_TYPES.STRAIGHT:
      return {
        enterVoice: step.title ? `请${step.title}。` : "请继续往前走。",
        nearVoice: "快到了，请看照片确认前方地点。",
        repeatVoice: step.title ? `请继续${step.title}。` : "请继续往前走。"
      };
    case DECISION_POINT_TYPES.RIGHT:
      return turnVoice(step, "右转");
    case DECISION_POINT_TYPES.BUS_ON:
      return {
        enterVoice: `请走到${transit.stationName || "公交站"}，等待${transit.lineName || "公交车"}${transitDirection}。`,
        nearVoice: `已经到公交站附近，请确认是${transit.lineName || "要乘坐的公交车"}${transitDirection}再上车。`,
        repeatVoice: `请在这里等待${transit.lineName || "公交车"}${transitDirection}，不要走开。`
      };
    case DECISION_POINT_TYPES.BUS_OFF:
      return {
        enterVoice: "请安心坐车，还没有到站。",
        nearVoice: `下一站${transit.stationName || ""}，请准备下车。`,
        repeatVoice: "请继续坐车，不要提前下车。"
      };
    case DECISION_POINT_TYPES.SUBWAY_IN:
      return {
        enterVoice: `请前往${transit.stationName || "地铁站"}，从${entrance}进站${transitDirection}。`,
        nearVoice: `已经到地铁站附近，请先停一下，确认从${entrance}进站。`,
        repeatVoice: `请找到${entrance}，不要从其他入口进站。`
      };
    case DECISION_POINT_TYPES.SUBWAY_OUT:
      return {
        enterVoice: `请在${transit.stationName || "目标站"}下车。`,
        nearVoice: `到站后请从${exit}出站。`,
        repeatVoice: `请找到${exit}，不要走错出口，找不到就联系家人。`
      };
    case DECISION_POINT_TYPES.TRANSFER:
      return {
        enterVoice: `请在${transit.stationName || "当前站"}下车，站内换乘${transit.lineName || "下一条线路"}${transitDirection}，不要出站。`,
        nearVoice: `请跟着站内指示，换乘${transit.lineName || "下一条线路"}${transitDirection}，不要走到出站口。`,
        repeatVoice: "这是站内换乘，不要出站。找不到请联系家人。"
      };
    case DECISION_POINT_TYPES.DESTINATION:
      return {
        enterVoice: `快到${destinationName}了，请继续找照片里的地方。`,
        nearVoice: "您已经到达目的地。",
        repeatVoice: "请在这里等家人。"
      };
    default:
      return {
        enterVoice: "请继续往前走。",
        nearVoice: "快到了，请看照片。",
        repeatVoice: "请按照照片继续走。"
      };
  }
}

function strengthenHighRiskVoice(voice, step) {
  const isWalkingTurn =
    step.type === DECISION_POINT_TYPES.LEFT || step.type === DECISION_POINT_TYPES.RIGHT;
  const repeatVoice = /找不到.*联系家人/.test(voice.repeatVoice)
    ? voice.repeatVoice
    : `${voice.repeatVoice}找不到请联系家人。`;
  return {
    enterVoice: isWalkingTurn || voice.enterVoice.startsWith("请先停一下")
      ? voice.enterVoice
      : `请先停一下。${voice.enterVoice}`,
    nearVoice: /确认安全/.test(voice.nearVoice)
      ? voice.nearVoice
      : `${voice.nearVoice}确认安全后再继续。`,
    repeatVoice
  };
}

function generateStepVoice(step, destinationName) {
  const baseVoice = generateBaseVoice(step, destinationName);
  const generated =
    step.riskLevel === RISK_LEVELS.HIGH ? strengthenHighRiskVoice(baseVoice, step) : baseVoice;
  return {
    voiceType: VOICE_TYPES.SYSTEM,
    audioUrl: "",
    ...generated,
    arrivedVoiceText:
      step.type === DECISION_POINT_TYPES.DESTINATION
        ? `您已经到达${destinationName}。`
        : "您已接近目标地点，请看照片确认。",
    offRouteVoiceText: "好像走远了，请先停一下，不要继续走。需要帮助请联系家人。",
    enterVoiceText: generated.enterVoice,
    repeatVoiceText: generated.repeatVoice,
    nearVoiceText: generated.nearVoice,
    enterAudioUrl: "",
    repeatAudioUrl: "",
    nearAudioUrl: "",
    arrivedAudioUrl: "",
    offRouteAudioUrl: "",
    enterVoiceType: VOICE_TYPES.SYSTEM,
    repeatVoiceType: VOICE_TYPES.SYSTEM,
    nearVoiceType: VOICE_TYPES.SYSTEM,
    arrivedVoiceType: VOICE_TYPES.SYSTEM,
    offRouteVoiceType: VOICE_TYPES.SYSTEM
  };
}

module.exports = {
  generateStepVoice
};
