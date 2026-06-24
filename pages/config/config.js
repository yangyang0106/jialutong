const { getSettings, saveSettings } = require("../../utils/settings");
const {
  createElderBindCode,
  getAuthState,
  listBoundElders,
  logoutFamilyAccount,
  requireFamilyLogin
} = require("../../utils/auth");
const app = getApp();

Page({
  data: {
    familyPhone: "",
    emergencyPhone: "",
    emergencyContactName: "",
    emergencyRelation: "",
    contactReady: false,
    contactWarning: "",
    authUser: null,
    elders: []
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

  saveContact(event) {
    const field = event.currentTarget.dataset.field;
    const value = String(event.detail.value || "").trim();
    if (!field) return;
    const patch = { [field]: value };
    if (field === "emergencyPhone") {
      patch.familyPhone = value;
    }
    const settings = saveSettings(patch);
    app.globalData.familyPhone = settings.familyPhone;
    app.globalData.emergencyPhone = settings.emergencyPhone;
    app.globalData.emergencyContactName = settings.emergencyContactName;
    app.globalData.emergencyRelation = settings.emergencyRelation;
    this.setData(settings);
    this.refreshContactStatus(settings);
    wx.showToast({ title: "已保存" });
  },

  refreshContactStatus(settings = getSettings()) {
    const phone = String(settings.emergencyPhone || "").trim();
    const hasName = Boolean(String(settings.emergencyContactName || "").trim());
    const hasRelation = Boolean(String(settings.emergencyRelation || "").trim());
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
      contactWarning
    });
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
        wx.showModal({
          title: `${elder.name}的绑定码`,
          content: `请在老人手机打开家路通，选择老人绑定，输入：${result.code}。绑定码30分钟内有效。`,
          showCancel: false,
          confirmText: "知道了"
        });
      })
      .catch((error) => {
        wx.showModal({
          title: "绑定码未生成",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      });
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
