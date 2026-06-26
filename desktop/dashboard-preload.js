// Preload for the WORKSPACE view (the ClaudeFather web dashboard loaded inside the desktop shell).
// It injects `window.cfDesktop` so the dashboard's own code can detect it's running in the DESKTOP runtime
// (real embedded browser + page capture + co-reading available) vs a plain web browser, and report that to
// the server so the AI/agents know what this user can actually do. Sandbox-safe (contextBridge only).
const { contextBridge } = require('electron');
try {
  contextBridge.exposeInMainWorld('cfDesktop', {
    runtime: 'desktop',
    platform: process.platform,                 // 'darwin' | 'win32' | 'linux'
    electron: process.versions.electron,
    capabilities: ['browser', 'browser-control', 'clip', 'screenshot', 'co-read', 'page-ingest', 'focus']
  });
} catch (e) { /* if exposure fails the dashboard simply treats this as the web runtime */ }
