const { getSettings } = require("./utils/settings");

App({
  globalData: {
    emergencyPhone: "16621633647",
    familyPhone: "16621633647"
  },

  onLaunch() {
    const settings = getSettings();
    this.globalData.emergencyPhone = settings.emergencyPhone;
    this.globalData.familyPhone = settings.familyPhone;
    wx.setKeepScreenOn({
      keepScreenOn: true
    });
  }
});
