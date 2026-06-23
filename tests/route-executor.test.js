const assert = require("node:assert/strict");
const test = require("node:test");

const {
  createExecutionState,
  processLocation,
  resetForStep,
  simulateLocation
} = require("../utils/route-executor");

const route = {
  steps: [
    {
      stepNo: 1,
      latitude: 31.25,
      longitude: 121.32,
      arriveRadius: 30,
      showDirectionDistance: 30,
      distanceTracking: true,
      riskLevel: "LOW",
      nearVoice: "快到了"
    },
    {
      stepNo: 2,
      latitude: 31.251,
      longitude: 121.321,
      arriveRadius: 30,
      showDirectionDistance: 30,
      distanceTracking: true,
      riskLevel: "HIGH",
      nearVoice: "请停一下"
    }
  ]
};

test("near and arrival events trigger once per step", () => {
  let state = createExecutionState(0);
  let result = processLocation(route, state, { latitude: 31.2504, longitude: 121.3204, accuracy: 5 });
  assert.deepEqual(result.events.map((event) => event.type), ["NEAR"]);
  state = result.state;
  result = processLocation(route, state, { latitude: 31.2504, longitude: 121.3204, accuracy: 5 });
  assert.deepEqual(result.events, []);
  state = result.state;
  result = processLocation(route, state, { latitude: 31.25, longitude: 121.32, accuracy: 5 });
  assert.deepEqual(result.events.map((event) => event.type), ["ARRIVED"]);
  result = processLocation(route, result.state, { latitude: 31.25, longitude: 121.32, accuracy: 5 });
  assert.deepEqual(result.events, []);
});

test("step reset allows near event for the next anchor", () => {
  let state = resetForStep(createExecutionState(0), 1);
  let result = processLocation(route, state, { latitude: 31.251, longitude: 121.321, accuracy: 5 });
  assert.deepEqual(result.events.map((event) => event.type), ["NEAR"]);
  result = processLocation(route, result.state, { latitude: 31.25, longitude: 121.32, accuracy: 5 });
  result = processLocation(route, result.state, { latitude: 31.251, longitude: 121.321, accuracy: 5 });
  assert.deepEqual(result.events.map((event) => event.type), ["ARRIVED"]);
});

test("polyline corridor avoids false off-route on a curved path", () => {
  const curvedRoute = {
    steps: [
      route.steps[0],
      {
        ...route.steps[1],
        pathPolyline: [31.25, 121.32, 31.252, 121.32, 31.251, 121.321]
      }
    ]
  };
  let state = createExecutionState(1);
  const onCurve = { latitude: 31.252, longitude: 121.32, accuracy: 5 };
  let result = processLocation(curvedRoute, state, onCurve, { corridorDistanceMeters: 40 });
  state = result.state;
  result = processLocation(curvedRoute, state, onCurve, { corridorDistanceMeters: 40 });
  assert.equal(result.events.some((event) => event.type === "OFF_ROUTE"), false);
});

test("location failures become unavailable only after confirmation", () => {
  let state = createExecutionState(0);
  let result;
  for (let count = 0; count < 3; count += 1) {
    result = processLocation(route, state, null);
    state = result.state;
  }
  assert.equal(result.status, "LOCATION_UNAVAILABLE");
  assert.deepEqual(result.events.map((event) => event.type), ["LOCATION_UNAVAILABLE"]);
});

test("simulator moves from previous anchor to current anchor", () => {
  const halfway = simulateLocation(route, 1, 0.5);
  assert.ok(halfway.latitude > route.steps[0].latitude);
  assert.ok(halfway.latitude < route.steps[1].latitude);
  const arrived = simulateLocation(route, 1, 1);
  assert.equal(arrived.latitude, route.steps[1].latitude);
  assert.equal(arrived.longitude, route.steps[1].longitude);
});

test("simulator ignores a path that does not end at the current anchor", () => {
  const mismatchedRoute = {
    steps: [
      route.steps[0],
      {
        ...route.steps[1],
        pathPolyline: [31.25, 121.32, 31.26, 121.34]
      }
    ]
  };
  const arrived = simulateLocation(mismatchedRoute, 1, 1);
  assert.equal(arrived.latitude, route.steps[1].latitude);
  assert.equal(arrived.longitude, route.steps[1].longitude);
});

test("off route requires repeated corridor violations", () => {
  let state = createExecutionState(1);
  const farAway = { latitude: 31.26, longitude: 121.34, accuracy: 5 };
  let result = processLocation(route, state, farAway);
  assert.equal(result.events.some((event) => event.type === "OFF_ROUTE"), false);
  state = result.state;
  result = processLocation(route, state, farAway);
  assert.equal(result.events.some((event) => event.type === "OFF_ROUTE"), true);
  result = processLocation(route, result.state, farAway);
  assert.equal(result.events.some((event) => event.type === "OFF_ROUTE"), false);
});
