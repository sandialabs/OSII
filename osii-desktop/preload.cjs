'use strict';
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('osiiDesktop', Object.freeze({
  profiles: () => ipcRenderer.invoke('desktop:profiles'),
  chooseFolder: () => ipcRenderer.invoke('desktop:choose-folder'),
  createProfile: fields => ipcRenderer.invoke('desktop:create-profile', fields),
  openProfile: identifier => ipcRenderer.invoke('desktop:open-profile', identifier),
  information: () => ipcRenderer.invoke('desktop:information'),
  diagnostics: () => ipcRenderer.invoke('desktop:diagnostics'),
  onStatus: callback => {
    const listener = (_event, value) => callback(value);
    ipcRenderer.on('desktop:status', listener);
    return () => ipcRenderer.removeListener('desktop:status', listener);
  },
}));
