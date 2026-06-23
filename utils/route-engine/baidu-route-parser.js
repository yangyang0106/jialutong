function normalizeLocation(location) {
  if (!location || location.lat == null || location.lng == null) return null;
  return {
    latitude: Number(location.lat),
    longitude: Number(location.lng)
  };
}

function parsePath(path) {
  if (!path || typeof path !== "string") return [];
  return path.split(";").reduce((points, value) => {
    const [longitude, latitude] = value.split(",").map(Number);
    if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
      points.push(latitude, longitude);
    }
    return points;
  }, []);
}

function stripHtml(value) {
  return String(value || "").replace(/<[^>]+>/g, "");
}

function firstText(...values) {
  return values.find((value) => typeof value === "string" && value.trim()) || "";
}

function extractAccessName(value) {
  const text = stripHtml(value);
  const match = text.match(
    /(?:地铁站)?([A-Za-z]?\d+\s*(?:号)?(?:出入)?口|[A-Za-z]\s*(?:出入)?口)/i
  );
  return match ? match[1].replace(/\s+/g, "") : "";
}

function cleanStationName(value) {
  return String(value || "")
    .replace(/[（(]\s*[A-Za-z]?\d+\s*(?:号)?(?:出入)?口\s*[）)]/gi, "")
    .trim();
}

function stationAccess(station, detail, kind) {
  const prefix = kind === "entrance" ? "entrance" : "exit";
  return firstText(
    station && station.accessName,
    station && station[`${prefix}_name`],
    station && station[prefix],
    detail && detail[`${prefix}_name`],
    detail && detail[prefix]
  ) || extractAccessName(
    firstText(
      station && station.name,
      station && station.start_name,
      station && station.end_name,
      station && station.instructions,
      station && station.instruction,
      detail && detail.instructions,
      detail && detail.instruction
    )
  );
}

function walkingSegment(step, sectionIndex, stepIndex) {
  const instruction = stripHtml(step.instruction);
  return {
    provider: "BAIDU_MAP",
    mode: "WALKING",
    vehicle: null,
    action: `${step.turn_type || ""} ${instruction}`.trim(),
    instruction,
    roadName: step.road_name || "",
    direction: step.direction || "",
    distance: Number(step.distance) || 0,
    facilityType: Number(step.traffic_condition) || 0,
    startLocation: normalizeLocation(step.start_location),
    endLocation: normalizeLocation(step.end_location),
    polyline: parsePath(step.path),
    sourceSectionIndex: sectionIndex,
    sourceStepIndex: stepIndex,
    sourcePolylineIndex: null
  };
}

function getVehicleDetail(step) {
  const vehicleInfo = step.vehicle_info || {};
  const detail = vehicleInfo.detail || step.vehicle || {};
  return { vehicleInfo, detail };
}

function getTransitVehicle(step) {
  const { vehicleInfo, detail } = getVehicleDetail(step);
  const rawType = String(
    vehicleInfo.type == null ? detail.type == null ? "" : detail.type : vehicleInfo.type
  ).toUpperCase();
  const name = detail.name || step.instructions || step.instruction || "";
  if (/SUBWAY|地铁|轨道/.test(`${rawType}${name}`)) return "SUBWAY";
  if (Number(detail.type) === 1) return "SUBWAY";
  return "BUS";
}

function transitSegment(step, sectionIndex, stepIndex) {
  const { detail } = getVehicleDetail(step);
  const vehicle = getTransitVehicle(step);
  const getOn = detail.departure_station || detail.start_info || {};
  const getOff = detail.arrive_station || detail.end_info || {};
  const direction = firstText(detail.direction, detail.direct_text, step.direction);
  return {
    provider: "BAIDU_MAP",
    mode: "TRANSIT",
    vehicle,
    action: "",
    instruction: stripHtml(step.instructions || step.instruction),
    roadName: "",
    direction,
    distance: Number(step.distance) || 0,
    facilityType: 0,
    startLocation: normalizeLocation(getOn.location || step.start_location),
    endLocation: normalizeLocation(getOff.location || step.end_location),
    polyline: parsePath(step.path),
    sourceSectionIndex: sectionIndex,
    sourceStepIndex: stepIndex,
    sourcePolylineIndex: null,
    transit: {
      vehicle,
      lineId: detail.uid || detail.line_id || "",
      lineName: detail.name || "",
      direction,
      getOn: {
        title: cleanStationName(getOn.name || getOn.start_name || detail.start_name || ""),
        location: getOn.location || getOn.start_location || step.start_location || null,
        accessName: stationAccess(getOn, detail, "entrance")
      },
      getOff: {
        title: cleanStationName(getOff.name || getOff.end_name || detail.end_name || ""),
        location: getOff.location || getOff.end_location || step.end_location || null,
        accessName: stationAccess(getOff, detail, "exit")
      },
      stationCount: Number(detail.stop_num) || 0,
      stations: detail.stop_info || []
    }
  };
}

function isTransitStep(step) {
  const { detail } = getVehicleDetail(step);
  return (
    Number(step.type) === 3 ||
    Boolean(detail.name || detail.line_id || detail.start_name || detail.end_name)
  );
}

function flattenTransitSteps(sourceSteps) {
  return (sourceSteps || []).flatMap((step) => (Array.isArray(step) ? step : [step]));
}

function normalizeBaiduRoute(response, routeIndex = 0) {
  const sourceRoute =
    response && response.result && response.result.routes
      ? response.result.routes[routeIndex]
      : null;
  if (!sourceRoute) throw new Error("百度地图未返回可用路线");

  const sourceSteps = flattenTransitSteps(sourceRoute.steps);
  const segments = sourceSteps.map((step, index) => {
    return isTransitStep(step)
      ? transitSegment(step, index, index)
      : walkingSegment(step, index, index);
  });
  segments.forEach((segment, index) => {
    if (!segment.transit || segment.transit.vehicle !== "SUBWAY") return;
    const previous = segments[index - 1];
    const next = segments[index + 1];
    if (!segment.transit.getOn.accessName && previous && previous.mode === "WALKING") {
      segment.transit.getOn.accessName = extractAccessName(previous.instruction);
    }
    if (!segment.transit.getOff.accessName && next && next.mode === "WALKING") {
      segment.transit.getOff.accessName = extractAccessName(next.instruction);
    }
  });
  const travelModes = [];
  segments.forEach((segment) => {
    const mode = segment.vehicle || segment.mode;
    if (!travelModes.includes(mode)) travelModes.push(mode);
  });
  return {
    distance: Number(sourceRoute.distance) || 0,
    duration: Number(sourceRoute.duration) || 0,
    bounds: sourceRoute.bounds || null,
    polyline: segments.flatMap((segment) => segment.polyline),
    travelModes,
    segments,
    sourceRoute
  };
}

module.exports = {
  cleanStationName,
  extractAccessName,
  normalizeBaiduRoute,
  isTransitStep,
  parsePath,
  stripHtml
};
