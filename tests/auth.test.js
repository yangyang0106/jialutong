const assert = require("node:assert/strict");
const test = require("node:test");

function loadAuthWithStorage(storage) {
  global.wx = {
    getStorageSync(key) {
      return storage[key] || null;
    },
    setStorageSync(key, value) {
      storage[key] = value;
    },
    removeStorageSync(key) {
      delete storage[key];
    },
    request() {}
  };
  delete require.cache[require.resolve("../utils/auth")];
  return require("../utils/auth");
}

test("auth helper recognizes family admin", () => {
  const auth = loadAuthWithStorage({
    jialutong_family_auth: {
      token: "session-token",
      user: { id: "user-1", role: "FAMILY_ADMIN" }
    }
  });
  assert.equal(auth.isFamilyLoggedIn(), true);
  assert.equal(auth.isFamilyAdmin(), true);
});

test("auth helper does not treat ordinary members as admin", () => {
  const auth = loadAuthWithStorage({
    jialutong_family_auth: {
      token: "session-token",
      user: { id: "user-2", role: "FAMILY_MEMBER" }
    }
  });
  assert.equal(auth.isFamilyLoggedIn(), true);
  assert.equal(auth.isFamilyAdmin(), false);
});


test("auth helper recognizes test super admin", () => {
  const auth = loadAuthWithStorage({
    jialutong_family_auth: {
      token: "session-token",
      user: { id: "user-super", role: "SUPER_ADMIN" }
    }
  });
  assert.equal(auth.isFamilyLoggedIn(), true);
  assert.equal(auth.isFamilyAdmin(), true);
});
