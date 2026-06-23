const {
  DECISION_POINT_TYPES,
  IMAGE_STATUSES,
  REVIEW_STATUSES,
  RISK_LEVELS,
  ROUTE_STATUSES
} = require("./route-model");

function getBlockingIssues(step) {
  const issues = [];
  const highRiskWalkingDecision =
    step.riskLevel === RISK_LEVELS.HIGH &&
    (step.type === DECISION_POINT_TYPES.LEFT ||
      step.type === DECISION_POINT_TYPES.RIGHT ||
      step.type === DECISION_POINT_TYPES.STRAIGHT);
  if (!step.location || step.location.latitude == null || step.location.longitude == null) {
    issues.push("缺少锚点坐标");
  }
  if (step.requiresFamilyReview && step.reviewStatus !== REVIEW_STATUSES.APPROVED) {
    issues.push("等待家属确认");
  }
  if (step.riskLevel === RISK_LEVELS.HIGH && step.reviewStatus !== REVIEW_STATUSES.APPROVED) {
    issues.push("高风险步骤未确认");
  }
  if (step.riskLevel === RISK_LEVELS.HIGH && step.imageStatus !== IMAGE_STATUSES.FAMILY) {
    issues.push("高风险步骤需要家属实拍照片");
  }
  if (highRiskWalkingDecision && !String(step.landmarkHint || "").trim()) {
    issues.push("高风险路口需要填写地标提示");
  }
  if (
    (step.type === DECISION_POINT_TYPES.BUS_ON ||
      step.type === DECISION_POINT_TYPES.BUS_OFF) &&
    (!step.transit || !step.transit.lineName || !step.transit.stationName)
  ) {
    issues.push("公交线路或站点不完整");
  }
  return issues;
}

function getRecommendedIssues(step) {
  const issues = [];
  if (step.imageStatus === IMAGE_STATUSES.NONE) issues.push("建议补充照片");
  if (!step.voice || step.voice.voiceType !== "CUSTOM") issues.push("建议录制家属语音");
  if (step.type === DECISION_POINT_TYPES.BUS_ON && (!step.transit || !step.transit.direction)) {
    issues.push("建议家属确认公交行驶方向");
  }
  if (
    (step.type === DECISION_POINT_TYPES.SUBWAY_IN ||
      step.type === DECISION_POINT_TYPES.SUBWAY_OUT) &&
    (!step.transit || !step.transit.accessName)
  ) {
    issues.push(step.type === DECISION_POINT_TYPES.SUBWAY_IN
      ? "建议家属确认地铁进站口"
      : "建议家属确认地铁出站口");
  }
  return issues;
}

function buildReviewSummary(steps) {
  const blockingSteps = [];
  const recommendedSteps = [];
  if (!steps.length) {
    blockingSteps.push({ stepNo: 0, type: "ROUTE", issues: ["路线没有锚点"] });
  }
  steps.forEach((step) => {
    const blockingIssues = getBlockingIssues(step);
    const recommendedIssues = getRecommendedIssues(step);
    if (blockingIssues.length) {
      blockingSteps.push({ stepNo: step.stepNo, type: step.type, issues: blockingIssues });
    }
    if (recommendedIssues.length) {
      recommendedSteps.push({ stepNo: step.stepNo, type: step.type, issues: recommendedIssues });
    }
  });

  return {
    totalSteps: steps.length,
    pendingReviewSteps: blockingSteps.length,
    highRiskSteps: steps.filter((step) => step.riskLevel === RISK_LEVELS.HIGH).length,
    missingPhotoSteps: steps.filter((step) => step.imageStatus === IMAGE_STATUSES.NONE).length,
    blockingSteps,
    recommendedSteps,
    ready: blockingSteps.length === 0
  };
}

function applyRouteReviewStatus(route) {
  const reviewSummary = buildReviewSummary(route.steps || []);
  return {
    ...route,
    status: reviewSummary.ready ? ROUTE_STATUSES.READY : ROUTE_STATUSES.NEEDS_REVIEW,
    reviewSummary
  };
}

module.exports = {
  applyRouteReviewStatus,
  buildReviewSummary,
  getBlockingIssues,
  getRecommendedIssues
};
