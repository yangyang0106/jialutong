const { applyAssetsToRoute } = require("./route-assets");

function stepNeedsLocation(step) {
  return step.mode.includes("步行") || step.mode.includes("骑行");
}

function getStepIssues(step) {
  const issues = [];
  if (!step.image) issues.push("照片");
  if (!step.audio) issues.push("语音");
  if (!step.desc || step.desc.includes("待家属")) issues.push("动作说明");
  if (stepNeedsLocation(step) && !step.direction) issues.push("方向箭头");
  if (stepNeedsLocation(step) && (!step.latitude || !step.longitude)) issues.push("坐标");
  if (stepNeedsLocation(step) && step.verificationRequired !== false) issues.push("实地确认");
  if (stepNeedsLocation(step) && step.distanceTracking !== true) issues.push("距离判断");
  return issues;
}

function getRouteStatus(route) {
  const configuredRoute = applyAssetsToRoute(route);
  const incompleteSteps = configuredRoute.steps
    .map((step) => ({
      stepNo: step.stepNo,
      title: step.title,
      issues: getStepIssues(step)
    }))
    .filter((step) => step.issues.length);

  return {
    route: configuredRoute,
    ready: incompleteSteps.length === 0,
    incompleteSteps
  };
}

module.exports = {
  getRouteStatus,
  getStepIssues,
  stepNeedsLocation
};
