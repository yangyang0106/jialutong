const app = getApp();
const {
  getCachedPublishedRouteBySlot,
  listPublishedElderSlotRoutes,
  loadElderRoute
} = require("../../utils/elder-route-loader");
const { ELDER_ROUTE_SLOTS } = require("../../utils/elder-route-slots");
const { getRouteStatus } = require("../../utils/route-status");
const { getAuthState, clearAuthState, getCurrentAccount, requireFamilyLogin } = require("../../utils/auth");

Page({
  data: {
    routeCards: [],
    isLoading: true,
    userRole: "GUEST",
    helpHolding: false
  },

  onShow() {
    const role = this.checkRole();
    this.verifySession();
    if (role === "GUEST") {
      this.setData({ routeCards: [], isLoading: false });
      return;
    }
    this.refreshRoutes();
  },

  verifySession() {
    const auth = getAuthState();
    if (!auth || !auth.token) return;
    getCurrentAccount()
      .then(() => {})
      .catch(() => {
        if (getAuthState()) {
          clearAuthState();
          this.setData({ userRole: "GUEST" });
          wx.showToast({ title: "登录已过期，请重新登录", icon: "none" });
        }
      });
  },

  checkRole() {
    const auth = getAuthState();
    if (!auth || !auth.user) {
      this.setData({ userRole: "GUEST" });
      return "GUEST";
    }
    if (auth.expiresAt) {
      const expiry = new Date(auth.expiresAt).getTime();
      if (!isNaN(expiry) && expiry < Date.now()) {
        clearAuthState();
        this.setData({ userRole: "GUEST" });
        return "GUEST";
      }
    }
    const role = auth.user.role;
    if (role === "ELDER_USER") {
      this.setData({ userRole: "ELDER" });
      return "ELDER";
    } else if (role === "FAMILY_ADMIN" || role === "FAMILY_MEMBER" || role === "SUPER_ADMIN") {
      this.setData({ userRole: "FAMILY" });
      return "FAMILY";
    } else {
      this.setData({ userRole: "GUEST" });
      return "GUEST";
    }
  },

  openFamilyLogin() {
    wx.navigateTo({ url: "/pages/family-login/family-login" });
  },

  openElderBind() {
    wx.navigateTo({ url: "/pages/elder-bind/elder-bind" });
  },

  refreshRoutes() {
    const update = () => {
      const routeCards = ELDER_ROUTE_SLOTS
        .map((slot) => this.buildRouteCard(getCachedPublishedRouteBySlot(slot)))
        .filter(Boolean);
      this.setData({ routeCards });
    };
    update();
    listPublishedElderSlotRoutes().then((routes) => {
      this.setData({ routeCards: (routes || []).map((route) => this.buildRouteCard(route)).filter(Boolean) });
    }).finally(() => {
      update();
      this.setData({ isLoading: false });
    });
  },

  buildRouteCard(route) {
    if (!route) return null;
    const status = getRouteStatus(route);
    const destination = route.destination && route.destination.name;
    const origin = route.origin && route.origin.name;
    const displayName = route.name || "家人路线";
    return {
      routeId: route.id,
      elderSlot: route.elderSlot,
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
          url: `/pages/route/route?id=${route.id}`
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

  openRouteManager() {
    if (!requireFamilyLogin("/pages/route-create/route-create")) return;
    wx.navigateTo({ url: "/pages/route-create/route-create" });
  },

  startHelpHold() {
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.setData({ helpHolding: true });
    this.helpHoldTimer = setTimeout(() => {
      this.helpHoldTimer = null;
      this.setData({ helpHolding: false });
      this.requestHelp();
    }, 3000);
  },

  cancelHelpHold() {
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.helpHoldTimer = null;
    if (this.data.helpHolding) this.setData({ helpHolding: false });
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
