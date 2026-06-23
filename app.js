const { getSettings } = require("./utils/settings");

App({
  globalData: {
    emergencyPhone: "",
    familyPhone: "",
    emergencyContactName: "",
    emergencyRelation: ""
  },

  onLaunch() {
    try {
      const settings = getSettings();
      this.globalData.emergencyPhone = settings.emergencyPhone;
      this.globalData.familyPhone = settings.familyPhone;
      this.globalData.emergencyContactName = settings.emergencyContactName;
      this.globalData.emergencyRelation = settings.emergencyRelation;
    } catch (error) {
      console.warn("读取设置失败，使用默认联系电话", error);
    }
    if (wx.setKeepScreenOn) {
      wx.setKeepScreenOn({
        keepScreenOn: true,
        fail: (error) => console.warn("保持屏幕常亮失败", error)
      });
    }
  }
});
