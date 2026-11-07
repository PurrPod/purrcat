const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('installerApi', {
  getDefaults: () => ipcRenderer.invoke('installer:get-defaults'),
  chooseDirectory: (options) => ipcRenderer.invoke('installer:choose-directory', options),
  validatePath: (target) => ipcRenderer.invoke('installer:validate-path', target),
  validateDataRoot: (target) => ipcRenderer.invoke('installer:validate-data-root', target),
  getDiskSpace: (target) => ipcRenderer.invoke('installer:disk-space', target),
  startInstall: (payload) => ipcRenderer.invoke('installer:start-install', payload),
  testModel: (payload) => ipcRenderer.invoke('installer:test-model', payload),
  saveModel: (payload) => ipcRenderer.invoke('installer:save-model', payload),
  finalize: (payload) => ipcRenderer.invoke('installer:finalize', payload),
  openPath: (target) => ipcRenderer.invoke('installer:open-path', target),
  minimize: () => ipcRenderer.send('installer:minimize'),
  close: () => ipcRenderer.send('installer:close'),
  onInstallEvent: (callback) => {
    const listener = (event, payload) => callback(payload);
    ipcRenderer.on('installer:event', listener);
    return () => ipcRenderer.removeListener('installer:event', listener);
  },
});
