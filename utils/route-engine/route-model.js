const DECISION_POINT_TYPES = Object.freeze({
  START: "START",
  STRAIGHT: "STRAIGHT",
  LEFT: "LEFT",
  RIGHT: "RIGHT",
  BUS_ON: "BUS_ON",
  BUS_OFF: "BUS_OFF",
  SUBWAY_IN: "SUBWAY_IN",
  SUBWAY_OUT: "SUBWAY_OUT",
  TRANSFER: "TRANSFER",
  DESTINATION: "DESTINATION"
});

const RISK_LEVELS = Object.freeze({
  LOW: "LOW",
  MEDIUM: "MEDIUM",
  HIGH: "HIGH"
});

const IMAGE_STATUSES = Object.freeze({
  NONE: "NONE",
  AUTO: "AUTO",
  FAMILY: "FAMILY"
});

const VOICE_TYPES = Object.freeze({
  SYSTEM: "SYSTEM",
  CUSTOM: "CUSTOM",
  TTS: "TTS"
});

const ROUTE_STATUSES = Object.freeze({
  DRAFT: "DRAFT",
  NEEDS_REVIEW: "NEEDS_REVIEW",
  READY: "READY",
  PUBLISHED: "PUBLISHED",
  DISABLED: "DISABLED"
});

const REVIEW_STATUSES = Object.freeze({
  PENDING: "PENDING",
  APPROVED: "APPROVED",
  REJECTED: "REJECTED"
});

const STEP_RESULTS = Object.freeze({
  FOUND: "FOUND",
  NOT_FOUND: "NOT_FOUND",
  HELP: "HELP"
});

const ELDER_ROUTE_SLOTS = Object.freeze({
  TO_MOM: "TO_MOM",
  TO_HOME: "TO_HOME"
});

const { normalizeVoiceConfig } = require("./voice-schema");

function createRouteStep(input) {
  const location = input.location || {};
  return {
    id: input.id || "",
    routeId: input.routeId || "",
    stepNo: Number(input.stepNo) || 0,
    type: input.type,
    title: input.title || "",
    shortAction: input.shortAction || "",
    location: {
      latitude: location.latitude == null ? null : Number(location.latitude),
      longitude: location.longitude == null ? null : Number(location.longitude)
    },
    arriveRadius: Number(input.arriveRadius) || 30,
    showDirectionDistance: Number(input.showDirectionDistance) || 30,
    direction: input.direction || "",
    roadName: input.roadName || "",
    landmarkHint: input.landmarkHint || "",
    riskLevel: input.riskLevel || RISK_LEVELS.LOW,
    imageUrl: input.imageUrl || "",
    imageStatus: input.imageStatus || IMAGE_STATUSES.NONE,
    voice: normalizeVoiceConfig({
      voiceType: VOICE_TYPES.SYSTEM,
      audioUrl: "",
      enterVoice: "",
      nearVoice: "",
      repeatVoice: "",
      ...(input.voice || {})
    }, input.shortAction || input.title || ""),
    transit: input.transit || null,
    requiresFamilyReview: Boolean(input.requiresFamilyReview),
    reviewStatus: input.reviewStatus || REVIEW_STATUSES.PENDING,
    reviewNote: input.reviewNote || "",
    stepResult: input.stepResult || null,
    source: input.source || null
  };
}

function createRoute(input) {
  const now = new Date().toISOString();
  return {
    id: input.id,
    name: input.name,
    elderSlot: input.elderSlot || null,
    origin: input.origin,
    destination: input.destination,
    travelModes: input.travelModes || [],
    status: input.status || ROUTE_STATUSES.DRAFT,
    version: Number(input.version) || 1,
    distance: Number(input.distance) || 0,
    estimatedDuration: Number(input.estimatedDuration) || 0,
    sourceProvider: input.sourceProvider || "BAIDU_MAP",
    sourceRouteId: input.sourceRouteId || "",
    sourcePolyline: input.sourcePolyline || [],
    steps: input.steps || [],
    reviewSummary: input.reviewSummary || null,
    createdAt: input.createdAt || now,
    updatedAt: input.updatedAt || now,
    publishedAt: input.publishedAt || ""
  };
}

module.exports = {
  DECISION_POINT_TYPES,
  RISK_LEVELS,
  IMAGE_STATUSES,
  VOICE_TYPES,
  ROUTE_STATUSES,
  REVIEW_STATUSES,
  STEP_RESULTS,
  ELDER_ROUTE_SLOTS,
  createRoute,
  createRouteStep
};
