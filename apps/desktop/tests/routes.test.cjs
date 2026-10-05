const {test} = require("node:test");
const assert = require("node:assert/strict");
const {allowedRoute} = require("../lib/routes.cjs");

test("allows only local core endpoints used by the desktop UI", () => {
  assert.equal(allowedRoute("GET", "/v1/status"), true);
  assert.equal(allowedRoute("POST", "/v1/run"), true);
  assert.equal(allowedRoute("POST", "/v1/settings/computer-control"), true);
  assert.equal(allowedRoute("POST", `/v1/sessions/${"a".repeat(32)}/resume`), true);
  assert.equal(allowedRoute("DELETE", `/v1/sessions/${"a".repeat(32)}`), true);
  assert.equal(allowedRoute("GET", "https://example.com/"), false);
  assert.equal(allowedRoute("GET", "/v1/sessions/../../admin"), false);
  assert.equal(allowedRoute("POST", "/docs"), false);
});
