const uploadConfig = require("../config/upload");

const AUTH_STORAGE_KEY = "jialutong_family_auth";

function getAuthState() {
  try {
    return wx.getStorageSync(AUTH_STORAGE_KEY) || null;
  } catch (error) {
    return null;
  }
}

function saveAuthState(auth) {
  wx.setStorageSync(AUTH_STORAGE_KEY, auth);
  return auth;
}

function clearAuthState() {
  try {
    wx.removeStorageSync(AUTH_STORAGE_KEY);
  } catch (error) {
    // 忽略本地清理失败，下一次登录会覆盖。
  }
}

function getAuthToken() {
  const auth = getAuthState();
  if (auth && auth.token) return auth.token;
  return "";
}

function getAuthHeader() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function isFamilyLoggedIn() {
  const auth = getAuthState();
  return Boolean(auth && auth.token && auth.user);
}

function isFamilyAdmin() {
  const auth = getAuthState();
  return Boolean(
    auth &&
      auth.token &&
      auth.user &&
      (auth.user.role === "FAMILY_ADMIN" || auth.user.role === "SUPER_ADMIN")
  );
}

function requestAuth(path, method = "GET", data) {
  if (!uploadConfig.apiBaseUrl) {
    return Promise.reject(new Error("请先配置路线服务地址"));
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${uploadConfig.apiBaseUrl}${path}`,
      method,
      data,
      header: getAuthHeader(),
      success: ({ statusCode, data: response }) => {
        if (statusCode < 200 || statusCode >= 300) {
          const message =
            response && response.detail
              ? typeof response.detail === "string"
                ? response.detail
                : response.detail.message || "账号请求失败"
              : `账号请求失败：${statusCode}`;
          reject(new Error(message));
          return;
        }
        resolve(response);
      },
      fail: (error) => {
        reject(new Error((error && (error.errMsg || error.message)) || "无法连接账号服务"));
      }
    });
  });
}

function getAuthStatus() {
  return requestAuth("/api/auth/status");
}


function getWechatLoginCode() {
  return new Promise((resolve, reject) => {
    wx.login({
      success: ({ code }) => {
        if (!code) {
          reject(new Error("微信登录没有返回 code，请重试"));
          return;
        }
        resolve(code);
      },
      fail: (error) => reject(new Error((error && error.errMsg) || "微信登录失败"))
    });
  });
}

function loginWithWechat(familyName = "我的家庭") {
  return getWechatLoginCode()
    .then((code) => requestAuth("/api/auth/wechat-login", "POST", { code, familyName }))
    .then(saveAuthState);
}

function bindElderWithWechat(bindCode) {
  return getWechatLoginCode()
    .then((code) => requestAuth("/api/auth/wechat-bind-elder", "POST", { code, bindCode }))
    .then(saveAuthState);
}

function createElderBindCode(elderId, relation = "本人") {
  return requestAuth("/api/auth/elder-bind-codes", "POST", { elderId, relation });
}

function logoutFamilyAccount() {
  return requestAuth("/api/auth/logout", "POST")
    .catch(() => null)
    .then(() => {
      clearAuthState();
      return true;
    });
}

function getCurrentAccount() {
  return requestAuth("/api/auth/me");
}

function listBoundElders() {
  return requestAuth("/api/auth/elders").then((response) => response.elders || []);
}

function requireFamilyLogin(redirectUrl = "") {
  if (isFamilyLoggedIn()) return true;
  const query = redirectUrl ? `?redirect=${encodeURIComponent(redirectUrl)}` : "";
  wx.navigateTo({ url: `/pages/family-login/family-login${query}` });
  return false;
}

module.exports = {
  bindElderWithWechat,
  createElderBindCode,
  clearAuthState,
  getAuthHeader,
  getAuthState,
  getAuthStatus,
  getCurrentAccount,
  isFamilyAdmin,
  isFamilyLoggedIn,
  listBoundElders,
  loginWithWechat,
  logoutFamilyAccount,
  requireFamilyLogin,
  saveAuthState
};
