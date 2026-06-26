# ClaudeFather Desktop — delivery & updates

## The model (read this — it removes most of the "installer update" labor)

ClaudeFather Desktop is a **thin shell**: an Electron window that loads your **live dashboard**
(served by `server.py`) plus a real Chromium browser. It does **not** fork or bundle the dashboard.

Consequence — there are **two independent update layers**:

| You changed… | Does the installer need rebuilding? | How users get it |
|---|---|---|
| `server.py`, the dashboard `PAGE`, lenses, features, agents, anything server-side | **No** | They reload the dashboard. The shell is just a window onto your server. This is ~99% of our work. |
| The **shell** — `desktop/main.js`, `preload.js`, `dashboard-preload.js`, `package.json` | **Yes** — cut a release | Installed apps self-update (see below) |

So "always update the installer when we ship" is **not** true: only **shell** changes need a release.

## Distribution

- **Download button:** the dashboard shows **"🎩 Try ClaudeFather Desktop"** (web runtime only —
  auto-hidden inside the desktop app). It links to GitHub Releases `latest/download` with **stable
  filenames**, so the links never change:
  - Mac Apple Silicon → `ClaudeFather-Desktop-arm64.dmg`
  - Mac Intel → `ClaudeFather-Desktop-x64.dmg`
  - Windows → `ClaudeFather-Desktop-Setup.exe`
- **Host / feed:** GitHub Releases on `jkarger123/claudesole-dist` (the public dist repo). One release
  per shell version, tag `v<version>`. This is BOTH the download source AND the auto-update feed.

## Auto-update (the shell)

`electron-updater` checks the release feed ~4s after launch:
- **Windows:** downloads in the background, installs on quit (works even unsigned). Fully automatic.
- **macOS:** unsigned apps **cannot** silently update (Squirrel.Mac requires a signature), so the app
  **notifies** the user and opens the releases page to download. To enable silent Mac updates, code-sign
  with an Apple Developer ID (`CSC_LINK`/`CSC_KEY_PASSWORD`) and remove `CSC_IDENTITY_AUTO_DISCOVERY=false`.

## Cutting a shell release

1. Bump `desktop/package.json` `"version"`.
2. Push `desktop/` to the dist mirror (`cc-update.sh` then push `claudesole-dist`) — the Windows box
   clones it to build.
3. Run `bash cf-desktop-release.sh` from Mission Control. It builds+publishes Mac here, builds Windows
   on the T490, and uploads all assets to release `v<version>`.

That's it — the download button always points at the newest release, and installed apps update themselves.
