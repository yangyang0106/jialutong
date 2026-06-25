const { adaptPublishedRoute } = require("./elder-route-adapter");
const { getRouteDraft, listRouteDrafts } = require("./route-api");
const {
  ELDER_ROUTE_SLOTS,
  cachePublishedRouteForSlot,
  getCachedPublishedRouteById,
  getCachedPublishedRouteBySlot,
  isElderRouteSlot,
  pickLatestPublishedRouteForSlot
} = require("./elder-route-slots");

function cachePublishedElderRoute(route) {
  return cachePublishedRouteForSlot(route);
}

function loadElderRoute(routeId) {
  if (isElderRouteSlot(routeId)) {
    return Promise.reject(new Error("首页槽位不能作为真实路线 ID 使用"));
  }
  return getRouteDraft(routeId)
    .then((remoteRoute) => {
      const route = adaptPublishedRoute(remoteRoute, remoteRoute && remoteRoute.elderSlot);
      if (!route) throw new Error("路线尚未发布");
      return cachePublishedElderRoute(route);
    })
    .catch((error) => {
      const cached = getCachedPublishedRouteById(routeId);
      if (cached) return cached;
      throw error;
    });
}

function loadElderRouteSlot(slot) {
  if (!isElderRouteSlot(slot)) {
    return Promise.reject(new Error("未知首页路线槽位"));
  }
  return listRouteDrafts("PUBLISHED")
    .then(({ routes }) => {
      const remoteRoute = pickLatestPublishedRouteForSlot(routes, slot);
      const route = adaptPublishedRoute(remoteRoute, slot);
      if (!route) return getCachedPublishedRouteBySlot(slot);
      return cachePublishedElderRoute(route);
    })
    .catch(() => getCachedPublishedRouteBySlot(slot));
}

function listPublishedElderSlotRoutes() {
  return listRouteDrafts("PUBLISHED")
    .then(({ routes }) => ELDER_ROUTE_SLOTS
      .map((slot) => adaptPublishedRoute(pickLatestPublishedRouteForSlot(routes, slot), slot))
      .filter(Boolean)
      .map(cachePublishedElderRoute))
    .catch(() => ELDER_ROUTE_SLOTS
      .map(getCachedPublishedRouteBySlot)
      .filter(Boolean));
}

module.exports = {
  cachePublishedElderRoute,
  getCachedPublishedRouteBySlot,
  listPublishedElderSlotRoutes,
  loadElderRoute,
  loadElderRouteSlot
};
