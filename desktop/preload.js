const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('udrDesktop', {
  selectDirectory: () => ipcRenderer.invoke('select-directory'),
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  isDesktop: true,
})
