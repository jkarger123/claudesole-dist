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
- **TLS:** standard valid certs (Tailscale `ts.net`, Let's Encrypt) and `http://localhost` work out of the
  box. A self-signed dashboard cert would need a cert exception (not added by default, on purpose).
- **`electron`/`electron-builder` versions** are pinned to recent stable ranges; `npm install` will resolve
  the latest matching. `WebContentsView` requires Electron ≥ 30 (satisfied).
- Code signing / notarization for distribution outside your own machines is **not** configured (no
  certificates bundled — BYO, per ClaudeFather principles).
```
