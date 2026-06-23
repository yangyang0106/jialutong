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
  delete require.cache[require.resolve("../utils/route-engine/route-repository")];
  delete require.cache[require.resolve("../utils/elder-route-loader")];
  return require("../utils/elder-route-loader");
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
  const storage = {
    routeStepAssets: {
      "engine-to-mom:1": { voiceText: "旧路线提示", image: "old-image.jpg" }
    }
  };
  let online = true;
  const loader = loadLoader((options) => {
    if (online) {
      options.success({ statusCode: 200, data: publishedRoute() });
      return;
    }
    options.fail(new Error("offline"));
  }, storage);

  const remote = await loader.loadElderRoute("to-mom");
  assert.equal(remote.engineRouteId, "engine-to-mom");
  assert.equal(remote.steps[0].voiceText, "请走到小区门口。");
  const { applyAssetsToRoute } = require("../utils/route-assets");
  assert.equal(applyAssetsToRoute(remote).steps[0].voiceText, "请走到小区门口。");

  online = false;
  const cached = await loader.loadElderRoute("to-mom");
  assert.equal(cached.engineRouteId, "engine-to-mom");
  assert.equal(cached.id, "engine-to-mom");
  assert.equal(cached.slotRouteId, "to-mom");
});
