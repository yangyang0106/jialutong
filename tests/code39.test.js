const assert = require("node:assert/strict");
const test = require("node:test");

const { buildCode39Bars, normalizeCode39Value } = require("../utils/code39");

test("code39 normalizes bind codes to scanner friendly characters", () => {
  assert.equal(normalizeCode39Value(" ab-12_cd "), "AB12CD");
});

test("code39 builds visible bars for a bind code", () => {
  const bars = buildCode39Bars("ABC123");
  assert.ok(bars.length > 60);
  assert.equal(bars[0].black, true);
  assert.ok(bars.some((item) => !item.black));
  assert.ok(bars.some((item) => item.width > 3));
});
