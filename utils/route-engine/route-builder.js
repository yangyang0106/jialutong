const { createRoute } = require("./route-model");
const { normalizeBaiduRoute } = require("./baidu-route-parser");
const { extractDecisionPoints } = require("./decision-point-extractor");
const { applyRouteReviewStatus } = require("./review");

function buildFamilyRouteFromBaidu(response, input) {
  const normalizedRoute = normalizeBaiduRoute(response, input.routeIndex || 0);
  const routeContext = {
    routeId: input.id,
    destinationName: input.destination.name,
    origin: input.origin,
    destination: input.destination
  };
  const steps = extractDecisionPoints(normalizedRoute, routeContext);
  const route = createRoute({
    id: input.id,
    name: input.name,
    elderSlot: input.elderSlot,
    origin: input.origin,
    destination: input.destination,
    travelModes: normalizedRoute.travelModes,
    distance: normalizedRoute.distance,
    estimatedDuration: normalizedRoute.duration,
    sourceProvider: "BAIDU_MAP",
    sourceRouteId: input.sourceRouteId || "",
    sourcePolyline: normalizedRoute.polyline,
    steps
  });
  return applyRouteReviewStatus(route);
}

module.exports = {
  buildFamilyRouteFromBaidu
};
