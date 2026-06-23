const app = getApp();
const {
  getCachedOrFixedElderRoute,
  loadElderRoute
} = require("../../utils/elder-route-loader");
const { getRouteStatus } = require("../../utils/route-status");
const { pullRouteConfig } = require("../../utils/remote-config");

Page({
  data: {
    routeCards: [],
    isLoading: true
  },

  onShow() {
    this.refreshRoutes();
  },

  refreshRoutes() {
    const routeIds = ["to-mom", "to-home"];
    const update = () => {
      const routeCards = routeIds
        .map((routeId) => this.buildRouteCard(routeId, getCachedOrFixedElderRoute(routeId)))
        .filter(Boolean);
      this.setData({ routeCards });
    };
    update();
    Promise.all(routeIds.map((routeId) =>
      Promise.all([pullRouteConfig(routeId), loadElderRoute(routeId)]).catch(() => null)
    )).then(() => {
      update();
      this.setData({ isLoading: false });
    });
  },

  buildRouteCard(routeId, route) {
    if (!route) return null;
    const status = getRouteStatus(route);
    const destination = route.destination && route.destination.name;
    const origin = route.origin && route.origin.name;
    const displayName = route.name || "家人路线";
    return {
      routeId,
      icon: displayName.trim().charAt(0) || "路",
      name: displayName,
      place: destination || origin || "家人准备的路线",
      ready: status.ready,
      issueCount: status.incompleteSteps.length
    };
  },

  goToRoute(event) {
    const routeId = event.currentTarget.dataset.routeId;
    wx.showLoading({ title: "正在准备路线", mask: true });
    loadElderRoute(routeId)
      .then((route) => {
        const status = getRouteStatus(route);
        if (!status.ready) {
          wx.showModal({
            title: "路线还没准备好",
            content: "请让家人先把照片、语音和关键地点确认好。",
            showCancel: false,
            confirmText: "知道了"
          });
          return;
        }
        wx.navigateTo({
          url: `/pages/route/route?id=${routeId}`
        });
      })
      .catch(() => {
        wx.showToast({ title: "路线还没准备好", icon: "none" });
      })
      .finally(() => {
        wx.hideLoading();
      });
  },

  openConfig() {
    wx.navigateTo({
      url: "/pages/config/config"
    });
  },

  requestHelp() {
    const phone = app.globalData.emergencyPhone;
    const name = app.globalData.emergencyContactName || "紧急联系人";
    const relation = app.globalData.emergencyRelation;
    if (!phone) {
      wx.showModal({
        title: "未设置求助电话",
        content: "请先让家人填写紧急联系人姓名、关系和电话。",
        confirmText: "去配置",
        cancelText: "取消",
        success: ({ confirm }) => {
          if (confirm) this.openConfig();
        }
      });
      return;
    }
    wx.showModal({
      title: "紧急求助",
      content: `是否立即联系${relation ? relation + " " : ""}${name}：${phone}？`,
      confirmText: "立即拨打",
      confirmColor: "#b33a3a",
      cancelText: "取消",
      success: (result) => {
        if (result.confirm) {
          wx.makePhoneCall({
            phoneNumber: phone
          });
        }
      }
    });
  }
});
