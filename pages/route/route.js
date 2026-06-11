const app = getApp();
const { getRouteById } = require("../../data/routes");
const { calculateDistance } = require("../../utils/geo");
const { applyAssetsToRoute } = require("../../utils/route-assets");
const { getRouteStatus } = require("../../utils/route-status");
const { getTripProgress, saveTripProgress, clearTripProgress } = require("../../utils/trip-progress");

const LOCATION_REFRESH_INTERVAL = 5000;
const NEARBY_DISTANCE_METERS = 30;
const OFF_ROUTE_DISTANCE_METERS = 120;
const OFF_ROUTE_INCREASE_METERS = 80;
const AUDIO_REPEAT_INTERVAL = 20000;
const NEARBY_CONFIRM_COUNT = 2;
const OFF_ROUTE_CONFIRM_COUNT = 2;
const MAX_LOCATION_ACCURACY_METERS = 50;

Page({
  data: {
    route: null,
    currentStepIndex: 0,
    currentStep: null,
    distance: null,
    distanceText: "正在获取当前位置...",
    isNearby: false,
    locationError: "",
    isFinished: false,
    isOffRoute: false,
    helpVisible: false,
    currentLocationText: "正在获取当前位置",
    familyPhone: "",
    canResume: true
  },

  onLoad(options) {
    const sourceRoute = getRouteById(options.id);

    if (!sourceRoute) {
      wx.showModal({
        title: "路线不存在",
        content: "请返回首页重新选择。",
        showCancel: false,
        success: () => wx.navigateBack()
      });
      return;
    }
    const status = getRouteStatus(sourceRoute);
    if (!status.ready) {
      wx.showModal({
        title: "路线尚未启用",
        content: "路线配置不完整，请让家属先完成配置。",
        showCancel: false,
        success: () => wx.navigateBack()
      });
      return;
    }
    const route = applyAssetsToRoute(sourceRoute);
    const progress = getTripProgress(route.id);
    const currentStepIndex =
      progress && progress.currentStepIndex < route.steps.length ? progress.currentStepIndex : 0;

    this.audioContext = wx.createInnerAudioContext();
    this.audioContext.onError(() => this.handleAssetError("语音"));
    this.setData({
      route,
      currentStepIndex,
      currentStep: route.steps[currentStepIndex],
      familyPhone: app.globalData.familyPhone
    });
    wx.setNavigationBarTitle({ title: route.name });
    this.resetStepTracking();
    this.playStepAudio();
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
  },

  onShow() {
    if (!this.data.route || this.data.isFinished) return;
    if (this.wasHidden) {
      this.wasHidden = false;
      wx.showModal({
        title: "导航已恢复",
        content: "小程序进入后台时无法保证持续定位。请确认当前位置和当前步骤后再继续。",
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

  pauseTimers() {
    if (this.locationTimer) clearInterval(this.locationTimer);
    if (this.audioRepeatTimer) clearInterval(this.audioRepeatTimer);
    this.locationTimer = null;
    this.audioRepeatTimer = null;
  },

  startTimers() {
    if (!this.locationTimer) {
      this.locationTimer = setInterval(() => this.refreshLocation(), LOCATION_REFRESH_INTERVAL);
    }
    if (!this.audioRepeatTimer) {
      this.audioRepeatTimer = setInterval(() => this.playStepAudio(), AUDIO_REPEAT_INTERVAL);
    }
  },

  resetStepTracking() {
    this.nearbyCount = 0;
    this.offRouteCount = 0;
    this.closestDistance = null;
    this.locationGeneration = (this.locationGeneration || 0) + 1;
    this.locationInFlight = false;
    if (this.audioRepeatTimer) {
      clearInterval(this.audioRepeatTimer);
    }
    this.audioRepeatTimer = setInterval(() => this.playStepAudio(), AUDIO_REPEAT_INTERVAL);
  },

  playStepAudio() {
    const step = this.data.currentStep;
    if (!step || !step.audio || !this.audioContext || this.data.isOffRoute) {
      return;
    }
    this.audioContext.stop();
    this.audioContext.src = step.audio;
    this.audioContext.play();
  },

  handleAssetError(kind) {
    if (this.data.helpVisible) return;
    if (this.audioContext) this.audioContext.stop();
    wx.vibrateLong();
    this.setData({
      isOffRoute: true,
      helpVisible: true,
      canResume: false
    });
    wx.showModal({
      title: `${kind}不可用`,
      content: "路线素材可能已丢失。请停下并联系家属。",
      showCancel: false
    });
    this.updateHelpLocation();
  },

  handleImageError() {
    this.handleAssetError("图片");
  },

  refreshLocation() {
    const { currentStep, isFinished, isOffRoute } = this.data;
    if (!currentStep || isFinished || isOffRoute) {
      return;
    }
    if (this.locationInFlight) return;

    if (!currentStep.distanceTracking) {
      this.setData({
        distance: null,
        distanceText: currentStep.verificationRequired
          ? "此转弯点尚未实地确认，暂不提供距离提示"
          : "乘车步骤，请按上方文字提示操作",
        isNearby: false,
        locationError: ""
      });
      return;
    }

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
        if (accuracy && accuracy > MAX_LOCATION_ACCURACY_METERS) {
          this.setData({
            locationError: `当前位置精度不足（误差约 ${Math.round(accuracy)} 米），不会自动切换步骤。`,
            distanceText: "正在等待更准确的位置"
          });
          return;
        }
        const distance = calculateDistance(
          latitude,
          longitude,
          currentStep.latitude,
          currentStep.longitude
        );
        const isNearby = distance < NEARBY_DISTANCE_METERS;
        this.closestDistance =
          this.closestDistance == null ? distance : Math.min(this.closestDistance, distance);
        this.nearbyCount = isNearby ? this.nearbyCount + 1 : 0;

        const isMovingAway =
          distance > OFF_ROUTE_DISTANCE_METERS &&
          distance - this.closestDistance > OFF_ROUTE_INCREASE_METERS;
        this.offRouteCount = isMovingAway ? this.offRouteCount + 1 : 0;

        this.setData({
          distance,
          distanceText: `距离下一个转弯点还有 ${distance} 米`,
          isNearby,
          currentLocationText: `纬度 ${latitude.toFixed(6)}，经度 ${longitude.toFixed(6)}`,
          locationError: ""
        });

        if (this.offRouteCount >= OFF_ROUTE_CONFIRM_COUNT) {
          this.triggerOffRoute();
          return;
        }
        if (this.nearbyCount >= NEARBY_CONFIRM_COUNT) {
          this.nextStep(true);
        }
      },
      fail: () => {
        this.setData({
          locationError: "无法获取当前位置，请检查手机定位权限。",
          distanceText: "暂时无法计算距离"
        });
      },
      complete: () => {
        if (requestId === this.locationRequestId) {
          this.locationInFlight = false;
        }
      }
    });
  },

  triggerOffRoute() {
    if (this.audioContext) {
      this.audioContext.stop();
    }
    wx.vibrateLong();
    this.setData({
      isOffRoute: true,
      helpVisible: true,
      canResume: true
    });
    this.updateHelpLocation();
  },

  nextStep(isAutomatic = false) {
    if (this.data.isOffRoute) {
      return;
    }
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
      distance: null,
      distanceText: "正在获取当前位置...",
      isNearby: false,
      locationError: ""
    });
    saveTripProgress(this.data.route.id, nextIndex);
    this.resetStepTracking();
    this.playStepAudio();
    if (isAutomatic) {
      wx.vibrateShort({ type: "medium" });
    }
    this.refreshLocation();
  },

  previousStep() {
    const previousIndex = this.data.currentStepIndex - 1;
    if (previousIndex < 0) {
      wx.vibrateShort({ type: "medium" });
      return;
    }
    this.setData({
      currentStepIndex: previousIndex,
      currentStep: this.data.route.steps[previousIndex],
      distance: null,
      distanceText: "正在获取当前位置...",
      isNearby: false,
      isOffRoute: false,
      helpVisible: false,
      locationError: ""
    });
    saveTripProgress(this.data.route.id, previousIndex);
    this.resetStepTracking();
    this.playStepAudio();
    this.refreshLocation();
  },

  replayAudio() {
    const { audio } = this.data.currentStep;
    if (!audio) {
      wx.showModal({
        title: "语音不可用",
        content: "请停下并联系家属，不要依赖文字继续前进。",
        showCancel: false,
        confirmText: "联系家属",
        success: () => this.requestHelp()
      });
      return;
    }

    this.playStepAudio();
  },

  requestHelp() {
    wx.vibrateLong();
    this.setData({
      helpVisible: true
    });
    this.updateHelpLocation();
  },

  updateHelpLocation() {
    wx.getLocation({
      type: "gcj02",
      isHighAccuracy: true,
      highAccuracyExpireTime: 4000,
      success: ({ latitude, longitude }) => {
        this.setData({
          currentLocationText: `纬度 ${latitude.toFixed(6)}，经度 ${longitude.toFixed(6)}`
        });
      },
      fail: () => {
        this.setData({
          currentLocationText: "定位失败，请查看手机地图或联系家属"
        });
      }
    });
  },

  closeHelp() {
    if (this.data.isOffRoute) {
      return;
    }
    this.setData({ helpVisible: false });
  },

  callFamily() {
    const phone = app.globalData.familyPhone;
    if (!phone) {
      wx.showModal({
        title: "未设置家属电话",
        content: "请先在 app.js 中填写家属电话号码。",
        showCancel: false
      });
      return;
    }
    wx.makePhoneCall({ phoneNumber: phone });
  },

  callEmergency() {
    wx.makePhoneCall({ phoneNumber: app.globalData.emergencyPhone });
  },

  resumeRoute() {
    if (!this.data.canResume) return;
    this.setData({
      isOffRoute: false,
      helpVisible: false,
      canResume: true
    });
    this.resetStepTracking();
    this.playStepAudio();
    this.refreshLocation();
  },

  backHome() {
    if (this.data.route) clearTripProgress(this.data.route.id);
    wx.reLaunch({
      url: "/pages/index/index"
    });
  }
});
