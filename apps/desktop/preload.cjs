const {contextBridge, ipcRenderer} = require("electron");

contextBridge.exposeInMainWorld("sovereign", {
  request: async (method, route, body) => {
    const result = await ipcRenderer.invoke("sovereign:request", {method, route, body});
    if (!result?.ok) throw new Error(result?.error || "Request to Sovereign failed");
    return result.payload;
  },
  installUpdate: () => ipcRenderer.invoke("sovereign:install-update"),
  showMessageMenu: (text, selection) => ipcRenderer.send("sovereign:message-context-menu", {text, selection}),
  onUpdate: (callback) => ipcRenderer.on("sovereign:update", (_event, detail) => callback(detail)),
});
