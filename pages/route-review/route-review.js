const { storeFile, removeStoredFile } = require("../../utils/file-storage");
const { deleteRemoteFile } = require("../../utils/file-api");
const { isFamilyAdmin, isFamilyLoggedIn } = require("../../utils/auth");
const {
  generateCollectionPlan,
  generateRouteAiVoices,
  generateRouteTtsBatch,
  generateStepTts,
  getRouteDraft,
  publishRouteDraft,
  reviewStepPhoto,
  reviewRouteStep
} = require("../../utils/route-api");
const { setVoiceMoment } = require("../../utils/voice-schema");
const { adaptPublishedRoute } = require("../../utils/elder-route-adapter");
const {
  enrichCollectionPlan,
  enrichRoute,
  voiceWithLandmark
} = require("./review-presenter");
const { cachePublishedElderRoute } = require("../../utils/elder-route-loader");
const { resolveRouteImagesForDisplay } = require("../../utils/local-media");


Page({
  data: {
    route: null,
    loading: true,
    busyStepId: "",
    recordingStepId: "",
    playingStepId: "",
    expandedVoiceStepId: "",
    publishing: false,
    currentReviewIndex: 0,
    currentStep: null,
    pendingStepCount: 0,
    nextPendingIndex: -1,
    showRouteTree: false,
    aiGenerating: false,
    batchTtsGenerating: false,
    collectionPlanning: false,
    collectionPlan: null,
    activeReviewTab: "steps"
  },

  onLoad(options) {
    this.routeId = options.id;
    if (!isFamilyLoggedIn()) {
      wx.redirectTo({
        url: `/pages/family-login/family-login?redirect=${encodeURIComponent(
          `/pages/route-review/route-review?id=${this.routeId}`
        )}`
      });
      return;
    }
    if (!isFamilyAdmin()) {
      wx.showModal({
        title: "需要家人确认",
        content: "路线审核和发布需要家庭管理员完成。",
        showCancel: false,
        success: () => wx.navigateBack({ fail: () => wx.switchTab && wx.switchTab({ url: "/pages/index/index" }) })
      });
      return;
    }
    this.recorder = wx.getRecorderManager();
    this.audioContext = wx.createInnerAudioContext();
    this.audioContext.obeyMuteSwitch = false;
    this.audioContext.volume = 1;
    if (wx.setInnerAudioOption) wx.setInnerAudioOption({ obeyMuteSwitch: false });
    this.bindRecorderEvents();
    this.bindAudioEvents();
    this.loadRoute();
  },

  onUnload() {
    if (this.pendingRecording) {
      this.pendingRecording = null;
      if (this.recorder) this.recorder.stop();
    }
    if (this.recorder && this.recorder.offStop && this.handleRecorderStop) {
      this.recorder.offStop(this.handleRecorderStop);
    }
    if (this.recorder && this.recorder.offError && this.handleRecorderError) {
      this.recorder.offError(this.handleRecorderError);
    }
    if (this.audioContext) {
      this.audioContext.destroy();
      this.audioContext = null;
    }
  },

  bindRecorderEvents() {
    this.handleRecorderStop = ({ tempFilePath, fileSize, duration }) => {
      const recording = this.pendingRecording;
      this.pendingRecording = null;
      this.setData({ recordingStepId: "" });
      if (!recording || !tempFilePath) return;
      if (duration && duration < 800) {
        wx.showToast({ title: "录音太短，请重新录制", icon: "none" });
        return;
      }
      this.saveCustomVoice(recording, tempFilePath, fileSize || 0);
    };
    this.handleRecorderError = () => {
      this.pendingRecording = null;
      this.setData({ recordingStepId: "" });
      wx.showModal({
        title: "录音未完成",
        content: "请允许使用麦克风后再试。",
        confirmText: "去设置",
        success: ({ confirm }) => {
          if (confirm) wx.openSetting();
        }
      });
    };
    this.recorder.onStop(this.handleRecorderStop);
    this.recorder.onError(this.handleRecorderError);
  },

  bindAudioEvents() {
    this.audioContext.onPlay(() => {
      wx.showToast({ title: "正在播放语音", icon: "none", duration: 1200 });
    });
    this.audioContext.onEnded(() => this.setData({ playingStepId: "" }));
    this.audioContext.onError(() => {
      this.setData({ playingStepId: "" });
      wx.showToast({ title: "这段录音暂时不能播放", icon: "none" });
    });
  },

  setRoute(route, extra = {}) {
    const enrichedRoute = enrichRoute(route, this.data.collectionPlan);
    const requestedIndex =
      typeof extra.currentReviewIndex === "number"
        ? extra.currentReviewIndex
        : this.data.currentReviewIndex;
    const reviewState = this.buildReviewState(enrichedRoute, requestedIndex);
    this.setData({
      route: enrichedRoute,
      ...reviewState,
      ...extra,
      currentReviewIndex: reviewState.currentReviewIndex
    });
    this.resolveRouteImages(enrichedRoute, reviewState.currentReviewIndex);
  },

  resolveRouteImages(route, currentReviewIndex) {
    const routeId = route && route.id;
    if (!routeId) return;
    this.imageResolveToken = (this.imageResolveToken || 0) + 1;
    const token = this.imageResolveToken;
    resolveRouteImagesForDisplay(route).then((displayRoute) => {
      if (token !== this.imageResolveToken) return;
      if (!this.data.route || this.data.route.id !== routeId) return;
      this.setData({
        route: displayRoute,
        ...this.buildReviewState(displayRoute, currentReviewIndex)
      });
    });
  },

  buildReviewState(route, index) {
    const steps = route && route.steps || [];
    const currentReviewIndex = Math.max(0, Math.min(Number(index) || 0, Math.max(steps.length - 1, 0)));
    const pendingIndexes = steps
      .map((step, stepIndex) => ({ step, stepIndex }))
      .filter(({ step }) => this.isStepPending(step))
      .map(({ stepIndex }) => stepIndex);
    let nextPendingIndex = -1;
    for (let i = 0; i < pendingIndexes.length; i += 1) {
      if (pendingIndexes[i] > currentReviewIndex) {
        nextPendingIndex = pendingIndexes[i];
        break;
      }
    }
    if (nextPendingIndex < 0) {
      for (let i = 0; i < pendingIndexes.length; i += 1) {
        if (pendingIndexes[i] !== currentReviewIndex) {
          nextPendingIndex = pendingIndexes[i];
          break;
        }
      }
    }
    return {
      currentReviewIndex,
      currentStep: steps[currentReviewIndex] || null,
      pendingStepCount: pendingIndexes.length,
      nextPendingIndex
    };
  },

  isStepPending(step) {
    if (!step) return false;
    return !step.approved || Boolean((step.blockingIssues || []).length);
  },

  loadRoute() {
    if (!this.routeId) return;
    this.setData({ loading: true });
    getRouteDraft(this.routeId)
      .then((route) => {
        this.setRoute(route, { loading: false });
        wx.setNavigationBarTitle({ title: route.name });
      })
      .catch((error) => {
        this.setData({ loading: false });
        wx.showModal({
          title: "路线读取失败",
          content: error.message || "请返回后重试。",
          showCancel: false
        });
      });
  },

  openSimulator() {
    wx.navigateTo({
      url: `/pages/route/route?id=${this.routeId}&simulator=1`
    });
  },

  openReviewCenter() {
    wx.navigateTo({ url: `/pages/route-review-center/route-review-center?id=${this.routeId}` });
  },

  switchReviewTab(event) {
    const tab = event.currentTarget.dataset.tab;
    if (!tab || tab === this.data.activeReviewTab) return;
    this.setData({ activeReviewTab: tab });
    wx.pageScrollTo({ scrollTop: 0, duration: 160 });
  },

  previousStep() {
    this.setReviewIndex(this.data.currentReviewIndex - 1);
  },

  nextStep() {
    this.setReviewIndex(this.data.currentReviewIndex + 1);
  },

  setReviewIndex(index) {
    const steps = this.data.route && this.data.route.steps || [];
    if (!steps.length) return;
    const currentReviewIndex = Math.max(0, Math.min(Number(index) || 0, steps.length - 1));
    this.setData({
      ...this.buildReviewState(this.data.route, currentReviewIndex),
      expandedVoiceStepId: "",
      activeReviewTab: "steps"
    });
    this.scrollToStepReview();
  },

  scrollToStepReview() {
    if (wx.pageScrollTo) {
      wx.pageScrollTo({
        scrollTop: 0,
        duration: 120
      });
    }
  },

  jumpToNextPending() {
    if (this.data.nextPendingIndex < 0) {
      wx.showToast({ title: "暂无待处理步骤", icon: "none" });
      return;
    }
    this.setReviewIndex(this.data.nextPendingIndex);
  },

  toggleRouteTree() {
    this.setData({ showRouteTree: !this.data.showRouteTree });
  },

  generateAiVoices() {
    if (this.data.route.status === "PUBLISHED" || this.data.aiGenerating) return;
    this.setData({ aiGenerating: true });
    generateRouteAiVoices(this.routeId)
      .then(({ route, generated, message }) => {
        this.setRoute(route);
        wx.showModal({
          title: generated ? "AI语音建议已生成" : "保留原有语音",
          content: message,
          showCancel: false
        });
      })
      .catch((error) => {
        wx.showModal({
          title: "AI语音建议未完成",
          content: error.message || "已保留原有系统文案。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ aiGenerating: false }));
  },

  batchGenerateTts() {
    if (this.data.route.status === "PUBLISHED" || this.data.batchTtsGenerating) return;
    wx.showActionSheet({
      itemList: ["跳过已有系统语音", "重新生成已有系统语音"],
      success: ({ tapIndex }) => {
        this.setData({ batchTtsGenerating: true });
        generateRouteTtsBatch(this.routeId, tapIndex === 1)
          .then(({ route, steps }) => {
            const moments = [];
            (steps || []).forEach((step) => {
              (step.moments || []).forEach((moment) => moments.push(moment));
            });
            const successCount = moments.filter((item) => item.status === "SUCCESS").length;
            const failedCount = moments.filter((item) => item.status === "FAILED").length;
            this.setRoute(route);
            wx.showModal({
              title: "批量语音生成完成",
              content: `成功 ${successCount} 段，失败 ${failedCount} 段。真人录音已保留。`,
              showCancel: false
            });
          })
          .catch((error) => {
            wx.showModal({
              title: "批量语音未完成",
              content: error.message || "请稍后再试。",
              showCancel: false
            });
          })
          .finally(() => this.setData({ batchTtsGenerating: false }));
      }
    });
  },

  generateCollectionChecklist() {
    if (!this.data.route || this.data.collectionPlanning) return;
    this.setData({ collectionPlanning: true });
    generateCollectionPlan(this.routeId)
      .then((plan) => {
        const collectionPlan = enrichCollectionPlan(plan);
        this.setData({
          collectionPlan,
          route: enrichRoute(this.data.route, collectionPlan),
          activeReviewTab: "steps"
        });
        this.scrollToStepReview();
        wx.showToast({ title: "采集清单已生成", icon: "none" });
      })
      .catch((error) => {
        wx.showModal({
          title: "采集清单未完成",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ collectionPlanning: false }));
  },

  updateVoiceText(event) {
    if (this.data.route.status === "PUBLISHED") return;
    const { stepId, moment } = event.currentTarget.dataset;
    const step = this.data.route.steps.find((item) => item.id === stepId);
    if (!step) return;
    const current = step.voiceMoments.find((item) => item.moment === moment);
    const text = String(event.detail.value || "").trim();
    if (!text || text === (current && current.text)) return;
    if (current && current.voiceType === "CUSTOM") {
      wx.showToast({ title: "真人录音请通过重录更新", icon: "none" });
      return;
    }
    const updates = { text };
    updates.audioUrl = "";
    updates.voiceType = "SYSTEM";
    this.setData({ busyStepId: stepId });
    reviewRouteStep(this.routeId, stepId, {
      voice: setVoiceMoment(step.voice, moment, updates),
      reviewStatus: "PENDING",
      needsReview: true
    })
      .then((route) => {
        this.setRoute(route);
        wx.showToast({ title: "语音文案已保存" });
      })
      .catch((error) => wx.showToast({ title: error.message || "保存失败", icon: "none" }))
      .finally(() => this.setData({ busyStepId: "" }));
  },

  approveStep(event) {
    const stepId = event.currentTarget.dataset.stepId;
    this.setData({ busyStepId: stepId });
    reviewRouteStep(this.routeId, stepId, {
      reviewStatus: "APPROVED",
      reviewNote: "家属已确认"
    })
      .then((route) => {
        this.setRoute(route);
        wx.showToast({ title: "这一步已确认" });
        const enrichedRoute = enrichRoute(route, this.data.collectionPlan);
        const nextPendingIndex = this.buildReviewState(
          enrichedRoute,
          this.data.currentReviewIndex
        ).nextPendingIndex;
        if (nextPendingIndex >= 0) {
          setTimeout(() => this.setReviewIndex(nextPendingIndex), 350);
        }
      })
      .catch((error) => wx.showToast({ title: error.message || "确认失败", icon: "none" }))
      .finally(() => this.setData({ busyStepId: "" }));
  },

  rejectStep(event) {
    const stepId = event.currentTarget.dataset.stepId;
    wx.showModal({
      title: "标记需要修改",
      content: "这一步将保持未通过状态，路线不能发布。",
      confirmText: "标记修改",
      success: ({ confirm }) => {
        if (!confirm) return;
        reviewRouteStep(this.routeId, stepId, {
          reviewStatus: "REJECTED",
          reviewNote: "家属认为这一步需要修改"
        })
          .then((route) => this.setRoute(route))
          .catch((error) => wx.showToast({ title: error.message || "操作失败", icon: "none" }));
      }
    });
  },

  addFamilyPhoto(event) {
    if (this.data.route.status === "PUBLISHED") return;
    const { stepId, stepNo } = event.currentTarget.dataset;
    this.setData({ busyStepId: stepId });
    wx.chooseMedia({
      count: 1,
      mediaType: ["image"],
      sourceType: ["camera", "album"],
      success: ({ tempFiles }) => {
        const file = tempFiles[0];
        if (!file || !file.tempFilePath) {
          this.setData({ busyStepId: "" });
          return;
        }
        storeFile(
          file.tempFilePath,
          { routeId: this.routeId, stepNo: String(stepNo), kind: "image" },
          file.size || 0
        )
          .then((imageUrl) =>
            reviewRouteStep(this.routeId, stepId, {
              reviewStatus: "APPROVED",
              reviewNote: "家属已实地确认并补充照片",
              imageUrl,
              imageStatus: "FAMILY"
            }).then((route) =>
              reviewStepPhoto(this.routeId, stepId, imageUrl, "FAMILY", file.size || 0)
                .then((result) => result.route)
                .catch(() => route)
            )
          )
          .then((route) => {
            this.setRoute(route);
            wx.showToast({ title: "照片和审核已保存" });
          })
          .catch((error) => {
            wx.showToast({ title: error.message || "照片保存失败", icon: "none" });
          })
          .finally(() => this.setData({ busyStepId: "" }));
      },
      fail: () => this.setData({ busyStepId: "" })
    });
  },

  startRecording(event) {
    if (this.data.route.status === "PUBLISHED" || this.data.recordingStepId) return;
    const { stepId, stepNo, moment } = event.currentTarget.dataset;
    const step = this.data.route.steps.find((item) => item.id === stepId);
    if (!step) return;
    if (this.audioContext) this.audioContext.stop();
    const voiceMoment = step.voiceMoments.find((item) => item.moment === moment);
    const recordingKey = `${stepId}:${moment}`;
    this.pendingRecording = {
      stepId,
      stepNo: Number(stepNo),
      moment,
      previousAudioUrl: voiceMoment && voiceMoment.audioUrl || "",
      voice: step.voice || {}
    };
    this.setData({ recordingStepId: recordingKey, playingStepId: "" });
    wx.vibrateShort({ type: "light" });
    this.recorder.start({
      duration: 60000,
      format: "mp3",
      sampleRate: 16000,
      numberOfChannels: 1,
      encodeBitRate: 48000
    });
  },

  stopRecording() {
    if (!this.data.recordingStepId) return;
    this.recorder.stop();
  },

  saveCustomVoice(recording, tempFilePath, fileSize) {
    this.setData({ busyStepId: recording.stepId });
    let uploadedAudioUrl = "";
    storeFile(
      tempFilePath,
      { routeId: this.routeId, stepNo: String(recording.stepNo), kind: "audio" },
      fileSize
    )
      .then((audioUrl) => {
        uploadedAudioUrl = audioUrl;
        return reviewRouteStep(this.routeId, recording.stepId, {
          voice: setVoiceMoment(recording.voice, recording.moment, {
            voiceType: "CUSTOM",
            audioUrl
          })
        }).then((route) => ({ route, audioUrl }));
      })
      .then(({ route, audioUrl }) => {
        this.setRoute(route);
        if (recording.previousAudioUrl && recording.previousAudioUrl !== audioUrl) {
          removeStoredFile(recording.previousAudioUrl);
          deleteRemoteFile(recording.previousAudioUrl).catch(() => null);
        }
        wx.showToast({ title: "真人语音已保存" });
      })
      .catch((error) => {
        if (uploadedAudioUrl) {
          removeStoredFile(uploadedAudioUrl);
          deleteRemoteFile(uploadedAudioUrl).catch(() => null);
        }
        wx.showToast({ title: error.message || "语音保存失败", icon: "none" });
      })
      .finally(() => this.setData({ busyStepId: "" }));
  },

  playCustomVoice(event) {
    const { stepId, moment, audio } = event.currentTarget.dataset;
    if (!audio || !this.audioContext) return;
    wx.vibrateShort({ type: "light" });
    const playingKey = `${stepId}:${moment}`;
    this.setData({ playingStepId: playingKey });
    if (this.audioContext.src === audio) {
      this.audioContext.seek(0);
      this.audioContext.play();
      return;
    }
    this.audioContext.stop();
    this.audioContext.src = audio;
    setTimeout(() => {
      if (this.audioContext && this.data.playingStepId === playingKey) this.audioContext.play();
    }, 80);
  },

  generateTts(event) {
    if (this.data.route.status === "PUBLISHED") return;
    const { stepId, moment } = event.currentTarget.dataset;
    const step = this.data.route.steps.find((item) => item.id === stepId);
    if (!step || this.data.busyStepId) return;
    this.setData({ busyStepId: stepId });
    const voiceMoment = step.voiceMoments.find((item) => item.moment === moment);
    generateStepTts(this.routeId, stepId, moment, voiceMoment && voiceMoment.text || "")
      .then((route) => {
        this.setRoute(route);
        wx.showToast({ title: "系统语音已生成" });
      })
      .catch((error) => {
        wx.showModal({
          title: "语音生成未完成",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ busyStepId: "" }));
  },

  deleteCustomVoice(event) {
    if (this.data.route.status === "PUBLISHED") return;
    const { stepId, moment } = event.currentTarget.dataset;
    const step = this.data.route.steps.find((item) => item.id === stepId);
    const voiceMoment = step && step.voiceMoments.find((item) => item.moment === moment);
    if (!step || !voiceMoment || !voiceMoment.hasCustomVoice) return;
    wx.showModal({
      title: "删除真人语音",
      content: "删除后将恢复使用系统提示文字。",
      confirmText: "删除",
      confirmColor: "#c94b3c",
      success: ({ confirm }) => {
        if (!confirm) return;
        const oldAudioUrl = voiceMoment.audioUrl;
        this.setData({ busyStepId: stepId });
        reviewRouteStep(this.routeId, stepId, {
          voice: setVoiceMoment(step.voice, moment, { voiceType: "SYSTEM", audioUrl: "" })
        })
          .then((route) => {
            if (this.audioContext) this.audioContext.stop();
            this.setRoute(route, { playingStepId: "" });
            removeStoredFile(oldAudioUrl);
            deleteRemoteFile(oldAudioUrl).catch(() => null);
            wx.showToast({ title: "真人语音已删除" });
          })
          .catch((error) => wx.showToast({ title: error.message || "删除失败", icon: "none" }))
          .finally(() => this.setData({ busyStepId: "" }));
      }
    });
  },

  toggleVoiceSettings(event) {
    const stepId = event.currentTarget.dataset.stepId;
    this.setData({
      expandedVoiceStepId: this.data.expandedVoiceStepId === stepId ? "" : stepId
    });
  },

  updateLandmarkHint(event) {
    const stepId = event.currentTarget.dataset.stepId;
    const step = this.data.route.steps.find((item) => item.id === stepId);
    const landmarkHint = String(event.detail.value || "").trim();
    reviewRouteStep(this.routeId, stepId, {
      landmarkHint,
      voice: step ? voiceWithLandmark(step, landmarkHint) : undefined
    })
      .then((route) => {
        this.setRoute(route);
        wx.showToast({ title: "地标提示已保存" });
      })
      .catch((error) => wx.showToast({ title: error.message || "保存失败", icon: "none" }));
  },

  publishRoute() {
    if (!this.data.route || this.data.route.status !== "READY") {
      wx.showModal({
        title: "还不能发布",
        content: "请先处理页面中标记为“必须处理”的步骤。",
        showCancel: false
      });
      return;
    }
    this.setData({ publishing: true });
    publishRouteDraft(this.routeId)
      .then((route) => {
        this.setRoute(route);
        const published = adaptPublishedRoute(route, route.elderSlot);
        if (published) cachePublishedElderRoute(published);
        wx.showModal({
          title: "路线已发布",
          content: "首页已经更新为这条路线。",
          showCancel: false,
          success: () => wx.reLaunch({ url: "/pages/index/index" })
        });
      })
      .catch((error) => {
        wx.showModal({
          title: "发布失败",
          content: error.message || "请检查待审核步骤。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ publishing: false }));
  }
});
