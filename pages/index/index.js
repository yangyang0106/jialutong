let routeLoader = null;
let routeSlots = null;
let routeStatus = null;
let auth = null;

function getRouteLoader() {
  if (!routeLoader) routeLoader = require("../../utils/elder-route-loader");
  return routeLoader;
}

function getRouteSlots() {
  if (!routeSlots) routeSlots = require("../../utils/elder-route-slots");
  return routeSlots;
}

function getRouteStatusModule() {
  if (!routeStatus) routeStatus = require("../../utils/route-status");
  return routeStatus;
}

function getAuthModule() {
  if (!auth) auth = require("../../utils/auth");
  return auth;
}

Page({
  data: {
    routeCards: [],
    isLoading: true,
    userRole: "GUEST",
    isGuest: true,
    hasActiveRole: false,
    isElder: false,
    isFamily: false,
    hasRoutes: false,
    showLoading: false,
    showEmpty: false,
    questionText: "今天要去哪里？",
    emptyText: "暂无路线，请联系家人",
    helpButtonText: "按住3秒 · 紧急求助",
    helpButtonClass: "help-button",
    helpHolding: false
  },

  onLoad() {
    this.setRole("GUEST");
    this.setRouteCards([], false);
  },

  onShow() {
    try {
      const role = this.checkRole();
      this.verifySession();
      if (role === "GUEST") {
        this.setRouteCards([], false);
        return;
      }
      this.setRouteCards([], true);
      this.refreshRoutes();
    } catch (error) {
      console.warn("首页初始化失败，显示访客入口", error);
      this.setRole("GUEST");
      this.setRouteCards([], false);
    }
  },

  setRole(role) {
    const isElder = role === "ELDER";
    const isFamily = role === "FAMILY";
    this.setData({
      userRole: role,
      isGuest: role === "GUEST",
      hasActiveRole: role !== "GUEST",
      isElder,
      isFamily,
      questionText: isElder ? "今天要去哪里？" : "家人路线",
      emptyText: isElder ? "暂无路线，请联系家人" : "暂无路线，点击下方创建"
    });
  },

  setRouteCards(routeCards, isLoading = this.data.isLoading) {
    const cards = routeCards || [];
    const hasRoutes = cards.length > 0;
    this.setData({
      routeCards: cards,
      hasRoutes,
      isLoading,
      showLoading: Boolean(isLoading && !hasRoutes),
      showEmpty: Boolean(!isLoading && !hasRoutes)
    });
  },

  verifySession() {
    try {
      const { getAuthState, clearAuthState, getCurrentAccount } = getAuthModule();
      const auth = getAuthState();
      if (!auth || !auth.token) return;
      getCurrentAccount()
        .then(() => {})
        .catch(() => {
          if (getAuthState()) {
            clearAuthState();
            this.setRole("GUEST");
            wx.showToast({ title: "登录已过期，请重新登录", icon: "none" });
          }
        });
    } catch (error) {
      console.warn("检查登录状态失败", error);
    }
  },

  checkRole() {
    try {
      const { getAuthState, clearAuthState } = getAuthModule();
      const auth = getAuthState();
      if (!auth || !auth.user) {
        this.setRole("GUEST");
        return "GUEST";
      }
      if (auth.expiresAt) {
        const expiry = new Date(auth.expiresAt).getTime();
        if (!isNaN(expiry) && expiry < Date.now()) {
          clearAuthState();
          this.setRole("GUEST");
          return "GUEST";
        }
      }
      const role = auth.user.role;
      if (role === "ELDER_USER") {
        this.setRole("ELDER");
        return "ELDER";
      } else if (role === "FAMILY_ADMIN" || role === "FAMILY_MEMBER" || role === "SUPER_ADMIN") {
        this.setRole("FAMILY");
        return "FAMILY";
      } else {
        this.setRole("GUEST");
        return "GUEST";
      }
    } catch (error) {
      console.warn("读取登录身份失败", error);
      this.setRole("GUEST");
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
    try {
      const { getCachedPublishedRouteBySlot, listPublishedElderSlotRoutes } = getRouteLoader();
      const { ELDER_ROUTE_SLOTS } = getRouteSlots();
      const update = () => {
        const routeCards = ELDER_ROUTE_SLOTS
          .map((slot) => this.buildRouteCard(getCachedPublishedRouteBySlot(slot)))
          .filter(Boolean);
        this.setRouteCards(routeCards);
      };
      update();
      listPublishedElderSlotRoutes().then((routes) => {
        this.setRouteCards((routes || []).map((route) => this.buildRouteCard(route)).filter(Boolean));
      }).finally(() => {
        update();
        this.setRouteCards(this.data.routeCards, false);
      });
    } catch (error) {
      console.warn("加载首页路线失败", error);
      this.setRouteCards([], false);
    }
  },

  buildRouteCard(route) {
    if (!route) return null;
    const { getRouteStatus } = getRouteStatusModule();
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
      issueCount: status.incompleteSteps.length,
      statusClass: status.ready ? "ready-text" : "not-ready-text",
      statusText: status.ready
        ? "路线已启用"
        : this.data.isElder
          ? "路线准备中，请联系家人"
          : `点这里补齐 · ${status.incompleteSteps.length} 步关键配置`
    };
  },

  goToRoute(event) {
    const { loadElderRoute } = getRouteLoader();
    const { getRouteStatus } = getRouteStatusModule();
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
    const { requireFamilyLogin } = getAuthModule();
    if (!requireFamilyLogin("/pages/route-create/route-create")) return;
    wx.navigateTo({ url: "/pages/route-create/route-create" });
  },

  startHelpHold() {
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.setData({
      helpHolding: true,
      helpButtonText: "继续按住3秒求助",
      helpButtonClass: "help-button help-holding"
    });
    this.helpHoldTimer = setTimeout(() => {
      this.helpHoldTimer = null;
      this.setData({
        helpHolding: false,
        helpButtonText: "按住3秒 · 紧急求助",
        helpButtonClass: "help-button"
      });
      this.requestHelp();
    }, 3000);
  },

  cancelHelpHold() {
    if (this.helpHoldTimer) clearTimeout(this.helpHoldTimer);
    this.helpHoldTimer = null;
    if (this.data.helpHolding) {
      this.setData({
        helpHolding: false,
        helpButtonText: "按住3秒 · 紧急求助",
        helpButtonClass: "help-button"
      });
    }
  },

  requestHelp() {
    const app = getApp();
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
