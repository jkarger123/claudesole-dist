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
  renderSidebarVisibility();   // co-reading only applies to browser tabs; re-evaluate on every tab change
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
// Explicit Save / Clip — "⭐ Save" and "📸 Clip" both capture {text + screenshot} of the active browser
// tab, then collect a subject + kind + note and POST /api/clip. This is a user action, not auto-capture.
// ---------------------------------------------------------------------------------------------------
let pendingClip = null;   // the captured page awaiting the user's subject/kind/note

async function startClip() {
  const t = activeTab();
  if (!t || t.type !== 'browser') { showToast('error', 'Open a browser tab to save a page.'); return; }
  if (!cfg.configured) { showToast('error', 'Set a server URL in ⚙ Settings first.'); openModal(); return; }

  showToast('info', '📸 Capturing this page…');
  const cap = await window.cf.clipCapture();
  if (!cap || !cap.ok) {
    showToast('error', 'Could not capture this page' + (cap && cap.reason ? ': ' + cap.reason : '') + '.');
    return;
  }
  pendingClip = cap;
  openClipModal(cap);
  // Load candidate subjects in the background; the picker works as free-text meanwhile.
  window.cf.clipSubjects().then((r) => fillSubjects((r && r.subjects) || []));
}

function openClipModal(cap) {
  // Screenshot preview (data URL is allowed by our CSP: img-src 'self' data:).
  const prev = $('clip-preview');
  prev.innerHTML = '';
  if (cap.image_b64) {
    const img = document.createElement('img');
    img.src = 'data:image/png;base64,' + cap.image_b64;
    img.alt = 'page screenshot';
    prev.appendChild(img);
    prev.classList.remove('hidden');
  } else {
    prev.classList.add('hidden');
  }
  $('clip-pagetitle').textContent = cap.title || '';
  $('clip-pageurl').textContent = cap.url || '';
  $('clip-subject').value = cap.siteName || '';
  $('clip-kind').value = 'reference';
  $('clip-note').value = '';
  $('clip-err').classList.add('hidden');
  $('clipmodal').classList.remove('hidden');
  window.cf.setOverlay(true);   // park the content view so the modal shows fully
  setTimeout(() => $('clip-subject').focus(), 30);
}

function closeClipModal() {
  $('clipmodal').classList.add('hidden');
  window.cf.setOverlay(false);
  pendingClip = null;
}

function fillSubjects(list) {
  const dl = $('clip-subjectlist');
  dl.innerHTML = '';
  for (const s of list) {
    const opt = document.createElement('option');
    opt.value = s;
    dl.appendChild(opt);
  }
}

$('clip-save').onclick = () => startClip();
$('clip-shot').onclick = () => startClip();     // same flow; both capture a screenshot
$('clip-cancel').onclick = () => closeClipModal();

$('clip-save-btn').onclick = async () => {
  if (!pendingClip) return;
  const subject = $('clip-subject').value.trim();
  if (!subject) {
    const err = $('clip-err'); err.textContent = 'Pick or type a subject.'; err.classList.remove('hidden');
    return;
  }
  const payload = {
    subject,
    kind: $('clip-kind').value,
    url: pendingClip.url,
    title: pendingClip.title,
    text: pendingClip.text,
    note: $('clip-note').value.trim(),
    image_b64: pendingClip.image_b64
  };
  const btn = $('clip-save-btn');
  btn.disabled = true;
  const res = await window.cf.clipSave(payload);
  btn.disabled = false;
  if (res && res.ok) {
    closeClipModal();
    showToast('sent', '⭐ Saved to "' + subject + '"');
  } else {
    const err = $('clip-err');
    err.textContent = 'Save failed: ' + ((res && res.reason) || 'unknown') + '.';
    err.classList.remove('hidden');
  }
};

// ---------------------------------------------------------------------------------------------------
// AI co-reading side panel — read-only, off by default. Shows what the server already knows about the
// current page. Content arrives via the 'intel:state' event (the main process does the fetch).
// ---------------------------------------------------------------------------------------------------
let sidebarOpen = false;

$('coread').onclick = () => window.cf.toggleSidebar();
$('sb-close').onclick = () => window.cf.toggleSidebar();   // it's open, so toggling closes it
$('sb-refresh').onclick = () => window.cf.refreshIntel();

// Show the panel only when it's enabled AND we're on a browser tab (the Workspace dashboard isn't co-read).
// This mirrors the main process, which reserves the right strip under exactly the same condition.
function renderSidebarVisibility() {
  const t = activeTab();
  const show = sidebarOpen && t && t.type === 'browser';
  $('sidebar').classList.toggle('hidden', !show);
  $('coread').classList.toggle('active', sidebarOpen);
}

function renderIntel(d) {
  const body = $('sb-body');
  body.innerHTML = '';
  if (!d || d.status === 'idle') {
    body.appendChild(intelMsg('Open a web page to see what your ClaudeFather knows about it.'));
    return;
  }
  if (d.status === 'loading') { body.appendChild(intelMsg('Reading the room…', true)); return; }
  if (d.status === 'skipped') { body.appendChild(intelMsg('Skipped — ' + (d.reason || 'private page') + '.')); return; }
  if (d.status === 'error') { body.appendChild(intelMsg('Couldn’t reach your server (' + (d.reason || 'error') + ').')); return; }

  // status === 'ok'
  const related = Array.isArray(d.related) ? d.related : [];
  const flags = Array.isArray(d.flags) ? d.flags : [];

  if (flags.length) {
    const fl = document.createElement('div');
    fl.className = 'sb-flags';
    for (const f of flags) {
      const chip = document.createElement('div');
      chip.className = 'sb-flag';
      chip.textContent = typeof f === 'string' ? f : JSON.stringify(f);
      fl.appendChild(chip);
    }
    body.appendChild(fl);
  }

  if (!related.length) {
    body.appendChild(intelMsg('Nothing connected to this yet.'));
    return;
  }

  const h = document.createElement('div');
  h.className = 'sb-section';
  h.textContent = 'Related';
  body.appendChild(h);

  for (const r of related) {
    const card = document.createElement('div');
    card.className = 'sb-card';

    const top = document.createElement('div');
    top.className = 'sb-card-top';
    const title = document.createElement('span');
    title.className = 'sb-card-title';
    title.textContent = r.title || r.source || '(untitled)';
    top.appendChild(title);
    if (r.kind) {
      const k = document.createElement('span');
      k.className = 'sb-card-kind';
      k.textContent = r.kind;
      top.appendChild(k);
    }
    card.appendChild(top);

    if (r.why) {
      const why = document.createElement('div');
      why.className = 'sb-card-why';
      why.textContent = r.why;
      card.appendChild(why);
    }
    if (r.source && r.source !== r.title) {
      const src = document.createElement('div');
      src.className = 'sb-card-src';
      src.textContent = r.source;
      card.appendChild(src);
    }
    body.appendChild(card);
  }
}

function intelMsg(text, spinning) {
  const el = document.createElement('div');
  el.className = 'sb-empty';
  if (spinning) { const sp = document.createElement('span'); sp.className = 'spin'; el.appendChild(sp); }
  const t = document.createElement('span');
  t.textContent = text;
  el.appendChild(t);
  return el;
}

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
window.cf.onSidebar((d) => { sidebarOpen = !!(d && d.open); renderSidebarVisibility(); });
window.cf.onIntel((d) => renderIntel(d));
window.cf.onSaveClip(() => startClip());   // ⌘⇧S hotkey from main

// ---------------------------------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------------------------------
(async function init() {
  cfg = await window.cf.getConfig();
  renderCapture();
  try { const sb = await window.cf.getSidebar(); sidebarOpen = !!(sb && sb.open); } catch (_) {}
  renderSidebarVisibility();
  if (!cfg.configured) openModal();   // first run -> force configuration
})();
