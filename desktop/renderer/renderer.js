// Chrome renderer — drives the tab bar, address bar, capture toggle, and settings modal.
// All real work happens in the main process via the `window.cf` bridge (see preload.js).
'use strict';

const $ = (id) => document.getElementById(id);

let state = { tabs: [], activeId: null };
let cfg = { serverUrl: '', hasToken: false, captureEnabled: false, configured: false };
let toastTimer = null;

// ---------------------------------------------------------------------------------------------------
// Render the tab strip
// ---------------------------------------------------------------------------------------------------
function renderTabs() {
  const wrap = $('tabs');
  wrap.innerHTML = '';
  for (const t of state.tabs) {
    const el = document.createElement('div');
    el.className = 'tab' + (t.active ? ' active' : '') + (t.type === 'workspace' ? ' workspace' : '');
    el.title = t.url || '';

    const kind = document.createElement('span');
    kind.className = 'kind';
    kind.textContent = t.type === 'workspace' ? 'WS' : 'WEB';
    el.appendChild(kind);

    if (t.loading) {
      const sp = document.createElement('span');
      sp.className = 'spin';
      el.appendChild(sp);
    }

    const label = document.createElement('span');
    label.className = 'label';
    label.textContent = t.title || (t.type === 'workspace' ? 'Workspace' : 'New Tab');
    el.appendChild(label);

    // Workspace tab is permanent (no close button); browser tabs are closable.
    if (t.type !== 'workspace') {
      const close = document.createElement('span');
      close.className = 'close';
      close.textContent = '×';
      close.onclick = (e) => { e.stopPropagation(); window.cf.closeTab(t.id); };
      el.appendChild(close);
    }

    el.onclick = () => window.cf.activateTab(t.id);
    wrap.appendChild(el);
  }
  renderToolbar();
}

function activeTab() { return state.tabs.find(t => t.id === state.activeId); }

function renderToolbar() {
  const t = activeTab();
  const isBrowser = t && t.type === 'browser';
  $('back').disabled = !t || !t.canGoBack;
  $('forward').disabled = !t || !t.canGoForward;
  $('reload').disabled = !t;
  // Only let you edit the address on browser tabs (the Workspace URL is fixed in settings).
  $('address').disabled = !isBrowser;
  if (document.activeElement !== $('address')) {
    $('address').value = t ? (t.url || '') : '';
  }
}

// ---------------------------------------------------------------------------------------------------
// Capture toggle
// ---------------------------------------------------------------------------------------------------
function renderCapture() {
  const btn = $('capture');
  const on = cfg.captureEnabled;
  btn.classList.toggle('on', on);
  btn.classList.toggle('off', !on);
  $('capturelabel').textContent = on ? 'AI capture: ON' : 'AI capture: OFF';
  btn.title = on
    ? 'Browser pages are being sent to your ClaudeFather. Click to stop.'
    : 'AI is NOT seeing your browsing. Click to let it see browser tabs.';
}

$('capture').onclick = async () => {
  if (!cfg.captureEnabled && !cfg.configured) {
    showToast('error', 'Set a server URL in ⚙ Settings before enabling capture.');
    openModal();
    return;
  }
  const res = await window.cf.setCapture(!cfg.captureEnabled);
  cfg.captureEnabled = !!res.enabled;
  renderCapture();
};

// ---------------------------------------------------------------------------------------------------
// Toolbar actions
// ---------------------------------------------------------------------------------------------------
$('back').onclick = () => { const t = activeTab(); if (t) window.cf.back(t.id); };
$('forward').onclick = () => { const t = activeTab(); if (t) window.cf.forward(t.id); };
$('reload').onclick = () => { const t = activeTab(); if (t) window.cf.reload(t.id); };
$('home').onclick = () => { const t = activeTab(); if (t) window.cf.home(t.id); };
$('newtab').onclick = () => window.cf.createTab('browser', 'https://duckduckgo.com');
$('gear').onclick = () => openModal();

$('address').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    const t = activeTab();
    if (t && t.type === 'browser') window.cf.navigate(t.id, $('address').value);
  }
});

// ---------------------------------------------------------------------------------------------------
// Settings / first-run modal
// ---------------------------------------------------------------------------------------------------
function openModal() {
  $('serverUrl').value = cfg.serverUrl || '';
  $('authToken').value = '';   // never echo the stored token back
  $('authToken').placeholder = cfg.hasToken ? '•••••• (saved — leave blank to keep)' : 'Only if your dashboard has auth enabled';
  $('modal-title').textContent = cfg.configured ? 'Settings' : 'Connect your ClaudeFather';
  $('modal-cancel').style.display = cfg.configured ? '' : 'none';   // first run: must configure
  $('modal-err').classList.add('hidden');
  $('modal').classList.remove('hidden');
  window.cf.setOverlay(true);   // hide content views so the modal is fully visible
}

function closeModal() {
  $('modal').classList.add('hidden');
  window.cf.setOverlay(false);
}

$('modal-cancel').onclick = () => closeModal();

$('modal-save').onclick = async () => {
  const url = $('serverUrl').value.trim();
  if (!/^https?:\/\//i.test(url)) {
    const err = $('modal-err');
    err.textContent = 'Enter a full URL starting with http:// or https://';
    err.classList.remove('hidden');
    return;
  }
  // Token: blank keeps the existing one (unless none saved). Passing undefined = keep.
  const tokenField = $('authToken').value;
  const token = (tokenField === '' && cfg.hasToken) ? undefined : tokenField.trim();
  await window.cf.setConfig(url, token);
  cfg = await window.cf.getConfig();
  closeModal();
  renderCapture();
};

// ---------------------------------------------------------------------------------------------------
// Toast (capture activity feedback)
// ---------------------------------------------------------------------------------------------------
function showToast(kind, msg) {
  const el = $('toast');
  el.className = kind;            // sent | skipped | error
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add('hidden'), 3200);
}

function hostOf(url) { try { return new URL(url).host; } catch (_) { return url || ''; } }

// ---------------------------------------------------------------------------------------------------
// Wire events from main
// ---------------------------------------------------------------------------------------------------
window.cf.onTabs((data) => { state = data; renderTabs(); });
window.cf.onConfig((data) => { cfg = data; renderCapture(); });
window.cf.onCaptureEvent((ev) => {
  if (ev.status === 'sent') showToast('sent', '👁  Shared with ClaudeFather: ' + hostOf(ev.url));
  else if (ev.status === 'skipped') showToast('skipped', '⛔  Skipped (' + (ev.reason || 'private') + '): ' + hostOf(ev.url));
  else showToast('error', '⚠  Capture failed: ' + (ev.reason || 'unknown') + ' — ' + hostOf(ev.url));
});

// ---------------------------------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------------------------------
(async function init() {
  cfg = await window.cf.getConfig();
  renderCapture();
  if (!cfg.configured) openModal();   // first run -> force configuration
})();
