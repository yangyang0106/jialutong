const assert = require("node:assert/strict");
const test = require("node:test");

const { getRouteById, routes } = require("../data/routes");

const VOICE_MOMENTS = ["enter", "repeat", "near", "arrived", "offRoute"];

test("default demo uses only the fully validated route", () => {
  const route = getRouteById("to-mom");

  assert.equal(Object.keys(routes).length, 1);
  assert.equal(getRouteById("to-home"), undefined);
  assert.equal(route.engineRouteId, "e2e-fuyou-lintao-walk-v5");
  assert.equal(route.origin.name, "富友嘉园");
  assert.equal(route.destination.name, "临洮路地铁站-1口");
  assert.equal(route.steps.length, 18);
});

test("validated demo keeps every photo and five voice moments", () => {
  const route = getRouteById("to-mom");

  route.steps.forEach((step) => {
    assert.ok(step.imageUrl, `第 ${step.stepNo} 步缺少演示图片`);
    VOICE_MOMENTS.forEach((moment) => {
      assert.ok(step.voice[`${moment}VoiceText`], `第 ${step.stepNo} 步缺少 ${moment} 文案`);
      assert.ok(step.voice[`${moment}AudioUrl`], `第 ${step.stepNo} 步缺少 ${moment} 音频`);
    });
  });
});
