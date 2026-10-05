const {app, BrowserWindow, ipcMain} = require("electron");
const {spawn} = require("node:child_process");
const {randomBytes} = require("node:crypto");
const {existsSync, writeFileSync} = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const {allowedRoute} = require("./lib/routes.cjs");

let core = null;
let port = null;
let token = null;
let window = null;
let updateReady = false;
let coreError = null;

async function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const selected = server.address().port;
      server.close(() => resolve(selected));
    });
  });
}

function coreCommand() {
  if (app.isPackaged) {
    const binary = path.join(process.resourcesPath, "core", process.platform === "win32" ? "sovereign-core.exe" : "sovereign-core");
    if (!existsSync(binary)) throw new Error(`Missing bundled Python core: ${binary}`);
    return {command: binary, args: []};
  }
  const root = path.resolve(__dirname, "../..");
  const binary = process.env.SOVEREIGN_PYTHON || path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  return {command: binary, args: ["-m", "sovereign"]};
}

async function startCore() {
  port = await availablePort();
  token = randomBytes(32).toString("hex");
  const {command, args} = coreCommand();
  core = spawn(command, [...args, "serve", "--host", "127.0.0.1", "--port", String(port)], {
    env: {...process.env, SOVEREIGN_API_TOKEN: token},
    windowsHide: true,
    stdio: "ignore",
  });
  core.once("error", (error) => { coreError = error; });
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (coreError) throw coreError;
    if (core.exitCode !== null) throw new Error(`Python core exited with code ${core.exitCode}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, {
        headers: {authorization: `Bearer ${token}`}, signal: AbortSignal.timeout(1500),
      });
      if (response.ok) return;
    } catch (_) {
      // Wait for the core to start listening.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("Python core did not become ready within 30 seconds");
}

async function apiRequest(_event, {method, route, body}) {
  try {
    if (typeof method !== "string" || typeof route !== "string" || !allowedRoute(method, route)) {
      return {ok: false, error: "API route is not allowed"};
    }
    const serialized = body === undefined ? undefined : JSON.stringify(body);
    if (serialized && serialized.length > 1_000_000) return {ok: false, error: "Request is too large"};
    const response = await fetch(`http://127.0.0.1:${port}${route}`, {
      method,
      headers: {authorization: `Bearer ${token}`, "content-type": "application/json"},
      body: serialized,
      signal: AbortSignal.timeout(900000),
    });
    const text = await response.text();
    let payload = null;
    try { payload = text ? JSON.parse(text) : null; } catch (_) { payload = text; }
    if (!response.ok) return {ok: false, error: payload?.detail || `HTTP ${response.status}`};
    return {ok: true, payload};
  } catch (error) {
    return {ok: false, error: error?.message || "Request to Sovereign failed"};
  }
}

function createWindow() {
  const snapshot = process.env.SOVEREIGN_UI_SNAPSHOT;
  window = new BrowserWindow({
    width: 1100, height: 760, minWidth: 750, minHeight: 520,
    title: "Sovereign",
    backgroundColor: "#111827",
    show: !snapshot,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(() => ({action: "deny"}));
  window.webContents.on("will-navigate", (event) => event.preventDefault());
  window.loadFile(path.join(__dirname, "renderer", "index.html"));
  if (snapshot) {
    window.webContents.once("did-finish-load", async () => {
      await new Promise((resolve) => setTimeout(resolve, 1500));
      const image = await window.webContents.capturePage();
      writeFileSync(snapshot, image.toPNG());
      app.quit();
    });
  }
}

async function checkUpdates() {
  if (!app.isPackaged) return;
  const {autoUpdater} = require("electron-updater");
  autoUpdater.autoDownload = false;
  autoUpdater.on("update-available", (info) => {
    updateReady = true;
    window?.webContents.send("sovereign:update", {available: true, version: info.version});
  });
  autoUpdater.on("error", (error) => {
    window?.webContents.send("sovereign:update", {available: false, error: error.message});
  });
  await autoUpdater.checkForUpdates();
}

app.whenReady().then(async () => {
  ipcMain.handle("sovereign:request", apiRequest);
  ipcMain.handle("sovereign:install-update", async () => {
    if (!updateReady) throw new Error("No update is available");
    const {autoUpdater} = require("electron-updater");
    await autoUpdater.downloadUpdate();
    autoUpdater.quitAndInstall();
  });
  try {
    await startCore();
    createWindow();
    setTimeout(() => void checkUpdates().catch(() => {}), 5000);
  } catch (error) {
    const {dialog} = require("electron");
    dialog.showErrorBox("Sovereign could not start", error.message);
    app.quit();
  }
});

app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0 && port) createWindow(); });
app.on("before-quit", () => { if (core && core.exitCode === null) core.kill(); });
