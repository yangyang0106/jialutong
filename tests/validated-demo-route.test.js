const assert = require("node:assert/strict");
const test = require("node:test");

const { getRouteById, routes } = require("../data/routes");

test("production package does not include a fixed real route", () => {
  assert.equal(Object.keys(routes).length, 0);
  assert.equal(getRouteById("to-mom"), undefined);
  assert.equal(getRouteById("to-home"), undefined);
});
