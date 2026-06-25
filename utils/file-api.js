const { apiBaseUrl } = require("../config/upload");
const { getAuthHeader } = require("./auth");

function request(path, method = "GET") {
  if (!apiBaseUrl) return Promise.resolve(null);
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBaseUrl}${path}`,
      method,
      header: getAuthHeader(),
      success: ({ statusCode, data }) => {
        if (statusCode < 200 || statusCode >= 300) {
          reject(new Error(`文件服务请求失败：${statusCode}`));
          return;
        }
        resolve(data);
      },
      fail: reject
    });
  });
}

function deleteRemoteFile(url) {
  if (!apiBaseUrl || !/^https?:\/\//.test(url || "")) {
    return Promise.resolve();
  }
  return request(`/api/files?url=${encodeURIComponent(url)}`, "DELETE");
}

module.exports = {
  deleteRemoteFile
};
