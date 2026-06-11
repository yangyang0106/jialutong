const { routes } = require("../../data/routes");
const {
  getStepAsset,
  saveStepAsset,
  saveStepConfig,
  removeStepAsset
} = require("../../utils/route-assets");
const { storeFile, removeStoredFile } = require("../../utils/file-storage");
const { stepNeedsLocation, getStepIssues } = require("../../utils/route-status");
const { getSettings, saveSettings } = require("../../utils/settings");
const { pushStepConfig, pullRouteConfig, deleteRemoteFile } = require("../../utils/remote-config");
const app = getApp();

Page({
  data: {
    routes: [],
    totalSteps: 0,
    imageCount: 0,
    audioCount: 0,
    missingImages: 0,
    missingAudios: 0,
    recordingKey: "",
    familyPhone: "",
    emergencyPhone: ""
  },

  onLoad() {
    this.recorder = wx.getRecorderManager();
    this.audioContext = wx.createInnerAudioContext();
    this.bindRecorderEvents();
    this.setData(getSettings());
    Promise.all([pullRouteConfig("to-mom"), pullRouteConfig("to-home")])
      .catch(() => null)
      .finally(() => this.refreshRoutes());
  },

  onShow() {
    this.refreshRoutes();
  },

  onUnload() {
    if (this.pendingRecording) {
      this.recorder.stop();
      this.pendingRecording = null;
    }
    if (this.recorder.offStop && this.handleRecorderStop) {
      this.recorder.offStop(this.handleRecorderStop);
    }
    if (this.recorder.offError && this.handleRecorderError) {
      this.recorder.offError(this.handleRecorderError);
    }
    if (this.audioContext) {
      this.audioContext.destroy();
    }
  },

  bindRecorderEvents() {
    this.handleRecorderStop = ({ tempFilePath, fileSize }) => {
      const recording = this.pendingRecording;
      this.pendingRecording = null;
      this.setData({ recordingKey: "" });
      if (!recording || !tempFilePath) {
        return;
      }
      const oldAudio = getStepAsset(recording.routeId, recording.stepNo).audio;
      storeFile(tempFilePath, {
        routeId: recording.routeId,
        stepNo: String(recording.stepNo),
        kind: "audio"
      }, fileSize)
        .then((audio) =>
          pushStepConfig(recording.routeId, recording.stepNo, { audio }).then(() => audio)
        )
        .then((audio) => {
          saveStepAsset(recording.routeId, recording.stepNo, { audio });
          if (oldAudio && oldAudio !== audio) {
            removeStoredFile(oldAudio);
            deleteRemoteFile(oldAudio).catch(() => null);
          }
          this.refreshRoutes();
          wx.showToast({ title: "语音已保存" });
        })
        .catch(() => wx.showToast({ title: "语音保存失败", icon: "none" }));
    };
    this.handleRecorderError = () => {
      this.pendingRecording = null;
      this.setData({ recordingKey: "" });
      wx.showToast({ title: "录音失败，请检查权限", icon: "none" });
    };
    this.recorder.onStop(this.handleRecorderStop);
    this.recorder.onError(this.handleRecorderError);
  },

  refreshRoutes() {
    let totalSteps = 0;
    let imageCount = 0;
    let audioCount = 0;
    const routeList = Object.values(routes).map((route) => ({
      ...route,
      steps: route.steps.map((step) => {
        const asset = getStepAsset(route.id, step.stepNo);
        totalSteps += 1;
        if (asset.image) imageCount += 1;
        if (asset.audio) audioCount += 1;
        return {
          ...step,
          ...asset,
          assetKey: `${route.id}:${step.stepNo}`,
          issues: getStepIssues({ ...step, ...asset }).join("、"),
          needsLocation: stepNeedsLocation(step)
        };
      })
    }));
    this.setData({
      routes: routeList,
      totalSteps,
      imageCount,
      audioCount,
      missingImages: totalSteps - imageCount,
      missingAudios: totalSteps - audioCount
    });
  },

  chooseImage(event) {
    const { routeId, stepNo } = event.currentTarget.dataset;
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["camera", "album"],
      success: ({ tempFiles }) => {
        const tempFilePath = tempFiles[0] && tempFiles[0].tempFilePath;
        if (!tempFilePath) return;
        const oldImage = getStepAsset(routeId, Number(stepNo)).image;
        this.compressImage(tempFilePath)
          .then((compressedPath) =>
            this.getFileSize(compressedPath).then((size) =>
              storeFile(
                compressedPath,
                {
                  routeId,
                  stepNo: String(stepNo),
                  kind: "image"
                },
                size
              )
            )
          )
          .then((image) => pushStepConfig(routeId, Number(stepNo), { image }).then(() => image))
          .then((image) => {
            saveStepAsset(routeId, Number(stepNo), { image });
            if (oldImage && oldImage !== image) {
              removeStoredFile(oldImage);
              deleteRemoteFile(oldImage).catch(() => null);
            }
            this.refreshRoutes();
            wx.showToast({ title: "照片已保存" });
          })
          .catch(() => wx.showToast({ title: "照片保存失败", icon: "none" }));
      }
    });
  },

  compressImage(src) {
    return new Promise((resolve) => {
      wx.compressImage({
        src,
        quality: 70,
        success: ({ tempFilePath }) => resolve(tempFilePath),
        fail: () => resolve(src)
      });
    });
  },

  getFileSize(filePath) {
    return new Promise((resolve) => {
      wx.getFileInfo({
        filePath,
        success: ({ size }) => resolve(size),
        fail: () => resolve(0)
      });
    });
  },

  startRecording(event) {
    const { routeId, stepNo } = event.currentTarget.dataset;
    this.pendingRecording = {
      routeId,
      stepNo: Number(stepNo)
    };
    this.setData({ recordingKey: `${routeId}:${stepNo}` });
    this.recorder.start({
      duration: 60000,
      format: "mp3",
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000
    });
  },

  stopRecording() {
    this.recorder.stop();
  },

  playAudio(event) {
    const { audio } = event.currentTarget.dataset;
    if (!audio) return;
    this.audioContext.stop();
    this.audioContext.src = audio;
    this.audioContext.play();
  },

  removeAsset(event) {
    const { routeId, stepNo, field } = event.currentTarget.dataset;
    const oldPath = getStepAsset(routeId, Number(stepNo))[field];
    removeStepAsset(routeId, Number(stepNo), field);
    removeStoredFile(oldPath);
    deleteRemoteFile(oldPath).catch(() => null);
    pushStepConfig(routeId, Number(stepNo), { [field]: "" }).catch(() => null);
    this.refreshRoutes();
    wx.showToast({ title: "已删除" });
  },

  savePhone(event) {
    const { field } = event.currentTarget.dataset;
    const value = event.detail.value.trim();
    if (!/^\d{7,20}$/.test(value)) {
      wx.showToast({ title: "请输入有效电话号码", icon: "none" });
      return;
    }
    const settings = saveSettings({ [field]: value });
    app.globalData.familyPhone = settings.familyPhone;
    app.globalData.emergencyPhone = settings.emergencyPhone;
    this.setData(settings);
    wx.showToast({ title: "电话已保存" });
  },

  saveStepField(event) {
    const { routeId, stepNo, field } = event.currentTarget.dataset;
    let value = event.detail.value;
    if (field === "latitude" || field === "longitude") {
      value = value === "" ? "" : Number(value);
      if (value !== "" && !Number.isFinite(value)) {
        wx.showToast({ title: "坐标格式不正确", icon: "none" });
        return;
      }
      if (
        value !== "" &&
        ((field === "latitude" && (value < -90 || value > 90)) ||
          (field === "longitude" && (value < -180 || value > 180)))
      ) {
        wx.showToast({ title: "坐标超出有效范围", icon: "none" });
        return;
      }
    }
    const current = getStepAsset(routeId, Number(stepNo));
    const nextConfig = { [field]: value };
    if (field === "latitude" || field === "longitude") {
      const latitude = field === "latitude" ? value : current.latitude;
      const longitude = field === "longitude" ? value : current.longitude;
      nextConfig.distanceTracking =
        current.verificationRequired === false && !!latitude && !!longitude;
    }
    pushStepConfig(routeId, Number(stepNo), nextConfig)
      .then(() => {
        saveStepConfig(routeId, Number(stepNo), nextConfig);
        this.refreshRoutes();
      })
      .catch(() => wx.showToast({ title: "配置同步失败", icon: "none" }));
  },

  toggleVerified(event) {
    const { routeId, stepNo } = event.currentTarget.dataset;
    const verificationRequired = event.detail.value.length === 0;
    const route = Object.values(routes).find((item) => item.id === routeId);
    const step = route.steps.find((item) => item.stepNo === Number(stepNo));
    const asset = getStepAsset(routeId, Number(stepNo));
    const latitude = asset.latitude || step.latitude;
    const longitude = asset.longitude || step.longitude;
    const config = {
      verificationRequired,
      distanceTracking: stepNeedsLocation(step) && !verificationRequired && !!latitude && !!longitude
    };
    pushStepConfig(routeId, Number(stepNo), config)
      .then(() => {
        saveStepConfig(routeId, Number(stepNo), config);
        this.refreshRoutes();
      })
      .catch(() => wx.showToast({ title: "确认状态同步失败", icon: "none" }));
  },

  captureLocation(event) {
    const { routeId, stepNo } = event.currentTarget.dataset;
    wx.getLocation({
      type: "gcj02",
      isHighAccuracy: true,
      highAccuracyExpireTime: 5000,
      success: ({ latitude, longitude, accuracy }) => {
        if (accuracy && accuracy > 50) {
          wx.showToast({ title: "定位精度不足，请稍后重试", icon: "none" });
          return;
        }
        const config = {
          latitude,
          longitude,
          distanceTracking: false,
          verificationRequired: true
        };
        pushStepConfig(routeId, Number(stepNo), config)
          .then(() => {
            saveStepConfig(routeId, Number(stepNo), config);
            this.refreshRoutes();
            wx.showToast({ title: "坐标已采集，请实地确认" });
          })
          .catch(() => wx.showToast({ title: "坐标同步失败", icon: "none" }));
      },
      fail: () => wx.showToast({ title: "定位失败，请检查权限", icon: "none" })
    });
  }
});
