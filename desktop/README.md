# ClaudeFather Desktop

A small, self-contained **Electron** app that gives your ClaudeFather *vision into what you browse*.

It does two things in one window:

1. **Workspace** — loads your **existing** ClaudeFather web dashboard from a URL you configure.
   It does **not** fork, copy, or modify the dashboard (`command-center/server.py` is untouched). The web
   app keeps working exactly as before for anyone who doesn't install this.
2. **Browser** — a **real Chromium browsing surface** (the open internet). A regular web page can't embed
   the live web (X-Frame-Options / CSP block iframes, same-origin blocks content reads) — a desktop shell
   can. That unlocks the point of this app: **the AI can see the page you're on.**

When you flip **AI capture ON**, each browser page you finish loading is read (`{url, title, text}`, text
truncated to ~8000 chars) and POSTed to **your own** configured ClaudeFather server. Nothing is sent
anywhere else, ever. Capture defaults **OFF**.

---

## Why this is a desktop app (architecture)

The dashboard already lives on your always-on Mac as a stdlib-Python server. A browser tab pointed at it
can't *also* embed arbitrary external sites or read their content — that's blocked by web security. So this
shell:

- **loads** the dashboard (Workspace tab) — it's the same server, just in a native window; and
- **adds** a real browser engine (Browser tabs) whose content the app *can* read and forward to the AI.

Content tabs use Electron's **`WebContentsView`** — the modern, supported successor to `BrowserView`
(deprecated in Electron 30). It keeps every reason `BrowserView` beat `<webview>`: out-of-process native
compositing (no in-DOM `<webview>` lifecycle bugs), the main process holds the `webContents` directly for
reliable navigation events and `executeJavaScript` content reads (best content access + control), and each
tab gets its own `webPreferences` + persistent session partition for isolation.

```
┌──────────────────────────────────────────────────────┐
│ tab strip   [ WS Workspace ] [ WEB duckduckgo ]  + ⚙  │  ← HTML chrome (window webContents)
│ toolbar     ‹ › ⟳ ⌂  [ address ............ ]  ● ON   │
├──────────────────────────────────────────────────────┤
│                                                        │
│   active WebContentsView (Workspace OR a Browser tab)  │  ← native view, positioned below the chrome
│                                                        │
└──────────────────────────────────────────────────────┘
```

---

## The context bridge (the whole point)

When a **Browser** tab finishes navigating *and capture is ON*, the main process reads the page text and
POSTs to your configured server, against this contract:

- `POST /api/focus-report` → `{ "lens": "browser", "subject": null, "url", "title", "text" }`
- `POST /api/context/ingest-page` → `{ "url", "title", "text", "trust": "external" }`

(Both endpoints are added to the ClaudeFather web app in parallel; this client codes against that contract.)

If an **auth token** is configured it's sent as `X-CC-Token` (and `Authorization: Bearer`) — the same value
the dashboard accepts as its `cc_auth` cookie, so it also auto-signs-in the Workspace view.

---

## Explicit capture (Save / Clip / Co-read)

Beyond the always-on toggle, three **user-initiated** capture features live in the browser toolbar. They
talk to the **same** server + auth the bridge uses, and each is an explicit action (the click/hotkey is the
consent) — they do **not** depend on the AI-capture toggle.

- **⭐ Save** *(or `⌘⇧S`)** — captures `{url, title, page text (~8k), PNG screenshot}` of the current page,
  then asks for a **subject** (free-text, prefilled with the site name, auto-completed from your server's
  known subjects via `GET /api/context/stats`), a **kind** (reference / lead / competitor / inspiration /
  read-later), and an optional **note**, and `POST`s `/api/clip`. A toast confirms the save.
- **📸 Clip** — the same flow, surfaced as a screenshot-first button (full-view PNG via
  `webContents.capturePage()`). Region-select / full-scroll stitching is a future enhancement.
- **🧠 Co-read** *(or `⌘⇧E`)** — a read-only right-hand panel, **off by default**. When open, each page you
  navigate to (debounced) is `POST`ed to `/api/context/page-intel` and the reply
  `{ related:[{title,source,kind,why}], flags:[…] }` is rendered as a sleek "what we already know about
  this" panel (e.g. "🔗 ties to your 2pm with Avenlur"). Sensitive pages are skipped; the active browser
  view is laid out narrower so the panel shows through.

### Server contract (added to the web app in parallel)

- `POST /api/clip` → `{ subject, kind, url, title, text, note, image_b64 }` ⇒ `{ ok, id }`
- `POST /api/context/page-intel` → `{ url, title, text }` ⇒ `{ related:[…], flags:[…] }`
- `GET  /api/context/stats` → used to populate the subject picker (parsed defensively).

Auth is the configured `authToken`, sent as `X-CC-Token` **and** `Authorization: Bearer` (same as the bridge).

### Privacy model

- **Capture is OFF by default** and only flips when *you* click the toggle. The toggle is always visible in
  the toolbar with a colored dot — green = the AI is seeing browser tabs, grey = it is not. A toast appears
  on every capture so it's never silent.
- **Workspace is never "captured"** as browsing — it's your own dashboard.
- **Sensitive pages are skipped** best-effort even when capture is ON: known password managers, and any URL
  whose host/path looks like `login` / `signin` / `password` / `auth` / `sso`. Non-`http(s)` schemes are skipped.
- **Only your server is ever contacted.** No telemetry, analytics, or third party — anywhere.
- Config (server URL + optional token) is stored locally in Electron's `userData` dir as `config.json`,
  written owner-only (`0600`).

---

## Agent-driven browser ("let me show you")

Your agents run on **your own** ClaudeFather server and know your context — so they can drive this browser
to *show you* things. The desktop app **polls your server** for queued browser commands (~every 1.5s, only
when a server is configured) and executes each in a real browser tab, then **acks** it (optionally with a
result the server can fold back into context). It only ever polls/obeys your configured server, using the
same auth as the bridge.

### Server contract (built into the web app in parallel)

- `GET  /api/browser/commands` → `{ ok, commands:[{ id, action, args }] }` — the server marks returned ones `sent`.
- `POST /api/browser/ack` → `{ id, ok, result?, error? }` — one ack per executed command. `result` may carry
  `{ url, title, image_b64 }` (e.g. for `screenshot`) or `{ url, title }`.

### Actions (`action`, with `args`)

| action | args | what it does |
|---|---|---|
| `open` / `navigate` | `{url}` | load url in the **active** browser tab (creates + activates one if none) |
| `new_tab` | `{url}` | open + activate a new browser tab |
| `scroll_to` | `{text \| selector}` | scroll to the first match (selector wins; text via tree-walk) |
| `highlight` | `{text \| selector}` | scroll to **and** briefly flash an outline on the first match |
| `screenshot` | — | `capturePage()`; acks `result:{url,title,image_b64}` |
| `reload` / `back` / `forward` | — | navigation on the active browser tab |
| `act` | `{kind:'click'\|'type', selector, value?}` | **GATED** — see below |

### Safety model

- **`🤖 Agent control` toggle (toolbar, DEFAULT OFF).** Show-me actions (everything except `act`) only *show*
  you things, so they run regardless. `act` (click/type) is **refused** while the toggle is OFF — the agent
  is acked `{ok:false, error:'agent control off'}`. Flip it ON to allow click/type.
- **Never silent.** Every executed agent command fires a visible, AI-accented toast (e.g. "🤖 ClaudeFather
  opened avenlur.com / highlighted …"). A blocked `act` shows a "turn on Agent control to allow it" toast.
- **Your server only.** No server configured → no polling at all. Same base + auth (`X-CC-Token` / Bearer)
  as the bridge; nothing else is ever contacted.
- The Workspace dashboard view is never driven — agent commands only ever target **browser** tabs.

## Configure

On first launch you're prompted for:

- **Server URL** — your running ClaudeFather, e.g.
  `https://your-mac.your-tailnet.ts.net:8443` or `http://localhost:8799`. No URL is hardcoded.
- **Auth token** *(optional)* — only if your dashboard has auth enabled (its `auth_token`). Leave blank otherwise.

Change either later via the **⚙** button in the tab strip.

---

## Run (development)

Requires Node.js + npm and a Mac **with a display** (it's a GUI app).

```bash
cd desktop
npm install
npm start
```

## Package a .dmg

```bash
cd desktop
npm run dist      # builds release/ with a .dmg + .zip (arm64 + x64) via electron-builder
# or, unpacked app only:
npm run pack
```

Output lands in `desktop/release/`.

---

## Known limitations / what needs a real-display test

- **Validated headlessly only.** This environment has no display, so `npm start` (which opens a window)
  can't be exercised here. The code is syntax-checked (`node --check` on every `.js`) and written to run on
  a Mac with a display. The interactive paths to verify there:
  - first-run modal → save server URL → Workspace tab loads the dashboard;
  - new Browser tab → navigate → flip capture ON → confirm the green dot, the "shared" toast, and that the
    two POSTs reach your server (and that `login`/password-manager pages are skipped);
  - tab open/close/switch and back/forward/reload.
  - **⭐ Save / `⌘⇧S`** on a browser tab → the dialog shows the screenshot preview + prefilled subject →
    pick a kind + note → Save → confirm `POST /api/clip` arrives with `image_b64` populated and the success
    toast fires. (Verify the screenshot is non-empty — `capturePage()` needs the view on-screen.)
  - **📸 Clip** → same dialog/flow as Save.
  - **🧠 Co-read / `⌘⇧E`** → panel opens, the browser view narrows by 340px, navigating fires
    `POST /api/context/page-intel`, and `related` + `flags` render; switching to the Workspace tab hides the
    panel and restores full width; sensitive pages show "Skipped".
  - **🤖 Agent-driven browser** → with your server queueing commands at `GET /api/browser/commands`:
    confirm an `open`/`navigate` command loads + activates a browser tab and a toast fires; `scroll_to` /
    `highlight` move + flash the right element; `screenshot` acks `result.image_b64` (non-empty — the view
    must be on-screen); `reload`/`back`/`forward` work; and `act` (click/type) is **refused** while the
    `🤖 Agent control` toggle is OFF (acked `{ok:false,error:'agent control off'}`, "blocked" toast) and
    **runs** once it's ON. Confirm polling only happens with a server configured, and stops if you clear it.
- **Hotkeys** are registered via `globalShortcut` only while the app window is focused (released on blur), so
  they fire even when a content view holds keyboard focus — confirm they don't leak to other apps.
- **TLS:** standard valid certs (Tailscale `ts.net`, Let's Encrypt) and `http://localhost` work out of the
  box. A self-signed dashboard cert would need a cert exception (not added by default, on purpose).
- **`electron`/`electron-builder` versions** are pinned to recent stable ranges; `npm install` will resolve
  the latest matching. `WebContentsView` requires Electron ≥ 30 (satisfied).
- Code signing / notarization for distribution outside your own machines is **not** configured (no
  certificates bundled — BYO, per ClaudeFather principles).
```
