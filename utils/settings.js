const STORAGE_KEY = "appSettings";
const DEFAULT_CONTACT_PHONE = "16621633647";

function getSettings() {
  return {
    familyPhone: DEFAULT_CONTACT_PHONE,
    emergencyPhone: DEFAULT_CONTACT_PHONE,
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
