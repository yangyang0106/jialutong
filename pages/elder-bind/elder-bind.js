const { bindElderWithWechat } = require("../../utils/auth");

Page({
  data: {
    bindCode: "",
    submitting: false
  },

  onInput(event) {
    this.setData({ bindCode: String(event.detail.value || "").trim().toUpperCase() });
  },

  submit() {
    if (this.data.submitting) return;
    const bindCode = this.data.bindCode.trim();
    if (!bindCode) {
      wx.showToast({ title: "请输入绑定码", icon: "none" });
      return;
    }
    this.setData({ submitting: true });
    bindElderWithWechat(bindCode)
      .then(() => {
        wx.showToast({ title: "绑定成功", icon: "none" });
        wx.redirectTo({ url: "/pages/index/index" });
      })
      .catch((error) => {
        wx.showModal({
          title: "绑定没有完成",
          content: error.message || "请确认绑定码是否正确。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ submitting: false }));
  }
});
