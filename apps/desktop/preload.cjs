const {contextBridge, ipcRenderer} = require("electron");

contextBridge.exposeInMainWorld("sovereign", {
  request: (method, route, body) => ipcRenderer.invoke("sovereign:request", {method, route, body}),
  installUpdate: () => ipcRenderer.invoke("sovereign:install-update"),
  onUpdate: (callback) => ipcRenderer.on("sovereign:update", (_event, detail) => callback(detail)),
});
