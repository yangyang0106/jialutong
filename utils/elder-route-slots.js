const ELDER_ROUTE_SLOTS = Object.freeze(["TO_MOM", "TO_HOME"]);
const CACHE_KEY = "publishedElderRoutes";

function isElderRouteSlot(value) {
  return ELDER_ROUTE_SLOTS.indexOf(value) >= 0;
}

function getCache() {
  return wx.getStorageSync(CACHE_KEY) || {};
}

function setCache(cache) {
  wx.setStorageSync(CACHE_KEY, cache);
}

function getCachedPublishedRouteBySlot(slot) {
  if (!isElderRouteSlot(slot)) return undefined;
  return getCache()[slot];
}

function getCachedPublishedRouteById(routeId) {
  const cache = getCache();
  return ELDER_ROUTE_SLOTS
    .map((slot) => cache[slot])
    .filter(Boolean)
    .find((route) => route.id === routeId || route.engineRouteId === routeId);
}

function cachePublishedRouteForSlot(route) {
  if (!route || !isElderRouteSlot(route.elderSlot)) return route;
  const cache = getCache();
  cache[route.elderSlot] = route;
  setCache(cache);
  return route;
}

function pickLatestPublishedRouteForSlot(routes, slot) {
  if (!isElderRouteSlot(slot)) return null;
  return (routes || [])
    .filter((route) => route.elderSlot === slot && route.status === "PUBLISHED")
    .sort((a, b) => String(b.publishedAt || b.updatedAt || "").localeCompare(String(a.publishedAt || a.updatedAt || "")))[0] || null;
}

module.exports = {
  ELDER_ROUTE_SLOTS,
  cachePublishedRouteForSlot,
  getCachedPublishedRouteById,
  getCachedPublishedRouteBySlot,
  isElderRouteSlot,
  pickLatestPublishedRouteForSlot
};
