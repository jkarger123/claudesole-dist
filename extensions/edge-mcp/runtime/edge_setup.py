#!/usr/bin/env python3
"""edge_setup -- vault wiring + easy two-sided install for Edge MCP Host.

ClaudeFather side (one command): mint (or import) a dedicated SSH key, store the PRIVATE half in the VAULT
(never a .secrets file), register the host, and print the ONE line the user runs on THEIR machine.
User side (one copy-paste): an OS-specific snippet that enables SSH + authorizes the key. Mac AND Windows.

Secrets rule: the private key lives ONLY in the vault (`vault_put` -> /api/vault-set); it is read back at
use-time via `cc-secure get` and materialized to a 0600 temp file (see edge_registry.resolve_key). Never printed.
"""
import os, sys, json, subprocess, tempfile, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CC = os.environ.get("CC_HOME") or os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # install root (extensions/edge-mcp/runtime -> CC_HOME)
CFG = os.environ.get("CC_CONFIG") or os.path.join(CC, "cc.config.json")


def _port_token():
    try:
        c = json.load(open(CFG))
        return c.get("port") or 8799, c.get("auth_token") or ""
    except Exception:
        return 8799, ""


def vault_put(key, value, label=None, scope="*"):
    """Store a secret into THIS install's vault via the operator API. Returns the API result (no value echoed)."""
    port, tok = _port_token()
    body = json.dumps({"id": key, "value": value, "label": label or ("Edge MCP: " + key),
                       "scope": scope}).encode()
    req = urllib.request.Request("http://127.0.0.1:%s/api/vault-set" % port, data=body,
                                 headers={"Content-Type": "application/json", "X-CC-Token": tok})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


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

    else:
        print("usage: edge_setup {add-host | add-server} ...")
        sys.exit(1)
