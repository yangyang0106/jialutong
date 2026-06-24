let localConfig = {};

try {
  localConfig = require("./upload.local");
} catch (error) {
  localConfig = {};
}

const apiBaseUrl = localConfig.apiBaseUrl || "https://jialutong.cloud";

module.exports = {
  apiBaseUrl,
  uploadUrl: localConfig.uploadUrl || `${apiBaseUrl}/api/files`,
  uploadToken: localConfig.uploadToken || "",
  enableLocalDemoRoutes: localConfig.enableLocalDemoRoutes === true
};
