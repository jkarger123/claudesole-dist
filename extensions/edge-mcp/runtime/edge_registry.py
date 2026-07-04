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
import os, sys, json, shlex, socket, tempfile, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PROXY = os.path.join(HERE, "mcp_proxy_log.py")
# Per-install runtime state lives OUTSIDE the (framework/signed) extension dir -- in the deployment's gitignored
# data/ area -- so registry/keys/activity never ship with the core and stay tenant-neutral.
CC_HOME = (os.environ.get("CC_HOME")
           or (os.path.dirname(os.environ["CC_CONFIG"]) if os.environ.get("CC_CONFIG") else "")
           or os.path.abspath(os.path.join(HERE, "..", "..", "..")))   # auto-scope to the instance whose session
# set CC_CONFIG (multi-instance: one `edge-mcp` command targets each instance's own registry + vault).
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


def host_run(reg, host, remote_cmd, timeout=40):
    """Run a shell command ON an edge host (ssh, or locally for node-local). Returns (rc, stdout, stderr).
    Used by recipes for pre-launch steps (e.g. ensure the user's browser/app is up)."""
    if is_local_host(host):
        argv = ["bash", "-lc", remote_cmd]
    else:
        kp = resolve_key(host.get("key_ref"))
        argv = ["ssh", "-i", kp, "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                "%s@%s" % (host.get("ssh_user"), host.get("addr")), "bash -lc %s" % shlex.quote(remote_cmd)]
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
        remote = " ".join(shlex.quote(a) for a in inner)   # one command string for the remote shell
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
