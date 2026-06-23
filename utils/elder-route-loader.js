const { getRouteById } = require("../data/routes");
const { adaptPublishedRoute } = require("./route-engine/elder-route-adapter");
const { getPublishedElderRoute } = require("./route-engine/route-repository");

const CACHE_KEY = "publishedElderRoutes";
const ROUTE_ID_SLOTS = Object.freeze({
  "to-mom": "TO_MOM",
  "to-home": "TO_HOME"
});

function getCache() {
  return wx.getStorageSync(CACHE_KEY) || {};
}

function getCachedOrFixedElderRoute(routeId) {
  return getCache()[routeId] || getRouteById(routeId);
}

function cachePublishedElderRoute(route) {
  const slotRouteId = route && ROUTE_ID_SLOTS[route.slotRouteId]
    ? route.slotRouteId
    : Object.keys(ROUTE_ID_SLOTS).find((routeId) => ROUTE_ID_SLOTS[routeId] === route.elderSlot);
  if (!route || !slotRouteId) return route;
  const cache = getCache();
  cache[slotRouteId] = route;
  wx.setStorageSync(CACHE_KEY, cache);
  return route;
}

function loadElderRoute(routeId) {
  const slot = ROUTE_ID_SLOTS[routeId];
  if (!slot) return Promise.resolve(getRouteById(routeId));

  return getPublishedElderRoute(slot)
    .then((remoteRoute) => {
      const route = adaptPublishedRoute(remoteRoute, slot);
      if (!route) return getCachedOrFixedElderRoute(routeId);
      return cachePublishedElderRoute(route);
    })
    .catch(() => getCachedOrFixedElderRoute(routeId));
}

module.exports = {
  cachePublishedElderRoute,
  getCachedOrFixedElderRoute,
  loadElderRoute
};
