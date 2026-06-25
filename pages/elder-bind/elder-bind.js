const { bindElderWithWechat } = require("../../utils/auth");

Page({
  data: {
    bindCode: "",
    submitting: false
  },

  onInput(event) {
    this.setData({ bindCode: String(event.detail.value || "").trim().toUpperCase() });
  },

  scanBindCode() {
    if (!wx.scanCode) {
      wx.showToast({ title: "当前微信版本不支持扫码", icon: "none" });
      return;
    }
    wx.scanCode({
      onlyFromCamera: false,
      scanType: ["barCode", "qrCode"],
      success: (result) => {
        const bindCode = this.extractBindCode(result.result || "");
        if (!bindCode) {
          wx.showModal({
            title: "没有识别到绑定码",
            content: "请对准家人手机上的绑定码条形码，或手动输入。",
            showCancel: false
          });
          return;
        }
        this.setData({ bindCode });
        wx.showModal({
          title: "识别到绑定码",
          content: bindCode,
          confirmText: "立即绑定",
          cancelText: "先看看",
          success: ({ confirm }) => {
            if (confirm) this.submit();
          }
        });
      },
      fail: () => {
        wx.showToast({ title: "扫码已取消", icon: "none" });
      }
    });
  },

  extractBindCode(value) {
    const text = String(value || "").toUpperCase();
    const prefixed = text.match(/JLT-BIND[:：/ ]+([A-Z0-9]{6,12})/);
    if (prefixed) return prefixed[1];
    return text.replace(/[^A-Z0-9]/g, "").slice(0, 12);
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
        wx.showToast({ title: "绑定成功", icon: "success" });
        setTimeout(() => {
          wx.reLaunch({ url: "/pages/index/index" });
        }, 1000);
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
