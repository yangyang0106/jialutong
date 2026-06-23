const { apiBaseUrl } = require("../../config/upload");
const { getAuthHeader } = require("../auth");

function request(path, method = "GET", data, options = {}) {
  if (!apiBaseUrl) {
    if (options.optional) return Promise.resolve(null);
    return Promise.reject(new Error("请先配置路线服务地址"));
  }
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBaseUrl}${path}`,
      method,
      data,
      header: getAuthHeader(),
      success: ({ statusCode, data: response }) => {
        if (statusCode < 200 || statusCode >= 300) {
          const message =
            response && response.detail
              ? typeof response.detail === "string"
                ? response.detail
                : response.detail.message || "路线服务请求失败"
              : `路线服务请求失败：${statusCode}`;
          reject(new Error(message));
          return;
        }
        resolve(response);
      },
      fail: (error) => {
        const detail = error && (error.errMsg || error.message);
        const isLocalService = /^http:\/\/(127\.0\.0\.1|localhost)/.test(apiBaseUrl);
        reject(
          new Error(
            isLocalService
              ? "无法连接本地路线服务。请确认服务已启动，并在开发者工具中关闭合法域名校验。真机调试需要使用 HTTPS 公网地址。"
              : detail || "无法连接路线服务，请检查网络后重试。"
          )
        );
      }
    });
  });
}

function listRouteDrafts(status) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return request(`/api/engine/routes${query}`);
}

function createRoutePlan(input) {
  return request("/api/engine/route-plans", "POST", input);
}

function adviseRoutePlans(input) {
  return request("/api/engine/routes/advise", "POST", input);
}

function searchPlaces(keyword, region = "上海") {
  return request("/api/engine/places/search", "POST", { keyword, region });
}

function reverseGeocode(location) {
  return request("/api/engine/places/reverse-geocode", "POST", { location });
}

function getRouteDraft(routeId) {
  return request(`/api/engine/routes/${routeId}`);
}

function getPublishedElderRoute(slot) {
  return request(`/api/engine/elder-routes/${slot}`, "GET", undefined, { optional: true });
}

function saveRouteDraft(route) {
  return request("/api/engine/routes", "POST", route);
}

function updateRouteDraft(route) {
  return request(`/api/engine/routes/${route.id}`, "PUT", route);
}

function deleteRouteDraft(routeId) {
  return request(`/api/engine/routes/${routeId}`, "DELETE");
}

function reviewRouteStep(routeId, stepId, review) {
  return request(`/api/engine/routes/${routeId}/steps/${stepId}/review`, "PUT", review);
}

function generateStepTts(routeId, stepId, moment, text) {
  if (text == null) {
    text = moment;
    moment = "enter";
  }
  return request(`/api/engine/routes/${routeId}/steps/${stepId}/tts`, "POST", { moment, text });
}

function generateRouteAiVoices(routeId) {
  return request(`/api/engine/routes/${routeId}/ai-generate-voices`, "POST");
}

function generateRouteTtsBatch(routeId, regenerateTts = false) {
  return request(`/api/engine/routes/${routeId}/tts/batch`, "POST", { regenerateTts });
}

function generateCollectionPlan(routeId) {
  return request(`/api/engine/routes/${routeId}/collection-plan`, "POST");
}

function getRouteReviewCenter(routeId) {
  return request(`/api/engine/routes/${routeId}/review-center`);
}

function analyzeRouteTrip(routeId) {
  return request(`/api/engine/routes/${routeId}/trip-analysis`, "POST");
}

function reviewStepPhoto(routeId, stepId, imageUrl, imageStatus = "FAMILY", fileSize = 0) {
  return request(`/api/engine/routes/${routeId}/steps/${stepId}/photo-review`, "POST", {
    imageUrl,
    imageStatus,
    fileSize
  });
}

function renderSystemVoice(routeId, stepId, moment, text) {
  return request("/api/engine/voice/render", "POST", { routeId, stepId, moment, text });
}

function publishRouteDraft(routeId) {
  return request(`/api/engine/routes/${routeId}/publish`, "POST");
}

function recordStepExecution(execution) {
  return request("/api/engine/trip-results", "POST", execution);
}

function getRouteTripSummary(routeId) {
  return request(`/api/engine/routes/${routeId}/trip-summary`);
}

function listRouteHelpEvents(routeId) {
  return request(`/api/engine/routes/${routeId}/help-events`);
}

function updateRouteHelpEvent(routeId, eventId, helpStatus = "RESOLVED", handledNote = "") {
  return request(`/api/engine/routes/${routeId}/help-events/${eventId}`, "PUT", {
    helpStatus,
    handledNote
  });
}

module.exports = {
  adviseRoutePlans,
  analyzeRouteTrip,
  createRoutePlan,
  deleteRouteDraft,
  getPublishedElderRoute,
  getRouteDraft,
  getRouteReviewCenter,
  getRouteTripSummary,
  generateCollectionPlan,
  generateRouteAiVoices,
  generateRouteTtsBatch,
  generateStepTts,
  listRouteDrafts,
  listRouteHelpEvents,
  publishRouteDraft,
  recordStepExecution,
  renderSystemVoice,
  reviewStepPhoto,
  reviewRouteStep,
  reverseGeocode,
  saveRouteDraft,
  searchPlaces,
  updateRouteDraft,
  updateRouteHelpEvent
};
