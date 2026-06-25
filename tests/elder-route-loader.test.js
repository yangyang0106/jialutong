const assert = require("node:assert/strict");
const test = require("node:test");

const uploadConfig = require("../config/upload");
uploadConfig.apiBaseUrl = "https://route.example.com";

function loadLoader(requestHandler, storage = {}) {
  global.wx = {
    getStorageSync(key) {
      return storage[key];
    },
    setStorageSync(key, value) {
      storage[key] = value;
    },
    request: requestHandler
  };
  delete require.cache[require.resolve("../utils/route-api")];
  delete require.cache[require.resolve("../utils/elder-route-slots")];
  delete require.cache[require.resolve("../utils/elder-route-loader")];
  return {
    loader: require("../utils/elder-route-loader"),
    repository: require("../utils/route-api")
  };
}

function publishedRoute() {
  return {
    id: "engine-to-mom",
    name: "去妈妈家",
    elderSlot: "TO_MOM",
    status: "PUBLISHED",
    steps: [
      {
        id: "step-1",
        stepNo: 1,
        type: "START",
        title: "从家出发",
        shortAction: "走到小区门口",
        location: { latitude: 31.25, longitude: 121.32 },
        voice: { enterVoice: "请走到小区门口。" }
      }
    ]
  };
}

test("elder route loader caches a published route and uses it when offline", async () => {
  const storage = {};
  let online = true;
  const { loader } = loadLoader((options) => {
    if (online) {
      options.success({ statusCode: 200, data: { routes: [publishedRoute()] } });
      return;
    }
    options.fail(new Error("offline"));
  }, storage);

  const remote = await loader.loadElderRouteSlot("TO_MOM");
  assert.equal(remote.engineRouteId, "engine-to-mom");
  assert.equal(remote.steps[0].voiceText, "请走到小区门口。");

  online = false;
  const cached = await loader.loadElderRouteSlot("TO_MOM");
  assert.equal(cached.engineRouteId, "engine-to-mom");
  assert.equal(cached.id, "engine-to-mom");
  assert.equal(cached.slotRouteId, "TO_MOM");
});

test("elder route loader rejects a slot when a real route id is required", async () => {
  const { loader } = loadLoader((options) => {
    options.success({ statusCode: 200, data: publishedRoute() });
  });
  await assert.rejects(() => loader.loadElderRoute("TO_MOM"), /真实路线 ID/);
});

test("review detail and execution loader use the same engine route id", async () => {
  const calls = [];
  const { loader, repository } = loadLoader((options) => {
    calls.push(options.url);
    options.success({ statusCode: 200, data: publishedRoute() });
  });

  const reviewRoute = await repository.getRouteDraft("engine-to-mom");
  const executionRoute = await loader.loadElderRoute("engine-to-mom");

  assert.equal(reviewRoute.id, "engine-to-mom");
  assert.equal(executionRoute.id, "engine-to-mom");
  assert.deepEqual(calls, [
    "https://route.example.com/api/engine/routes/engine-to-mom",
    "https://route.example.com/api/engine/routes/engine-to-mom"
  ]);
});
