const assert = require("node:assert/strict");
const test = require("node:test");
const {
  canPlayMoment,
  createVoiceCompanionState,
  getAutoVoiceDecision,
  markMomentPlayed,
  resolveStepVoice,
  resumeFromOffRoute,
  VOICE_TIMING
} = require("../utils/voice-companion");
const { normalizeVoiceConfig, setVoiceMoment } = require("../utils/route-engine/voice-schema");

test("旧语音结构会补齐五类语音文案", () => {
  const voice = normalizeVoiceConfig({
    voiceType: "CUSTOM",
    audioUrl: "/enter.mp3",
    enterVoice: "现在出发。",
    repeatVoice: "继续走。",
    nearVoice: "快到了。"
  });
  assert.equal(voice.enterAudioUrl, "/enter.mp3");
  assert.equal(voice.enterVoiceType, "CUSTOM");
  assert.equal(voice.arrivedVoiceText, "您已接近目标地点，请看照片确认。");
  assert.match(voice.offRouteVoiceText, /请先停一下/);
});

test("普通途中提醒保持长静默，直行安心点不重复播接近和到达", () => {
  const now = 1000000;
  const state = markMomentPlayed(createVoiceCompanionState(1), "enter", now);
  const straight = { type: "STRAIGHT", riskLevel: "LOW" };
  assert.equal(getAutoVoiceDecision(state, "repeat", straight, now + 30000).play, false);
  assert.equal(
    getAutoVoiceDecision(state, "repeat", straight, now + VOICE_TIMING.repeatIntervalMs).play,
    true
  );
  assert.equal(getAutoVoiceDecision(state, "near", straight, now + 60000).play, false);
  assert.equal(getAutoVoiceDecision(state, "arrived", straight, now + 60000).play, false);
});

test("转弯接近提醒等待静默期，普通到达静默，高风险和终点保留到达提醒", () => {
  const now = 2000000;
  const state = markMomentPlayed(createVoiceCompanionState(2), "enter", now);
  const turn = { type: "RIGHT", riskLevel: "LOW" };
  const highRiskTurn = { type: "RIGHT", riskLevel: "HIGH" };
  const destination = { type: "DESTINATION", riskLevel: "LOW" };
  assert.equal(getAutoVoiceDecision(state, "near", turn, now + 10000).play, false);
  assert.equal(
    getAutoVoiceDecision(state, "near", turn, now + VOICE_TIMING.normalNearSilenceMs).play,
    true
  );
  assert.equal(getAutoVoiceDecision(state, "arrived", turn, now + 60000).play, false);
  assert.equal(
    getAutoVoiceDecision(state, "arrived", highRiskTurn, now + VOICE_TIMING.highRiskSilenceMs).play,
    true
  );
  assert.equal(getAutoVoiceDecision(state, "arrived", destination, now + 1000).play, true);
});

test("每类语音可以独立使用真人录音或 TTS", () => {
  let voice = normalizeVoiceConfig({}, "向前走");
  voice = setVoiceMoment(voice, "near", { voiceType: "CUSTOM", audioUrl: "/near.mp3" });
  voice = setVoiceMoment(voice, "arrived", { voiceType: "TTS", audioUrl: "/arrived.mp3" });
  assert.equal(resolveStepVoice({ voice }, "near").voiceType, "CUSTOM");
  assert.equal(resolveStepVoice({ voice }, "arrived").voiceType, "TTS");
});

test("接近和到达每步只播一次，偏航恢复后可再次播报", () => {
  let state = createVoiceCompanionState(1);
  assert.equal(canPlayMoment(state, "near"), true);
  state = markMomentPlayed(state, "near");
  assert.equal(canPlayMoment(state, "near"), false);
  assert.equal(canPlayMoment(state, "near", false, true), true);
  state = markMomentPlayed(state, "offRoute");
  assert.equal(canPlayMoment(state, "offRoute"), false);
  state = resumeFromOffRoute(state);
  assert.equal(canPlayMoment(state, "offRoute"), true);
  assert.equal(canPlayMoment(state, "repeat", true, false), false);
  assert.equal(canPlayMoment(state, "repeat", true, true), true);
});
