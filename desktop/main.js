// ClaudeFather Desktop — Electron main process.
//
// WHAT THIS IS
//   A thin desktop SHELL around two things:
//     1. "Workspace" — your EXISTING ClaudeFather web dashboard, loaded from a URL you configure
//        (e.g. https://studio.tailnet.ts.net:8443 or http://localhost:8799). We do NOT fork or modify
//        the dashboard; we just point a real browser engine at it.
//     2. "Browser"  — a real Chromium browsing surface (the open internet), which a normal web page
//        cannot embed (X-Frame-Options / CSP / same-origin all block iframes + content reads). A desktop
//        Electron view can — full sites AND full content access.
//
//   THE CONTEXT BRIDGE (the whole point): when a Browser tab finishes navigating AND the user has
//   flipped capture ON, we read {url, title, text} from the page and POST it to the user's OWN configured
//   ClaudeFather server (/api/focus-report + /api/context/ingest-page). Nothing is sent anywhere else,
//   ever. Capture defaults OFF; the portal is the consented surface.
//
// WHY WebContentsView (NOT <webview>, NOT the deprecated BrowserView)
//   The task says "webview or BrowserView (justify — BrowserView gives best content access + control)".
//   We use **WebContentsView**, which is the modern, supported successor to BrowserView (BrowserView is
//   deprecated as of Electron 30). It keeps every reason BrowserView was the right call over <webview>:
//     - Out-of-process, native-composited content (no in-DOM <webview> quirks / lifecycle bugs).
//     - The main process holds the `webContents` directly, so we get clean, reliable navigation events
//       and `executeJavaScript` for content capture — i.e. best content access + control.
//     - Each tab gets its own view with its own webPreferences + session partition (isolation).
//   The chrome (tab bar + address bar) is plain HTML in the window's own webContents; content views are
//   positioned BELOW it, so the chrome strip always shows through.

'use strict';

const { app, BrowserWindow, WebContentsView, ipcMain, session, net, shell, dialog, globalShortcut } = require('electron');
const path = require('path');
const fs = require('fs');

// ---------------------------------------------------------------------------------------------------
// Config — persisted as a small JSON in Electron's per-user userData dir. NEVER hardcode a server URL.
//   { serverUrl: string, authToken: string, captureEnabled: boolean }
// authToken (optional) is the dashboard's auth_token: it doubles as the `cc_auth` cookie value AND the
// `X-CC-Token` header the server accepts — so one value authenticates both the Workspace view and the
// bridge POSTs.
// ---------------------------------------------------------------------------------------------------
const CONFIG_PATH = () => path.join(app.getPath('userData'), 'config.json');
// agentControlEnabled gates the WRITE actions an agent can take (click/type). Default OFF: "show-me"
// actions (open/scroll/highlight/screenshot/nav) always run, but click/type are refused until you opt in.
const DEFAULT_CONFIG = { serverUrl: '', authToken: '', captureEnabled: false, agentControlEnabled: false };

function loadConfig() {
  try {
    const raw = fs.readFileSync(CONFIG_PATH(), 'utf8');
    return Object.assign({}, DEFAULT_CONFIG, JSON.parse(raw));
  } catch (_) {
    return Object.assign({}, DEFAULT_CONFIG);
  }
}
function saveConfig(cfg) {
  try {
    fs.mkdirSync(app.getPath('userData'), { recursive: true });
    // 0600: the file may hold the auth token; keep it owner-only (matches ClaudeFather's secret-file hygiene).
    fs.writeFileSync(CONFIG_PATH(), JSON.stringify(cfg, null, 2), { mode: 0o600 });
    try { fs.chmodSync(CONFIG_PATH(), 0o600); } catch (_) {}
  } catch (e) {
    console.error('[config] save failed:', e.message);
  }
}

let config = Object.assign({}, DEFAULT_CONFIG);

// ---------------------------------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------------------------------
const CHROME_HEIGHT = 84;          // px reserved at the top of the window for the HTML chrome (tabs + toolbar)
const MAX_TEXT = 8000;             // truncate captured page text to ~8k chars (attention budget; privacy)
const CAPTURE_DEBOUNCE_MS = 700;   // collapse rapid navigation events into one capture
const INTEL_DEBOUNCE_MS = 900;     // collapse rapid navigation events into one co-reading intel fetch
const SIDEBAR_WIDTH = 340;         // px reserved on the right for the co-reading panel when it's open

// One shared snippet that reads {title, text} from a page in its OWN context — text only, no DOM mutation,
// no screenshots. Used by capture (the always-on bridge), the explicit Clip/Save flow, and co-reading.
const PAGE_READ_JS =
  `(function(){
     try {
       var t = (document.body && document.body.innerText) ? document.body.innerText : '';
       return { title: document.title || '', text: t.slice(0, ${MAX_TEXT}) };
     } catch (e) { return { title: document.title || '', text: '' }; }
   })()`;

let win = null;                    // the BrowserWindow (its webContents renders the chrome HTML)
let overlayOpen = false;           // when the renderer shows a full-window modal we hide content views
let sidebarOpen = false;           // co-reading side panel (off by default; explicit user opt-in)
let tabs = [];                     // [{ id, type:'workspace'|'browser', view, title, url, _debounce, _intelDebounce }]
let activeTabId = null;
let nextId = 1;

// ---------------------------------------------------------------------------------------------------
// Sensitive-page heuristic — best-effort: never capture obvious credential pages.
// ---------------------------------------------------------------------------------------------------
const SECRET_HOSTS = [
  '1password.com', 'lastpass.com', 'bitwarden.com', 'dashlane.com', 'keepersecurity.com',
  'nordpass.com', 'protonpass.com', 'roboform.com', 'enpass.io', 'keepassxc.org'
];
function isSensitive(url) {
  let u;
  try { u = new URL(url); } catch (_) { return true; }            // unparseable -> treat as sensitive (skip)
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return true; // file:, data:, about:, chrome: -> skip
  const host = (u.hostname || '').toLowerCase();
  if (SECRET_HOSTS.some(h => host === h || host.endsWith('.' + h))) return true;
  const hay = (host + ' ' + (u.pathname || '')).toLowerCase();
  if (/(^|[^a-z])(login|signin|sign-in|logon|password|passwd|auth|oauth|sso|account\/security)([^a-z]|$)/.test(hay)) return true;
  return false;
}

// ---------------------------------------------------------------------------------------------------
// The CONTEXT BRIDGE — POST captured page context to the user's own ClaudeFather server.
// Uses Electron's net.fetch (Chromium networking stack). Sends auth as X-CC-Token (and Bearer) when set.
// ---------------------------------------------------------------------------------------------------
function serverBase() {
  return (config.serverUrl || '').trim().replace(/\/+$/, '');
}

async function postJson(pathName, body) {
  const base = serverBase();
  if (!base) return { ok: false, reason: 'no-server' };
  const headers = { 'Content-Type': 'application/json' };
  if (config.authToken) {
    headers['X-CC-Token'] = config.authToken;
    headers['Authorization'] = 'Bearer ' + config.authToken;
  }
  try {
    const resp = await net.fetch(base + pathName, {
      method: 'POST',
      headers,
      body: JSON.stringify(body)
    });
    return { ok: resp.ok, status: resp.status };
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// Like postJson but also parses + returns the JSON response body (and supports GET). Used by the
// explicit Clip/Save flow (/api/clip), the subject picker (/api/context/stats), and co-reading
// (/api/context/page-intel) — all of which need the server's reply, not just the status.
async function apiRequest(method, pathName, body) {
  const base = serverBase();
  if (!base) return { ok: false, reason: 'no-server' };
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (config.authToken) {
    headers['X-CC-Token'] = config.authToken;
    headers['Authorization'] = 'Bearer ' + config.authToken;
  }
  try {
    const resp = await net.fetch(base + pathName, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined
    });
    let data = null;
    try { data = await resp.json(); } catch (_) { /* non-JSON / empty body */ }
    return { ok: resp.ok, status: resp.status, data };
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// Derive a friendly default subject from a URL's host, e.g. https://www.avenlur.com/x -> "Avenlur".
function siteNameFromUrl(url) {
  try {
    const host = new URL(url).hostname.replace(/^www\./i, '');
    const label = (host.split('.')[0] || host || '').trim();
    return label ? label.charAt(0).toUpperCase() + label.slice(1) : '';
  } catch (_) { return ''; }
}

async function captureAndReport(tab) {
  if (!config.captureEnabled) return;                 // HARD rule: never capture/report when OFF
  if (!tab || tab.type !== 'browser') return;         // Workspace = your own dashboard, not "browsing"
  const wc = tab.view && tab.view.webContents;
  if (!wc || wc.isDestroyed()) return;

  const url = wc.getURL();
  if (!url || url === 'about:blank') return;
  if (isSensitive(url)) {
    notifyCapture(tab.id, 'skipped', url, 'sensitive page (login / password manager)');
    return;
  }

  let page;
  try {
    // Read text-only content in the page's own context. No screenshots, no DOM mutation.
    page = await wc.executeJavaScript(PAGE_READ_JS, false /* userGesture */);
  } catch (e) {
    notifyCapture(tab.id, 'error', url, 'read failed: ' + e.message);
    return;
  }

  const title = (page && page.title) || tab.title || '';
  const text = (page && page.text) || '';

  // Fire both endpoints against the documented contract. focus-report = "what the user is looking at now";
  // ingest-page = durable context store (trust:"external" — untrusted web content, data not instructions).
  const [a, b] = await Promise.all([
    postJson('/api/focus-report', { lens: 'browser', subject: null, url, title, text }),
    postJson('/api/context/ingest-page', { url, title, text, trust: 'external' })
  ]);

  if (a.ok || b.ok) notifyCapture(tab.id, 'sent', url, '');
  else notifyCapture(tab.id, 'error', url, (a.reason || b.reason || ('HTTP ' + (a.status || b.status || '?'))));
}

function notifyCapture(tabId, status, url, reason) {
  if (win && !win.isDestroyed()) {
    win.webContents.send('capture:event', { tabId, status, url, reason, ts: Date.now() });
  }
}

// ---------------------------------------------------------------------------------------------------
// EXPLICIT SAVE — "⭐ Save to ClaudeFather" / "📸 Clip".
//
// This is an explicit, user-initiated save and is INDEPENDENT of the always-on capture toggle: clicking
// the button (or its hotkey) is the consent. We grab {url, title, page text, PNG screenshot} of the
// active browser tab and hand it back to the renderer, which collects a subject + kind + note and then
// calls clipSave() -> POST /api/clip. We never auto-send anything here.
// ---------------------------------------------------------------------------------------------------
async function captureClip(tab) {
  if (!tab || tab.type !== 'browser') return { ok: false, reason: 'not a browser tab' };
  const wc = tab.view && tab.view.webContents;
  if (!wc || wc.isDestroyed()) return { ok: false, reason: 'no page' };

  const url = wc.getURL();
  if (!url || url === 'about:blank') return { ok: false, reason: 'blank page' };

  // Page text (best-effort; a screenshot-only save is still valid if the read fails).
  let page;
  try { page = await wc.executeJavaScript(PAGE_READ_JS, false); }
  catch (_) { page = { title: wc.getTitle() || '', text: '' }; }

  // Full-view PNG screenshot. capturePage() grabs the rendered view; on the active tab it's on-screen.
  // (Region select / full-scroll stitching would be a future enhancement.)
  let image_b64 = '';
  try {
    const img = await wc.capturePage();
    if (img && !img.isEmpty()) image_b64 = img.toPNG().toString('base64');
  } catch (_) { /* screenshot is best-effort; text-only save still works */ }

  return {
    ok: true,
    url,
    title: (page && page.title) || wc.getTitle() || '',
    text: (page && page.text) || '',
    image_b64,
    siteName: siteNameFromUrl(url)
  };
}

// Candidate subjects for the picker — pulled from the server's context stats. Defensive about shape:
// accepts an array of strings or of objects with a name/subject/title/id field, under a few likely keys.
async function fetchSubjects() {
  const r = await apiRequest('GET', '/api/context/stats');
  if (!r.ok || !r.data) return [];
  const d = r.data;
  const raw = d.subjects || d.top_subjects || d.subject_list || (d.stats && d.stats.subjects) || [];
  const out = [];
  for (const s of (Array.isArray(raw) ? raw : [])) {
    if (typeof s === 'string') { if (s.trim()) out.push(s.trim()); }
    else if (s && typeof s === 'object') {
      const v = s.subject || s.name || s.title || s.id;
      if (v) out.push(String(v));
    }
  }
  return out;
}

async function saveClip(payload) {
  const p = payload || {};
  const subject = (p.subject || '').trim();
  if (!subject) return { ok: false, reason: 'subject required' };
  const body = {
    subject,
    kind: p.kind || 'reference',
    url: p.url || '',
    title: p.title || '',
    text: p.text || '',
    note: p.note || '',
    image_b64: p.image_b64 || ''
  };
  const r = await apiRequest('POST', '/api/clip', body);
  if (r.ok) return { ok: true, id: r.data && r.data.id };
  return { ok: false, reason: r.reason || ('HTTP ' + (r.status || '?')) };
}

// ---------------------------------------------------------------------------------------------------
// AI CO-READING — a read-only side panel that, when open, asks the user's OWN server what it already
// knows about the current page (POST /api/context/page-intel). OFF by default; opening it is the
// consent. Sensitive pages are skipped just like capture. Only ever talks to the configured server.
// ---------------------------------------------------------------------------------------------------
function sendIntel(payload) {
  if (win && !win.isDestroyed()) win.webContents.send('intel:state', payload);
}

async function fetchIntel(tab) {
  if (!sidebarOpen) return;
  if (!tab || tab.type !== 'browser') { sendIntel({ status: 'idle' }); return; }
  const wc = tab.view && tab.view.webContents;
  if (!wc || wc.isDestroyed()) return;

  const url = wc.getURL();
  if (!url || url === 'about:blank') { sendIntel({ status: 'idle' }); return; }
  if (isSensitive(url)) { sendIntel({ status: 'skipped', url, reason: 'sensitive page' }); return; }

  sendIntel({ status: 'loading', url });

  let page;
  try { page = await wc.executeJavaScript(PAGE_READ_JS, false); }
  catch (_) { page = { title: wc.getTitle() || '', text: '' }; }

  const r = await apiRequest('POST', '/api/context/page-intel', {
    url, title: (page && page.title) || '', text: (page && page.text) || ''
  });
  // The active tab may have navigated again while we were waiting; only render if URL still matches.
  const stillHere = !wc.isDestroyed() && wc.getURL() === url;
  if (!stillHere) return;

  if (r.ok && r.data) {
    sendIntel({
      status: 'ok',
      url,
      related: Array.isArray(r.data.related) ? r.data.related : [],
      flags: Array.isArray(r.data.flags) ? r.data.flags : []
    });
  } else {
    sendIntel({ status: 'error', url, reason: r.reason || ('HTTP ' + (r.status || '?')) });
  }
}

function setSidebar(open) {
  sidebarOpen = !!open;
  layoutActiveView();          // reserve / release the right-hand strip for the panel
  broadcastSidebar();
  if (sidebarOpen) fetchIntel(getTab(activeTabId));
  else sendIntel({ status: 'idle' });
}

function broadcastSidebar() {
  if (win && !win.isDestroyed()) win.webContents.send('sidebar:state', { open: sidebarOpen });
}

// ---------------------------------------------------------------------------------------------------
// AGENT-DRIVEN BROWSER — "let me show you".
//
// The user's agents run on the user's OWN ClaudeFather server. They can't reach the desktop directly, so
// this client POLLS the server for queued browser commands and executes them in a real browser tab, then
// ACKs each one (optionally with a result the server can fold back into context). The whole point: the AI
// already knows your context, so it can drive the browser to SHOW you things.
//
// Safety model (see also the "🤖 Agent control" toggle, DEFAULT OFF):
//   - We only ever poll/obey the user's OWN configured server (same base + auth as the bridge). No server
//     configured  ->  no polling at all.
//   - "Show-me" actions (open/navigate/new_tab/scroll_to/highlight/screenshot/reload/back/forward) only
//     SHOW you things, so they run regardless of the toggle.
//   - WRITE actions (`act`: click/type) are REFUSED unless you flip "🤖 Agent control" ON. We ack
//     {ok:false, error:'agent control off'} when it's off — the agent learns it was declined.
//   - Every executed command fires a visible toast ("🤖 agent opened this / highlighted this") so the
//     browser is never silently driven.
// ---------------------------------------------------------------------------------------------------
const AGENT_POLL_MS = 1500;          // poll cadence; the server marks returned commands 'sent'
let agentPollTimer = null;
let agentPollBusy = false;           // never overlap polls
const seenCommandIds = new Set();    // defensive de-dupe (server shouldn't re-send, but be safe)

function maybeStartAgentPoll() {
  if (agentPollTimer) return;        // already running
  if (!serverBase()) return;         // only ever poll a configured server
  agentPollTimer = setInterval(pollAgentCommands, AGENT_POLL_MS);
}
function stopAgentPoll() {
  if (agentPollTimer) { clearInterval(agentPollTimer); agentPollTimer = null; }
}

async function pollAgentCommands() {
  if (agentPollBusy) return;
  if (!serverBase()) { stopAgentPoll(); return; }     // server cleared since we started
  agentPollBusy = true;
  try {
    const r = await apiRequest('GET', '/api/browser/commands');
    if (!r.ok || !r.data) return;
    const cmds = Array.isArray(r.data.commands) ? r.data.commands : [];
    for (const cmd of cmds) {
      if (!cmd || cmd.id === undefined || cmd.id === null) continue;
      if (seenCommandIds.has(cmd.id)) continue;        // already handled this one
      seenCommandIds.add(cmd.id);
      await executeAndAck(cmd);
    }
    if (seenCommandIds.size > 1000) seenCommandIds.clear();   // bound the de-dupe set
  } catch (_) {
    /* transient network/server error — next tick retries */
  } finally {
    agentPollBusy = false;
  }
}

async function executeAndAck(cmd) {
  let res;
  try { res = await executeAgentCommand(cmd); }
  catch (e) { res = { ok: false, error: e && e.message ? e.message : String(e) }; }
  res = res || { ok: false, error: 'no result' };

  notifyAgent(cmd, res);   // visible toast so the user always sees the browser being driven

  const body = { id: cmd.id, ok: !!res.ok };
  if (res.error) body.error = res.error;
  if (res.result) body.result = res.result;     // e.g. {url,title,image_b64} for screenshot
  await postJson('/api/browser/ack', body);
}

// The active tab IF it's a browser tab (we never drive the Workspace dashboard view).
function activeBrowserTab() {
  const t = getTab(activeTabId);
  return (t && t.type === 'browser') ? t : null;
}
// Get the active browser tab, or create + activate a fresh one if the active tab isn't a browser.
function ensureBrowserTab() {
  let t = activeBrowserTab();
  if (!t) t = createTab('browser', '');
  activateTab(t.id);
  return t;
}

// Build a page-context JS snippet that finds the first element matching {selector} or {text} (selector
// wins), scrolls it into view, and — for 'highlight' — briefly flashes an outline/background, restoring
// the original inline style after a moment. Args are JSON-embedded so they can't break out of the string.
function domOpJs(op, args) {
  const sel = args && args.selector ? String(args.selector) : '';
  const txt = args && args.text ? String(args.text) : '';
  const doHighlight = op === 'highlight';
  return `(function(){
    try {
      var sel = ${JSON.stringify(sel)};
      var txt = ${JSON.stringify(txt)};
      var el = null;
      if (sel) { try { el = document.querySelector(sel); } catch(e){} }
      if (!el && txt) {
        var low = txt.toLowerCase();
        var w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
        var n;
        while ((n = w.nextNode())) {
          if (n.nodeValue && n.nodeValue.toLowerCase().indexOf(low) !== -1) { el = n.parentElement; break; }
        }
      }
      if (!el) return { ok:false, error:'no match' };
      el.scrollIntoView({ behavior:'smooth', block:'center' });
      ${doHighlight ? `
      var prev = el.getAttribute('style') || '';
      el.style.outline = '3px solid #6c8cff';
      el.style.outlineOffset = '2px';
      el.style.backgroundColor = 'rgba(108,140,255,0.22)';
      el.style.transition = 'background-color .4s ease, outline-color .4s ease';
      setTimeout(function(){ try { el.setAttribute('style', prev); } catch(e){} }, 2600);
      ` : ``}
      return { ok:true };
    } catch (e) { return { ok:false, error: String((e && e.message) || e) }; }
  })()`;
}

// Build a page-context JS snippet that clicks or types into the first element matching {selector}. Used
// ONLY by `act`, which is gated by the agent-control toggle.
function actJs(kind, selector, value) {
  return `(function(){
    try {
      var el = document.querySelector(${JSON.stringify(selector)});
      if (!el) return { ok:false, error:'no match for selector' };
      el.scrollIntoView({ block:'center' });
      ${kind === 'click'
        ? `el.click();`
        : `el.focus();
           if ('value' in el) {
             el.value = ${JSON.stringify(value || '')};
             el.dispatchEvent(new Event('input', { bubbles:true }));
             el.dispatchEvent(new Event('change', { bubbles:true }));
           } else if (el.isContentEditable) {
             el.textContent = ${JSON.stringify(value || '')};
             el.dispatchEvent(new Event('input', { bubbles:true }));
           } else { return { ok:false, error:'element is not typeable' }; }`}
      return { ok:true };
    } catch (e) { return { ok:false, error: String((e && e.message) || e) }; }
  })()`;
}

// Run one agent command. Returns { ok, error?, result? }.
async function executeAgentCommand(cmd) {
  const action = String(cmd.action || '').toLowerCase().trim();
  const args = (cmd.args && typeof cmd.args === 'object') ? cmd.args : {};

  switch (action) {
    case 'open':
    case 'navigate': {
      const url = normalizeInput(args.url || '');
      if (!url) return { ok: false, error: 'no url' };
      const t = ensureBrowserTab();
      t.view.webContents.loadURL(url);
      return { ok: true, result: { url } };
    }

    case 'new_tab': {
      const url = normalizeInput(args.url || '') || 'about:blank';
      const t = createTab('browser', url);
      activateTab(t.id);
      return { ok: true, result: { url: url === 'about:blank' ? '' : url } };
    }

    case 'scroll_to':
    case 'highlight': {
      const t = activeBrowserTab();
      if (!t) return { ok: false, error: 'no active browser tab' };
      const wc = t.view.webContents;
      if (!wc || wc.isDestroyed()) return { ok: false, error: 'no page' };
      const out = await wc.executeJavaScript(domOpJs(action, args), false);
      return {
        ok: !!(out && out.ok),
        error: out && out.error,
        result: { url: wc.getURL(), title: wc.getTitle() }
      };
    }

    case 'screenshot': {
      const t = activeBrowserTab();
      if (!t) return { ok: false, error: 'no active browser tab' };
      const wc = t.view.webContents;
      if (!wc || wc.isDestroyed()) return { ok: false, error: 'no page' };
      let image_b64 = '';
      try {
        const img = await wc.capturePage();
        if (img && !img.isEmpty()) image_b64 = img.toPNG().toString('base64');
      } catch (e) { return { ok: false, error: 'capture failed: ' + e.message }; }
      return { ok: true, result: { url: wc.getURL(), title: wc.getTitle(), image_b64 } };
    }

    case 'reload': {
      const t = activeBrowserTab();
      if (!t) return { ok: false, error: 'no active browser tab' };
      t.view.webContents.reload();
      return { ok: true, result: { url: t.view.webContents.getURL() } };
    }
    case 'back': {
      const t = activeBrowserTab();
      if (!t) return { ok: false, error: 'no active browser tab' };
      const wc = t.view.webContents;
      if (!wc.navigationHistory.canGoBack()) return { ok: false, error: 'cannot go back' };
      wc.navigationHistory.goBack();
      return { ok: true };
    }
    case 'forward': {
      const t = activeBrowserTab();
      if (!t) return { ok: false, error: 'no active browser tab' };
      const wc = t.view.webContents;
      if (!wc.navigationHistory.canGoForward()) return { ok: false, error: 'cannot go forward' };
      wc.navigationHistory.goForward();
      return { ok: true };
    }

    case 'act': {
      // GATED: write actions only run when the user has flipped agent control ON.
      if (!config.agentControlEnabled) return { ok: false, error: 'agent control off' };
      const kind = String(args.kind || '').toLowerCase();
      if (kind !== 'click' && kind !== 'type') return { ok: false, error: 'unknown act kind: ' + kind };
      if (!args.selector) return { ok: false, error: 'selector required' };
      const t = activeBrowserTab();
      if (!t) return { ok: false, error: 'no active browser tab' };
      const wc = t.view.webContents;
      if (!wc || wc.isDestroyed()) return { ok: false, error: 'no page' };
      // userGesture=true so click()/focus() are treated as user-initiated by the page.
      const out = await wc.executeJavaScript(actJs(kind, String(args.selector), args.value), true);
      return {
        ok: !!(out && out.ok),
        error: out && out.error,
        result: { url: wc.getURL(), title: wc.getTitle() }
      };
    }

    default:
      return { ok: false, error: 'unknown action: ' + action };
  }
}

// Tell the chrome renderer an agent just drove the browser, so it can show a visible toast/indicator.
function notifyAgent(cmd, res) {
  if (!win || win.isDestroyed()) return;
  win.webContents.send('agent:event', {
    action: cmd.action,
    args: cmd.args || {},
    ok: !!(res && res.ok),
    error: res && res.error,
    ts: Date.now()
  });
}

// ---------------------------------------------------------------------------------------------------
// Tab / view management
// ---------------------------------------------------------------------------------------------------
function browserPartitionFor(type) {
  // Persistent partitions so logins/cookies survive restarts. Workspace is isolated from general browsing.
  return type === 'workspace' ? 'persist:cf-workspace' : 'persist:cf-browser';
}

function createTab(type, url) {
  const id = nextId++;
  const partition = browserPartitionFor(type);
  const view = new WebContentsView({
    webPreferences: {
      partition,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,           // content views run sandboxed; we never inject node into web pages
      // The Workspace (dashboard) view gets a tiny preload that injects window.cfDesktop so the web app knows
      // it's the DESKTOP runtime (real browser + capture). Browser tabs get no preload (they're the open web).
      ...(type === 'workspace' ? { preload: path.join(__dirname, 'dashboard-preload.js') } : {})
    }
  });

  const tab = { id, type, view, title: type === 'workspace' ? 'Workspace' : 'New Tab', url: url || '', _debounce: null, _intelDebounce: null };
  tabs.push(tab);

  const wc = view.webContents;

  // Open target=_blank / window.open into a new in-app browser tab (instead of a detached OS window).
  wc.setWindowOpenHandler(({ url: u }) => {
    if (/^https?:\/\//i.test(u)) { createTab('browser', u); broadcastTabs(); }
    else if (u) shell.openExternal(u);   // mailto:, tel:, etc -> OS default
    return { action: 'deny' };
  });

  const onNav = () => {
    tab.url = wc.getURL();
    tab.title = wc.getTitle() || tab.title;
    broadcastTabs();
    if (tab.type === 'browser') {
      clearTimeout(tab._debounce);
      tab._debounce = setTimeout(() => captureAndReport(tab), CAPTURE_DEBOUNCE_MS);
      // Co-reading refresh (independent of capture): only when the panel is actually open.
      if (sidebarOpen) {
        clearTimeout(tab._intelDebounce);
        tab._intelDebounce = setTimeout(() => fetchIntel(tab), INTEL_DEBOUNCE_MS);
      }
    }
  };

  wc.on('page-title-updated', () => { tab.title = wc.getTitle() || tab.title; broadcastTabs(); });
  wc.on('did-stop-loading', onNav);
  wc.on('did-navigate', () => broadcastTabs());
  wc.on('did-navigate-in-page', () => broadcastTabs());
  wc.on('did-start-loading', () => broadcastTabs());

  if (type === 'workspace') {
    primeWorkspaceCookie(partition).finally(() => { if (url) wc.loadURL(url); });
  } else if (url) {
    wc.loadURL(url);
  }

  return tab;
}

// Pre-seed the dashboard's `cc_auth` cookie from the configured token so the Workspace view is already
// authenticated (the cookie value equals the auth_token on the server). Best-effort; if auth is off or
// no token is set, the user just logs in inside the view as usual.
async function primeWorkspaceCookie(partition) {
  const base = serverBase();
  if (!base || !config.authToken) return;
  try {
    const ses = session.fromPartition(partition);
    const u = new URL(base);
    await ses.cookies.set({
      url: base,
      name: 'cc_auth',
      value: config.authToken,
      httpOnly: true,
      sameSite: 'lax',
      secure: u.protocol === 'https:',
      expirationDate: Math.floor(Date.now() / 1000) + 30 * 24 * 3600
    });
  } catch (e) {
    console.error('[workspace] cookie prime failed:', e.message);
  }
}

function getTab(id) { return tabs.find(t => t.id === id); }

function activateTab(id) {
  const tab = getTab(id);
  if (!tab) return;
  activeTabId = id;
  // Hide every other content view; show + lay out the active one (unless an HTML overlay is up).
  for (const t of tabs) {
    if (t.id === id) {
      if (!win.contentView.children.includes(t.view)) win.contentView.addChildView(t.view);
      t.view.setVisible(!overlayOpen);
    } else {
      t.view.setVisible(false);
    }
  }
  layoutActiveView();
  broadcastTabs();
  // Refresh the co-reading panel for the newly-active tab (no-op if the panel is closed).
  if (sidebarOpen) fetchIntel(getTab(id));
}

function closeTab(id) {
  const idx = tabs.findIndex(t => t.id === id);
  if (idx === -1) return;
  const [tab] = tabs.splice(idx, 1);
  try {
    clearTimeout(tab._debounce);
    clearTimeout(tab._intelDebounce);
    if (win.contentView.children.includes(tab.view)) win.contentView.removeChildView(tab.view);
    if (!tab.view.webContents.isDestroyed()) tab.view.webContents.close();
  } catch (_) {}
  if (activeTabId === id) {
    const next = tabs[idx] || tabs[idx - 1] || tabs[0];
    if (next) activateTab(next.id);
    else { activeTabId = null; broadcastTabs(); }
  } else {
    broadcastTabs();
  }
}

function layoutActiveView() {
  if (!win || win.isDestroyed()) return;
  const tab = getTab(activeTabId);
  if (!tab) return;
  const [w, h] = win.getContentSize();
  const y = overlayOpen ? h : CHROME_HEIGHT;      // when overlay is up, park the view off-screen
  // Reserve the right strip for the co-reading panel ONLY when it's open AND we're on a browser tab
  // (the Workspace dashboard isn't co-read, so it keeps the full width). Matches the renderer's logic.
  const reserve = (sidebarOpen && !overlayOpen && tab.type === 'browser') ? SIDEBAR_WIDTH : 0;
  const width = Math.max(0, Math.round(w - reserve));
  tab.view.setBounds({ x: 0, y, width, height: Math.max(0, Math.round(h - y)) });
}

// Push the full serializable tab list + capture/config state to the chrome renderer.
function broadcastTabs() {
  if (!win || win.isDestroyed()) return;
  const list = tabs.map(t => {
    const wc = t.view.webContents;
    const alive = wc && !wc.isDestroyed();
    return {
      id: t.id,
      type: t.type,
      title: t.title || (t.type === 'workspace' ? 'Workspace' : 'New Tab'),
      url: alive ? (wc.getURL() || t.url) : t.url,
      loading: alive ? wc.isLoading() : false,
      canGoBack: alive ? wc.navigationHistory.canGoBack() : false,
      canGoForward: alive ? wc.navigationHistory.canGoForward() : false,
      active: t.id === activeTabId
    };
  });
  win.webContents.send('tabs:state', { tabs: list, activeId: activeTabId });
}

function broadcastConfig() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send('config:state', {
    serverUrl: config.serverUrl,
    hasToken: !!config.authToken,
    captureEnabled: config.captureEnabled,
    agentControlEnabled: config.agentControlEnabled,
    configured: !!serverBase()
  });
}

// ---------------------------------------------------------------------------------------------------
// Address-bar input -> URL (or a web search for free text).
// ---------------------------------------------------------------------------------------------------
function normalizeInput(text) {
  const s = (text || '').trim();
  if (!s) return '';
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(s)) return s;                 // already has a scheme
  if (/^(localhost|[\w-]+(\.[\w-]+)+)(:\d+)?(\/.*)?$/i.test(s) && !/\s/.test(s)) return 'https://' + s;
  return 'https://duckduckgo.com/?q=' + encodeURIComponent(s);      // free text -> search
}

// ---------------------------------------------------------------------------------------------------
// IPC — renderer (chrome) -> main
// ---------------------------------------------------------------------------------------------------
function wireIpc() {
  ipcMain.handle('config:get', () => ({
    serverUrl: config.serverUrl,
    hasToken: !!config.authToken,
    captureEnabled: config.captureEnabled,
    agentControlEnabled: config.agentControlEnabled,
    configured: !!serverBase()
  }));

  ipcMain.handle('config:set', (_e, { serverUrl, authToken }) => {
    const hadServer = !!serverBase();
    config.serverUrl = (serverUrl || '').trim();
    if (typeof authToken === 'string') config.authToken = authToken.trim();  // '' clears it
    saveConfig(config);
    broadcastConfig();
    // If we just gained a server and there's no Workspace tab yet, open one.
    if (!hadServer && serverBase() && !tabs.some(t => t.type === 'workspace')) {
      const t = createTab('workspace', serverBase());
      activateTab(t.id);
    }
    // Start/stop the agent-command poll loop to match the (now-)configured server.
    if (serverBase()) maybeStartAgentPoll();
    else stopAgentPoll();
    return { ok: true };
  });

  ipcMain.handle('capture:set', (_e, { enabled }) => {
    config.captureEnabled = !!enabled;
    saveConfig(config);
    broadcastConfig();
    return { ok: true, enabled: config.captureEnabled };
  });

  // Agent control toggle (DEFAULT OFF) — gates write actions (`act`: click/type) only.
  ipcMain.handle('agent:set', (_e, { enabled }) => {
    config.agentControlEnabled = !!enabled;
    saveConfig(config);
    broadcastConfig();
    return { ok: true, enabled: config.agentControlEnabled };
  });

  ipcMain.handle('tabs:create', (_e, { type, url }) => {
    const t = createTab(type === 'workspace' ? 'workspace' : 'browser', url || (type === 'workspace' ? serverBase() : ''));
    activateTab(t.id);
    return { id: t.id };
  });

  ipcMain.handle('tabs:activate', (_e, { id }) => { activateTab(id); });
  ipcMain.handle('tabs:close', (_e, { id }) => { closeTab(id); });

  ipcMain.handle('tab:navigate', (_e, { id, url }) => {
    const tab = getTab(id);
    if (!tab) return;
    const target = normalizeInput(url);
    if (target) tab.view.webContents.loadURL(target);
  });

  ipcMain.handle('tab:back', (_e, { id }) => { const t = getTab(id); if (t && t.view.webContents.navigationHistory.canGoBack()) t.view.webContents.navigationHistory.goBack(); });
  ipcMain.handle('tab:forward', (_e, { id }) => { const t = getTab(id); if (t && t.view.webContents.navigationHistory.canGoForward()) t.view.webContents.navigationHistory.goForward(); });
  ipcMain.handle('tab:reload', (_e, { id }) => { const t = getTab(id); if (t) t.view.webContents.reload(); });
  ipcMain.handle('tab:stop', (_e, { id }) => { const t = getTab(id); if (t) t.view.webContents.stop(); });
  ipcMain.handle('tab:home', (_e, { id }) => { const t = getTab(id); if (t && serverBase()) t.view.webContents.loadURL(serverBase()); });

  // The renderer raises/lowers a full-window HTML modal (settings / first-run). Hide content views so it shows.
  ipcMain.handle('overlay:set', (_e, { open }) => {
    overlayOpen = !!open;
    const tab = getTab(activeTabId);
    if (tab) tab.view.setVisible(!overlayOpen);
    layoutActiveView();
  });

  // "Capture now" — manual one-shot capture of the active browser tab (respects the OFF rule).
  ipcMain.handle('capture:now', async () => {
    const tab = getTab(activeTabId);
    if (tab) await captureAndReport(tab);
  });

  // --- Explicit Save / Clip (independent of the capture toggle) ---
  // Grab {url,title,text,screenshot} of the active browser tab and hand it to the renderer's save dialog.
  ipcMain.handle('clip:capture', async () => captureClip(getTab(activeTabId)));
  // Subjects for the picker.
  ipcMain.handle('clip:subjects', async () => ({ subjects: await fetchSubjects() }));
  // Commit the save -> POST /api/clip.
  ipcMain.handle('clip:save', async (_e, payload) => saveClip(payload));

  // --- Co-reading side panel ---
  ipcMain.handle('sidebar:toggle', () => { setSidebar(!sidebarOpen); return { open: sidebarOpen }; });
  ipcMain.handle('sidebar:get', () => ({ open: sidebarOpen }));
  ipcMain.handle('intel:refresh', () => { fetchIntel(getTab(activeTabId)); });
}

// ---------------------------------------------------------------------------------------------------
// Global shortcuts — registered while OUR window is focused (and released on blur), so the hotkeys work
// even when a content WebContentsView holds keyboard focus (a renderer keydown wouldn't fire then).
//   ⌘/Ctrl + Shift + S  -> Save the current page to ClaudeFather
//   ⌘/Ctrl + Shift + E  -> Toggle the AI co-reading panel
// ---------------------------------------------------------------------------------------------------
function registerShortcuts() {
  try {
    globalShortcut.register('CommandOrControl+Shift+S', () => {
      if (win && !win.isDestroyed()) win.webContents.send('menu:save-clip');
    });
    globalShortcut.register('CommandOrControl+Shift+E', () => setSidebar(!sidebarOpen));
  } catch (_) { /* a key may be held by another app; non-fatal */ }
}
function unregisterShortcuts() { try { globalShortcut.unregisterAll(); } catch (_) {} }

// ---------------------------------------------------------------------------------------------------
// Window
// ---------------------------------------------------------------------------------------------------
function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 720,
    minHeight: 480,
    backgroundColor: '#0a0a0f',
    title: 'ClaudeFather Desktop',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  win.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  win.webContents.on('did-finish-load', () => {
    broadcastConfig();
    broadcastSidebar();
    // First run: no server configured -> the renderer shows the first-run overlay (no tabs yet).
    if (serverBase()) {
      const ws = createTab('workspace', serverBase());
      createTab('browser', 'https://duckduckgo.com');
      activateTab(ws.id);
    } else {
      broadcastTabs();
    }
    // Begin polling the user's own server for agent browser commands (no-op if no server configured).
    maybeStartAgentPoll();
  });

  win.on('resize', layoutActiveView);
  // Hotkeys are live only while our window is focused (released otherwise so we never hold them globally).
  win.on('focus', registerShortcuts);
  win.on('blur', unregisterShortcuts);
  win.on('closed', () => { unregisterShortcuts(); stopAgentPoll(); win = null; });
}

// ---------------------------------------------------------------------------------------------------
// Auto-update (electron-updater + GitHub Releases). The SHELL self-updates; dashboard/feature updates are
// server-side and need no rebuild (we just load the live dashboard). Windows: silent download + install on
// quit. macOS (unsigned): can't silently update, so notify + open the releases page to download. No-op in
// dev (unpackaged) and never crashes the app (every step guarded).
// ---------------------------------------------------------------------------------------------------
const RELEASES_URL = 'https://github.com/jkarger123/claudesole-dist/releases/latest';
function initAutoUpdate() {
  if (!app.isPackaged) return;                       // only a built app has an update feed
  let autoUpdater;
  try { ({ autoUpdater } = require('electron-updater')); } catch (e) { return; }
  try {
    autoUpdater.autoDownload = (process.platform === 'win32');   // mac (unsigned) can't silently install
    autoUpdater.autoInstallOnAppQuit = true;
    autoUpdater.on('update-available', (info) => {
      if (process.platform === 'win32') return;                  // win downloads automatically
      dialog.showMessageBox(win, { type: 'info', buttons: ['Download', 'Later'], defaultId: 0,
        title: 'Update available',
        message: 'ClaudeFather Desktop ' + ((info && info.version) || '') + ' is available.',
        detail: 'A newer version is ready to download.' })
        .then(r => { if (r.response === 0) shell.openExternal(RELEASES_URL); }).catch(() => {});
    });
    autoUpdater.on('update-downloaded', (info) => {
      dialog.showMessageBox(win, { type: 'info', buttons: ['Restart now', 'Later'], defaultId: 0,
        title: 'Update ready',
        message: 'ClaudeFather Desktop ' + ((info && info.version) || '') + ' has been downloaded.',
        detail: 'Restart to finish updating.' })
        .then(r => { if (r.response === 0) autoUpdater.quitAndInstall(); }).catch(() => {});
    });
    autoUpdater.on('error', (e) => console.log('[updater]', e && e.message));
    autoUpdater.checkForUpdates().catch(e => console.log('[updater] check', e && e.message));
  } catch (e) { console.log('[updater] init', e && e.message); }
}

// ---------------------------------------------------------------------------------------------------
// App lifecycle
// ---------------------------------------------------------------------------------------------------
app.whenReady().then(() => {
  config = loadConfig();
  wireIpc();
  createWindow();
  registerShortcuts();   // the window starts focused; 'focus' may not fire on first show
  setTimeout(initAutoUpdate, 4000);   // check shortly after launch (let the window settle first)

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('will-quit', () => { unregisterShortcuts(); stopAgentPoll(); });

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
