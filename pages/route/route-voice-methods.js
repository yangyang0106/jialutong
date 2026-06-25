const { renderSystemVoice } = require("../../utils/route-api");
const {
  canPlayMoment,
  getAutoVoiceDecision,
  markMomentPlayed,
  resetVoiceCompanionState,
  resolveStepVoice,
  VOICE_TIMING
} = require("../../utils/voice-companion");
const {
  LOCATION_REFRESH_INTERVAL,
  SECOND_AUDIO_DELAY
} = require("./route-presenter");
const {
  createExecutionState,
  resetForStep
} = require("../../utils/route-executor");

module.exports = {
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

};
