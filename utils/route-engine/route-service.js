const {
  adviseRoutePlans,
  createRoutePlan,
  createRouteDraftFromBaidu,
  publishRouteDraft,
  reviewRouteStep,
  summarizeRoutePlansFromBaidu,
  updateRouteDraft
} = require("./route-repository");

function summarizeRoutePlans(response, input) {
  return summarizeRoutePlansFromBaidu({
    origin: input.origin,
    destination: input.destination,
    planResponse: response
  }).then((result) => result.plans || []);
}

function prepareRouteAdvice(input) {
  return createRoutePlan({
    mode: input.mode === "WALKING" ? "WALKING" : "TRANSIT",
    origin: input.origin,
    destination: input.destination,
    policy: input.policy || "LEAST_TIME"
  }).then((response) => {
    return summarizeRoutePlans(response, input).then((plans) => {
      if (!plans.length) throw new Error("百度地图未返回可用路线");
      return adviseRoutePlans({
        originName: input.origin.name,
        destinationName: input.destination.name,
        plans
      }).then((advice) => ({ response, plans, advice }));
    });
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
      createRouteDraftFromBaidu({
        id: input.id,
        name: input.name,
        elderSlot: input.elderSlot,
        origin: input.origin,
        destination: input.destination,
        planResponse: response,
        routeIndex: input.routeIndex || 0
      })
    );
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
