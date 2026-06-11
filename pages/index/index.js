const app = getApp();
const { getRouteById } = require("../../data/routes");
const { getRouteStatus } = require("../../utils/route-status");
const { pullRouteConfig } = require("../../utils/remote-config");

Page({
  data: {
    toMomReady: false,
    toHomeReady: false,
    toMomIssueCount: 0,
    toHomeIssueCount: 0
  },

  onShow() {
    Promise.all([pullRouteConfig("to-mom"), pullRouteConfig("to-home")])
      .catch(() => null)
      .finally(() => this.refreshStatuses());
  },

  refreshStatuses() {
    const toMom = getRouteStatus(getRouteById("to-mom"));
    const toHome = getRouteStatus(getRouteById("to-home"));
    this.setData({
      toMomReady: toMom.ready,
      toHomeReady: toHome.ready,
      toMomIssueCount: toMom.incompleteSteps.length,
      toHomeIssueCount: toHome.incompleteSteps.length
    });
  },

  goToRoute(event) {
    const routeId = event.currentTarget.dataset.routeId;
    const status = getRouteStatus(getRouteById(routeId));
    if (!status.ready) {
      wx.showModal({
        title: "路线尚未启用",
        content: `还有 ${status.incompleteSteps.length} 个步骤未完成配置，请家属先补齐照片、语音、动作说明和坐标。`,
        confirmText: "去配置",
        cancelText: "取消",
        success: ({ confirm }) => {
          if (confirm) this.openConfig();
        }
      });
      return;
    }
    wx.navigateTo({
      url: `/pages/route/route?id=${routeId}`
    });
  },

  openConfig() {
    wx.navigateTo({
      url: "/pages/config/config"
    });
  },

  requestHelp() {
    wx.showModal({
      title: "紧急求助",
      content: `是否立即拨打 ${app.globalData.emergencyPhone}？`,
      confirmText: "立即拨打",
      confirmColor: "#b33a3a",
      cancelText: "取消",
      success: (result) => {
        if (result.confirm) {
          wx.makePhoneCall({
            phoneNumber: app.globalData.emergencyPhone
          });
        }
      }
    });
  }
});
