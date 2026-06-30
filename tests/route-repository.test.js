const assert = require("node:assert/strict");
const test = require("node:test");

const uploadConfig = require("../config/upload");
uploadConfig.apiBaseUrl = "https://route.example.com";

function loadRepositoryWithMock(responder, storage = null) {
  global.wx = {
    getStorageSync(key) {
      return storage && storage[key] || null;
    },
    request(options) {
      responder(options);
    }
  };
  delete require.cache[require.resolve("../utils/auth")];
  delete require.cache[require.resolve("../utils/route-api")];
  return require("../utils/route-api");
}

test("route repository does not use upload token as an auth fallback", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: options.data });
  });
  const route = { id: "route-1", steps: [] };
  const response = await repository.saveRouteDraft(route);
  assert.deepEqual(response, route);
  assert.equal(calls[0].url, "https://route.example.com/api/engine/routes");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].header, {});
});

test("route repository uses the family session token after login", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock(
    (options) => {
      calls.push(options);
      options.success({ statusCode: 200, data: options.data });
    },
    {
      jialutong_family_auth: {
        token: "session-token",
        user: { id: "user-1" }
      }
    }
  );
  await repository.saveRouteDraft({ id: "route-1", steps: [] });
  assert.equal(calls[0].header.Authorization, "Bearer session-token");
});

test("route repository requests route planning from the server", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { status: 0, result: { routes: [] } } });
  });
  await repository.createRoutePlan({
    mode: "WALKING",
    origin: { latitude: 31.25, longitude: 121.32 },
    destination: { latitude: 31.3, longitude: 121.45 }
  });
  assert.match(calls[0].url, /api\/engine\/route-plans$/);
  assert.equal(calls[0].method, "POST");
});

test("route repository creates route drafts from Baidu response on the server", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { id: options.data.id, steps: [] } });
  });
  const response = await repository.createRouteDraftFromBaidu({
    id: "route-1",
    name: "测试路线",
    elderSlot: "TO_MOM",
    origin: { name: "起点", latitude: 31.25, longitude: 121.32 },
    destination: { name: "终点", latitude: 31.3, longitude: 121.45 },
    planResponse: { result: { routes: [] } },
    routeIndex: 0
  });
  assert.equal(response.id, "route-1");
  assert.match(calls[0].url, /api\/engine\/routes\/from-baidu$/);
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].data.name, "测试路线");
  assert.deepEqual(calls[0].data.planResponse, { result: { routes: [] } });
});

test("route repository requests structured route advice from the server", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({
      statusCode: 200,
      data: { recommendedPlanIndex: 0, risks: [] }
    });
  });
  const response = await repository.adviseRoutePlans({
    originName: "富友嘉园一期",
    destinationName: "星荟中心",
    plans: [{ index: 0, distance: 1000 }]
  });
  assert.equal(response.recommendedPlanIndex, 0);
  assert.match(calls[0].url, /api\/engine\/routes\/advise$/);
  assert.equal(calls[0].method, "POST");
});

test("route repository asks server to summarize Baidu plans", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({
      statusCode: 200,
      data: { plans: [{ index: 0, decisionPointCount: 3 }] }
    });
  });
  const response = await repository.summarizeRoutePlansFromBaidu({
    origin: { name: "起点", latitude: 31.25, longitude: 121.32 },
    destination: { name: "终点", latitude: 31.3, longitude: 121.45 },
    planResponse: { result: { routes: [] } }
  });
  assert.equal(response.plans[0].decisionPointCount, 3);
  assert.match(calls[0].url, /api\/engine\/routes\/plan-summaries$/);
  assert.equal(calls[0].method, "POST");
});

test("route repository searches places through the server", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({
      statusCode: 200,
      data: { places: [{ name: "富友嘉园一期", latitude: 31.25, longitude: 121.32 }] }
    });
  });
  const result = await repository.searchPlaces("富友嘉园一期");
  assert.equal(result.places[0].name, "富友嘉园一期");
  assert.match(calls[0].url, /api\/engine\/places\/search$/);
  assert.deepEqual(calls[0].data, { keyword: "富友嘉园一期", region: "上海" });
});

test("route repository reverse geocodes the current location", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({
      statusCode: 200,
      data: {
        place: {
          name: "星荟中心一座",
          address: "上海市虹口区四川北路",
          latitude: 31.246,
          longitude: 121.487
        }
      }
    });
  });
  const result = await repository.reverseGeocode({ latitude: 31.246, longitude: 121.487 });
  assert.equal(result.place.name, "星荟中心一座");
  assert.match(calls[0].url, /api\/engine\/places\/reverse-geocode$/);
});

test("route repository sends family review and publishes", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { status: "PUBLISHED" } });
  });
  await repository.reviewRouteStep("route-1", "step-1", {
    reviewStatus: "APPROVED",
    imageStatus: "FAMILY"
  });
  const published = await repository.publishRouteDraft("route-1");
  assert.equal(published.status, "PUBLISHED");
  assert.equal(calls[0].method, "PUT");
  assert.match(calls[0].url, /steps\/step-1\/review$/);
  assert.match(calls[1].url, /route-1\/publish$/);
});

test("route repository deletes a route draft", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { deleted: true } });
  });
  const result = await repository.deleteRouteDraft("route-1");
  assert.equal(result.deleted, true);
  assert.equal(calls[0].method, "DELETE");
  assert.match(calls[0].url, /api\/engine\/routes\/route-1$/);
});

test("route repository requests generated TTS for a step", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { id: "route-1" } });
  });
  await repository.generateStepTts("route-1", "step-1", "请从这里出发。");
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].data, { moment: "enter", text: "请从这里出发。" });
  assert.match(calls[0].url, /route-1\/steps\/step-1\/tts$/);
});

test("route repository requests AI voice suggestions", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { generated: true, route: { id: "route-1" } } });
  });
  await repository.generateRouteAiVoices("route-1");
  assert.equal(calls[0].method, "POST");
  assert.match(calls[0].url, /route-1\/ai-generate-voices$/);
});

test("route repository requests batch TTS with regeneration choice", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { route: { id: "route-1" }, steps: [] } });
  });
  await repository.generateRouteTtsBatch("route-1", true);
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].data, { regenerateTts: true });
  assert.match(calls[0].url, /route-1\/tts\/batch$/);
});

test("route repository requests AI collection plan", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { summary: "采集清单", photoTasks: [] } });
  });
  const result = await repository.generateCollectionPlan("route-1");
  assert.equal(result.summary, "采集清单");
  assert.equal(calls[0].method, "POST");
  assert.match(calls[0].url, /route-1\/collection-plan$/);
});

test("route repository requests route review center and trip analysis", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { routeId: "route-1", problemSteps: [] } });
  });
  await repository.getRouteReviewCenter("route-1");
  await repository.analyzeRouteTrip("route-1");
  assert.equal(calls[0].method, "GET");
  assert.match(calls[0].url, /route-1\/review-center$/);
  assert.equal(calls[1].method, "POST");
  assert.match(calls[1].url, /route-1\/trip-analysis$/);
});

test("route repository requests rule based photo review", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { photoReview: { status: "PASS" } } });
  });
  await repository.reviewStepPhoto("route-1", "step-1", "https://files.example.com/a.jpg", "FAMILY", 1000);
  assert.equal(calls[0].method, "POST");
  assert.deepEqual(calls[0].data, {
    imageUrl: "https://files.example.com/a.jpg",
    imageStatus: "FAMILY",
    fileSize: 1000
  });
  assert.match(calls[0].url, /route-1\/steps\/step-1\/photo-review$/);
});

test("route repository records trip results", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: options.data });
  });
  await repository.recordStepExecution({
    tripId: "trip-1",
    routeId: "route-1",
    stepId: "step-1",
    stepNo: 1,
    stepResult: "FOUND"
  });
  assert.match(calls[0].url, /api\/engine\/trip-results$/);
  assert.equal(calls[0].data.stepResult, "FOUND");
});



test("route repository lists and resolves help events", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { events: [] } });
  });
  await repository.listRouteHelpEvents("route-1");
  assert.equal(calls[0].method, "GET");
  assert.match(calls[0].url, /api\/engine\/routes\/route-1\/help-events$/);

  calls.length = 0;
  await repository.updateRouteHelpEvent("route-1", "event-1", "RESOLVED", "已处理");
  assert.equal(calls[0].method, "PUT");
  assert.match(calls[0].url, /api\/engine\/routes\/route-1\/help-events\/event-1$/);
  assert.deepEqual(calls[0].data, { helpStatus: "RESOLVED", handledNote: "已处理" });
});

test("route repository lists arrival events", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({ statusCode: 200, data: { events: [] } });
  });
  await repository.listRouteArrivalEvents("route-1");
  assert.equal(calls[0].method, "GET");
  assert.match(calls[0].url, /api\/engine\/routes\/route-1\/arrival-events$/);

  calls.length = 0;
  await repository.listFamilyArrivalEvents("NOTIFIED");
  assert.equal(calls[0].method, "GET");
  assert.match(calls[0].url, /api\/engine\/arrival-events\?status=NOTIFIED$/);

  calls.length = 0;
  await repository.updateRouteArrivalEvent("route-1", "event-1", "ACKNOWLEDGED", "已看到");
  assert.equal(calls[0].method, "PUT");
  assert.match(calls[0].url, /api\/engine\/routes\/route-1\/arrival-events\/event-1$/);
  assert.deepEqual(calls[0].data, {
    arrivalStatus: "ACKNOWLEDGED",
    acknowledgedNote: "已看到"
  });
});


test("route repository lists published routes for elderly home slots", async () => {
  const calls = [];
  const repository = loadRepositoryWithMock((options) => {
    calls.push(options);
    options.success({
      statusCode: 200,
      data: { routes: [{ id: "published-route", elderSlot: "TO_MOM", status: "PUBLISHED" }] }
    });
  });
  const result = await repository.listRouteDrafts("PUBLISHED");
  assert.equal(result.routes[0].id, "published-route");
  assert.match(calls[0].url, /api\/engine\/routes\?status=PUBLISHED$/);
  assert.equal(calls[0].method, "GET");
});

test("route repository returns readable server errors", async () => {
  const repository = loadRepositoryWithMock((options) => {
    options.success({
      statusCode: 409,
      data: { detail: { message: "route is not ready" } }
    });
  });
  await assert.rejects(() => repository.publishRouteDraft("route-1"), /route is not ready/);
});

test("route repository explains local service connection failures", async () => {
  uploadConfig.apiBaseUrl = "http://127.0.0.1:8090";
  const repository = loadRepositoryWithMock((options) => {
    options.fail({ errMsg: "request:fail url not in domain list" });
  });
  await assert.rejects(
    () => repository.searchPlaces("富友嘉园一期"),
    /无法连接本地路线服务/
  );
});
