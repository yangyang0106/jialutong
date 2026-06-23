const STORAGE_KEY = "appSettings";
const DEFAULT_CONTACT_PHONE = "";

function getSettings() {
  return {
    familyPhone: DEFAULT_CONTACT_PHONE,
    emergencyPhone: DEFAULT_CONTACT_PHONE,
    emergencyContactName: "",
    emergencyRelation: "",
    ...(wx.getStorageSync(STORAGE_KEY) || {})
  };
}

function saveSettings(settings) {
  const nextSettings = {
    ...getSettings(),
    ...settings
  };
  wx.setStorageSync(STORAGE_KEY, nextSettings);
  return nextSettings;
}

module.exports = {
  DEFAULT_CONTACT_PHONE,
  getSettings,
  saveSettings
};
