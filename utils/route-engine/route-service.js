const { buildFamilyRouteFromBaidu } = require("./route-builder");
const { normalizeBaiduRoute } = require("./baidu-route-parser");
const { extractDecisionPoints } = require("./decision-point-extractor");
const {
  adviseRoutePlans,
  createRoutePlan,
  publishRouteDraft,
  reviewRouteStep,
  saveRouteDraft,
  updateRouteDraft
} = require("./route-repository");

function summarizeRoutePlan(response, input, routeIndex) {
  const normalized = normalizeBaiduRoute(response, routeIndex);
  const steps = extractDecisionPoints(normalized, {
    routeId: `advice-plan-${routeIndex}`,
    destinationName: input.destination.name,
    origin: input.origin,
    destination: input.destination
  });
  const descriptions = normalized.segments
    .map((segment) => segment.instruction || segment.action)
    .filter(Boolean)
    .filter((value, index, values) => values.indexOf(value) === index)
    .slice(0, 8);
  const transitSegments = normalized.segments.filter((segment) => segment.mode === "TRANSIT");
  return {
    index: routeIndex,
    distance: normalized.distance,
    duration: normalized.duration,
    description: descriptions.join("；").slice(0, 800),
    walkDistance: normalized.segments
      .filter((segment) => segment.mode === "WALKING")
      .reduce((total, segment) => total + segment.distance, 0),
    transferCount: Math.max(0, transitSegments.length - 1),
    riskPointCount: steps.filter((step) => step.riskLevel !== "LOW").length,
    decisionPointCount: steps.length
  };
}

function summarizeRoutePlans(response, input) {
  const routes = response && response.result && response.result.routes || [];
  return routes.slice(0, 5).map((_route, index) => summarizeRoutePlan(response, input, index));
}

function prepareRouteAdvice(input) {
  return createRoutePlan({
    mode: input.mode === "WALKING" ? "WALKING" : "TRANSIT",
    origin: input.origin,
    destination: input.destination,
    policy: input.policy || "LEAST_TIME"
  }).then((response) => {
    const plans = summarizeRoutePlans(response, input);
    if (!plans.length) throw new Error("百度地图未返回可用路线");
    return adviseRoutePlans({
      originName: input.origin.name,
      destinationName: input.destination.name,
      plans
    }).then((advice) => ({ response, plans, advice }));
  });
}

function createAndSaveRouteDraft(input) {
  const planResponse = input.planResponse
    ? Promise.resolve(input.planResponse)
    : createRoutePlan({
        mode: input.mode === "WALKING" ? "WALKING" : "TRANSIT",
        origin: input.origin,
        destination: input.destination,
        policy: input.policy || "LEAST_TIME"
      });
  return planResponse
    .then((response) =>
      buildFamilyRouteFromBaidu(response, {
        id: input.id,
        name: input.name,
        elderSlot: input.elderSlot,
        origin: input.origin,
        destination: input.destination,
        routeIndex: input.routeIndex || 0
      })
    )
    .then((route) => saveRouteDraft(route));
}

function saveReviewedRoute(route) {
  return updateRouteDraft(route);
}

function approveRemoteRouteStep(routeId, stepId, reviewNote = "", familyPhoto = null) {
  const review = {
    reviewStatus: "APPROVED",
    reviewNote
  };
  if (familyPhoto) {
    review.imageUrl = familyPhoto;
    review.imageStatus = "FAMILY";
  }
  return reviewRouteStep(routeId, stepId, review);
}

function publishRemoteRoute(routeId) {
  return publishRouteDraft(routeId);
}

module.exports = {
  approveRemoteRouteStep,
  createAndSaveRouteDraft,
  prepareRouteAdvice,
  publishRemoteRoute,
  saveReviewedRoute,
  summarizeRoutePlans
};
