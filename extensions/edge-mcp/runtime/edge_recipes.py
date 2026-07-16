#!/usr/bin/env python3
"""edge_recipes -- first-class PATTERNS for the popular local-app MCPs (see EDGE_MCP_CANDIDATES.md).

A recipe encapsulates one pattern so supporting a specific server (the user's real Chrome, Blender, Photoshop,
WhatsApp) is a REGISTRY ENTRY + `recipe:` reference, not a bespoke build. A recipe supplies:
  - default_config    : knobs, merged under the server's `config`
  - mode_default      : per-session | warm
  - resolve_launch()  : the MCP-server argv to run on the host (built from config)
  - pre_launch()      : ensure the app/browser/bridge is up on the host BEFORE the session spawns (health gate)
  - setup_steps       : human text for the setup agent / add-server
  - warm_probe        : optional benign tool call to confirm end-to-end readiness

First recipe: `browser-attach` -- the #1 popular pattern (chrome-devtools-mcp, playwright-mcp, BrowserMCP):
attach an MCP server to a Chrome running with a remote-debugging port, so agents drive a REAL browser.
"""
import edge_registry as R

RECIPES = {}


def recipe(rid):
    def _reg(cls):
        RECIPES[rid] = cls
        cls.id = rid
        return cls
    return _reg


def _cfg(server, defaults):
    c = dict(defaults)
    c.update(server.get("config") or {})
    return c


def _plat(host, val):
    """Pick a per-platform value: val may be a {macos:..,windows:..} dict or a plain scalar."""
    if isinstance(val, dict):
        return val.get(host.get("platform", "macos")) or val.get("macos")
    return val


# ---- browser-attach ---------------------------------------------------------------------------

# The agent browser's profile is PERSISTENT so logins are REMEMBERED across sessions: log into Facebook (etc.)
# once and every future session returns already logged in. It lives in a DURABLE home dir -- NOT ~/.cache, which
# macOS periodically purges (that would silently drop the user's logins). `$HOME/.edge-mcp/profiles/<name>`.
DURABLE_PROFILE = "$HOME/.edge-mcp/profiles/%s"
LEGACY_PROFILE = "$HOME/.cache/edge-mcp/chrome-%s"   # old (evictable) location -> auto-migrated on next cold start

# Windows pre-launch (see BrowserAttach._pre_launch_windows). Ships base64-encoded via host_run. The run-once
# scheduled task is how a Session-0 ssh command puts a VISIBLE Chrome on the logged-on user's interactive
# desktop (Session 1). The launcher .cmd uses `start ""` so cmd returns at once (Chrome detaches, the task
# completes, and we can delete it). Prints ALREADY_UP / STARTED / FAILED as its final line.
_WIN_BROWSER_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$PORT = %(port)d
$CHROME = '%(chrome)s'
$NODEDIR = '%(node_dir)s'
%(prof_expr)s
# node preflight: the MCP server (chrome-devtools-mcp / playwright) needs Node >= 20.19. Fail LOUD here
# with the actual version rather than letting npx emit a cryptic 'does not support Node vX' error later.
if ($NODEDIR -ne '') { $NODE = Join-Path $NODEDIR 'node.exe' } else { $NODE = 'node' }
$nv = ''
try { $nv = (& $NODE --version) } catch {}
if ($nv -match '^v(\d+)\.(\d+)\.(\d+)') {
  $okNode = ([int]$Matches[1] -gt 20) -or ([int]$Matches[1] -eq 20 -and [int]$Matches[2] -ge 19)
} else { $okNode = $false }
if (-not $okNode) { Write-Output "NODE_TOO_OLD $nv"; exit 1 }
$verUrl = "http://127.0.0.1:$PORT/json/version"
try { $r = Invoke-WebRequest -UseBasicParsing -Uri $verUrl -TimeoutSec 3; if ($r.StatusCode -eq 200) { Write-Output 'ALREADY_UP'; exit 0 } } catch {}
$base = Join-Path $env:USERPROFILE '.edge-mcp'
New-Item -ItemType Directory -Force -Path $base | Out-Null
New-Item -ItemType Directory -Force -Path $PROF | Out-Null
$cmdPath = Join-Path $base ("launch-chrome-$PORT.cmd")
$body = @('@echo off', ('start "" "' + $CHROME + '" --remote-debugging-port=' + $PORT + ' --user-data-dir="' + $PROF + '" --no-first-run --no-default-browser-check%(headless)s'))
Set-Content -Path $cmdPath -Value $body -Encoding ASCII
$tn = "edgemcp_browser_$PORT"
schtasks /create /tn $tn /tr "`"$cmdPath`"" /sc ONCE /st 23:59 /f | Out-Null
schtasks /run /tn $tn | Out-Null
$ok = $false
for ($i = 0; $i -lt 30; $i++) {
  try { $r = Invoke-WebRequest -UseBasicParsing -Uri $verUrl -TimeoutSec 2; if ($r.StatusCode -eq 200) { $ok = $true; break } } catch {}
  Start-Sleep -Milliseconds 500
}
schtasks /delete /tn $tn /f | Out-Null
if ($ok) { Write-Output 'STARTED'; exit 0 } else { Write-Output 'FAILED'; exit 1 }
"""


def browser_profile(server):
    """Durable, persistent profile path for a browser-attach server (where the remembered logins live).
    Explicit config.user_data_dir wins; else config.profile_name; else a per-port default."""
    c = server.get("config") or {}
    if c.get("user_data_dir"):
        return c["user_data_dir"]
    name = c.get("profile_name") or ("chrome-%s" % c.get("debug_port", 9222))
    return DURABLE_PROFILE % name


@recipe("browser-attach")
class BrowserAttach:
    mode_default = "warm"
    default_config = {
        "mcp": "chrome-devtools",           # chrome-devtools | playwright
        "debug_port": 9222,
        "headless": False,                  # True only for a headless test box (no display)
        "user_data_dir": None,              # None -> durable per-port profile (browser_profile()); set to pin a path
        "profile_name": None,               # None -> "chrome-<port>"; set to share/separate remembered-login sets
        "chrome_bin": {"macos": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "windows": "C:/Program Files/Google/Chrome/Application/chrome.exe"},
        "npx_bin": {"macos": "/opt/homebrew/bin/npx", "windows": "npx.cmd"},
        "node_dir": None,                   # Windows only: a node dir to PREPEND to PATH (npx alone isn't
                                            # enough -- the MCP package's shim re-resolves `node` from PATH).
                                            # None -> use system node (must be >= 20.19; pre_launch enforces).
                                            # Set to a portable node dir (space-free path) if the system node
                                            # is too old and you can't upgrade it (no admin needed).
    }
    warm_probe = None                       # no plugin handshake; MCP initialize == ready

    @staticmethod
    def resolve_launch(server, host):
        import os as _os
        c = _cfg(server, BrowserAttach.default_config)
        port = c["debug_port"]
        url = "http://127.0.0.1:%s" % port
        npx = _plat(host, c["npx_bin"])
        if host.get("platform") == "windows":
            # Windows: node/npm/npx.cmd are on the system PATH for a non-interactive ssh (verified via
            # `where node`), so no env-PATH prefix and no POSIX `#!/usr/bin/env node` shebang problem.
            pkg = (["-y", "@playwright/mcp@latest", "--cdp-endpoint", url] if c["mcp"] == "playwright"
                   else ["-y", "chrome-devtools-mcp@latest", "--browserUrl", url])
            node_dir = _plat(host, c.get("node_dir"))
            if node_dir:
                # A pinned (e.g. portable) node: PREPEND its dir to PATH so BOTH npx AND the MCP package's
                # own `node` shim resolve to it. cmd.exe wrapper; node_dir must be a space-free path so no
                # nested quoting is needed (documented on the config knob). Proven live against t480.
                nd = node_dir.rstrip("\\/")
                inner = "set PATH=%s;%%PATH%% && %s\\npx.cmd %s" % (nd, nd, " ".join(pkg))
                return ["cmd", "/c", inner]
            return [npx] + pkg
        # Run the MCP server over ssh with an EXPLICIT absolute PATH (env PATH=...), not the host's login-shell
        # PATH. npx's `#!/usr/bin/env node` shebang otherwise fails with "env: node: No such file or directory"
        # on a non-interactive ssh where Homebrew's shellenv was never sourced. Fixed superset, no $PATH needed.
        nodedir = _os.path.dirname(npx) or "/opt/homebrew/bin"
        pathv = "%s:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" % nodedir
        pfx = ["env", "PATH=" + pathv]
        if c["mcp"] == "playwright":
            return pfx + [npx, "-y", "@playwright/mcp@latest", "--cdp-endpoint", url]
        # default: Chrome DevTools MCP (official)
        return pfx + [npx, "-y", "chrome-devtools-mcp@latest", "--browserUrl", url]

    @staticmethod
    def pre_launch(reg, host, server):
        """Ensure Chrome is up on the host with the remote-debugging port, using the DURABLE profile so logins
        persist. Idempotent: if the port already answers we don't touch it (never migrate a live profile); else
        we migrate any legacy ~/.cache profile to the durable home once, then launch."""
        if host.get("platform") == "windows":
            return BrowserAttach._pre_launch_windows(reg, host, server)
        c = _cfg(server, BrowserAttach.default_config)
        port = int(c["debug_port"])
        chrome = _plat(host, c["chrome_bin"])
        profile = browser_profile(server)
        legacy = LEGACY_PROFILE % port
        headless = " --headless=new" if c.get("headless") else ""
        cmd = (
            'PORT=%d\n'
            'if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then echo ALREADY_UP; exit 0; fi\n'
            'PROF="%s"; OLD="%s"\n'
            '# one-time migration: preserve logins saved under the old evictable ~/.cache location\n'
            'if [ ! -d "$PROF" ] && [ -d "$OLD" ]; then mkdir -p "$(dirname "$PROF")"; mv "$OLD" "$PROF" 2>/dev/null; fi\n'
            'mkdir -p "$PROF"\n'
            'nohup "%s" --remote-debugging-port=$PORT --user-data-dir="$PROF" '
            '--no-first-run --no-default-browser-check%s >/dev/null 2>&1 &\n'
            'for i in $(seq 1 30); do curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1 '
            '&& { echo STARTED; exit 0; }; sleep 0.5; done\n'
            'echo FAILED; exit 1\n'
        ) % (port, profile, legacy, chrome, headless)
        rc, out, err = R.host_run(reg, host, cmd, timeout=45)
        state = (out or "").strip().splitlines()[-1] if out.strip() else "FAILED"
        return {"ok": rc == 0 and state in ("ALREADY_UP", "STARTED"), "state": state,
                "port": port, "err": (err or "")[:200]}

    @staticmethod
    def _pre_launch_windows(reg, host, server):
        """Windows variant of pre_launch. A Windows OpenSSH host lands us in Session 0 (non-interactive) --
        a Chrome launched there is invisible to the logged-in user. To put a VISIBLE Chrome on the user's
        interactive desktop we go through a run-once SCHEDULED TASK: created + triggered by the ssh user
        (who is the logged-on user), it runs in that user's interactive session (Session 1) with no stored
        password. R.host_run ships this PowerShell base64-encoded (quoting-proof). Idempotent: if the port
        already answers we don't touch it. Durable profile under %USERPROFILE%\\.edge-mcp\\profiles so logins
        persist across sessions. (proven on t480: visible Chrome in Session 1 + debug port live.)"""
        c = _cfg(server, BrowserAttach.default_config)
        port = int(c["debug_port"])
        chrome = _plat(host, c["chrome_bin"])
        headless = " --headless=new" if c.get("headless") else ""
        # profile: explicit user_data_dir wins; else a durable per-name dir under the user's home
        cfg = server.get("config") or {}
        if cfg.get("user_data_dir"):
            prof_expr = "$PROF = '%s'" % cfg["user_data_dir"].replace("'", "''")
        else:
            name = cfg.get("profile_name") or ("chrome-%s" % port)
            prof_expr = "$PROF = Join-Path $env:USERPROFILE '.edge-mcp\\profiles\\%s'" % name
        node_dir = _plat(host, c.get("node_dir")) or ""
        ps = _WIN_BROWSER_PS % {
            "port": port, "chrome": chrome.replace("'", "''"),
            "prof_expr": prof_expr, "headless": headless,
            "node_dir": node_dir.replace("'", "''"),
        }
        rc, out, err = R.host_run(reg, host, ps, timeout=45)
        lines = [l for l in (out or "").strip().splitlines() if l.strip()]
        state = lines[-1].strip() if lines else "FAILED"
        ok = rc == 0 and state in ("ALREADY_UP", "STARTED")
        detail = state
        if state.startswith("NODE_TOO_OLD"):
            detail = ("%s -- need Node >= 20.19; upgrade the host's node or set this server's "
                      "config.node_dir to a newer (portable) node dir" % state)
        return {"ok": ok, "state": state, "port": port,
                "err": (detail if not ok else (err or ""))[:220]}

    setup_steps = (
        "browser-attach: drive the user's REAL Chrome. Setup:\n"
        " 1) SSH key to the host (add-host).\n"
        " 2) Chrome must be launchable on the host. By default we start a DEDICATED debug profile on a port\n"
        "    (reliable, isolated). To drive the user's LOGGED-IN sessions, set config.user_data_dir to their\n"
        "    real Chrome profile -- note Chrome 136+ blocks --remote-debugging-port on the DEFAULT profile dir,\n"
        "    so use a copied/secondary profile or chrome-devtools-mcp's autoConnect on Chrome 144+.\n"
        " 3) config.mcp = chrome-devtools (default) or playwright; config.debug_port (default 9222)."
    )


# ---- plugin-app -------------------------------------------------------------------------------

@recipe("plugin-app")
class PluginApp:
    """A GUI desktop app driven by an MCP server that talks to an in-app plugin/addon over a loopback
    socket (Sidekick/InDesign, adb-mcp/Photoshop, blender-mcp, cursor-talk-to-figma, ableton-mcp, ...).
    The server LAUNCH is per-app (config.launch); this recipe supplies the warm-session default + the
    plugin-handshake health gate (warm_probe -- retried until the app plugin round-trips). We cannot
    cold-launch a GUI app, so the app must already be OPEN with its plugin loaded (surfaced as 'not ready').
    Proven at scale via Sidekick (built a 356-page InDesign book through it)."""
    mode_default = "warm"
    default_config = {
        "launch": None,                     # argv of the app's MCP server on the host (required)
        "warm_probe": None,                 # {tool, args} benign call to confirm the plugin handshaked
        "app_hint": "open the target app with its plugin/addon loaded before use",
    }

    @staticmethod
    def resolve_launch(server, host):
        launch = server.get("launch") or (server.get("config") or {}).get("launch")
        if not launch:
            raise RuntimeError("plugin-app server %r needs a launch argv (config.launch)" % server.get("id"))
        return launch

    setup_steps = (
        "plugin-app: (1) SSH key to the host. (2) Install the app's plugin/addon + open the app with a\n"
        " document. (3) Register the server's launch argv (or use a known autodetect, e.g. --autodetect\n"
        " sidekick). The warm session keeps the plugin handshaked; calls before the plugin connects report\n"
        " 'not ready' rather than failing silently."
    )


# ---- dispatch ---------------------------------------------------------------------------------

def get(rid):
    return RECIPES.get(rid)


def resolve_launch(server, host):
    r = get(server.get("recipe"))
    if not r:
        raise RuntimeError("unknown recipe %r" % server.get("recipe"))
    return r.resolve_launch(server, host)


def pre_launch(reg, host, server):
    """Run the recipe's pre-launch (ensure app/browser up). Returns None if the recipe has no pre_launch."""
    r = get(server.get("recipe"))
    if not r or not hasattr(r, "pre_launch"):
        return None
    return r.pre_launch(reg, host, server)


def apply_defaults(server):
    """Fill a server record from its recipe (mode + warm_probe) at add-server time."""
    r = get(server.get("recipe"))
    if not r:
        return server
    server.setdefault("mode", getattr(r, "mode_default", "per-session"))
    if getattr(r, "warm_probe", None) and "warm_probe" not in server:
        server["warm_probe"] = r.warm_probe
    return server
