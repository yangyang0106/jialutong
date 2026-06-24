const app = getApp();
const { loadElderRoute } = require("../../utils/elder-route-loader");
const {
  getRouteDraft,
  recordStepExecution,
  renderSystemVoice
} = require("../../utils/route-engine/route-repository");
const { adaptRouteForExecution } = require("../../utils/route-engine/elder-route-adapter");
const { applyAssetsToRoute } = require("../../utils/route-assets");
const { getRouteStatus } = require("../../utils/route-status");
const { getTripProgress, saveTripProgress, clearTripProgress } = require("../../utils/trip-progress");
const {
  createExecutionState,
  processLocation,
  resetForStep,
  simulateLocation
} = require("../../utils/route-executor");
const {
  canPlayMoment,
  createVoiceCompanionState,
  getAutoVoiceDecision,
  markMomentPlayed,
  resetVoiceCompanionState,
  resolveStepVoice,
  resumeFromOffRoute,
  VOICE_TIMING
} = require("../../utils/voice-companion");

const LOCATION_REFRESH_INTERVAL = 5000;
const SECOND_AUDIO_DELAY = 1200;
const HELP_HOLD_DURATION = 3000;

function getShortTask(step) {
  if (!step) return "";
  if (step.shortAction) return Array.from(step.shortAction).slice(0, 10).join("");
  if (step.direction) return Array.from(step.direction).slice(0, 8).join("");
  if (step.title.includes("14 号线")) return "坐14号线";
  if (step.title.includes("3 号线")) return step.title.includes("换乘") ? "换乘3号线" : "坐3号线";
  if (step.title.includes("887 路")) return "坐887路";
  if (step.title.includes("江湾镇")) return "江湾镇下车";
  if (step.title.includes("临洮路")) return "临洮路下车";
  return Array.from(step.title).slice(0, 8).join("");
}

Page({
  data: {
    route: null,
    currentStepIndex: 0,
    currentStep: null,
    currentTask: "",
    distance: null,
    remainingDistanceText: "正在确认位置",
    isNearby: false,
    showDirection: false,
    arrivalMessage: "",
    isFinished: false,
    isOffRoute: false,
    helpVisible: false,
    helpHolding: false,
    familyPhone: "",
    emergencyPhone: "",
    emergencyContactName: "",
    emergencyRelation: "",
    canResume: true,
    userLocation: null,
    audioFallback: false,
    audioButtonText: "再听一遍",
    audioStatusText: "",
    isAudioPlaying: false,
    imageUnavailable: false,
    routeSafetyWarning: false,
    locationWarning: "",
    riskReminder: "",
    simulatorEnabled: false,
    simulatorProgress: 0
  },

  onLoad(options) {
    this.simulatorEnabled = options.simulator === "1";
    this.setData({ simulatorEnabled: this.simulatorEnabled });
    wx.showLoading({ title: "正在准备路线", mask: true });
    const routeLoader = this.simulatorEnabled
      ? getRouteDraft(options.id).then((route) => adaptRouteForExecution(route, route.elderSlot))
      : loadElderRoute(options.id);
    routeLoader
      .then((sourceRoute) => this.initializeRoute(sourceRoute))
      .catch(() => this.showMissingRoute())
      .finally(() => wx.hideLoading());
  },

  showMissingRoute() {
    wx.showModal({
      title: "路线不存在",
      content: "请返回首页重新选择。",
      showCancel: false,
      success: () => wx.navigateBack()
    });
  },

  initializeRoute(sourceRoute) {
    if (!sourceRoute) {
      this.showMissingRoute();
      return;
    }
    const status = getRouteStatus(sourceRoute);
    if (!status.ready && !this.simulatorEnabled) {
      const firstStep = status.incompleteSteps[0];
      wx.redirectTo({
        url: `/pages/config/config?routeId=${sourceRoute.id}&stepNo=${firstStep.stepNo}`
      });
      return;
    }
    const route = applyAssetsToRoute(sourceRoute);
    const progress = getTripProgress(route.id);
    this.tripId = progress && progress.tripId || `${route.id}-${Date.now()}`;
    const currentStepIndex =
      progress && progress.currentStepIndex < route.steps.length ? progress.currentStepIndex : 0;
    this.executionState = createExecutionState(currentStepIndex);
    this.voiceCompanionState = createVoiceCompanionState(route.steps[currentStepIndex].stepNo);
    this.systemVoiceCache = {};

    this.audioContext = wx.createInnerAudioContext();
    this.audioContext.obeyMuteSwitch = false;
    this.audioContext.volume = 1;
    if (wx.setInnerAudioOption) {
      wx.setInnerAudioOption({ obeyMuteSwitch: false });
    }
    this.bindAudioEvents();
    this.setData({
      route,
      currentStepIndex,
      currentStep: route.steps[currentStepIndex],
      currentTask: getShortTask(route.steps[currentStepIndex]),
      audioFallback: !route.steps[currentStepIndex].audio,
      familyPhone: app.globalData.familyPhone,
      emergencyPhone: app.globalData.emergencyPhone,
      emergencyContactName: app.globalData.emergencyContactName || "紧急联系人",
      emergencyRelation: app.globalData.emergencyRelation,
      riskReminder: this.getRiskReminder(route.steps[currentStepIndex])
    });
    wx.setNavigationBarTitle({ title: route.name });
    this.resetStepTracking();
    this.playVoiceMoment("enter");
    this.refreshLocation();
    this.startTimers();
    if (currentStepIndex > 0) {
      wx.showToast({ title: `已恢复到第 ${currentStepIndex + 1} 步`, icon: "none" });
    }
  },

  onHide() {
    this.wasHidden = true;
    this.locationGeneration = (this.locationGeneration || 0) + 1;
    this.locationInFlight = false;
    this.pauseTimers();
    if (this.audioContext) this.audioContext.pause();
    this.audioBusy = false;
  },

  onShow() {
    if (!this.data.route || this.data.isFinished) return;
    if (this.wasHidden) {
      this.wasHidden = false;
      wx.showModal({
        title: "请看照片",
        content: "请确认照片中的地点后再继续。",
        showCancel: false
      });
    }
    this.startTimers();
    this.refreshLocation();
  },

  onUnload() {
    this.stopResources();
  },

  stopResources() {
    this.pauseTimers();
    if (this.audioContext) {
      this.audioContext.destroy();
      this.audioContext = null;
    }
  },

  bindAudioEvents() {
    this.audioContext.onPlay(() => {
      this.audioBusy = true;
      this.clearAudioFeedbackTimer();
      this.setData({
        audioFallback: false,
        audioButtonText: "正在播放",
        audioStatusText: "正在播放语音",
        isAudioPlaying: true
      });
    });
    this.audioContext.onWaiting(() => {
      this.audioBusy = true;
      this.setData({
        audioButtonText: "正在加载",
        audioStatusText: "正在准备语音",
        isAudioPlaying: false
      });
      this.startAudioFeedbackTimer();
    });
    this.audioContext.onEnded(() => {
      this.audioBusy = false;
      this.clearAudioFeedbackTimer();
      this.setData({
        audioButtonText: "再听一遍",
        audioStatusText: "语音播放完成",
        isAudioPlaying: false
      });
      if (!this.playPendingAudioRepeat()) this.playNextQueuedVoice();
    });
    this.audioContext.onError(() => this.handleAudioError());
  },

  pauseTimers() {
    if (this.locationTimer) clearInterval(this.locationTimer);
    if (this.audioRepeatTimer) clearTimeout(this.audioRepeatTimer);
    if (this.secondAudioTimer) clearTimeout(this.secondAudioTimer);
    Object.values(this.deferredVoiceTimers || {}).forEach((timer) => clearTimeout(timer));
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.clearAudioFeedbackTimer();
    this.locationTimer = null;
    this.audioRepeatTimer = null;
    this.secondAudioTimer = null;
    this.deferredVoiceTimers = {};
    this.helpHoldTimer = null;
  },

  clearAudioFeedbackTimer() {
    if (this.audioFeedbackTimer) clearTimeout(this.audioFeedbackTimer);
    this.audioFeedbackTimer = null;
  },

  startAudioFeedbackTimer() {
    this.clearAudioFeedbackTimer();
    this.audioFeedbackTimer = setTimeout(() => {
      this.audioFeedbackTimer = null;
      if (!this.data.isAudioPlaying) {
        this.setData({
          audioButtonText: "再听一遍",
          audioStatusText: "请再点一次"
        });
      }
    }, 5000);
  },

  startTimers() {
    if (!this.locationTimer && !this.simulatorEnabled) {
      this.locationTimer = setInterval(() => this.refreshLocation(), LOCATION_REFRESH_INTERVAL);
    }
    this.scheduleRepeatVoice();
  },

  resetStepTracking() {
    this.executionState = resetForStep(this.executionState || createExecutionState(), this.data.currentStepIndex);
    this.voiceCompanionState = resetVoiceCompanionState(
      null,
      this.data.currentStep && this.data.currentStep.stepNo || 0
    );
    this.voiceQueue = [];
    Object.values(this.deferredVoiceTimers || {}).forEach((timer) => clearTimeout(timer));
    this.deferredVoiceTimers = {};
    this.locationGeneration = (this.locationGeneration || 0) + 1;
    this.locationInFlight = false;
    if (this.audioRepeatTimer) {
      clearTimeout(this.audioRepeatTimer);
    }
    this.audioRepeatTimer = null;
    this.scheduleRepeatVoice();
  },

  playVoiceMoment(moment, options = {}) {
    const step = this.data.currentStep;
    const { playTwice = false, userInitiated = false, allowOffRoute = false } = options;
    if (!step || !this.audioContext || (this.data.isOffRoute && !allowOffRoute)) {
      return;
    }
    this.voiceCompanionState = resetVoiceCompanionState(this.voiceCompanionState, step.stepNo);
    if (!userInitiated) {
      const decision = getAutoVoiceDecision(this.voiceCompanionState, moment, step);
      if (!decision.play) {
        if (moment !== "repeat" && decision.retryAfterMs) {
          this.scheduleDeferredVoice(moment, decision.retryAfterMs, step.stepNo);
        }
        return;
      }
    }
    if ((this.audioBusy || this.voicePreparationBusy) && !userInitiated) {
      this.queueVoiceMoment(moment, options);
      return;
    }
    if (!canPlayMoment(this.voiceCompanionState, moment, this.audioBusy, userInitiated)) return;
    const voice = resolveStepVoice(step, moment);
    const cacheKey = `${step.engineStepId || step.stepNo}:${moment}`;
    const audioUrl = voice.audioUrl || this.systemVoiceCache[cacheKey] || "";
    if (!audioUrl && voice.text) {
      this.voicePreparing = this.voicePreparing || {};
      if (this.voicePreparing[cacheKey]) return;
      this.voicePreparing[cacheKey] = true;
      this.voicePreparationBusy = true;
      this.setData({
        audioFallback: false,
        audioButtonText: "正在准备",
        audioStatusText: "正在准备语音",
        isAudioPlaying: false
      });
      renderSystemVoice(
        this.data.route.engineRouteId || this.data.route.id,
        step.engineStepId || String(step.stepNo),
        moment,
        voice.text
      )
        .then((result) => {
          if (!result || !result.audioUrl || this.data.currentStep.stepNo !== step.stepNo) return;
          this.systemVoiceCache[cacheKey] = result.audioUrl;
          this.playResolvedAudio(moment, result.audioUrl, playTwice, userInitiated);
        })
        .catch(() => {
          this.setData({
            audioFallback: true,
            audioButtonText: "再听一遍",
            audioStatusText: voice.text,
            isAudioPlaying: false
          });
        })
        .finally(() => {
          delete this.voicePreparing[cacheKey];
          this.voicePreparationBusy = false;
          if (!this.audioBusy) this.playNextQueuedVoice();
        });
      return;
    }
    this.playResolvedAudio(moment, audioUrl, playTwice, userInitiated);
  },

  playResolvedAudio(moment, audioUrl, playTwice = false, userInitiated = false) {
    if (!audioUrl || !this.audioContext) return;
    if (this.audioBusy && !userInitiated) {
      return;
    }
    if (this.audioBusy && userInitiated) {
      this.audioContext.stop();
    }
    this.audioBusy = true;
    this.pendingAudioRepeat = playTwice;
    this.pendingAudioMoment = moment;
    this.voiceCompanionState = markMomentPlayed(this.voiceCompanionState, moment);
    this.scheduleRepeatVoice();
    this.setData({
      audioButtonText: "正在加载",
      audioStatusText: "正在准备语音",
      isAudioPlaying: false
    });
    this.startAudioFeedbackTimer();

    if (this.audioContext.src === audioUrl) {
      this.audioContext.seek(0);
      this.audioContext.play();
      return;
    }

    this.audioContext.stop();
    this.audioContext.src = audioUrl;
    setTimeout(() => {
      if (this.audioContext) {
        this.audioContext.play();
      }
    }, 80);
  },

  playPendingAudioRepeat() {
    if (!this.pendingAudioRepeat || this.data.isOffRoute) return false;
    this.pendingAudioRepeat = false;
    if (this.secondAudioTimer) clearTimeout(this.secondAudioTimer);
    this.secondAudioTimer = setTimeout(() => {
      this.secondAudioTimer = null;
      this.playVoiceMoment(this.pendingAudioMoment || "enter");
    }, SECOND_AUDIO_DELAY);
    return true;
  },

  queueVoiceMoment(moment, options) {
    if (moment === "repeat") return;
    this.voiceQueue = this.voiceQueue || [];
    if (this.voiceQueue.some((item) => item.moment === moment)) return;
    this.voiceQueue.push({ moment, options });
  },

  scheduleRepeatVoice(delay = null) {
    if (this.audioRepeatTimer) clearTimeout(this.audioRepeatTimer);
    this.audioRepeatTimer = null;
    if (!this.data.route || this.data.isFinished || this.data.isOffRoute) return;
    const step = this.data.currentStep || {};
    const interval =
      delay ||
      (step.riskLevel === "HIGH"
        ? VOICE_TIMING.highRiskRepeatIntervalMs
        : VOICE_TIMING.repeatIntervalMs);
    this.audioRepeatTimer = setTimeout(() => {
      this.audioRepeatTimer = null;
      this.playVoiceMoment("repeat");
      this.scheduleRepeatVoice();
    }, interval);
  },

  scheduleDeferredVoice(moment, delay, stepNo) {
    this.deferredVoiceTimers = this.deferredVoiceTimers || {};
    if (this.deferredVoiceTimers[moment]) return;
    this.deferredVoiceTimers[moment] = setTimeout(() => {
      delete this.deferredVoiceTimers[moment];
      if (this.data.currentStep && this.data.currentStep.stepNo === stepNo) {
        this.playVoiceMoment(moment);
      }
    }, Math.max(1000, delay));
  },

  cancelDeferredVoice(moment) {
    if (!this.deferredVoiceTimers || !this.deferredVoiceTimers[moment]) return;
    clearTimeout(this.deferredVoiceTimers[moment]);
    delete this.deferredVoiceTimers[moment];
  },

  playNextQueuedVoice() {
    if (this.audioBusy || this.voicePreparationBusy || !this.voiceQueue || !this.voiceQueue.length) {
      return;
    }
    const next = this.voiceQueue.shift();
    this.playVoiceMoment(next.moment, next.options);
  },

  handleAudioError() {
    this.audioBusy = false;
    this.clearAudioFeedbackTimer();
    if (this.audioContext) this.audioContext.stop();
    this.pendingAudioRepeat = false;
    this.setData({
      audioFallback: true,
      audioButtonText: "查看提示",
      audioStatusText: "请查看当前提示",
      isAudioPlaying: false
    });
    this.playNextQueuedVoice();
  },

  handleImageError() {
    this.setData({ imageUnavailable: true });
  },

  refreshLocation() {
    const { currentStep, isFinished, isOffRoute } = this.data;
    if (!currentStep || isFinished || isOffRoute) {
      return;
    }
    if (this.locationInFlight) return;
    if (this.simulatorEnabled) return;

    const generation = this.locationGeneration;
    const stepIndex = this.data.currentStepIndex;
    const requestId = (this.locationRequestId || 0) + 1;
    this.locationRequestId = requestId;
    this.locationInFlight = true;
    wx.getLocation({
      type: "gcj02",
      isHighAccuracy: true,
      highAccuracyExpireTime: 4000,
      success: ({ latitude, longitude, accuracy }) => {
        if (generation !== this.locationGeneration || stepIndex !== this.data.currentStepIndex) {
          return;
        }
        this.handleLocationUpdate({ latitude, longitude, accuracy });
      },
      fail: () => {
        this.handleLocationUpdate(null);
      },
      complete: () => {
        if (requestId === this.locationRequestId) {
          this.locationInFlight = false;
        }
      }
    });
  },

  handleLocationUpdate(location) {
    const result = processLocation(
      this.data.route,
      this.executionState || createExecutionState(this.data.currentStepIndex),
      location
    );
    this.executionState = result.state;
    if (result.status === "LOCATION_UNAVAILABLE") {
      this.setData({
        remainingDistanceText: "正在确认位置",
        locationWarning: "暂时无法确认位置，请先停一下"
      });
    } else if (result.status === "LOCATING") {
      this.setData({ remainingDistanceText: "正在确认位置" });
    } else if (result.status === "UNTRACKED") {
      this.setData({
        userLocation: result.userLocation || null,
        distance: null,
        remainingDistanceText: "请按语音和照片前进",
        locationWarning: ""
      });
    } else if (result.distance != null) {
      this.setData({
        userLocation: result.userLocation,
        distance: result.distance,
        remainingDistanceText: result.isNearby
          ? "您已接近目标地点"
          : `距离约 ${result.distance} 米`,
        isNearby: result.isNearby,
        showDirection: result.showDirection,
        routeSafetyWarning: result.routeSafetyWarning,
        locationWarning: ""
      });
    }
    (result.events || []).forEach((event) => this.handleExecutionEvent(event));
  },

  handleExecutionEvent(event) {
    if (event.type === "NEAR") {
      const nearVoice = event.step.nearVoice || "快到了，请看看照片中的地方。";
      this.setData({ arrivalMessage: nearVoice });
      if (event.step.riskLevel === "HIGH") {
        wx.vibrateLong();
      } else {
        wx.vibrateShort({ type: "light" });
      }
      wx.showToast({ title: nearVoice, icon: "none", duration: 2500 });
      this.playVoiceMoment("near");
      return;
    }
    if (event.type === "ARRIVED") {
      this.cancelDeferredVoice("near");
      this.setData({
        isNearby: true,
        arrivalMessage: "您已接近目标地点"
      });
      wx.vibrateLong();
      this.playVoiceMoment("arrived");
      return;
    }
    if (event.type === "OFF_ROUTE") {
      this.triggerOffRoute();
    }
  },

  getRiskReminder(step) {
    if (!step) return "";
    if (step.riskLevel === "HIGH") return "请先停一下，确认安全后再继续";
    if (step.riskLevel === "MEDIUM") return "请放慢速度，确认后继续";
    return "";
  },

  triggerOffRoute() {
    if (this.audioContext) {
      this.audioContext.stop();
    }
    this.audioBusy = false;
    this.voiceQueue = [];
    wx.vibrateLong();
    this.setData({
      isOffRoute: true,
      helpVisible: true,
      routeSafetyWarning: true,
      canResume: true
    });
    this.playVoiceMoment("offRoute", { allowOffRoute: true });
  },

  nextStep() {
    if (this.data.isOffRoute) {
      return;
    }
    this.recordCurrentStepResult("FOUND");
    const nextIndex = this.data.currentStepIndex + 1;
    if (nextIndex >= this.data.route.steps.length) {
      clearTripProgress(this.data.route.id);
      this.stopResources();
      this.setData({ isFinished: true });
      wx.showModal({
        title: "已经到达",
        content: "路线已完成，请注意安全。",
        showCancel: false
      });
      return;
    }

    this.setData({
      currentStepIndex: nextIndex,
      currentStep: this.data.route.steps[nextIndex],
      currentTask: getShortTask(this.data.route.steps[nextIndex]),
      distance: null,
      remainingDistanceText: "正在确认位置",
      isNearby: false,
      showDirection: false,
      arrivalMessage: "",
      audioFallback: !this.data.route.steps[nextIndex].audio,
      audioButtonText: "再听一遍",
      audioStatusText: "",
      isAudioPlaying: false,
      imageUnavailable: false,
      routeSafetyWarning: false,
      locationWarning: "",
      riskReminder: this.getRiskReminder(this.data.route.steps[nextIndex]),
      simulatorProgress: 0
    });
    this.audioBusy = false;
    saveTripProgress(this.data.route.id, nextIndex, this.tripId);
    this.resetStepTracking();
    this.playVoiceMoment("enter");
    this.refreshLocation();
  },

  notFoundYet() {
    this.recordCurrentStepResult("NOT_FOUND");
    this.setData({
      arrivalMessage: "请继续找照片里的地方"
    });
    this.playVoiceMoment("repeat", { userInitiated: true });
  },

  replayAudio() {
    wx.vibrateShort({ type: "light" });
    const moment = this.voiceCompanionState && this.voiceCompanionState.lastMoment || "enter";
    this.playVoiceMoment(moment, { userInitiated: true });
  },

  startHelpHold() {
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.setData({ helpHolding: true });
    this.helpHoldCompleted = false;
    this.helpHoldTimer = setTimeout(() => {
      this.helpHoldTimer = null;
      this.helpHoldCompleted = true;
      this.setData({ helpHolding: false });
      this.requestHelp();
    }, HELP_HOLD_DURATION);
  },

  cancelHelpHold() {
    const shouldShowCancelled = Boolean(this.helpHoldTimer) && !this.helpHoldCompleted;
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.helpHoldTimer = null;
    if (this.data.helpHolding) this.setData({ helpHolding: false });
    if (shouldShowCancelled) wx.showToast({ title: "已取消求助", icon: "none" });
  },

  requestHelp() {
    this.recordCurrentStepResult("HELP", this.data.isOffRoute ? "OFF_ROUTE" : "USER_REQUEST");
    wx.vibrateLong();
    this.setData({
      helpVisible: true
    });
  },

  recordCurrentStepResult(stepResult, helpReason = "", helpStatus = "") {
    if (this.simulatorEnabled || !this.data.route || !this.data.currentStep) return;
    const step = this.data.currentStep;
    recordStepExecution({
      tripId: this.tripId,
      routeId: this.data.route.engineRouteId || this.data.route.id,
      stepId: step.engineStepId || String(step.stepNo),
      stepNo: step.stepNo,
      stepResult,
      occurredAt: new Date().toISOString(),
      helpReason,
      helpStatus: stepResult === "HELP" ? (helpStatus || "REQUESTED") : "NONE",
      emergencyContactName: app.globalData.emergencyContactName || "",
      emergencyRelation: app.globalData.emergencyRelation || "",
      emergencyPhone: app.globalData.emergencyPhone || ""
    }).catch(() => null);
  },

  closeHelp() {
    if (this.data.isOffRoute) {
      return;
    }
    this.setData({ helpVisible: false });
  },

  callEmergency() {
    const phone = app.globalData.emergencyPhone;
    if (!phone) {
      wx.showModal({
        title: "未设置求助电话",
        content: "请让家人先填写紧急联系人姓名、关系和电话。",
        showCancel: false
      });
      return;
    }
    this.recordCurrentStepResult("HELP", "CALL_EMERGENCY", "CALLING");
    wx.makePhoneCall({ phoneNumber: phone });
  },

  resumeRoute() {
    if (!this.data.canResume) return;
    this.setData({
      isOffRoute: false,
      helpVisible: false,
      canResume: true
    });
    this.voiceCompanionState = resumeFromOffRoute(this.voiceCompanionState);
    this.resetStepTracking();
    this.playVoiceMoment("enter");
    this.refreshLocation();
  },

  simulateStart() {
    this.setData({ simulatorProgress: 0 });
    this.handleLocationUpdate(simulateLocation(this.data.route, this.data.currentStepIndex, 0));
  },

  simulateMove() {
    const progress = Math.min(0.9, Number(this.data.simulatorProgress || 0) + 0.25);
    this.setData({ simulatorProgress: progress });
    this.handleLocationUpdate(simulateLocation(this.data.route, this.data.currentStepIndex, progress));
  },

  simulateArrival() {
    this.setData({ simulatorProgress: 1 });
    this.handleLocationUpdate(simulateLocation(this.data.route, this.data.currentStepIndex, 1));
  },

  simulateNextStep() {
    this.nextStep();
  },

  simulateLocationFailure() {
    this.handleLocationUpdate(null);
    this.handleLocationUpdate(null);
    this.handleLocationUpdate(null);
  },

  simulateOffRoute() {
    const step = this.data.currentStep;
    if (!step || step.latitude == null || step.longitude == null) return;
    this.handleLocationUpdate({
      latitude: Number(step.latitude),
      longitude: Number(step.longitude),
      accuracy: 5
    });
    const farAway = {
      latitude: Number(step.latitude) + 0.01,
      longitude: Number(step.longitude) + 0.01,
      accuracy: 5
    };
    this.handleLocationUpdate(farAway);
    this.handleLocationUpdate(farAway);
  },

  simulateVoiceMoment(event) {
    this.playVoiceMoment(event.currentTarget.dataset.moment, { userInitiated: true });
  },

  backHome() {
    if (this.data.route) clearTripProgress(this.data.route.id);
    wx.reLaunch({
      url: "/pages/index/index"
    });
  }
});
