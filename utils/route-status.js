function stepNeedsLocation(step) {
  return step.mode.includes("步行") || step.mode.includes("骑行");
}

function getRequiredStepIssues(step) {
  const issues = [];
  if (stepNeedsLocation(step) && (!step.latitude || !step.longitude)) issues.push("坐标");
  if (stepNeedsLocation(step) && step.verificationRequired !== false) issues.push("实地确认");
  return issues;
}

function getOptionalStepIssues(step) {
  const issues = [];
  if (!step.image && !step.imageUrl) issues.push("照片");
  if (!step.audio) issues.push("真人语音");
  if (stepNeedsLocation(step) && !step.direction) issues.push("方向箭头");
  return issues;
}

function getStepIssues(step) {
  return getRequiredStepIssues(step);
}

function getRouteStatus(route) {
  const configuredRoute = route;
  const incompleteSteps = configuredRoute.steps
    .map((step) => ({
      stepNo: step.stepNo,
      title: step.title,
      issues: getRequiredStepIssues(step)
    }))
    .filter((step) => step.issues.length);
  const recommendedSteps = configuredRoute.steps
    .map((step) => ({
      stepNo: step.stepNo,
      title: step.title,
      issues: getOptionalStepIssues(step)
    }))
    .filter((step) => step.issues.length);

  return {
    route: configuredRoute,
    ready: incompleteSteps.length === 0,
    incompleteSteps,
    recommendedSteps
  };
}

module.exports = {
  getRouteStatus,
  getStepIssues,
  getRequiredStepIssues,
  getOptionalStepIssues,
  stepNeedsLocation
};
