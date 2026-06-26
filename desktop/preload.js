// Preload for the chrome window (the tab bar / address bar HTML).
// Exposes a tiny, explicit IPC surface to the renderer via contextBridge — no node, no remote.
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('cf', {
  // --- config ---
  getConfig: () => ipcRenderer.invoke('config:get'),
  setConfig: (serverUrl, authToken) => ipcRenderer.invoke('config:set', { serverUrl, authToken }),

  // --- capture (the AI vision toggle) ---
  setCapture: (enabled) => ipcRenderer.invoke('capture:set', { enabled }),
  captureNow: () => ipcRenderer.invoke('capture:now'),

  // --- tabs ---
  createTab: (type, url) => ipcRenderer.invoke('tabs:create', { type, url }),
  activateTab: (id) => ipcRenderer.invoke('tabs:activate', { id }),
  closeTab: (id) => ipcRenderer.invoke('tabs:close', { id }),

  // --- navigation ---
  navigate: (id, url) => ipcRenderer.invoke('tab:navigate', { id, url }),
  back: (id) => ipcRenderer.invoke('tab:back', { id }),
  forward: (id) => ipcRenderer.invoke('tab:forward', { id }),
  reload: (id) => ipcRenderer.invoke('tab:reload', { id }),
  stop: (id) => ipcRenderer.invoke('tab:stop', { id }),
  home: (id) => ipcRenderer.invoke('tab:home', { id }),

  // --- overlay (modal) coordination: tells main to hide/show content views ---
  setOverlay: (open) => ipcRenderer.invoke('overlay:set', { open }),

  // --- events main -> renderer ---
  onTabs: (cb) => ipcRenderer.on('tabs:state', (_e, data) => cb(data)),
  onConfig: (cb) => ipcRenderer.on('config:state', (_e, data) => cb(data)),
  onCaptureEvent: (cb) => ipcRenderer.on('capture:event', (_e, data) => cb(data))
});
