const {test} = require("node:test");
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function loadBridge(result) {
  let exposed;
  const source = readFileSync(path.join(__dirname, "../preload.cjs"), "utf8");
  const electron = {
    contextBridge: {exposeInMainWorld: (_name, api) => { exposed = api; }},
    ipcRenderer: {invoke: async () => result, on: () => {}, send: () => {}},
  };
  vm.runInNewContext(source, {
    require: () => electron,
  });
  return exposed;
}

test("preload unwraps successful core API responses", async () => {
  const bridge = loadBridge({ok: true, payload: {version: "8.0.0"}});
  assert.deepEqual(await bridge.request("GET", "/v1/status"), {version: "8.0.0"});
  bridge.showMessageMenu("answer", "selection");
});

test("preload reports the core's error without Electron IPC wrapper text", async () => {
  const bridge = loadBridge({ok: false, error: "computer control is disabled"});
  await assert.rejects(bridge.request("POST", "/v1/computer/run"), {
    message: "computer control is disabled",
  });
});
