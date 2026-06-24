const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { adaptRouteForExecution } = require("../utils/elder-route-adapter");
const { createExecutionState, processLocation, resetForStep, simulateLocation } = require("../utils/route-executor");
const { calculateDistance } = require("../utils/geo");

const BASE_URL = process.env.JIALUTONG_BASE_URL || "http://127.0.0.1:8090";
const TOKEN = process.env.JIALUTONG_UPLOAD_TOKEN || "";
const ROUTE_ID = process.env.JIALUTONG_E2E_ROUTE_ID || "e2e-fuyou-lintao-walk";
const REUSE_AUDIO_ROUTE_ID = process.env.JIALUTONG_REUSE_AUDIO_ROUTE_ID || "";
const headers = {
  Authorization: `Bearer ${TOKEN}`,
  "Content-Type": "application/json"
};

if (!TOKEN) {
  throw new Error("请先设置 JIALUTONG_UPLOAD_TOKEN，再运行真实路线 E2E 脚本。");
}

async function jsonRequest(pathname, options = {}) {
  const response = await fetch(`${BASE_URL}${pathname}`, {
    ...options,
    headers: { ...headers, ...(options.headers || {}) }
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`${pathname}: ${JSON.stringify(body)}`);
  return body;
}

async function searchPlace(keyword) {
  const result = await jsonRequest("/api/engine/places/search", {
    method: "POST",
    body: JSON.stringify({ keyword, region: "上海" })
  });
  assert.ok(result.places.length, `找不到地点：${keyword}`);
  return result.places[0];
}

async function uploadAnchorMap(step) {
  const pngBytes = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
    "base64"
  );
  const form = new FormData();
  form.append("routeId", ROUTE_ID);
  form.append("stepNo", String(step.stepNo));
  form.append("kind", "image");
  form.append("file", new Blob([pngBytes], { type: "image/png" }), `anchor-${step.stepNo}.png`);
  const response = await fetch(`${BASE_URL}/api/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${TOKEN}` },
    body: form
  });
  const body = await response.json();
  if (!response.ok) throw new Error(`上传锚点图失败：${JSON.stringify(body)}`);
  return body.url;
}

async function main() {
  const originSearch = await jsonRequest("/api/engine/places/search", {
    method: "POST",
    body: JSON.stringify({ keyword: "富友嘉园一期", region: "上海" })
  });
  const origin = originSearch.places.find((place) => place.name === "富友嘉园") || originSearch.places[0];
  const destinationSearch = await jsonRequest("/api/engine/places/search", {
    method: "POST",
    body: JSON.stringify({ keyword: "临洮路地铁站-1口", region: "上海" })
  });
  const destination =
    destinationSearch.places.find((place) => place.name.includes("1口")) ||
    (await searchPlace("临洮路站"));

  const plan = await jsonRequest("/api/engine/route-plans", {
    method: "POST",
    body: JSON.stringify({
      mode: "WALKING",
      origin: { latitude: origin.latitude, longitude: origin.longitude },
      destination: { latitude: destination.latitude, longitude: destination.longitude }
    })
  });
  const existing = await jsonRequest("/api/engine/routes");
  const previous = existing.routes.find((item) => item.id === ROUTE_ID);
  if (previous && previous.status !== "PUBLISHED") {
    await jsonRequest(`/api/engine/routes/${ROUTE_ID}`, { method: "DELETE" });
  }
  if (previous && previous.status === "PUBLISHED") {
    throw new Error("同名端到端测试路线已经发布，请先更换 ROUTE_ID");
  }

  let saved = await jsonRequest("/api/engine/routes/from-baidu", {
    method: "POST",
    body: JSON.stringify({
      id: ROUTE_ID,
      name: "测试：富友嘉园到临洮路站",
      elderSlot: "TO_MOM",
      origin,
      destination,
      planResponse: plan,
      routeIndex: 0
    })
  });

  const reusable = existing.routes.find((item) => item.id === REUSE_AUDIO_ROUTE_ID);
  if (reusable && reusable.steps.length === saved.steps.length) {
    saved.steps.forEach((step, index) => {
      const sourceStep = reusable.steps[index];
      if (sourceStep.type === step.type) step.voice = sourceStep.voice;
    });
    saved = await jsonRequest(`/api/engine/routes/${ROUTE_ID}`, {
      method: "PUT",
      body: JSON.stringify(saved)
    });
  }

  for (const step of saved.steps) {
    const imageUrl = await uploadAnchorMap(step);
    saved = await jsonRequest(`/api/engine/routes/${ROUTE_ID}/steps/${step.id}/review`, {
      method: "PUT",
      body: JSON.stringify({
        reviewStatus: "APPROVED",
        reviewNote: "端到端测试：坐标地图图，不代表家属实景照片",
        imageUrl,
        imageStatus: "FAMILY",
        landmarkHint: step.landmarkHint || (step.riskLevel === "HIGH" ? "请家属现场确认的明显地标" : "")
      })
    });
  }

  const moments = ["enter", "repeat", "near", "arrived", "offRoute"];
  for (const step of saved.steps) {
    for (const moment of moments) {
      const text = step.voice[`${moment}VoiceText`];
      if (step.voice[`${moment}AudioUrl`]) continue;
      saved = await jsonRequest(`/api/engine/routes/${ROUTE_ID}/steps/${step.id}/tts`, {
        method: "POST",
        body: JSON.stringify({ moment, text })
      });
    }
  }

  const published = await jsonRequest(`/api/engine/routes/${ROUTE_ID}/publish`, { method: "POST" });
  const executionRoute = adaptRouteForExecution(published, published.elderSlot);
  const execution = [];
  for (let index = 0; index < executionRoute.steps.length; index += 1) {
    let state = resetForStep(createExecutionState(index), index);
    state = processLocation(executionRoute, state, simulateLocation(executionRoute, index, 0)).state;
    const near = processLocation(executionRoute, state, simulateLocation(executionRoute, index, 0.8));
    state = near.state;
    const arrived = processLocation(executionRoute, state, simulateLocation(executionRoute, index, 1));
    execution.push({
      stepNo: executionRoute.steps[index].stepNo,
      type: executionRoute.steps[index].type,
      nearEvents: near.events.map((event) => event.type),
      arrivedEvents: arrived.events.map((event) => event.type)
    });
  }

  const trackedIndex = executionRoute.steps.findIndex((step, index) => index > 0 && step.distanceTracking);
  let offRouteEvents = [];
  if (trackedIndex > 0) {
    let state = createExecutionState(trackedIndex);
    const target = executionRoute.steps[trackedIndex];
    const far = { latitude: target.latitude + 0.01, longitude: target.longitude + 0.01, accuracy: 5 };
    let result = processLocation(executionRoute, state, far);
    result = processLocation(executionRoute, result.state, far);
    offRouteEvents = result.events.map((event) => event.type);
  }

  for (const stepResult of ["FOUND", "NOT_FOUND", "HELP"]) {
    await jsonRequest("/api/engine/trip-results", {
      method: "POST",
      body: JSON.stringify({
        tripId: `${ROUTE_ID}-test-trip`,
        routeId: ROUTE_ID,
        stepId: executionRoute.steps[0].engineStepId,
        stepNo: 1,
        stepResult,
        helpReason: stepResult === "HELP" ? "E2E_TEST" : ""
      })
    });
  }
  const tripSummary = await jsonRequest(`/api/engine/routes/${ROUTE_ID}/trip-summary`);

  const latest = await jsonRequest(`/api/engine/routes/${ROUTE_ID}`);
  const anchorGaps = latest.steps.slice(1).map((step, index) => {
    const previous = latest.steps[index];
    return calculateDistance(
      previous.location.latitude,
      previous.location.longitude,
      step.location.latitude,
      step.location.longitude
    );
  });
  const report = {
    routeId: ROUTE_ID,
    status: latest.status,
    origin: latest.origin,
    destination: latest.destination,
    distance: latest.distance,
    estimatedDuration: latest.estimatedDuration,
    stepCount: latest.steps.length,
    highRiskSteps: latest.steps.filter((step) => step.riskLevel === "HIGH").length,
    imagesReady: latest.steps.filter((step) => step.imageUrl).length,
    fiveVoiceTextsReady: latest.steps.filter((step) =>
      moments.every((moment) => step.voice[`${moment}VoiceText`])
    ).length,
    fiveAudioUrlsReady: latest.steps.filter((step) =>
      moments.every((moment) => step.voice[`${moment}AudioUrl`])
    ).length,
    maxAnchorGap: Math.max(...anchorGaps),
    closeAnchorRadii: latest.steps
      .filter((step) => step.arriveRadius < 30)
      .map((step) => ({ stepNo: step.stepNo, arriveRadius: step.arriveRadius })),
    stepTypes: latest.steps.map((step) => step.type),
    execution,
    offRouteEvents,
    tripSummary: tripSummary.summary,
    safetyNote: "测试图片是坐标静态地图，不是家属实景照片，不能用于真实老人出行。"
  };
  const reportPath = path.resolve(__dirname, "../../docs/真实路线端到端测试结果.json");
  fs.writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
