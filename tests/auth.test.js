const assert = require("node:assert/strict");
const test = require("node:test");

function loadAuthWithStorage(storage, responder = null) {
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
    request(options) {
      if (responder) responder(options);
    }
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

test("auth helper reads and saves emergency contact through account service", async () => {
  const calls = [];
  const auth = loadAuthWithStorage(
    {
      jialutong_family_auth: {
        token: "session-token",
        user: { id: "user-1", role: "FAMILY_ADMIN" }
      }
    },
    (options) => {
      calls.push(options);
      options.success({
        statusCode: 200,
        data: options.method === "PUT"
          ? { name: options.data.name, relation: options.data.relation, phone: options.data.phone }
          : { name: "小王", relation: "女儿", phone: "13800000000" }
      });
    }
  );

  const contact = await auth.getEmergencyContact();
  assert.equal(contact.phone, "13800000000");
  const saved = await auth.saveEmergencyContact({
    name: "小李",
    relation: "儿子",
    phone: "13900000000"
  });
  assert.equal(saved.name, "小李");
  assert.match(calls[0].url, /api\/auth\/emergency-contact$/);
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].header.Authorization, "Bearer session-token");
  assert.match(calls[1].url, /api\/auth\/emergency-contact$/);
  assert.equal(calls[1].method, "PUT");
  assert.deepEqual(calls[1].data, {
    name: "小李",
    relation: "儿子",
    phone: "13900000000"
  });
});
