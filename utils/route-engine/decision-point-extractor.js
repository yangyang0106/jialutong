const { calculateDistance } = require("../geo");
const {
  DECISION_POINT_TYPES,
  RISK_LEVELS,
  IMAGE_STATUSES,
  REVIEW_STATUSES,
  createRouteStep
} = require("./route-model");
const { generateStepVoice } = require("./voice-generator");

const MERGE_DISTANCE_METERS = 20;
const MIN_WALK_CONNECTOR_METERS = 30;
const MAX_WALK_WITHOUT_CONFIRMATION_METERS = 380;

function normalizeLocation(location) {
  if (!location || location.lat == null && location.latitude == null) return null;
  return {
    latitude: Number(location.latitude == null ? location.lat : location.latitude),
    longitude: Number(location.longitude == null ? location.lng : location.longitude)
  };
}

function typeFromAction(action) {
  if (/左转|左前方|偏左|靠左|左后转|左转掉头/.test(action || "")) {
    return DECISION_POINT_TYPES.LEFT;
  }
  if (/右转|右前方|偏右|靠右|右后转/.test(action || "")) {
    return DECISION_POINT_TYPES.RIGHT;
  }
  if (/进入.*辅路|驶入.*辅路|转入.*辅路/.test(action || "")) {
    return DECISION_POINT_TYPES.STRAIGHT;
  }
  return null;
}

function roadNameFromSegment(segment) {
  if (segment.roadName) return segment.roadName;
  const instruction = segment.instruction || "";
  const enteredRoad = instruction.match(/(?:进入|转入)([^，,。]+?)(?:走|直行|$)/);
  return enteredRoad ? enteredRoad[1].trim() : "";
}

function riskFromSegment(segment, type) {
  const instruction = `${segment.instruction || ""}${segment.action || ""}`;
  if (segment.facilityType === 1 || segment.facilityType === 2 || segment.facilityType === 3) {
    return RISK_LEVELS.HIGH;
  }
  if (/过马路|穿过马路|横穿|人行横道|红绿灯|地下通道|天桥/.test(instruction)) {
    return RISK_LEVELS.HIGH;
  }
  if (
    type === DECISION_POINT_TYPES.SUBWAY_IN ||
    type === DECISION_POINT_TYPES.SUBWAY_OUT ||
    type === DECISION_POINT_TYPES.TRANSFER
  ) {
    return RISK_LEVELS.HIGH;
  }
  if (type === DECISION_POINT_TYPES.BUS_ON || type === DECISION_POINT_TYPES.BUS_OFF) {
    return RISK_LEVELS.MEDIUM;
  }
  return RISK_LEVELS.LOW;
}

function requiresReview(type, riskLevel) {
  return (
    riskLevel === RISK_LEVELS.HIGH ||
    type === DECISION_POINT_TYPES.START ||
    type === DECISION_POINT_TYPES.DESTINATION ||
    type === DECISION_POINT_TYPES.BUS_ON ||
    type === DECISION_POINT_TYPES.BUS_OFF ||
    type === DECISION_POINT_TYPES.SUBWAY_IN ||
    type === DECISION_POINT_TYPES.SUBWAY_OUT ||
    type === DECISION_POINT_TYPES.TRANSFER
  );
}

function createCandidate(type, segment, location, extra = {}) {
  const riskLevel = riskFromSegment(segment, type);
  return {
    type,
    location: normalizeLocation(location),
    riskLevel,
    requiresFamilyReview: requiresReview(type, riskLevel),
    roadName: roadNameFromSegment(segment),
    source: {
      provider: segment.provider || "BAIDU_MAP",
      sourceSectionIndex: segment.sourceSectionIndex,
      sourceStepIndexes: [segment.sourceStepIndex],
      instruction: segment.instruction || "",
      polylineIndex: segment.sourcePolylineIndex,
      polyline: segment.polyline || []
    },
    ...extra
  };
}

function polylinePoints(polyline) {
  const result = [];
  for (let index = 0; index < (polyline || []).length - 1; index += 2) {
    result.push({ latitude: Number(polyline[index]), longitude: Number(polyline[index + 1]) });
  }
  return result;
}

function interpolatePoint(start, end, ratio) {
  return {
    latitude: start.latitude + (end.latitude - start.latitude) * ratio,
    longitude: start.longitude + (end.longitude - start.longitude) * ratio
  };
}

function reassuranceLocations(segment) {
  if (segment.mode !== "WALKING" || Number(segment.distance) <= MAX_WALK_WITHOUT_CONFIRMATION_METERS) {
    return [];
  }
  const points = polylinePoints(segment.polyline);
  if (points.length < 2) return [];
  const targets = [];
  for (
    let target = MAX_WALK_WITHOUT_CONFIRMATION_METERS;
    target < Number(segment.distance) - 100;
    target += MAX_WALK_WITHOUT_CONFIRMATION_METERS
  ) {
    targets.push(target);
  }
  const locations = [];
  let walked = 0;
  let targetIndex = 0;
  for (let index = 1; index < points.length && targetIndex < targets.length; index += 1) {
    const segmentLength = calculateDistance(
      points[index - 1].latitude,
      points[index - 1].longitude,
      points[index].latitude,
      points[index].longitude
    );
    while (targetIndex < targets.length && walked + segmentLength >= targets[targetIndex]) {
      locations.push(
        interpolatePoint(points[index - 1], points[index], (targets[targetIndex] - walked) / segmentLength)
      );
      targetIndex += 1;
    }
    walked += segmentLength;
  }
  return locations;
}

function landmarkHintFromSegment(segment) {
  const instruction = segment.instruction || "";
  const road = roadNameFromSegment(segment);
  if (/辅路/.test(instruction) && road) return `${road}路口`;
  return "";
}

function approachPolyline(previous, candidate, segments) {
  const endIndex = Number(candidate.source && candidate.source.sourceSectionIndex);
  const previousIndex = previous
    ? Number(previous.source && previous.source.sourceSectionIndex)
    : endIndex;
  if (!Number.isFinite(endIndex)) return candidate.source && candidate.source.polyline || [];
  const startIndex = Number.isFinite(previousIndex) ? Math.min(previousIndex, endIndex) : endIndex;
  return segments
    .slice(startIndex, endIndex + 1)
    .flatMap((segment) => segment.polyline || []);
}

function buildTransitCandidate(segment, type, station) {
  const transit = segment.transit || {};
  return createCandidate(type, segment, station && station.location, {
    transit: {
      vehicle: transit.vehicle,
      lineName: transit.lineName,
      direction: transit.direction,
      stationName: station ? station.title || "" : "",
      accessName: station ? station.accessName || "" : "",
      stationCount: transit.stationCount
    }
  });
}

function isStationTransferWalk(segment) {
  return (
    segment &&
    segment.mode === "WALKING" &&
    /站内|换乘|通道/.test(`${segment.instruction || ""}${segment.action || ""}`)
  );
}

function findConnectedSubway(segments, startIndex, direction) {
  for (
    let index = startIndex + direction;
    index >= 0 && index < segments.length;
    index += direction
  ) {
    const segment = segments[index];
    if (segment.mode === "TRANSIT") {
      return segment.transit && segment.transit.vehicle === "SUBWAY" ? segment : null;
    }
    if (!isStationTransferWalk(segment)) return null;
  }
  return null;
}

function getNextTransit(segments, startIndex) {
  for (let index = startIndex + 1; index < segments.length; index += 1) {
    const segment = segments[index];
    if (segment.mode === "TRANSIT") return segment;
    if (!isStationTransferWalk(segment) && segment.mode !== "WALKING") return null;
  }
  return null;
}

function isWalkingRunEnd(segments, index) {
  const next = segments[index + 1];
  return !next || next.mode !== "WALKING" || isStationTransferWalk(next);
}

function walkingConnectorCopy(segments, segmentIndex, destinationName) {
  const nextTransit = getNextTransit(segments, segmentIndex);
  if (nextTransit && nextTransit.transit) {
    const stationName =
      nextTransit.transit.getOn && nextTransit.transit.getOn.title
        ? nextTransit.transit.getOn.title
        : nextTransit.transit.vehicle === "SUBWAY"
          ? "地铁站入口"
          : "公交站";
    return {
      title: `步行到${stationName}`,
      shortAction: `走到${stationName}`
    };
  }
  return {
    title: `步行到${destinationName}`,
    shortAction: "继续走到目的地"
  };
}

function mergeNearbyCandidates(candidates) {
  return candidates.reduce((result, candidate) => {
    const previous = result[result.length - 1];
    if (
      previous &&
      previous.type === candidate.type &&
      previous.location &&
      candidate.location &&
      calculateDistance(
        previous.location.latitude,
        previous.location.longitude,
        candidate.location.latitude,
        candidate.location.longitude
      ) <= MERGE_DISTANCE_METERS
    ) {
      previous.source.sourceStepIndexes.push(...candidate.source.sourceStepIndexes);
      previous.riskLevel =
        candidate.riskLevel === RISK_LEVELS.HIGH ? RISK_LEVELS.HIGH : previous.riskLevel;
      previous.requiresFamilyReview =
        previous.requiresFamilyReview || candidate.requiresFamilyReview;
      return result;
    }
    result.push(candidate);
    return result;
  }, []);
}

function walkingCandidateGapDistance(previous, candidate, segments) {
  const startIndex = Number(previous.source && previous.source.sourceSectionIndex);
  const endIndex = Number(candidate.source && candidate.source.sourceSectionIndex);
  if (!Number.isFinite(startIndex) || !Number.isFinite(endIndex)) return 0;
  const gapSegments = segments.slice(Math.min(startIndex, endIndex), Math.max(startIndex, endIndex) + 1);
  if (!gapSegments.every((segment) => segment.mode === "WALKING" && !isStationTransferWalk(segment))) {
    return 0;
  }
  return gapSegments.reduce((total, segment) => total + Number(segment.distance || 0), 0);
}

function fillLongWalkingGaps(candidates, segments) {
  return candidates.reduce((result, candidate) => {
    const previous = result[result.length - 1];
    const walkingDistance =
      previous && previous.location && candidate.location
        ? walkingCandidateGapDistance(previous, candidate, segments)
        : 0;
    if (!walkingDistance || walkingDistance <= MAX_WALK_WITHOUT_CONFIRMATION_METERS) {
      result.push(candidate);
      return result;
    }
    const distance = calculateDistance(
      previous.location.latitude,
      previous.location.longitude,
      candidate.location.latitude,
      candidate.location.longitude
    );
    if (distance > walkingDistance * 1.5 + 50) {
      result.push(candidate);
      return result;
    }
    const insertCount = Math.ceil(distance / MAX_WALK_WITHOUT_CONFIRMATION_METERS) - 1;
    for (let index = 1; index <= insertCount; index += 1) {
      const location = interpolatePoint(previous.location, candidate.location, index / (insertCount + 1));
      result.push(
        createCandidate(DECISION_POINT_TYPES.STRAIGHT, segments[candidate.source.sourceSectionIndex], location, {
          reassurance: true,
          riskLevel: RISK_LEVELS.LOW,
          requiresFamilyReview: false,
          walkingTitle: "继续往前走",
          walkingShortAction: "继续往前走",
          fixedApproachPolyline: [
            previous.location.latitude,
            previous.location.longitude,
            location.latitude,
            location.longitude
          ]
        })
      );
    }
    result.push(candidate);
    return result;
  }, []);
}

function candidateTitle(candidate, destinationName) {
  const transit = candidate.transit || {};
  const stationName = transit.stationName || "当前站";
  const stationInsideName = stationName.endsWith("站") ? `${stationName}内` : `${stationName}站内`;
  const accessName = transit.accessName || "";
  const direction = transit.direction ? `，开往${transit.direction}` : "";
  switch (candidate.type) {
    case DECISION_POINT_TYPES.START:
      return "从起点出发";
    case DECISION_POINT_TYPES.LEFT:
      return candidate.roadName ? `左转进入${candidate.roadName}` : "在前面路口左转";
    case DECISION_POINT_TYPES.RIGHT:
      return candidate.roadName ? `右转进入${candidate.roadName}` : "在前面路口右转";
    case DECISION_POINT_TYPES.STRAIGHT:
      return candidate.walkingTitle || "继续往前走";
    case DECISION_POINT_TYPES.BUS_ON:
      return `在${transit.stationName || "公交站"}乘坐${transit.lineName || "公交车"}${direction}`;
    case DECISION_POINT_TYPES.BUS_OFF:
      return `在${transit.stationName || "目标站"}下车`;
    case DECISION_POINT_TYPES.SUBWAY_IN:
      return `从${transit.stationName || "地铁站"}${accessName || "家属确认的入口"}进站`;
    case DECISION_POINT_TYPES.SUBWAY_OUT:
      return `从${transit.stationName || "目标站"}${accessName || "家属确认的出口"}出站`;
    case DECISION_POINT_TYPES.TRANSFER:
      return `在${stationInsideName}换乘${transit.lineName || "下一条线路"}${direction}`;
    case DECISION_POINT_TYPES.DESTINATION:
      return `到达${destinationName}`;
    default:
      return "继续前进";
  }
}

function candidateShortAction(candidate) {
  const transit = candidate.transit || {};
  const crossesRoad = /过马路|穿过马路|横穿|人行横道|红绿灯/.test(
    candidate.source && candidate.source.instruction || ""
  );
  switch (candidate.type) {
    case DECISION_POINT_TYPES.START:
      return "准备出发";
    case DECISION_POINT_TYPES.LEFT:
      return crossesRoad ? "过马路左转" : "前面左转";
    case DECISION_POINT_TYPES.RIGHT:
      return crossesRoad ? "过马路右转" : "前面右转";
    case DECISION_POINT_TYPES.STRAIGHT:
      return candidate.walkingShortAction || "继续往前走";
    case DECISION_POINT_TYPES.BUS_ON:
      return `等${transit.lineName || "公交车"}`;
    case DECISION_POINT_TYPES.BUS_OFF:
      return "准备下车";
    case DECISION_POINT_TYPES.SUBWAY_IN:
      return "进入地铁站";
    case DECISION_POINT_TYPES.SUBWAY_OUT:
      return "走出地铁站";
    case DECISION_POINT_TYPES.TRANSFER:
      return "站内换乘";
    case DECISION_POINT_TYPES.DESTINATION:
      return "已经到达";
    default:
      return "继续前进";
  }
}

function extractDecisionPoints(normalizedRoute, routeContext) {
  const segments = normalizedRoute.segments || [];
  if (!segments.length) throw new Error("路线中没有可解析的路段");

  const candidates = [];
  candidates.push(
    createCandidate(
      DECISION_POINT_TYPES.START,
      segments[0],
      routeContext.origin || segments[0].startLocation
    )
  );

  segments.forEach((segment, segmentIndex) => {
    if (segment.mode === "WALKING") {
      if (isStationTransferWalk(segment)) return;
      reassuranceLocations(segment).forEach((location) => {
        candidates.push(
          createCandidate(DECISION_POINT_TYPES.STRAIGHT, segment, location, {
            reassurance: true,
            riskLevel: RISK_LEVELS.LOW,
            requiresFamilyReview: false,
            walkingTitle: segment.roadName ? `继续沿${segment.roadName}往前走` : "继续往前走",
            walkingShortAction: "继续往前走"
          })
        );
      });
      const type = typeFromAction(`${segment.action || ""}${segment.instruction || ""}`);
      if (type) {
        candidates.push(
          createCandidate(type, segment, segment.endLocation, {
            landmarkHint: landmarkHintFromSegment(segment)
          })
        );
      }
      if (
        isWalkingRunEnd(segments, segmentIndex) &&
        (Number(segment.distance) >= MIN_WALK_CONNECTOR_METERS || !type)
      ) {
        const copy = walkingConnectorCopy(segments, segmentIndex, routeContext.destinationName);
        candidates.push(
          createCandidate(DECISION_POINT_TYPES.STRAIGHT, segment, segment.endLocation, {
            walkingTitle: copy.title,
            walkingShortAction: copy.shortAction
          })
        );
      }
      return;
    }

    const transit = segment.transit || {};
    if (transit.vehicle === "BUS") {
      candidates.push(buildTransitCandidate(segment, DECISION_POINT_TYPES.BUS_ON, transit.getOn));
      candidates.push(buildTransitCandidate(segment, DECISION_POINT_TYPES.BUS_OFF, transit.getOff));
    } else if (transit.vehicle === "SUBWAY") {
      const previousSubway = findConnectedSubway(segments, segmentIndex, -1);
      const nextSubway = findConnectedSubway(segments, segmentIndex, 1);
      if (previousSubway) {
        candidates.push(
          buildTransitCandidate(segment, DECISION_POINT_TYPES.TRANSFER, transit.getOn)
        );
      } else {
        candidates.push(
          buildTransitCandidate(segment, DECISION_POINT_TYPES.SUBWAY_IN, transit.getOn)
        );
      }
      if (!nextSubway) {
        candidates.push(
          buildTransitCandidate(segment, DECISION_POINT_TYPES.SUBWAY_OUT, transit.getOff)
        );
      }
    }
  });

  candidates.push(
    createCandidate(
      DECISION_POINT_TYPES.DESTINATION,
      segments[segments.length - 1],
      segments[segments.length - 1].endLocation || routeContext.destination
    )
  );

  const merged = fillLongWalkingGaps(mergeNearbyCandidates(candidates), segments);
  return merged.map((candidate, index) => {
    const previous = merged[index - 1];
    candidate.source.polyline =
      candidate.fixedApproachPolyline || approachPolyline(previous, candidate, segments);
    const previousDistance =
      previous && previous.location && candidate.location
        ? calculateDistance(
            previous.location.latitude,
            previous.location.longitude,
            candidate.location.latitude,
            candidate.location.longitude
          )
        : null;
    const arriveRadius =
      previousDistance != null && previousDistance <= 45
        ? Math.max(10, Math.floor(previousDistance / 3))
        : 30;
    const baseStep = createRouteStep({
      id: `${routeContext.routeId}-step-${index + 1}`,
      routeId: routeContext.routeId,
      stepNo: index + 1,
      type: candidate.type,
      title: candidateTitle(candidate, routeContext.destinationName),
      shortAction: candidateShortAction(candidate),
      location: candidate.location,
      roadName: candidate.roadName,
      landmarkHint: candidate.landmarkHint || "",
      arriveRadius,
      riskLevel: candidate.riskLevel,
      imageStatus: IMAGE_STATUSES.NONE,
      transit: candidate.transit || null,
      requiresFamilyReview: candidate.requiresFamilyReview,
      reviewStatus: REVIEW_STATUSES.PENDING,
      source: candidate.source
    });
    return {
      ...baseStep,
      voice: generateStepVoice(baseStep, routeContext.destinationName)
    };
  });
}

module.exports = {
  extractDecisionPoints,
  findConnectedSubway,
  getNextTransit,
  isWalkingRunEnd,
  isStationTransferWalk,
  mergeNearbyCandidates,
  fillLongWalkingGaps,
  riskFromSegment,
  roadNameFromSegment,
  reassuranceLocations,
  approachPolyline,
  typeFromAction
};
