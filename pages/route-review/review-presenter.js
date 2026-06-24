const {
  listVoiceMoments,
  normalizeVoiceConfig,
  setVoiceMoment
} = require("../../utils/voice-schema");

const TYPE_LABELS = {
  START: "起点",
  STRAIGHT: "步行接驳",
  LEFT: "左转",
  RIGHT: "右转",
  BUS_ON: "公交上车",
  BUS_OFF: "公交下车",
  SUBWAY_IN: "地铁进站",
  SUBWAY_OUT: "地铁出站",
  TRANSFER: "换乘",
  DESTINATION: "目的地"
};

const STATUS_LABELS = {
  NEEDS_REVIEW: "等待家属审核",
  READY: "可以发布",
  PUBLISHED: "已经发布",
  DISABLED: "已经停用"
};

const PRIORITY_LABELS = {
  MUST: "必须",
  SHOULD: "建议",
  OPTIONAL: "可选"
};

const VOICE_TYPE_LABELS = {
  enter: "进入语音",
  repeat: "途中重复",
  near: "接近提醒",
  arrived: "到达确认",
  offRoute: "偏航求助"
};

const PHOTO_REVIEW_LABELS = {
  PASS: "照片可以使用",
  WARNING: "建议再确认",
  REJECT: "建议重拍"
};

function withPriorityLabel(task) {
  return {
    ...task,
    priorityLabel: PRIORITY_LABELS[task.priority] || task.priority,
    badExampleText: (task.badExamples || []).join("；"),
    landmarkTypeText: (task.suggestedLandmarkTypes || []).join("、"),
    voiceTypeLabel: VOICE_TYPE_LABELS[task.voiceType] || task.voiceType
  };
}

function enrichCollectionPlan(plan) {
  const photoTasks = (plan.photoTasks || []).map(withPriorityLabel);
  const landmarkTasks = (plan.landmarkTasks || []).map(withPriorityLabel);
  const voiceTasks = (plan.voiceTasks || []).map(withPriorityLabel);
  const reviewTasks = (plan.reviewTasks || []).map(withPriorityLabel);
  const stepTasksById = {};

  function addStepTask(task, key) {
    if (!task.stepId) return;
    if (!stepTasksById[task.stepId]) {
      stepTasksById[task.stepId] = {
        photoTasks: [],
        landmarkTasks: [],
        voiceTasks: [],
        reviewTasks: [],
        total: 0
      };
    }
    stepTasksById[task.stepId][key].push(task);
    stepTasksById[task.stepId].total += 1;
  }

  photoTasks.forEach((task) => addStepTask(task, "photoTasks"));
  landmarkTasks.forEach((task) => addStepTask(task, "landmarkTasks"));
  voiceTasks.forEach((task) => addStepTask(task, "voiceTasks"));
  reviewTasks.forEach((task) => addStepTask(task, "reviewTasks"));

  return {
    ...plan,
    photoTaskCount: photoTasks.length,
    landmarkTaskCount: landmarkTasks.length,
    voiceTaskCount: voiceTasks.length,
    reviewTaskCount: reviewTasks.length,
    stepTasksById,
    mustPhotoTasks: photoTasks.filter((item) => item.priority === "MUST"),
    shouldPhotoTasks: photoTasks.filter((item) => item.priority === "SHOULD"),
    optionalPhotoTasks: photoTasks.filter((item) => item.priority === "OPTIONAL"),
    mustLandmarkTasks: landmarkTasks.filter((item) => item.priority === "MUST"),
    shouldLandmarkTasks: landmarkTasks.filter((item) => item.priority === "SHOULD"),
    voiceTasks,
    reviewTasks,
    testTasks: plan.testTasks || []
  };
}

function enrichRoute(route, collectionPlan = null) {
  const blockingByStep = {};
  const summary = route.reviewSummary || {};
  (summary.blockingSteps || []).forEach((item) => {
    blockingByStep[item.stepNo] = item.issues || [];
  });
  const stepTasksById = collectionPlan && collectionPlan.stepTasksById || {};
  return {
    ...route,
    statusLabel: STATUS_LABELS[route.status] || route.status,
    steps: route.steps.map((step) => enrichStep(step, blockingByStep, stepTasksById))
  };
}

function enrichStep(step, blockingByStep, stepTasksById) {
  const voice = normalizeVoiceConfig(step.voice, step.shortAction || step.title);
  const voiceMoments = listVoiceMoments(voice).map((moment) => ({
    ...moment,
    key: `${step.id}:${moment.moment}`,
    hasAudio: Boolean(moment.audioUrl),
    hasCustomVoice: moment.voiceType === "CUSTOM" && Boolean(moment.audioUrl),
    typeLabel:
      moment.voiceType === "CUSTOM"
        ? "真人录音"
        : moment.voiceType === "TTS"
          ? "系统语音"
          : "默认文案"
  }));
  const transit = step.transit || null;
  const transitWarning = buildTransitWarning(step, transit);
  const aiConfidenceLabel =
    step.aiConfidence === "HIGH" ? "高" : step.aiConfidence === "MEDIUM" ? "中" : "低";
  const photoReview = step.photoReview || null;
  const collectionTasks = stepTasksById[step.id] || {
    photoTasks: [],
    landmarkTasks: [],
    voiceTasks: [],
    reviewTasks: [],
    total: 0
  };

  return {
    ...step,
    voice,
    voiceMoments,
    preparedVoiceCount: voiceMoments.filter((item) => item.text).length,
    typeLabel: TYPE_LABELS[step.type] || step.type,
    riskLabel:
      step.riskLevel === "HIGH" ? "高风险" : step.riskLevel === "MEDIUM" ? "中风险" : "低风险",
    blockingIssues: blockingByStep[step.stepNo] || [],
    blockingIssueText: (blockingByStep[step.stepNo] || []).join("、"),
    transitWarning,
    aiConfidenceLabel,
    photoReview,
    photoReviewLabel: photoReview ? PHOTO_REVIEW_LABELS[photoReview.status] || photoReview.status : "",
    photoReviewIssueText: photoReview ? (photoReview.issues || []).join("；") : "",
    photoReviewSuggestionText: photoReview ? (photoReview.suggestions || []).join("；") : "",
    collectionTasks,
    hasCollectionTasks: collectionTasks.total > 0,
    approved: step.reviewStatus === "APPROVED",
    canApprove:
      step.reviewStatus !== "APPROVED" &&
      !(step.riskLevel === "HIGH" && step.imageStatus !== "FAMILY")
  };
}

function buildTransitWarning(step, transit) {
  if (step.type === "BUS_ON" && transit && !transit.direction) {
    return "百度未提供公交行驶方向，请家属现场确认后再发布。";
  }
  if ((step.type === "SUBWAY_IN" || step.type === "SUBWAY_OUT") && transit && !transit.accessName) {
    return `百度未提供${step.type === "SUBWAY_IN" ? "进站口" : "出站口"}，请家属现场确认并补充照片。`;
  }
  return "";
}

function voiceWithLandmark(step, landmarkHint) {
  if (!landmarkHint) return step.voice;
  const action = step.type === "LEFT" ? "左转" : step.type === "RIGHT" ? "右转" : "继续往前走";
  let voice = step.voice;
  const enterText =
    step.type === "STRAIGHT"
      ? `请继续往前走，看到${landmarkHint}，说明方向正确。`
      : `请往前走，看到${landmarkHint}后，在前面路口${action}。`;
  const nearText =
    step.type === "STRAIGHT"
      ? `快到${landmarkHint}了，请继续按照片方向走。`
      : `快到了，看到${landmarkHint}后，请${action}。`;
  voice = setVoiceMoment(voice, "enter", {
    text: enterText,
    audioUrl: step.voice.enterVoiceType === "CUSTOM" ? step.voice.enterAudioUrl : "",
    voiceType: step.voice.enterVoiceType === "CUSTOM" ? "CUSTOM" : "SYSTEM"
  });
  return setVoiceMoment(voice, "near", {
    text: nearText,
    audioUrl: step.voice.nearVoiceType === "CUSTOM" ? step.voice.nearAudioUrl : "",
    voiceType: step.voice.nearVoiceType === "CUSTOM" ? "CUSTOM" : "SYSTEM"
  });
}

module.exports = {
  enrichCollectionPlan,
  enrichRoute,
  voiceWithLandmark
};
