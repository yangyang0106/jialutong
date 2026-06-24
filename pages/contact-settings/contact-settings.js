const { getSettings, saveSettings } = require("../../utils/settings");

const app = getApp();

Page({
  data: {
    familyPhone: "",
    emergencyPhone: "",
    emergencyContactName: "",
    emergencyRelation: "",
    contactReady: false,
    contactMessage: "请填写真实求助电话。"
  },

  onShow() {
    const settings = getSettings();
    this.setData(settings);
    this.refreshContactStatus(settings);
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
    this.syncGlobalSettings(settings);
    this.setData(settings);
    this.refreshContactStatus(settings);
  },

  saveAndBack() {
    const settings = saveSettings({
      emergencyContactName: String(this.data.emergencyContactName || "").trim(),
      emergencyRelation: String(this.data.emergencyRelation || "").trim(),
      emergencyPhone: String(this.data.emergencyPhone || "").trim(),
      familyPhone: String(this.data.emergencyPhone || "").trim()
    });
    this.syncGlobalSettings(settings);
    this.setData(settings);
    this.refreshContactStatus(settings);
    if (!this.data.contactReady) {
      wx.showToast({ title: "请补齐联系人", icon: "none" });
      return;
    }
    wx.showToast({ title: "已保存" });
    setTimeout(() => wx.navigateBack(), 300);
  },

  refreshContactStatus(settings = getSettings()) {
    const phone = String(settings.emergencyPhone || "").trim();
    const hasName = Boolean(String(settings.emergencyContactName || "").trim());
    const hasRelation = Boolean(String(settings.emergencyRelation || "").trim());
    const hasValidPhone = /^1\d{10}$/.test(phone);
    let contactMessage = "求助联系人已设置。";
    if (!phone) {
      contactMessage = "请填写真实求助电话。";
    } else if (!hasValidPhone) {
      contactMessage = "求助电话看起来不完整，请填写 11 位手机号。";
    } else if (!hasName || !hasRelation) {
      contactMessage = "建议补充联系人姓名和关系，老人求助时更清楚。";
    }
    this.setData({
      contactReady: hasValidPhone && hasName && hasRelation,
      contactMessage
    });
  },

  syncGlobalSettings(settings) {
    app.globalData.familyPhone = settings.familyPhone;
    app.globalData.emergencyPhone = settings.emergencyPhone;
    app.globalData.emergencyContactName = settings.emergencyContactName;
    app.globalData.emergencyRelation = settings.emergencyRelation;
  }
});
