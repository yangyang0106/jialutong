const LOCATION_REFRESH_INTERVAL = 5000;
const SECOND_AUDIO_DELAY = 1200;
const HELP_HOLD_DURATION = 3000;

function takeChars(value, count) {
  return Array.from(value || "").slice(0, count).join("");
}

function getShortTask(step) {
  if (!step) return "";
  if (step.elderShortAction) return takeChars(step.elderShortAction, 10);
  if (step.shortAction) return takeChars(step.shortAction, 10);
  if (step.direction) return takeChars(step.direction, 8);
  return takeChars(step.title, 8);
}

function getRiskReminder(step) {
  if (!step) return "";
  if (step.riskLevel === "HIGH") return "请先停一下，确认安全后再继续";
  if (step.riskLevel === "MEDIUM") return "请放慢速度，确认后继续";
  return "";
}

function buildStepState(step, overrides = {}) {
  return {
    currentStep: step,
    currentTask: getShortTask(step),
    distance: null,
    remainingDistanceText: "正在确认位置",
    isNearby: false,
    showDirection: false,
    arrivalMessage: "",
    audioFallback: !step.audio,
    audioButtonText: "再听一遍",
    audioStatusText: "",
    isAudioPlaying: false,
    imageUnavailable: false,
    routeSafetyWarning: false,
    locationWarning: "",
    riskReminder: getRiskReminder(step),
    simulatorProgress: 0,
    ...overrides
  };
}

module.exports = {
  HELP_HOLD_DURATION,
  LOCATION_REFRESH_INTERVAL,
  SECOND_AUDIO_DELAY,
  buildStepState,
  getRiskReminder,
  getShortTask
};
