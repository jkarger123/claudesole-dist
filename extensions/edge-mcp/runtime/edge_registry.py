#!/usr/bin/env python3
"""edge_registry -- the host/server registry + transport resolver for Edge MCP Host.

This is the generalization of the Sidekick PoC: NOTHING is hardcoded. A registry (per-install state, JSON)
lists `hosts` (any machine, any account, tailnet-reached) and `servers` (an MCP server that runs on a host).
Given a server id, `build_transport_cmd` returns the proxy-wrapped argv to launch it -- resolving BOTH modes:

  * SSH-reach  : the host is a remote machine -> ssh -i <key> user@addr <launch...>   (Layer 1)
  * node-local : the host also runs a ClaudeFather node (or is this box) -> run <launch...> directly (Layer 3)

Everything is wrapped in mcp_proxy_log.py so every edge call is transparent. Credentials are resolved via
`resolve_key` -- a `vault:KEY` ref materializes the private key to a 0600 temp file (server-side wiring), or a
direct filesystem path is used as-is (works today).
"""
import os, sys, json, shlex, socket, tempfile, subprocess, base64

HERE = os.path.dirname(os.path.abspath(__file__))
PROXY = os.path.join(HERE, "mcp_proxy_log.py")


def _find_cc_home():
    """WHICH ClaudeFather node does this CLI invocation belong to? Resolution order:
      1) CC_HOME env  (the framework exports this into every launched session -- the normal path)
      2) dir of CC_CONFIG env
      3) nearest cc.config.json walking up from CWD (a hand-run CLI inside a node's project tree)
      4) the install this runtime physically lives under (the /opt/homebrew/bin/edge-mcp symlink target)
    The single global symlink means a bare `edge-mcp` on a co-located node would otherwise silently hit the
    PRIMARY install's vault/registry (401s + split registries); this makes it scope to the right node, and
    `cc_target()` reports exactly which node it picked so nothing is silent."""
    if os.environ.get("CC_HOME"):
        return os.environ["CC_HOME"]
    if os.environ.get("CC_CONFIG"):
        return os.path.dirname(os.environ["CC_CONFIG"])
    d = os.getcwd()
    for _ in range(10):
        if os.path.isfile(os.path.join(d, "cc.config.json")):
            return d
        nd = os.path.dirname(d)
        if nd == d:
            break
        d = nd
    return os.path.abspath(os.path.join(HERE, "..", "..", ".."))


# Per-install runtime state lives OUTSIDE the (framework/signed) extension dir -- in the deployment's gitignored
# data/ area -- so registry/keys/activity never ship with the core and stay tenant-neutral.
CC_HOME = _find_cc_home()


def cc_target(cc_home=None):
    """Resolve the node's vault/API endpoint for THIS invocation: {cc_home, cfg, port, token, live}.
    `live` = whether that node's server actually answers on 127.0.0.1:<port> (so callers can give a precise
    'this session isn't scoped to this node' error instead of a raw 401/traceback)."""
    home = cc_home or CC_HOME
    cfg = (os.environ["CC_CONFIG"] if (not cc_home and os.environ.get("CC_CONFIG"))
           else os.path.join(home, "cc.config.json"))
    port, token = 8799, ""
    try:
        c = json.load(open(cfg))
        port = c.get("port") or 8799
        token = c.get("auth_token") or ""
    except Exception:
        pass
    live = False
    try:
        s = socket.create_connection(("127.0.0.1", int(port)), timeout=2); s.close(); live = True
    except Exception:
        pass
    return {"cc_home": home, "cfg": cfg, "port": port, "token": token, "live": live}


STATE_DIR = os.environ.get("EDGE_MCP_STATE") or os.path.join(CC_HOME, "data", "edge-mcp")
REGISTRY = os.path.join(STATE_DIR, "registry.json")
ACTIVITY_DIR = os.path.join(STATE_DIR, "_mcp_activity")
LOCAL_ADDRS = {"", "local", "localhost", "127.0.0.1", "::1"}


def load_registry(path):
    try:
        d = json.load(open(path))
    except Exception:
        d = {}
    d.setdefault("hosts", [])
    d.setdefault("servers", [])
    return d


def save_registry(path, reg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(reg, f, indent=2)
    os.replace(tmp, path)


def get_host(reg, host_id):
    return next((h for h in reg["hosts"] if h.get("id") == host_id), None)


def get_server(reg, server_id):
    return next((s for s in reg["servers"] if s.get("id") == server_id), None)


def is_local_host(host):
    """A host is driven WITHOUT ssh when it runs a CF node (node-local mode) or is this very box."""
    return bool(host.get("node_id")) or str(host.get("addr", "")).lower() in LOCAL_ADDRS \
        or host.get("transport_local") is True


_KEY_CACHE = {}   # key_ref -> materialized 0600 temp path (reused for this process's lifetime)


def _cc_secure_get(name):
    """Read a secret's value from THIS install's vault via the sanctioned CLI (never prints it). Tries
    `cc-secure` on PATH, then the command-center copy. Returns the value string or None."""
    import shutil
    exe = shutil.which("cc-secure")
    if not exe:
        cand = os.path.abspath(os.path.join(HERE, "..", "..", "..", "command-center", "cc-secure"))
        exe = cand if os.path.exists(cand) else None
    if not exe:
        return None
    import time as _t
    for attempt in range(3):
        try:
            r = subprocess.run([exe, "get", name], capture_output=True, text=True, timeout=15)
            v = r.stdout or ""
            if v.strip():          # non-empty check, but return the RAW value: SSH private keys must keep
                return v            # their exact bytes incl. the trailing newline (do NOT strip)
        except Exception:
            pass
        _t.sleep(0.5)
    return None


def resolve_key(key_ref):
    """Return a filesystem path to the SSH private key for `key_ref`.
      * 'vault:NAME' -> read the material from the VAULT (cc-secure get NAME) and write a 0600 temp file.
                        Falls back to the env var NAME if a server already injected it (_deploy_env path).
      * anything else -> a direct filesystem path (expanded). The value is never printed.
    """
    if not key_ref:
        return None
    if key_ref.startswith("vault:"):
        if key_ref in _KEY_CACHE and os.path.exists(_KEY_CACHE[key_ref]):
            return _KEY_CACHE[key_ref]
        name = key_ref.split(":", 1)[1]
        material = os.environ.get(name) or _cc_secure_get(name)
        if not material:
            raise RuntimeError("vault key %r not provisioned (run the edge-mcp setup / cc-secure)" % name)
        if isinstance(material, bytes):
            material = material.decode()
        if not material.endswith("\n"):     # an OpenSSH private key is invalid without a trailing newline
            material += "\n"
        fd, p = tempfile.mkstemp(prefix="edge_key_", suffix=".pem")
        os.write(fd, material.encode())
        os.close(fd)
        os.chmod(p, 0o600)
        _KEY_CACHE[key_ref] = p
        return p
    return os.path.expanduser(key_ref)


def host_reachable(host, timeout=3):
    """Cheap liveness check: node-local hosts are always reachable; ssh hosts get a TCP probe of port 22
    (so we can tell 'laptop asleep' from 'server crashed' without launching an expensive ssh)."""
    if is_local_host(host):
        return True
    try:
        s = socket.create_connection((host["addr"], 22), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def is_windows_host(host):
    """A remote edge host whose OpenSSH login shell is cmd.exe / PowerShell, not a POSIX shell.
    Recipes + transport must emit PowerShell (not bash) and use scheduled tasks for visible GUI launch."""
    return (host or {}).get("platform") == "windows"


def ps_encoded_arg(script):
    """Wrap a PowerShell script as a single `powershell -EncodedCommand` arg (base64 of UTF-16LE).
    Quoting-proof: the base64 blob carries no shell-special chars, so it survives the ssh -> cmd.exe ->
    PowerShell layers intact (the only reliable way we found to ship a script to a Windows OpenSSH host)."""
    b = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    return "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand %s" % b


def win_cmdline(argv):
    """Join an argv into one cmd.exe command line, double-quoting args that contain whitespace.
    Used to ship a Windows MCP-server launch (e.g. npx.cmd ...) over ssh into cmd.exe."""
    return " ".join(('"%s"' % a if (" " in a or "\t" in a) else a) for a in argv)


def host_run(reg, host, remote_cmd, timeout=40):
    """Run a command ON an edge host (ssh, or locally for node-local). Returns (rc, stdout, stderr).
    Used by recipes for pre-launch steps (e.g. ensure the user's browser/app is up). For a Windows host,
    `remote_cmd` must be a PowerShell script (recipes emit PowerShell there); it is shipped base64-encoded."""
    if is_local_host(host):
        argv = ["bash", "-lc", remote_cmd]
    else:
        kp = resolve_key(host.get("key_ref"))
        target = "%s@%s" % (host.get("ssh_user"), host.get("addr"))
        base = ["ssh", "-i", kp, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", target]
        if is_windows_host(host):
            argv = base + [ps_encoded_arg(remote_cmd)]
        else:
            argv = base + ["bash -lc %s" % shlex.quote(remote_cmd)]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except Exception as e:
        return 1, "", str(e)


def build_transport_cmd(reg, server, logdir, key_path=None):
    """Return the proxy-wrapped argv to launch `server`. `key_path` (optional) overrides key resolution
    (e.g. a caller that already materialized the vault key). Raises with a clear message on misconfig."""
    host = get_host(reg, server.get("host_id"))
    if not host:
        raise RuntimeError("server %r references unknown host %r" % (server.get("id"), server.get("host_id")))
    if server.get("recipe"):
        import edge_recipes
        inner = edge_recipes.resolve_launch(server, host)
    else:
        inner = server.get("launch") or []
    if not inner:
        raise RuntimeError("server %r has no launch argv" % server.get("id"))

    if is_local_host(host):
        transport = list(inner)                       # node-local: run directly, no ssh
    else:
        kp = key_path or resolve_key(host.get("key_ref"))
        if not kp:
            raise RuntimeError("host %r has no key_ref for ssh" % host.get("id"))
        # one command string for the remote shell: cmd.exe quoting on Windows, POSIX quoting elsewhere
        remote = win_cmdline(inner) if is_windows_host(host) else " ".join(shlex.quote(a) for a in inner)
        transport = ["ssh", "-i", kp, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                     "-o", "ServerAliveInterval=15", "%s@%s" % (host.get("ssh_user"), host.get("addr")),
                     remote]

    return [sys.executable, PROXY, "--label", server["id"], "--logdir", logdir, "--"] + transport


if __name__ == "__main__":
    # tiny self-check: resolve transport for every server in a registry file
    reg = load_registry(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "config.example.json"))
    for s in reg["servers"]:
        h = get_host(reg, s.get("host_id")) or {}
        mode = "node-local" if is_local_host(h) else "ssh:%s@%s" % (h.get("ssh_user"), h.get("addr"))
        try:
            cmd = build_transport_cmd(reg, s, "/tmp/_edge_activity",
                                      key_path="(KEY)" if not is_local_host(h) else None)
            print("server %-20s host=%-12s mode=%-22s" % (s["id"], h.get("id"), mode))
            print("   ->", " ".join(shlex.quote(c) for c in cmd))
        except Exception as e:
            print("server %-20s ERROR: %s" % (s.get("id"), e))
