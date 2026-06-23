const {
  analyzeRouteTrip,
  getRouteReviewCenter,
  listRouteHelpEvents,
  updateRouteHelpEvent
} = require("../../utils/route-engine/route-repository");

const HEALTH_LABELS = {
  GOOD: "整体可用",
  WARNING: "需要观察",
  BAD: "暂不建议继续使用"
};

const PROBLEM_LABELS = {
  NORMAL: "正常",
  NEEDS_ATTENTION: "需要关注",
  SERIOUS: "严重"
};

const HELP_STATUS_LABELS = {
  REQUESTED: "等待处理",
  CALLING: "已拨打电话",
  RESOLVED: "已处理"
};

function enrichHelpEvent(event) {
  const contact = [event.emergencyRelation, event.emergencyContactName, event.emergencyPhone]
    .filter(Boolean)
    .join(" ");
  return {
    ...event,
    helpStatusText: HELP_STATUS_LABELS[event.helpStatus] || event.helpStatus || "等待处理",
    contactText: contact || "未记录联系人",
    reasonText: event.helpReason || "老人主动求助"
  };
}

function percent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function enrichCenter(center) {
  return {
    ...center,
    healthLabel: HEALTH_LABELS[center.routeHealthLevel] || center.routeHealthLevel,
    foundRateText: percent(center.foundRate),
    notFoundRateText: percent(center.notFoundRate),
    helpRateText: percent(center.helpRate),
    problemSteps: (center.problemSteps || []).map(enrichStep),
    stepStats: (center.stepStats || []).map(enrichStep)
  };
}

function enrichStep(step) {
  return {
    ...step,
    problemLabel: PROBLEM_LABELS[step.problemLevel] || step.problemLevel,
    foundRateText: percent(step.foundRate),
    notFoundRateText: percent(step.notFoundRate),
    helpRateText: percent(step.helpRate)
  };
}

Page({
  data: {
    loading: true,
    analyzing: false,
    center: null,
    analysis: null,
    helpEvents: [],
    resolvingHelpId: ""
  },

  onLoad(options) {
    this.routeId = options.id;
    this.loadCenter();
  },

  loadCenter() {
    this.setData({ loading: true });
    getRouteReviewCenter(this.routeId)
      .then((center) => {
        this.setData({ center: enrichCenter(center), loading: false });
        wx.setNavigationBarTitle({ title: "路线复盘" });
        this.loadHelpEvents();
      })
      .catch((error) => {
        this.setData({ loading: false });
        wx.showModal({
          title: "复盘读取失败",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      });
  },


  loadHelpEvents() {
    listRouteHelpEvents(this.routeId)
      .then((result) => {
        const helpEvents = (result.events || []).map(enrichHelpEvent);
        this.setData({ helpEvents });
      })
      .catch(() => {
        this.setData({ helpEvents: [] });
      });
  },

  resolveHelpEvent(event) {
    const eventId = event.currentTarget.dataset.id;
    if (!eventId || this.data.resolvingHelpId) return;
    this.setData({ resolvingHelpId: eventId });
    updateRouteHelpEvent(this.routeId, eventId, "RESOLVED", "家属已确认处理")
      .then(() => {
        wx.showToast({ title: "已标记处理", icon: "none" });
        this.loadHelpEvents();
        this.loadCenter();
      })
      .catch((error) => {
        wx.showModal({
          title: "处理状态未保存",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ resolvingHelpId: "" }));
  },

  analyzeTrip() {
    if (this.data.analyzing) return;
    this.setData({ analyzing: true });
    analyzeRouteTrip(this.routeId)
      .then((analysis) => {
        this.setData({ analysis });
        wx.showToast({ title: "AI建议已生成", icon: "none" });
      })
      .catch((error) => {
        wx.showModal({
          title: "AI分析未完成",
          content: error.message || "已保留规则统计，请稍后再试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ analyzing: false }));
  }
});
