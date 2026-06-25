const { getSettings } = require("../../utils/settings");
const { buildCode39Bars } = require("../../utils/code39");
const {
  createElderBindCode,
  getAuthState,
  listBoundElders,
  logoutFamilyAccount,
  requireFamilyLogin
} = require("../../utils/auth");
Page({
  data: {
    familyPhone: "",
    emergencyPhone: "",
    emergencyContactName: "",
    emergencyRelation: "",
    contactReady: false,
    contactWarning: "",
    contactSummary: "老人找不到路时，优先联系这里的人。发布前请填写真实号码。",
    authUser: null,
    elders: [],
    bindCodePanel: null
  },

  onShow() {
    const settings = getSettings();
    this.setData({
      ...settings,
      authUser: (getAuthState() || {}).user || null
    });
    this.refreshContactStatus(settings);
    if (this.data.authUser) {
      listBoundElders()
        .then((elders) => this.setData({ elders }))
        .catch(() => this.setData({ elders: [] }));
    } else {
      this.setData({ elders: [] });
    }
  },

  refreshContactStatus(settings = getSettings()) {
    const phone = String(settings.emergencyPhone || "").trim();
    const name = String(settings.emergencyContactName || "").trim();
    const relation = String(settings.emergencyRelation || "").trim();
    const hasName = Boolean(name);
    const hasRelation = Boolean(relation);
    const hasValidPhone = /^1\d{10}$/.test(phone);
    let contactWarning = "";
    if (!phone) {
      contactWarning = "请填写真实求助电话。";
    } else if (!hasValidPhone) {
      contactWarning = "求助电话看起来不完整，请填写 11 位手机号。";
    } else if (!hasName || !hasRelation) {
      contactWarning = "建议补充联系人姓名和关系，老人求助时更清楚。";
    }
    this.setData({
      contactReady: hasValidPhone && hasName && hasRelation,
      contactWarning,
      contactSummary:
        hasValidPhone && hasName
          ? `${relation ? relation + " " : ""}${name} · ${phone}`
          : "老人找不到路时，优先联系这里的人。发布前请填写真实号码。"
    });
  },

  openContactSettings() {
    wx.navigateTo({ url: "/pages/contact-settings/contact-settings" });
  },

  openRouteManager() {
    if (!requireFamilyLogin("/pages/route-create/route-create")) return;
    wx.navigateTo({ url: "/pages/route-create/route-create" });
  },

  openFamilyLogin() {
    wx.navigateTo({ url: "/pages/family-login/family-login" });
  },

  generateElderBindCode(event) {
    const elderId = event.currentTarget.dataset.id;
    const elder = this.data.elders.find((item) => item.id === elderId);
    if (!elderId || !elder) return;
    createElderBindCode(elderId, "本人")
      .then((result) => {
        this.setData({
          bindCodePanel: {
            elderName: elder.name,
            code: result.code,
            bars: buildCode39Bars(result.code),
            expiresAt: result.expiresAt
          }
        });
        wx.showToast({ title: "绑定码已生成", icon: "none" });
      })
      .catch((error) => {
        wx.showModal({
          title: "绑定码未生成",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      });
  },

  closeBindCodePanel() {
    this.setData({ bindCodePanel: null });
  },

  logoutFamily() {
    wx.showModal({
      title: "退出家属账号",
      content: "退出后仍可使用老人端导航，但不能创建和审核路线。",
      confirmText: "退出",
      success: ({ confirm }) => {
        if (!confirm) return;
        logoutFamilyAccount().then(() => {
          this.setData({ authUser: null });
          wx.showToast({ title: "已退出" });
        });
      }
    });
  }
});
