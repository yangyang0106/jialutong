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
    authUser: null,
    elders: []
  },

  onShow() {
    this.setData({
      ...getSettings(),
      authUser: (getAuthState() || {}).user || null
    });
    if (this.data.authUser) {
      listBoundElders()
        .then((elders) => this.setData({ elders }))
        .catch(() => this.setData({ elders: [] }));
    } else {
      this.setData({ elders: [] });
    }
  },

  savePhone(event) {
    const field = event.currentTarget.dataset.field;
    const value = String(event.detail.value || "").trim();
    if (!field) return;
    const settings = saveSettings({ [field]: value });
    app.globalData.familyPhone = settings.familyPhone;
    app.globalData.emergencyPhone = settings.emergencyPhone;
    app.globalData.emergencyContactName = settings.emergencyContactName;
    app.globalData.emergencyRelation = settings.emergencyRelation;
    this.setData(settings);
    wx.showToast({ title: "已保存" });
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
