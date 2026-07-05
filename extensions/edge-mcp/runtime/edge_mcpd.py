#!/usr/bin/env python3
"""edge_mcpd -- ClaudeFather-managed WARM driver + CLI for any registered edge MCP server.

Generalizes the proven Sidekick daemon: reads the host/server registry, keeps ONE persistent,
transparency-proxied MCP session warm per `mode:warm` server (reachability-aware -- backs off while a
laptop host sleeps, auto-rewarms on wake), and exposes generic tool calls over a per-server unix socket.

    edge-mcp hosts                         list registered hosts (reachable?)
    edge-mcp servers                       list registered servers
    edge-mcp start  <server-id>            warm the server (idempotent)
    edge-mcp status <server-id>            {warm, reachable, ready, calls, logfile}
    edge-mcp call   <server-id> <tool> ['<json-args>']   invoke a tool, print JSON result
    edge-mcp probe  <server-id>            one-shot initialize + tools/list (no warm daemon)
    edge-mcp stop   <server-id>            stop the warm daemon

Transport per call:  daemon <-> mcp_proxy_log.py (logs every frame) <-> ssh/node-local <-> the MCP server.
Nothing hardcoded; host/account/key/launch all come from the registry (see edge_registry.py).
"""
import sys, os, json, socket, subprocess, threading, time, argparse
import edge_registry as R


def _run_pre_launch(reg, server):
    """If the server uses a recipe with a pre-launch (ensure app/browser up), run it; raise on failure."""
    if not server.get("recipe"):
        return
    import edge_recipes
    host = R.get_host(reg, server.get("host_id"))
    pl = edge_recipes.pre_launch(reg, host, server)
    if pl and not pl.get("ok"):
        raise RuntimeError("pre_launch failed: %s %s" % (pl.get("state"), pl.get("err") or ""))


STATE = R.STATE_DIR
REG_PATH = os.environ.get("EDGE_MCP_REGISTRY") or R.REGISTRY
DEV_REG = os.path.join(R.HERE, "..", "config.example.json")
LOGDIR = R.ACTIVITY_DIR


def _reg():
    return R.load_registry(REG_PATH if os.path.exists(REG_PATH) else DEV_REG)


def _paths(sid):
    return (os.path.join(STATE, "%s.sock" % sid), os.path.join(STATE, "%s.status.json" % sid),
            os.path.join(STATE, "%s.daemon.log" % sid))


class EdgeSession:
    """A generic warm MCP session over the proxy-wrapped transport. Serialized tool calls."""
    def __init__(self, reg, server):
        self.reg = reg
        self.server = server
        self.proc = None
        self.responses = {}
        self.rlock = threading.Lock()
        self.calllock = threading.Lock()
        self.nid = 0
        self.ready = False       # initialized AND (if a warm_probe is set) the probe round-trips
        self.started_at = None
        self.calls = 0

    def _spawn(self):
        os.makedirs(LOGDIR, exist_ok=True)
        cmd = R.build_transport_cmd(self.reg, self.server, LOGDIR)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        for line in iter(self.proc.stdout.readline, b""):
            try:
                msg = json.loads(line.decode("utf-8", "replace"))
            except Exception:
                continue
            if "id" in msg:
                with self.rlock:
                    self.responses[msg["id"]] = msg
        self.ready = False

    def _send(self, obj):
        self.proc.stdin.write((json.dumps(obj) + "\n").encode())
        self.proc.stdin.flush()

    def _rpc(self, method, params, timeout=90):
        with self.rlock:
            self.nid += 1
            mid = self.nid
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params})
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.rlock:
                if mid in self.responses:
                    return self.responses.pop(mid)
            if self.proc.poll() is not None:
                return None
            time.sleep(0.03)
        return None

    def _tool(self, name, args, timeout=600):
        return self._rpc("tools/call", {"name": name, "arguments": args or {}}, timeout)

    def start(self):
        _run_pre_launch(self.reg, self.server)
        self._spawn()
        init = self._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "claudefather-edge-mcp", "version": "0.1"}}, timeout=120)
        if not init:
            raise RuntimeError("MCP initialize failed (server didn't answer)")
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        probe = self.server.get("warm_probe")
        if probe:
            # some edge servers (GUI plugins) need a post-start handshake; retry the probe until it round-trips
            tool = probe.get("tool", "execute") if isinstance(probe, dict) else "execute"
            args = probe.get("args") if isinstance(probe, dict) else {"code": str(probe),
                    "description": "ClaudeFather warm probe\nManual: n/a"}
            for _ in range(15):
                r = self._tool(tool, args)
                txt = json.dumps(r) if r else ""
                if r and not (r.get("result", {}).get("isError") and "not connected" in txt):
                    self.ready = True
                    break
                time.sleep(1.2)
        else:
            self.ready = True
        self.started_at = time.time()
        return self.ready

    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def tool_call(self, name, args, timeout=600):
        with self.calllock:
            if not self.alive():
                return {"ok": False, "error": "session not alive"}
            r = self._tool(name, args, timeout)
            self.calls += 1
            if not r:
                return {"ok": False, "error": "no response (timeout or session died)"}
            res = r.get("result", {})
            is_err = res.get("isError", False)
            text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
            if is_err and "not connected" in text:
                self.ready = False
            return {"ok": not is_err, "isError": is_err, "text": text, "content": res.get("content", [])}

    def stop(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.stdin.close()
                self.proc.wait(timeout=5)
        except Exception:
            try: self.proc.terminate()
            except Exception: pass


# ---- daemon (one server) -----------------------------------------------------------------------

def _status(sid, sess, state):
    reg = state["reg"]; srv = R.get_server(reg, sid) or {}; host = R.get_host(reg, srv.get("host_id")) or {}
    st = {"server": sid, "warm": bool(sess and sess.alive()), "ready": bool(sess and sess.ready),
          "reachable": state.get("reachable"), "last_error": state.get("last_error"),
          "recipe": srv.get("recipe"), "run_mode": srv.get("mode", "per-session"),
          "host": host.get("id"), "transport": "node-local" if R.is_local_host(host) else "ssh",
          "uptime_s": round(time.time() - sess.started_at, 1) if (sess and sess.started_at) else None,
          "calls": sess.calls if sess else 0, "logfile": os.path.join(LOGDIR, sid + ".jsonl"),
          "pid": os.getpid()}
    _, statusfile, _ = _paths(sid)
    try: json.dump(st, open(statusfile, "w"))
    except Exception: pass
    return st


def daemon_main(sid):
    os.makedirs(STATE, exist_ok=True); os.makedirs(LOGDIR, exist_ok=True)
    sock, _, _ = _paths(sid)
    if os.path.exists(sock): os.remove(sock)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); srv.bind(sock); srv.listen(8)

    reg = _reg(); server = R.get_server(reg, sid)
    if not server:
        sys.stderr.write("[edge_mcpd] unknown server %r\n" % sid); return
    state = {"reg": reg, "sess": EdgeSession(reg, server), "reachable": None,
             "last_error": None, "next_retry_at": 0.0, "backoff": 5.0}

    def _try_warm():
        now = time.time()
        if state["sess"].alive() or now < state["next_retry_at"]:
            return
        host = R.get_host(reg, server.get("host_id")) or {}
        if not R.host_reachable(host):
            state["reachable"] = False
            state["last_error"] = "host unreachable (asleep / off-network?)"
            state["next_retry_at"] = now + min(state["backoff"], 30)
            state["backoff"] = min(state["backoff"] * 1.5, 30)
            return
        state["reachable"] = True
        try: state["sess"].stop()
        except Exception: pass
        s = EdgeSession(reg, server)
        try:
            s.start(); state["sess"] = s
            state["last_error"] = None if s.ready else "server up but not ready (plugin/handshake)"
            state["backoff"] = 5.0; state["next_retry_at"] = 0.0
            sys.stderr.write("[edge_mcpd:%s] warm (ready=%s)\n" % (sid, s.ready)); sys.stderr.flush()
        except Exception as e:
            state["last_error"] = "warm-up failed: %s" % e
            state["next_retry_at"] = time.time() + state["backoff"]
            state["backoff"] = min(state["backoff"] * 1.5, 60)
            sys.stderr.write("[edge_mcpd:%s] %s\n" % (sid, state["last_error"])); sys.stderr.flush()

    _try_warm()
    stop = {"v": False}
    while not stop["v"]:
        srv.settimeout(1.0)
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            _try_warm(); continue
        except Exception:
            break
        try:
            data = b""; conn.settimeout(120)
            while b"\n" not in data:
                chunk = conn.recv(65536)
                if not chunk: break
                data += chunk
            req = json.loads(data.decode("utf-8")); op = req.get("op")
            if op == "status":
                resp = _status(sid, state["sess"], state)
            elif op == "call":
                if not state["sess"].alive(): _try_warm()
                if not state["sess"].alive():
                    resp = {"ok": False, "error": state["last_error"] or "not warm", "reachable": state["reachable"]}
                else:
                    resp = state["sess"].tool_call(req.get("tool"), req.get("args"), req.get("timeout", 600))
            elif op == "stop":
                resp = {"ok": True, "stopping": True}; stop["v"] = True
            else:
                resp = {"ok": False, "error": "unknown op %r" % op}
            conn.sendall((json.dumps(resp) + "\n").encode())
        except Exception as e:
            try: conn.sendall((json.dumps({"ok": False, "error": str(e)}) + "\n").encode())
            except Exception: pass
        finally:
            conn.close()
    state["sess"].stop()
    try: os.remove(sock)
    except Exception: pass


# ---- client + CLI ------------------------------------------------------------------------------

def _client(sid, req, timeout=600):
    sock, _, _ = _paths(sid)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(timeout); s.connect(sock)
    s.sendall((json.dumps(req) + "\n").encode())
    buf = b""
    while b"\n" not in buf:
        chunk = s.recv(65536)
        if not chunk: break
        buf += chunk
    s.close(); return json.loads(buf.decode("utf-8"))


def _running(sid):
    sock, _, _ = _paths(sid)
    return os.path.exists(sock)


def _start(sid):
    if _running(sid):
        return {"ok": True, "already": True, "status": _client(sid, {"op": "status"})}
    os.makedirs(STATE, exist_ok=True)
    _, _, dlog = _paths(sid)
    subprocess.Popen([sys.executable, os.path.abspath(__file__), "_daemon", sid],
                     stdout=open(dlog, "a"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(40):
        if _running(sid):
            time.sleep(0.3)
            return {"ok": True, "started": True, "status": _client(sid, {"op": "status"})}
        time.sleep(0.3)
    return {"ok": False, "error": "daemon did not come up; see %s" % dlog}


def probe_once(sid):
    """One-shot: initialize + tools/list, no warm daemon. Proves reachability + lists the server's tools."""
    reg = _reg(); server = R.get_server(reg, sid)
    if not server: return {"ok": False, "error": "unknown server %r" % sid}
    sess = EdgeSession(reg, server)
    try:
        _run_pre_launch(reg, server)
        sess._spawn()
        init = sess._rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "edge-probe", "version": "0.1"}}, timeout=120)
        if not init: return {"ok": False, "error": "no initialize response"}
        sess._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tl = sess._rpc("tools/list", {}, timeout=30)
        tools = [t.get("name") for t in (tl or {}).get("result", {}).get("tools", [])]
        return {"ok": True, "serverInfo": init.get("result", {}).get("serverInfo"), "tools": tools}
    finally:
        sess.stop()


def _host_key(reg, host_id):
    """Print where the host's ssh key lives (vault -> materialized 0600 temp) + the user@addr target, so an
    agent can scp/ssh by hand without hunting for edge_key_*.pem in /var/folders."""
    host = R.get_host(reg, host_id)
    if not host: return {"ok": False, "error": "unknown host %r" % host_id}
    if R.is_local_host(host): return {"ok": True, "node_local": True, "note": "node-local host; no ssh key needed"}
    return {"ok": True, "key_path": R.resolve_key(host.get("key_ref")),
            "target": "%s@%s" % (host.get("ssh_user"), host.get("addr"))}


def _host_sh(reg, host_id, cmd):
    """Run a shell command ON an edge host (ssh, or locally for node-local)."""
    host = R.get_host(reg, host_id)
    if not host: return {"ok": False, "error": "unknown host %r" % host_id}
    rc, out, err = R.host_run(reg, host, cmd, timeout=120)
    return {"ok": rc == 0, "rc": rc, "stdout": out, "stderr": err}


def _scp(reg, host_id, local, remote, direction):
    """scp a file to/from an edge host using the vault-materialized key. direction: 'push' (local->host) or
    'pull' (host->local). Far more robust than base64-chunking binaries through a plugin tool."""
    host = R.get_host(reg, host_id)
    if not host: return {"ok": False, "error": "unknown host %r" % host_id}
    if R.is_local_host(host):
        return {"ok": False, "error": "host %r is node-local; use a normal filesystem path, not scp" % host_id}
    kp = R.resolve_key(host.get("key_ref"))
    target = "%s@%s" % (host.get("ssh_user"), host.get("addr"))
    opts = ["-i", kp, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
    if direction == "push":
        argv = ["scp"] + opts + [local, "%s:%s" % (target, remote)]
    else:
        argv = ["scp"] + opts + ["%s:%s" % (target, remote), local]
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        return {"ok": r.returncode == 0, "rc": r.returncode, "stderr": r.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def main():
    ap = argparse.ArgumentParser(prog="edge-mcp")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hosts"); sub.add_parser("servers")
    for c in ("start", "status", "stop", "probe"):
        sub.add_parser(c).add_argument("server")
    pc = sub.add_parser("call"); pc.add_argument("server"); pc.add_argument("tool"); pc.add_argument("args", nargs="?", default="{}")
    sub.add_parser("host-key").add_argument("host")
    hs = sub.add_parser("sh"); hs.add_argument("host"); hs.add_argument("command")
    pl = sub.add_parser("pull"); pl.add_argument("host"); pl.add_argument("remote"); pl.add_argument("local")
    ph = sub.add_parser("push"); ph.add_argument("host"); ph.add_argument("local"); ph.add_argument("remote")
    sub.add_parser("_daemon").add_argument("server")   # internal
    a = ap.parse_args()

    if a.cmd == "_daemon":
        daemon_main(a.server); return
    if a.cmd == "hosts":
        reg = _reg()
        for h in reg["hosts"]:
            mode = "node-local" if R.is_local_host(h) else "ssh:%s@%s" % (h.get("ssh_user"), h.get("addr"))
            print("%-14s %-24s %-14s reachable=%s" % (h.get("id"), mode, h.get("power", "?"), R.host_reachable(h)))
        return
    if a.cmd == "servers":
        reg = _reg()
        for s in reg["servers"]:
            print("%-20s host=%-12s mode=%-8s warm=%s" % (s.get("id"), s.get("host_id"),
                  s.get("mode", "per-session"), _running(s.get("id"))))
        return
    if a.cmd == "start":
        print(json.dumps(_start(a.server), indent=2)); return
    if a.cmd == "probe":
        print(json.dumps(probe_once(a.server), indent=2)); return
    if a.cmd == "host-key":
        print(json.dumps(_host_key(_reg(), a.host), indent=2)); return
    if a.cmd == "sh":
        print(json.dumps(_host_sh(_reg(), a.host, a.command), indent=2)); return
    if a.cmd == "pull":
        print(json.dumps(_scp(_reg(), a.host, a.remote, a.local, "pull"), indent=2)); return
    if a.cmd == "push":
        print(json.dumps(_scp(_reg(), a.host, a.local, a.remote, "push"), indent=2)); return
    if not _running(a.server) and a.cmd in ("status", "call", "stop"):
        if a.cmd == "call":
            r = _start(a.server)
            if not r.get("ok"): print(json.dumps(r)); sys.exit(1)
        else:
            print(json.dumps({"ok": False, "error": "not running; run: edge-mcp start %s" % a.server})); return
    if a.cmd == "status":
        print(json.dumps(_client(a.server, {"op": "status"}), indent=2))
    elif a.cmd == "call":
        try: args = json.loads(a.args)
        except Exception as e: print(json.dumps({"ok": False, "error": "bad json args: %s" % e})); sys.exit(1)
        print(json.dumps(_client(a.server, {"op": "call", "tool": a.tool, "args": args}), indent=2))
    elif a.cmd == "stop":
        try: print(json.dumps(_client(a.server, {"op": "stop"})))
        except Exception as e: print(json.dumps({"ok": False, "error": str(e)}))


if __name__ == "__main__":
    main()
