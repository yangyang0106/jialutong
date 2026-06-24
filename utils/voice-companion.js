const { getVoiceMoment } = require("./voice-schema");

const ONCE_PER_STEP = new Set(["near", "arrived"]);
const VOICE_TIMING = Object.freeze({
  repeatIntervalMs: 150000,
  highRiskRepeatIntervalMs: 120000,
  normalNearSilenceMs: 30000,
  highRiskSilenceMs: 15000
});

function createVoiceCompanionState(stepNo = 0) {
  return {
    stepNo,
    played: {},
    offRoutePlayed: false,
    lastMoment: "enter",
    lastPlayedAt: null
  };
}

function resetVoiceCompanionState(state, stepNo) {
  if (!state || state.stepNo !== stepNo) return createVoiceCompanionState(stepNo);
  return state;
}

function canPlayMoment(state, moment, busy = false, userInitiated = false) {
  if (busy && !userInitiated) return false;
  if (!userInitiated && ONCE_PER_STEP.has(moment) && state.played[moment]) return false;
  if (!userInitiated && moment === "offRoute" && state.offRoutePlayed) return false;
  return true;
}

function markMomentPlayed(state, moment, playedAt = Date.now()) {
  const next = {
    ...state,
    played: { ...state.played, [moment]: true },
    lastMoment: moment,
    lastPlayedAt: playedAt
  };
  if (moment === "offRoute") next.offRoutePlayed = true;
  return next;
}

function resumeFromOffRoute(state) {
  return { ...state, offRoutePlayed: false, lastMoment: "enter" };
}

function getAutoVoiceDecision(state, moment, step = {}, now = Date.now()) {
  if (moment === "enter" || moment === "offRoute") return { play: true, retryAfterMs: 0 };
  const elapsed = state && state.lastPlayedAt != null ? now - state.lastPlayedAt : Infinity;
  const highRisk = step.riskLevel === "HIGH";

  if (moment === "repeat") {
    const interval = highRisk
      ? VOICE_TIMING.highRiskRepeatIntervalMs
      : VOICE_TIMING.repeatIntervalMs;
    return {
      play: elapsed >= interval,
      retryAfterMs: Math.max(0, interval - elapsed)
    };
  }

  if (moment === "near") {
    if (!highRisk && (step.type === "START" || step.type === "STRAIGHT")) {
      return { play: false, retryAfterMs: null };
    }
    const silence = highRisk
      ? VOICE_TIMING.highRiskSilenceMs
      : VOICE_TIMING.normalNearSilenceMs;
    return {
      play: elapsed >= silence,
      retryAfterMs: Math.max(0, silence - elapsed)
    };
  }

  if (moment === "arrived") {
    if (!highRisk && step.type !== "DESTINATION") {
      return { play: false, retryAfterMs: null };
    }
    if (step.type === "DESTINATION") return { play: true, retryAfterMs: 0 };
    return {
      play: elapsed >= VOICE_TIMING.highRiskSilenceMs,
      retryAfterMs: Math.max(0, VOICE_TIMING.highRiskSilenceMs - elapsed)
    };
  }

  return { play: true, retryAfterMs: 0 };
}

function resolveStepVoice(step, moment) {
  const fallbackText =
    step.voiceText || step.desc || step.shortAction || step.title || "请继续前进。";
  const fromMoments = (step.voiceMoments || []).find((item) => item.moment === moment);
  return fromMoments || getVoiceMoment(step.voice || {}, moment, fallbackText);
}

module.exports = {
  canPlayMoment,
  createVoiceCompanionState,
  getAutoVoiceDecision,
  markMomentPlayed,
  resetVoiceCompanionState,
  resolveStepVoice,
  resumeFromOffRoute,
  VOICE_TIMING
};
