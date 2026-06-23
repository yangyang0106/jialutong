const {
  calculateDistance,
  calculateDistanceToPolyline,
  calculateDistanceToSegment,
  normalizePolyline
} = require("./geo");

const DEFAULTS = Object.freeze({
  maxAccuracyMeters: 50,
  nearDistanceMeters: 60,
  offRouteDistanceMeters: 120,
  offRouteIncreaseMeters: 80,
  offRouteConfirmCount: 2,
  corridorDistanceMeters: 60,
  corridorConfirmCount: 2,
  locationFailureConfirmCount: 3
});

function createExecutionState(stepIndex = 0) {
  return {
    stepIndex,
    closestDistance: null,
    offRouteCount: 0,
    corridorOffRouteCount: 0,
    locationFailureCount: 0,
    nearTriggeredStepNo: null,
    arrivedTriggeredStepNo: null,
    offRouteTriggered: false,
    arrivalArmed: false,
    initialDistance: null
  };
}

function resetForStep(state, stepIndex) {
  return createExecutionState(stepIndex == null ? state.stepIndex : stepIndex);
}

function getStepLocation(step) {
  if (!step || step.latitude == null || step.longitude == null) return null;
  return {
    latitude: Number(step.latitude),
    longitude: Number(step.longitude)
  };
}

function getSegmentStart(route, stepIndex) {
  if (!route || stepIndex <= 0) return null;
  return getStepLocation(route.steps[stepIndex - 1]);
}

function processLocation(route, state, location, options = {}) {
  const config = { ...DEFAULTS, ...options };
  const step = route && route.steps ? route.steps[state.stepIndex] : null;
  if (!step) return { state, status: "NO_STEP", events: [] };

  if (!location || location.latitude == null || location.longitude == null) {
    const nextState = {
      ...state,
      locationFailureCount: state.locationFailureCount + 1
    };
    return {
      state: nextState,
      status:
        nextState.locationFailureCount >= config.locationFailureConfirmCount
          ? "LOCATION_UNAVAILABLE"
          : "LOCATING",
      events:
        nextState.locationFailureCount === config.locationFailureConfirmCount
          ? [{ type: "LOCATION_UNAVAILABLE" }]
          : []
    };
  }

  if (location.accuracy && location.accuracy > config.maxAccuracyMeters) {
    return processLocation(route, state, null, options);
  }

  const nextState = { ...state, locationFailureCount: 0 };
  if (!step.distanceTracking || !getStepLocation(step)) {
    return {
      state: nextState,
      status: "UNTRACKED",
      events: [],
      userLocation: location
    };
  }

  const target = getStepLocation(step);
  const distance = calculateDistance(
    location.latitude,
    location.longitude,
    target.latitude,
    target.longitude
  );
  const arriveRadius = Number(step.arriveRadius) || 30;
  const showDirectionDistance = Number(step.showDirectionDistance) || 30;
  const nearDistance = Math.max(
    Number(step.nearVoiceDistance) || config.nearDistanceMeters,
    arriveRadius + 20
  );
  const isNearby = distance <= arriveRadius;
  const isNear = distance <= nearDistance;
  const closestDistance =
    state.closestDistance == null ? distance : Math.min(state.closestDistance, distance);
  const movingAway =
    distance > config.offRouteDistanceMeters &&
    distance - closestDistance > config.offRouteIncreaseMeters;
  const offRouteCount = movingAway ? state.offRouteCount + 1 : 0;
  const segmentStart = getSegmentStart(route, state.stepIndex);
  const pathPolyline = step.pathPolyline || [];
  const corridorDistance = pathPolyline.length
    ? calculateDistanceToPolyline(location.latitude, location.longitude, pathPolyline)
    : segmentStart
      ? calculateDistanceToSegment(location.latitude, location.longitude, segmentStart, target)
      : null;
  const outsideCorridor =
    corridorDistance != null && corridorDistance > config.corridorDistanceMeters;
  const corridorOffRouteCount = outsideCorridor ? state.corridorOffRouteCount + 1 : 0;
  const events = [];

  if (isNear && state.nearTriggeredStepNo !== step.stepNo) {
    events.push({ type: "NEAR", step, distance });
    nextState.nearTriggeredStepNo = step.stepNo;
  }
  const initialDistance = state.initialDistance == null ? distance : state.initialDistance;
  const meaningfulApproach =
    initialDistance - distance >= Math.max(5, Number(location.accuracy) || 0);
  const arrivalArmed =
    state.arrivalArmed ||
    distance > arriveRadius + Math.max(10, Number(location.accuracy) || 0) ||
    meaningfulApproach;
  if (isNearby && arrivalArmed && state.arrivedTriggeredStepNo !== step.stepNo) {
    events.push({ type: "ARRIVED", step, distance });
    nextState.arrivedTriggeredStepNo = step.stepNo;
  }

  const shouldTriggerOffRoute =
    !state.offRouteTriggered &&
    (offRouteCount >= config.offRouteConfirmCount ||
      corridorOffRouteCount >= config.corridorConfirmCount);
  if (shouldTriggerOffRoute) {
    events.push({ type: "OFF_ROUTE", step, distance, corridorDistance });
    nextState.offRouteTriggered = true;
  }

  Object.assign(nextState, {
    closestDistance,
    offRouteCount,
    corridorOffRouteCount,
    arrivalArmed,
    initialDistance
  });

  return {
    state: nextState,
    status: shouldTriggerOffRoute ? "OFF_ROUTE" : isNearby ? "ARRIVED" : isNear ? "NEAR" : "MOVING",
    events,
    distance,
    corridorDistance,
    isNearby,
    isNear,
    showDirection: distance <= showDirectionDistance,
    routeSafetyWarning: outsideCorridor,
    userLocation: location
  };
}

function simulateLocation(route, stepIndex, progress) {
  const step = route && route.steps ? route.steps[stepIndex] : null;
  const target = getStepLocation(step);
  if (!target) return null;
  const pathPoints = normalizePolyline(step.pathPolyline || []);
  const start = getSegmentStart(route, stepIndex) || {
    latitude: target.latitude - 0.001,
    longitude: target.longitude - 0.001
  };
  const ratio = Math.max(0, Math.min(1, Number(progress) || 0));
  const pathEnd = pathPoints[pathPoints.length - 1];
  const pathEndsAtTarget =
    pathEnd &&
    calculateDistance(
      pathEnd.latitude,
      pathEnd.longitude,
      target.latitude,
      target.longitude
    ) <= Math.max(20, Number(step.arriveRadius) || 30);
  if (pathPoints.length > 1 && pathEndsAtTarget) {
    const lengths = pathPoints.slice(1).map((point, index) =>
      calculateDistance(
        pathPoints[index].latitude,
        pathPoints[index].longitude,
        point.latitude,
        point.longitude
      )
    );
    const total = lengths.reduce((sum, length) => sum + length, 0);
    const targetDistance = total * ratio;
    let walked = 0;
    for (let index = 0; index < lengths.length; index += 1) {
      if (walked + lengths[index] >= targetDistance) {
        const segmentRatio = lengths[index]
          ? (targetDistance - walked) / lengths[index]
          : 0;
        return {
          latitude:
            pathPoints[index].latitude +
            (pathPoints[index + 1].latitude - pathPoints[index].latitude) * segmentRatio,
          longitude:
            pathPoints[index].longitude +
            (pathPoints[index + 1].longitude - pathPoints[index].longitude) * segmentRatio,
          accuracy: 5
        };
      }
      walked += lengths[index];
    }
  }
  return {
    latitude: start.latitude + (target.latitude - start.latitude) * ratio,
    longitude: start.longitude + (target.longitude - start.longitude) * ratio,
    accuracy: 5
  };
}

module.exports = {
  DEFAULTS,
  createExecutionState,
  processLocation,
  resetForStep,
  simulateLocation
};
