const {
  getAuthStatus,
  loginWithWechat
} = require("../../utils/auth");

Page({
  data: {
    bootstrapped: true,
    familyName: "我的家庭",
    redirect: "",
    submitting: false
  },

  onLoad(query) {
    this.setData({ redirect: query.redirect ? decodeURIComponent(query.redirect) : "" });
    this.refreshStatus();
  },

  refreshStatus() {
    getAuthStatus()
      .then((status) => {
        this.setData({ bootstrapped: Boolean(status.bootstrapped) });
      })
      .catch((error) => {
        wx.showModal({
          title: "账号服务未连接",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      });
  },

  onInput(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({ [field]: event.detail.value });
  },

  openElderBind() {
    wx.navigateTo({ url: "/pages/elder-bind/elder-bind" });
  },

  submit() {
    if (this.data.submitting) return;
    const familyName = this.data.familyName.trim() || "我的家庭";
    this.setData({ submitting: true });
    loginWithWechat(familyName)
      .then(() => {
        wx.showToast({ title: "已登录" });
        const redirect = this.data.redirect;
        setTimeout(() => {
          if (redirect) {
            wx.redirectTo({ url: redirect });
            return;
          }
          wx.reLaunch({ url: "/pages/index/index" });
        }, 500);
      })
      .catch((error) => {
        wx.showModal({
          title: "微信登录失败",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ submitting: false }));
  }
});
