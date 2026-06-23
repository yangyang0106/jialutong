const { apiBaseUrl } = require("../config/upload");
const { getAuthHeader } = require("./auth");
const { saveStepConfig } = require("./route-assets");

function request(path, method = "GET", data) {
  if (!apiBaseUrl) {
    return Promise.resolve(null);
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBaseUrl}${path}`,
      method,
      data,
      header: getAuthHeader(),
      success: ({ statusCode, data: response }) => {
        if (statusCode < 200 || statusCode >= 300) {
          reject(new Error(`路线配置同步失败：${statusCode}`));
          return;
        }
        resolve(response);
      },
      fail: reject
    });
  });
}

function pushStepConfig(routeId, stepNo, config) {
  return request(`/api/routes/${routeId}/steps/${stepNo}`, "PUT", config);
}

function pullRouteConfig(routeId) {
  return request(`/api/routes/${routeId}`).then((response) => {
    if (!response || !response.steps) return false;
    Object.entries(response.steps).forEach(([stepNo, config]) => {
      saveStepConfig(routeId, Number(stepNo), config);
    });
    return true;
  });
}

function deleteRemoteFile(url) {
  if (!apiBaseUrl || !/^https?:\/\//.test(url || "")) {
    return Promise.resolve();
  }
  return request(`/api/files?url=${encodeURIComponent(url)}`, "DELETE");
}

module.exports = {
  pushStepConfig,
  pullRouteConfig,
  deleteRemoteFile
};
