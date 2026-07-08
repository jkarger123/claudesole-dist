#!/usr/bin/env python3
"""edge_setup -- vault wiring + easy two-sided install for Edge MCP Host.

ClaudeFather side (one command): mint (or import) a dedicated SSH key, store the PRIVATE half in the VAULT
(never a .secrets file), register the host, and print the ONE line the user runs on THEIR machine.
User side (one copy-paste): an OS-specific snippet that enables SSH + authorizes the key. Mac AND Windows.

Secrets rule: the private key lives ONLY in the vault (`vault_put` -> /api/vault-set); it is read back at
use-time via `cc-secure get` and materialized to a 0600 temp file (see edge_registry.resolve_key). Never printed.
"""
import os, sys, json, subprocess, tempfile, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
import edge_registry as R


def vault_put(key, value, label=None, scope="*"):
    """Store a secret into THIS node's vault via the operator API. Targets the node resolved by
    edge_registry.cc_target() (env -> CWD -> runtime install). Returns a STRUCTURED result on failure
    (never raises a bare HTTPError/traceback) so the caller can show the user exactly what to fix."""
    t = R.cc_target()
    if not t["live"]:
        return {"ok": False, "error": "no ClaudeFather server answering on 127.0.0.1:%s (config %s). "
                "This CLI resolved to that node -- run it from the node's console, or set "
                "CC_CONFIG=<node>/cc.config.json." % (t["port"], t["cfg"]), "target": t["cfg"]}
    body = json.dumps({"id": key, "value": value, "label": label or ("Edge MCP: " + key),
                       "scope": scope}).encode()
    req = urllib.request.Request("http://127.0.0.1:%s/api/vault-set" % t["port"], data=body,
                                 headers={"Content-Type": "application/json", "X-CC-Token": t["token"]})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        hint = ("this session isn't scoped to this node -- re-run from the node's own console (it exports "
                "CC_CONFIG), or pass CC_CONFIG=<node>/cc.config.json" if e.code in (401, 403)
                else "the vault server rejected the write")
        return {"ok": False, "http": e.code, "target": t["cfg"],
                "error": "vault-set failed (HTTP %s) on node %s (port %s): %s" % (e.code, t["cfg"], t["port"], hint)}
    except Exception as e:
        return {"ok": False, "target": t["cfg"],
                "error": "vault-set unreachable at 127.0.0.1:%s (%s)" % (t["port"], e)}


def import_key_to_vault(key_name, private_key_path):
    """Import an EXISTING private key file into the vault under key_name (so an already-authorized key keeps
    working). Reads the file, stores it, and returns {ok, ...} -- the material is never printed."""
    with open(os.path.expanduser(private_key_path)) as f:
        material = f.read()
    res = vault_put(key_name, material)
    return res


def mint_key(key_name):
    """Generate a fresh dedicated ed25519 keypair, store the PRIVATE half in the vault, return the PUBLIC key.
    The private key never lands on disk outside a shredded temp file."""
    d = tempfile.mkdtemp(prefix="edge_mint_")
    priv = os.path.join(d, "k")
    subprocess.run(["ssh-keygen", "-t", "ed25519", "-f", priv, "-N", "", "-C", key_name, "-q"], check=True,
                   input=b"y\n", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pub = open(priv + ".pub").read().strip()
    res = vault_put(key_name, open(priv).read())
    for p in (priv, priv + ".pub"):
        try:
            with open(p, "wb") as f: f.write(b"\0" * 512)  # best-effort shred
            os.remove(p)
        except Exception: pass
    try: os.rmdir(d)
    except Exception: pass
    return pub, res


def authorize_snippet(pubkey, platform="macos", ssh_user=None):
    """The ONE thing the user runs on THEIR machine to enable SSH + authorize the key. Copy-paste, no password
    sharing. Returns a human block. `platform`: macos | windows."""
    if platform in ("win", "windows"):
        return (
            "# --- Run in PowerShell (as Administrator) on the Windows machine ---\n"
            "# 1) Enable the OpenSSH server (one-time):\n"
            "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0\n"
            "Set-Service sshd -StartupType Automatic; Start-Service sshd\n"
            "# 2) Authorize ClaudeFather's key:\n"
            "$k = '%s'\n"
            "$d = \"$env:USERPROFILE\\.ssh\"; New-Item -ItemType Directory -Force $d | Out-Null\n"
            "Add-Content \"$d\\authorized_keys\" $k\n"
            "icacls \"$d\\authorized_keys\" /inheritance:r /grant:r \"$($env:USERNAME):(R,W)\" | Out-Null\n"
            "Write-Host \"AUTHORIZED as $env:USERNAME@$env:COMPUTERNAME\"\n" % pubkey
        )
    # macOS (default)
    return (
        "# --- Run in Terminal on the Mac ---\n"
        "# 1) Enable Remote Login (one-time): System Settings > General > Sharing > Remote Login = On\n"
        "#    (or:  sudo systemsetup -setremotelogin on )\n"
        "# 2) Authorize ClaudeFather's key:\n"
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && \\\n"
        "printf '%%s\\n' \"%s\" >> ~/.ssh/authorized_keys && \\\n"
        "chmod 600 ~/.ssh/authorized_keys && echo \"AUTHORIZED as $(whoami)@$(hostname)\"\n" % pubkey
    )


def add_host(reg_path, host_id, ssh_target, platform="macos", power="laptop", key_name=None,
             import_from=None, node_id=None):
    """Register an edge host end-to-end: mint/import its key into the vault, add the host record, and return
    the public key + the user-side authorize snippet. `ssh_target` = 'user@addr' (or just 'addr' for node-local)."""
    import edge_registry as R
    reg = R.load_registry(reg_path)
    if "@" in ssh_target:
        ssh_user, addr = ssh_target.split("@", 1)
    else:
        ssh_user, addr = None, ssh_target
    key_name = key_name or ("EDGE_SSH_KEY_" + host_id.upper().replace("-", "_"))
    local = bool(node_id) or str(addr).lower() in R.LOCAL_ADDRS

    pub, res = (None, {"ok": True, "local": True})
    if not local:
        if import_from:
            res = import_key_to_vault(key_name, import_from)
            pub = subprocess.run(["ssh-keygen", "-y", "-f", os.path.expanduser(import_from)],
                                 capture_output=True, text=True).stdout.strip()
        else:
            pub, res = mint_key(key_name)
        if not res.get("ok"):
            return {"ok": False, "error": "vault store failed: %s" % res}

    host = {"id": host_id, "label": host_id, "addr": addr, "ssh_user": ssh_user,
            "key_ref": None if local else ("vault:" + key_name), "platform": platform,
            "power": power, "node_id": node_id}
    reg["hosts"] = [h for h in reg["hosts"] if h.get("id") != host_id] + [host]
    R.save_registry(reg_path, reg)
    out = {"ok": True, "host": host_id, "key_ref": host["key_ref"]}
    if pub:
        out["public_key"] = pub
        out["authorize"] = authorize_snippet(pub, platform, ssh_user)
    return out


def _host_run(reg, host, remote_cmd, timeout=20):
    """Run a shell command ON an edge host (ssh, or locally for node-local). Returns stdout str or None."""
    import edge_registry as R
    if R.is_local_host(host):
        argv = ["bash", "-lc", remote_cmd]
    else:
        kp = R.resolve_key(host.get("key_ref"))
        argv = ["ssh", "-i", kp, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                "%s@%s" % (host.get("ssh_user"), host.get("addr")), "bash -lc %s" % _shq(remote_cmd)]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _shq(s):
    import shlex
    return shlex.quote(s)


# default location the Sidekick .mcpb installs to (used when the host is asleep and can't be probed live)
_SIDEKICK_GLOB = "Library/Application Support/Claude/Claude Extensions/*indesign-sidekick*/dist/index.js"
_SIDEKICK_DEFAULT = ["/opt/homebrew/bin/node",
                     "/Users/%s/Library/Application Support/Claude/Claude Extensions/"
                     "local.mcpb.east-pole-b.v..indesign-sidekick/dist/index.js"]


def detect_sidekick(reg, host):
    """Find Sidekick's node launch on the host: (node_path, index_js). Probes live over ssh; falls back to the
    known default path (parameterized by the account) if the host is unreachable, so setup still works asleep."""
    out = _host_run(reg, host, 'node -e 0 >/dev/null 2>&1 && command -v node; '
                    'ls -1 $HOME/%s 2>/dev/null | head -1' % _SIDEKICK_GLOB)
    node_path, index_js = None, None
    if out:
        lines = [l for l in out.splitlines() if l.strip()]
        for l in lines:
            if l.endswith("index.js"):
                index_js = l.strip()
            elif "/" in l and l.strip().endswith("node"):
                node_path = l.strip()
    if not node_path:
        node_path = _host_run(reg, host, "command -v node || echo /opt/homebrew/bin/node")
        node_path = (node_path or "/opt/homebrew/bin/node").strip().splitlines()[-1]
    if index_js and node_path:
        return [node_path, index_js], True
    # fallback (host asleep): known default, parameterized by the ssh account
    d = list(_SIDEKICK_DEFAULT)
    d[1] = d[1] % (host.get("ssh_user") or "USER")
    return d, False


def add_server(reg_path, server_id, host_id, launch=None, mode="per-session", label=None,
               warm_probe=None, autodetect=None, recipe=None, config=None):
    """Register an edge MCP server in the registry. Three ways to specify what runs: `recipe` (a named pattern
    that supplies launch/health/setup), `autodetect='sidekick'`, or an explicit `launch` argv. Validates the
    host exists. Returns {ok, server, ...}."""
    import edge_registry as R
    reg = R.load_registry(reg_path)
    host = R.get_host(reg, host_id)
    if not host:
        return {"ok": False, "error": "unknown host %r (run add-host first)" % host_id}

    if recipe:
        import edge_recipes
        if not edge_recipes.get(recipe):
            return {"ok": False, "error": "unknown recipe %r (have: %s)" % (recipe, ", ".join(edge_recipes.RECIPES))}
        server = {"id": server_id, "host_id": host_id, "label": label or server_id,
                  "transport": "stdio", "recipe": recipe}
        if config:
            server["config"] = config
        edge_recipes.apply_defaults(server)
        reg["servers"] = [s for s in reg["servers"] if s.get("id") != server_id] + [server]
        R.save_registry(reg_path, reg)
        return {"ok": True, "server": server_id, "host": host_id, "recipe": recipe,
                "mode": server.get("mode"), "config": server.get("config", {}),
                "setup": getattr(edge_recipes.get(recipe), "setup_steps", None)}

    verified = None
    reg_recipe = None
    if autodetect == "sidekick" and not launch:
        launch, verified = detect_sidekick(reg, host)
        mode = "warm"; reg_recipe = "plugin-app"          # Sidekick is a plugin-app instance
        warm_probe = warm_probe or {"tool": "execute",
                    "args": {"code": "return 1;", "description": "warm probe\nManual: n/a"}}
        label = label or "Sidekick for InDesign"
    if not launch:
        return {"ok": False, "error": "no launch argv (pass -- <argv...> or --autodetect sidekick)"}
    server = {"id": server_id, "host_id": host_id, "label": label or server_id, "transport": "stdio",
              "mode": mode, "launch": launch}
    if reg_recipe:
        server["recipe"] = reg_recipe
    if warm_probe:
        server["warm_probe"] = warm_probe
    reg["servers"] = [s for s in reg["servers"] if s.get("id") != server_id] + [server]
    R.save_registry(reg_path, reg)
    return {"ok": True, "server": server_id, "host": host_id, "mode": mode, "launch": launch,
            "verified_live": verified}


# ---- host preflight + one-command browser setup -----------------------------------------------

def _key_authenticates(ssh_target, key_path):
    """True if `key_path` already logs into ssh_target non-interactively (BatchMode, no prompt)."""
    if "@" not in ssh_target:
        return False
    try:
        r = subprocess.run(["ssh", "-i", os.path.expanduser(key_path), "-o", "BatchMode=yes",
                            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
                            ssh_target, "true"], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def find_working_key(ssh_target):
    """Return the path to an already-authorized private key for this host, if one exists -- so setup can
    IMPORT it (zero copy-paste for the user) instead of minting a fresh key they'd have to authorize."""
    cands = ["~/.ssh/afp_mesh_ed25519", "~/.ssh/id_ed25519", "~/.ssh/id_rsa", "~/.ssh/imac_access"]
    for p in cands:
        ep = os.path.expanduser(p)
        if os.path.isfile(ep) and _key_authenticates(ssh_target, ep):
            return ep
    return None


_PREFLIGHT_SH = r'''
NODE=""
for p in /opt/homebrew/bin/node /usr/local/bin/node "$HOME"/.nvm/versions/node/*/bin/node; do [ -x "$p" ] && NODE="$p" && break; done
[ -z "$NODE" ] && NODE="$(command -v node 2>/dev/null)"
echo "NODE=$NODE"
NPX=""
for p in /opt/homebrew/bin/npx /usr/local/bin/npx; do [ -x "$p" ] && NPX="$p" && break; done
[ -z "$NPX" ] && NPX="$(command -v npx 2>/dev/null)"
echo "NPX=$NPX"
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
[ -x "$CH" ] && echo "CHROME=yes" || echo "CHROME=no"
echo "BREW=$(command -v brew 2>/dev/null || (ls /opt/homebrew/bin/brew 2>/dev/null))"
'''


def _probe_host(reg, host):
    out = _host_run(reg, host, _PREFLIGHT_SH, timeout=25) or ""
    kv = {}
    for ln in out.splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1); kv[k.strip()] = v.strip()
    return kv


def preflight_browser_host(reg, host, remediate=True):
    """Check (and, if remediate, auto-fix) everything the browser-attach recipe needs on the host:
    SSH reachable, Node.js present (chrome-devtools-mcp needs it), Chrome present. Returns a checklist +
    the resolved absolute npx path (so the recipe never depends on the host's login-shell PATH)."""
    import edge_registry as _R
    checks = []
    if not _R.host_reachable(host):
        checks.append({"check": "ssh", "ok": False,
                       "detail": "host unreachable on :22 (asleep / Remote Login off?)",
                       "fix": "wake the machine; enable System Settings > General > Sharing > Remote Login"})
        return {"ok": False, "checks": checks, "npx": None}
    checks.append({"check": "ssh", "ok": True, "detail": "reachable, key authorized"})

    kv = _probe_host(reg, host)
    node, npx, chrome, brew = kv.get("NODE"), kv.get("NPX"), kv.get("CHROME") == "yes", kv.get("BREW")

    if not node and remediate and brew:
        # install Node via Homebrew (no sudo). Long op -- allow several minutes.
        _host_run(reg, host, "%s install node >/dev/null 2>&1; true" % brew, timeout=420)
        kv = _probe_host(reg, host)
        node, npx = kv.get("NODE"), kv.get("NPX")
        checks.append({"check": "node", "ok": bool(node),
                       "detail": ("installed Node via Homebrew: " + node) if node else "brew install node failed",
                       "fixed": bool(node)})
    elif node:
        checks.append({"check": "node", "ok": True, "detail": node})
    else:
        checks.append({"check": "node", "ok": False,
                       "detail": "Node.js not found (chrome-devtools-mcp needs it)",
                       "fix": "install Node on the host: brew install node" if brew
                              else "install Homebrew + Node on the host"})

    checks.append({"check": "chrome", "ok": bool(chrome),
                   "detail": "Google Chrome installed" if chrome else "Google Chrome not found",
                   "fix": None if chrome else "install Google Chrome on the host"})

    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks, "npx": npx or "/opt/homebrew/bin/npx"}


def setup_browser(reg_path, host_id, ssh_target, import_from=None, platform="macos", power="laptop",
                  remediate=True, debug_port=9222, server_id=None):
    """ONE command to stand up 'drive the user's real Chrome' end-to-end: register the host (auto-importing an
    already-authorized key when one exists, else minting + printing an authorize snippet), preflight + auto-fix
    the host (Node/Chrome), register the browser-attach server, and report a single clean checklist ending in
    the ONE human step (log in). Idempotent; safe to re-run."""
    import edge_registry as _R
    server_id = server_id or ("chrome-" + host_id)
    result = {"ok": False, "host": host_id, "server": server_id, "steps": []}

    # 1) host + key -----------------------------------------------------------------------------
    if not import_from and "@" in ssh_target:
        import_from = find_working_key(ssh_target)   # reuse an already-authorized key -> no user paste
    hr = add_host(reg_path, host_id, ssh_target, platform=platform, power=power, import_from=import_from)
    if not hr.get("ok"):
        result["error"] = "host registration failed: %s" % hr.get("error")
        result["steps"].append({"check": "host", "ok": False, "detail": result["error"]})
        return result
    result["steps"].append({"check": "host", "ok": True,
                            "detail": ("imported existing authorized key" if import_from
                                       else "minted a dedicated key -- user must authorize it (see 'authorize')")})
    if hr.get("authorize"):
        result["authorize"] = hr["authorize"]        # user still needs to paste this (no working key found)

    reg = _R.load_registry(reg_path)
    host = _R.get_host(reg, host_id)

    # 2) preflight + remediate the host ---------------------------------------------------------
    pf = preflight_browser_host(reg, host, remediate=remediate)
    result["steps"].extend(pf["checks"])

    # 3) register the browser-attach server (absolute npx so it never depends on login-shell PATH) --
    cfg = {"debug_port": int(debug_port), "npx_bin": {platform: pf["npx"]}}
    sr = add_server(reg_path, server_id, host_id, recipe="browser-attach", config=cfg,
                    label="Chrome on %s" % host_id)
    result["steps"].append({"check": "server", "ok": sr.get("ok", False),
                            "detail": "registered %s (browser-attach, port %s)" % (server_id, debug_port)})
    result["config"] = cfg

    # 4) verdict + the one human step -----------------------------------------------------------
    blocking = [c for c in result["steps"] if not c.get("ok") and c["check"] in ("host", "node", "server")]
    result["ok"] = not blocking and not result.get("authorize")
    if result.get("authorize"):
        result["next"] = "Send the authorize block to the user to paste on the host, then run: edge-mcp start %s" % server_id
    elif result["ok"]:
        result["next"] = ("Run `edge-mcp start %s`, then have the user LOG IN once in the Chrome window that opens "
                          "on their machine (isolated debug profile). That login becomes the scraping session."
                          % server_id)
    else:
        result["next"] = "Resolve the failing checks above, then re-run setup-browser (it's idempotent)."
    result["consent_note"] = ("Cookies from that login persist in the host's debug profile and stay reachable by "
                              "future sessions on THIS node until revoked (edge-mcp revoke %s)." % server_id)
    return result


def import_logins(reg_path, server_id, source_profile="Default"):
    """BEST-EFFORT seed: copy the user's EXISTING Chrome logins into the agent's durable profile, so it starts
    already logged into what they use (Facebook, etc.) without logging in even once. Requires the user's Chrome
    QUIT (cookie DB is locked while it runs) and same OS user (cookies are keychain-encrypted with an app-level
    key we copy from 'Local State'). Not guaranteed per-site/platform -- if a site still asks to log in, the user
    logs in once and it's remembered thereafter (that path is bulletproof)."""
    import edge_registry as _R, edge_recipes
    reg = _R.load_registry(reg_path); server = _R.get_server(reg, server_id)
    if not server: return {"ok": False, "error": "unknown server %r" % server_id}
    host = _R.get_host(reg, server.get("host_id"))
    dest = edge_recipes.browser_profile(server)
    sh = (
        'PROF="%s"; SRC="$HOME/Library/Application Support/Google/Chrome"; SP="%s"\n'
        'pkill -f "user-data-dir=$PROF" 2>/dev/null; sleep 1\n'   # stop OUR debug Chrome so the dest profile is writable
        'if pgrep -f "Google Chrome.app/Contents/MacOS/Google Chrome" >/dev/null 2>&1; then echo CHROME_RUNNING; exit 3; fi\n'
        'if [ ! -d "$SRC/$SP" ]; then echo NO_SOURCE_PROFILE; exit 4; fi\n'
        'mkdir -p "$PROF/Default/Network"\n'
        'cp -f "$SRC/Local State" "$PROF/Local State" 2>/dev/null\n'   # app-level cookie key -> copied cookies decrypt
        'for f in "Network/Cookies" "Cookies" "Login Data" "Web Data"; do\n'
        '  [ -f "$SRC/$SP/$f" ] && { mkdir -p "$PROF/Default/$(dirname "$f")"; cp -f "$SRC/$SP/$f" "$PROF/Default/$f" 2>/dev/null; }\n'
        'done\n'
        'echo IMPORTED\n'
    ) % (dest, source_profile)
    rc, out, err = _R.host_run(reg, host, sh, timeout=60)
    state = (out or "").strip().splitlines()[-1] if (out or "").strip() else "FAILED"
    if state == "CHROME_RUNNING":
        return {"ok": False, "need": "quit_chrome",
                "error": "Chrome is running on the host. Fully QUIT Chrome (Cmd-Q) on that machine, then import "
                         "again -- the login files are locked while it's open."}
    if state == "NO_SOURCE_PROFILE":
        return {"ok": False, "error": "no Chrome profile %r found on the host (try a different --profile)" % source_profile}
    ok = (state == "IMPORTED")
    return {"ok": ok, "server": server_id, "source_profile": source_profile,
            "note": ("Seeded existing logins (best-effort). Click Start and check the sites; any that still ask "
                     "to log in, log in once and it's remembered.") if ok else "import failed: %s" % state}


def _parse_flags(a, names):
    """Pull --flag value pairs out of arg list a; returns (kw, positionals-before-'--', launch-after-'--')."""
    kw, pos, launch = {}, [], None
    i = 0
    while i < len(a):
        tok = a[i]
        if tok == "--":
            launch = a[i + 1:]
            break
        if tok.startswith("--") and tok[2:] in names:
            kw[tok[2:]] = a[i + 1]; i += 2; continue
        pos.append(tok); i += 1
    return kw, pos, launch


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else ""

    import edge_registry as _R
    REGP = _R.REGISTRY
    if cmd == "add-host":
        kw, pos, _ = _parse_flags(a[1:], {"platform", "power", "import", "node"})
        if len(pos) < 2:
            print("usage: edge-mcp add-host <host-id> <user@addr> "
                  "[--platform macos|windows] [--power laptop|always-on] [--import <privkey>] [--node <node_id>]")
            sys.exit(1)
        kw2 = {"platform": kw.get("platform", "macos"), "power": kw.get("power", "laptop"),
               "import_from": kw.get("import"), "node_id": kw.get("node")}
        r = add_host(REGP, pos[0], pos[1], **kw2)
        if r.get("authorize"):
            print(json.dumps({k: v for k, v in r.items() if k != "authorize"}, indent=2))
            print("\n===== SEND THIS TO THE USER (run on their machine) =====\n")
            print(r["authorize"])
        else:
            print(json.dumps(r, indent=2))

    elif cmd == "add-server":
        kw, pos, launch = _parse_flags(a[1:], {"mode", "label", "autodetect", "recipe", "config"})
        if len(pos) < 2:
            print("usage: edge-mcp add-server <server-id> <host-id> "
                  "[--recipe <id>] [--config '<json>'] [--mode warm|per-session] [--label \"...\"] "
                  "[--autodetect sidekick] [-- <launch argv...>]")
            sys.exit(1)
        cfg = None
        if kw.get("config"):
            try: cfg = json.loads(kw["config"])
            except Exception as e: print(json.dumps({"ok": False, "error": "bad --config json: %s" % e})); sys.exit(1)
        r = add_server(REGP, pos[0], pos[1], launch=launch, mode=kw.get("mode", "per-session"),
                       label=kw.get("label"), autodetect=kw.get("autodetect"),
                       recipe=kw.get("recipe"), config=cfg)
        print(json.dumps(r, indent=2))
        if r.get("ok") and r.get("verified_live") is False:
            print("\nNOTE: host was not reachable to verify the launch live (asleep?). Registered the known "
                  "default path; run `edge-mcp probe %s` once the host is awake to confirm." % pos[0])

    elif cmd == "setup-browser":
        kw, pos, _ = _parse_flags(a[1:], {"platform", "power", "import", "port", "server", "no-remediate"})
        if len(pos) < 2:
            print("usage: edge-mcp setup-browser <host-id> <user@addr> "
                  "[--import <privkey>] [--platform macos|windows] [--power laptop|always-on] "
                  "[--port 9222] [--server <server-id>]")
            sys.exit(1)
        r = setup_browser(REGP, pos[0], pos[1], import_from=kw.get("import"),
                          platform=kw.get("platform", "macos"), power=kw.get("power", "laptop"),
                          remediate=("no-remediate" not in kw), debug_port=kw.get("port", 9222),
                          server_id=kw.get("server"))
        auth = r.pop("authorize", None)
        print(json.dumps(r, indent=2))
        if auth:
            print("\n===== SEND THIS TO THE USER (run on their machine) =====\n")
            print(auth)

    elif cmd == "import-logins":
        kw, pos, _ = _parse_flags(a[1:], {"profile"})
        if len(pos) < 1:
            print("usage: edge-mcp import-logins <server-id> [--profile Default]"); sys.exit(1)
        print(json.dumps(import_logins(REGP, pos[0], source_profile=kw.get("profile", "Default")), indent=2))

    else:
        print("usage: edge_setup {add-host | add-server | setup-browser | import-logins} ...")
        sys.exit(1)
