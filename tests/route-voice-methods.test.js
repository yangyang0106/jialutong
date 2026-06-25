const assert = require("node:assert/strict");
const test = require("node:test");

const voiceMethods = require("../pages/route/route-voice-methods");

function createPageContext(overrides = {}) {
  return {
    ...voiceMethods,
    data: {
      route: null,
      currentStepIndex: 0,
      currentStep: { stepNo: 1, riskLevel: "LOW" },
      isFinished: false,
      isOffRoute: false,
      isAudioPlaying: false,
      ...overrides.data
    },
    simulatorEnabled: false,
    setData(update) {
      this.data = { ...this.data, ...update };
    },
    refreshLocation() {
      this.refreshed = true;
    },
    ...overrides
  };
}

test("route voice timer methods own their route executor dependencies", () => {
  const page = createPageContext();

  assert.doesNotThrow(() => voiceMethods.resetStepTracking.call(page));
  assert.equal(page.executionState.stepIndex, 0);

  assert.doesNotThrow(() => voiceMethods.startTimers.call(page));
  assert.ok(page.locationTimer);

  voiceMethods.pauseTimers.call(page);
  assert.equal(page.locationTimer, null);
});
