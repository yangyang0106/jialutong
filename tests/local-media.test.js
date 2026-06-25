const assert = require("node:assert/strict");
const test = require("node:test");

delete require.cache[require.resolve("../utils/local-media")];
const {
  isLocalHttpMediaUrl,
  resolveLocalHttpMediaUrl,
  resolveRouteImagesForDisplay
} = require("../utils/local-media");

test("local media resolver only treats localhost http urls as local dev media", () => {
  assert.equal(isLocalHttpMediaUrl("http://127.0.0.1:8090/files/a.jpg"), true);
  assert.equal(isLocalHttpMediaUrl("http://localhost:8090/files/a.jpg"), true);
  assert.equal(isLocalHttpMediaUrl("https://jialutong.cloud/files/a.jpg"), false);
  assert.equal(isLocalHttpMediaUrl("http://example.com/files/a.jpg"), false);
});

test("local media resolver downloads localhost http media to a temp path", async () => {
  global.wx = {
    downloadFile(options) {
      assert.equal(options.url, "http://127.0.0.1:8090/files/a.jpg");
      options.success({ statusCode: 200, tempFilePath: "wxfile://tmp/a.jpg" });
    }
  };

  const resolved = await resolveLocalHttpMediaUrl("http://127.0.0.1:8090/files/a.jpg");
  assert.equal(resolved, "wxfile://tmp/a.jpg");
});

test("route image resolver keeps original imageUrl and adds displayImageUrl", async () => {
  global.wx = {
    downloadFile(options) {
      options.success({ statusCode: 200, tempFilePath: "wxfile://tmp/route.jpg" });
    }
  };

  const route = {
    id: "route-1",
    steps: [
      { id: "step-1", imageUrl: "http://localhost:8090/files/route/1.jpg" },
      { id: "step-2", imageUrl: "https://jialutong.cloud/files/route/2.jpg" }
    ]
  };
  const resolved = await resolveRouteImagesForDisplay(route);

  assert.equal(resolved.steps[0].imageUrl, "http://localhost:8090/files/route/1.jpg");
  assert.equal(resolved.steps[0].displayImageUrl, "wxfile://tmp/route.jpg");
  assert.equal(resolved.steps[1].displayImageUrl, "https://jialutong.cloud/files/route/2.jpg");
});
