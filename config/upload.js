let localConfig = {};

function shouldUseLocalConfig() {
  try {
    return typeof __wxConfig !== "undefined" && __wxConfig.envVersion === "develop";
  } catch (error) {
    return false;
  }
}

if (shouldUseLocalConfig()) {
  try {
    localConfig = require("./upload.local");
  } catch (error) {
    localConfig = {};
  }
}

const apiBaseUrl = localConfig.apiBaseUrl || "https://jialutong.cloud";

module.exports = {
  apiBaseUrl,
  uploadUrl: localConfig.uploadUrl || `${apiBaseUrl}/api/files`
};
