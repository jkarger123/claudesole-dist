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

@recipe("browser-attach")
class BrowserAttach:
    mode_default = "warm"
    default_config = {
        "mcp": "chrome-devtools",           # chrome-devtools | playwright
        "debug_port": 9222,
        "headless": False,                  # True only for a headless test box (no display)
        "user_data_dir": None,              # None -> dedicated debug profile (reliable). Set to the user's real
                                            #   profile to drive their logged-in sessions (see setup note re Chrome).
        "chrome_bin": {"macos": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "windows": "C:/Program Files/Google/Chrome/Application/chrome.exe"},
        "npx_bin": {"macos": "/opt/homebrew/bin/npx", "windows": "npx.cmd"},
    }
    warm_probe = None                       # no plugin handshake; MCP initialize == ready

    @staticmethod
    def resolve_launch(server, host):
        c = _cfg(server, BrowserAttach.default_config)
        port = c["debug_port"]
        url = "http://127.0.0.1:%s" % port
        npx = _plat(host, c["npx_bin"])
        if c["mcp"] == "playwright":
            return [npx, "-y", "@playwright/mcp@latest", "--cdp-endpoint", url]
        # default: Chrome DevTools MCP (official)
        return [npx, "-y", "chrome-devtools-mcp@latest", "--browserUrl", url]

    @staticmethod
    def pre_launch(reg, host, server):
        """Ensure Chrome is running on the host with the remote-debugging port. Idempotent: if the port already
        answers we do nothing; else we launch Chrome (dedicated debug profile by default) and wait for it."""
        c = _cfg(server, BrowserAttach.default_config)
        port = int(c["debug_port"])
        chrome = _plat(host, c["chrome_bin"])
        profile = c.get("user_data_dir") or "$HOME/.cache/edge-mcp/chrome-%s" % port
        headless = " --headless=new" if c.get("headless") else ""
        cmd = (
            'PORT=%d\n'
            'if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then echo ALREADY_UP; exit 0; fi\n'
            'PROF="%s"; mkdir -p "$PROF"\n'
            'nohup "%s" --remote-debugging-port=$PORT --user-data-dir="$PROF" '
            '--no-first-run --no-default-browser-check%s >/dev/null 2>&1 &\n'
            'for i in $(seq 1 30); do curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1 '
            '&& { echo STARTED; exit 0; }; sleep 0.5; done\n'
            'echo FAILED; exit 1\n'
        ) % (port, profile, chrome, headless)
        rc, out, err = R.host_run(reg, host, cmd, timeout=45)
        state = (out or "").strip().splitlines()[-1] if out.strip() else "FAILED"
        return {"ok": rc == 0 and state in ("ALREADY_UP", "STARTED"), "state": state,
                "port": port, "err": (err or "")[:200]}

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
