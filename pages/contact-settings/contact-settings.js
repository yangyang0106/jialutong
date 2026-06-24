const { getSettings, saveSettings } = require("../../utils/settings");
const {
  getEmergencyContact,
  isFamilyLoggedIn,
  saveEmergencyContact
} = require("../../utils/auth");

const app = getApp();

Page({
  data: {
    familyPhone: "",
    emergencyPhone: "",
    emergencyContactName: "",
    emergencyRelation: "",
    contactReady: false,
    contactMessage: "请填写真实求助电话。",
    loadingContact: false,
    savingContact: false
  },

  onShow() {
    const settings = getSettings();
    this.setData(settings);
    this.refreshContactStatus(settings);
    this.loadRemoteContact();
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
    const patch = {
      emergencyContactName: String(this.data.emergencyContactName || "").trim(),
      emergencyRelation: String(this.data.emergencyRelation || "").trim(),
      emergencyPhone: String(this.data.emergencyPhone || "").trim(),
      familyPhone: String(this.data.emergencyPhone || "").trim()
    };
    const settings = saveSettings(patch);
    this.syncGlobalSettings(settings);
    this.setData(settings);
    const contactStatus = this.getContactStatus(settings);
    this.refreshContactStatus(settings);
    if (!contactStatus.contactReady) {
      wx.showToast({ title: "请补齐联系人", icon: "none" });
      return;
    }
    this.saveRemoteContact(patch)
      .then(() => {
        wx.showToast({ title: "已保存" });
        setTimeout(() => wx.navigateBack(), 300);
      })
      .catch((error) => {
        wx.showModal({
          title: "联系人未同步",
          content: error.message || "请稍后再试。",
          showCancel: false
        });
      });
  },

  loadRemoteContact() {
    if (!isFamilyLoggedIn()) return;
    this.setData({ loadingContact: true });
    getEmergencyContact()
      .then((contact) => {
        if (!contact || !contact.phone) return;
        const settings = saveSettings({
          emergencyContactName: contact.name || "",
          emergencyRelation: contact.relation || "",
          emergencyPhone: contact.phone || "",
          familyPhone: contact.phone || ""
        });
        this.syncGlobalSettings(settings);
        this.setData(settings);
        this.refreshContactStatus(settings);
      })
      .catch(() => null)
      .finally(() => this.setData({ loadingContact: false }));
  },

  saveRemoteContact(patch) {
    if (!isFamilyLoggedIn()) return Promise.resolve(null);
    this.setData({ savingContact: true });
    return saveEmergencyContact({
      name: patch.emergencyContactName,
      relation: patch.emergencyRelation,
      phone: patch.emergencyPhone
    })
      .then((contact) => {
        const settings = saveSettings({
          emergencyContactName: contact.name || patch.emergencyContactName,
          emergencyRelation: contact.relation || patch.emergencyRelation,
          emergencyPhone: contact.phone || patch.emergencyPhone,
          familyPhone: contact.phone || patch.emergencyPhone
        });
        this.syncGlobalSettings(settings);
        this.setData(settings);
        this.refreshContactStatus(settings);
        return contact;
      })
      .finally(() => this.setData({ savingContact: false }));
  },

  refreshContactStatus(settings = getSettings()) {
    this.setData(this.getContactStatus(settings));
  },

  getContactStatus(settings = getSettings()) {
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
    return {
      contactReady: hasValidPhone && hasName && hasRelation,
      contactMessage
    };
  },

  syncGlobalSettings(settings) {
    app.globalData.familyPhone = settings.familyPhone;
    app.globalData.emergencyPhone = settings.emergencyPhone;
    app.globalData.emergencyContactName = settings.emergencyContactName;
    app.globalData.emergencyRelation = settings.emergencyRelation;
  }
});
