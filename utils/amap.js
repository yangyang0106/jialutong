const { webServiceKey } = require("../config/amap");

const AMAP_BASE_URL = "https://restapi.amap.com";

function requestAmap(path, data) {
  if (!webServiceKey) {
    return Promise.reject(new Error("请先在 config/amap.js 中填写高德 Web 服务 Key"));
  }

  return new Promise((resolve, reject) => {
    wx.request({
      url: `${AMAP_BASE_URL}${path}`,
      data: {
        ...data,
        key: webServiceKey
      },
      success: ({ data: response }) => {
        if (response.status !== "1") {
          reject(new Error(response.info || "高德地图请求失败"));
          return;
        }
        resolve(response);
      },
      fail: reject
    });
  });
}

function getWalkingRoute(origin, destination) {
  return requestAmap("/v3/direction/walking", {
    origin,
    destination
  });
}

function getBicyclingRoute(origin, destination) {
  return requestAmap("/v4/direction/bicycling", {
    origin,
    destination
  });
}

function getTransitRoute(origin, destination, city = "上海") {
  return requestAmap("/v3/direction/transit/integrated", {
    origin,
    destination,
    city,
    cityd: city,
    strategy: 0,
    nightflag: 0
  });
}

module.exports = {
  getWalkingRoute,
  getBicyclingRoute,
  getTransitRoute
};
