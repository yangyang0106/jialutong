const app = getApp();
const { loadElderRoute } = require("../../utils/elder-route-loader");
const {
  getRouteDraft,
  recordStepExecution
} = require("../../utils/route-api");
const { adaptRouteForExecution } = require("../../utils/elder-route-adapter");
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
  createVoiceCompanionState,
  resumeFromOffRoute
} = require("../../utils/voice-companion");

const {
  HELP_HOLD_DURATION,
  LOCATION_REFRESH_INTERVAL,
  buildStepState,
  getRiskReminder
} = require("./route-presenter");
const voiceMethods = require("./route-voice-methods");

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

  ...voiceMethods,

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
      ...buildStepState(route.steps[currentStepIndex], {
        familyPhone: app.globalData.familyPhone,
        emergencyPhone: app.globalData.emergencyPhone,
        emergencyContactName: app.globalData.emergencyContactName || "紧急联系人",
        emergencyRelation: app.globalData.emergencyRelation
      })
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

  getRiskReminder: getRiskReminder,

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
      ...buildStepState(this.data.route.steps[nextIndex])
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
