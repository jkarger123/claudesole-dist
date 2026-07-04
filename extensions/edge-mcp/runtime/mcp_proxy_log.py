#!/usr/bin/env python3
"""mcp_proxy_log.py -- a transparent, byte-exact logging shim for stdio MCP servers.

WHY: MCP stdio servers (Sidekick/InDesign, github, notion, playwright, ...) are a black box to
the client -- you see a tool name go in and (eventually) a result come out, with no visibility
into WHAT was sent, WHAT came back, or WHERE the seconds went. This proxy sits between the MCP
client (Claude Code) and the real server, forwarding every byte UNCHANGED while tee-ing a COPY
of every JSON-RPC frame to a JSONL activity log that the Command Center's "MCP Activity" lens tails.

USAGE (as an MCP `command` in .mcp.json):
    python3 mcp_proxy_log.py --label sidekick --logdir <dir> -- <real-cmd> [args...]
  e.g.
    python3 mcp_proxy_log.py --label sidekick --logdir ~/.../_mcp_activity -- \
        ssh air indesign-sidekick start

CONTRACT / SAFETY:
  * Transparency must NEVER change behavior: client<->server bytes are forwarded verbatim on a
    line boundary (MCP stdio framing is newline-delimited JSON; frames MUST NOT contain embedded
    newlines per the MCP spec). We parse a COPY for logging only; a parse failure is logged and
    the raw line is still forwarded.
  * Logging must NEVER break the stream: every log write is best-effort inside try/except.
  * The child's stderr is captured to the log (many servers log there) AND mirrored to our stderr
    so the client still sees it.

The activity log is append-only newline-delimited JSON. One record per frame:
    {t, ev, label, dir, method?, id?, dt_ms?, bytes, preview, is_error?}
  ev: "req" (client->server request w/ id), "notify" (either dir, no id), "resp" (server->client
      response, dt_ms = round-trip since its req), "stderr", "life" (proxy lifecycle).
"""
import sys, os, json, time, threading, subprocess, argparse

PREVIEW_MAX = 2000          # chars of params/result kept in the log (full size also recorded)


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()) + (".%03d" % int((time.time() % 1) * 1000))


class Activity:
    """Append-only JSONL sink + request/response latency matcher. Thread-safe."""
    def __init__(self, path, label):
        self.path = path
        self.label = label
        self.lock = threading.Lock()
        self.pending = {}       # jsonrpc id -> (method, monotonic_start)

    def _write(self, rec):
        rec.setdefault("t", _now())
        rec.setdefault("label", self.label)
        try:
            with self.lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass  # never let logging break the proxy

    def life(self, msg, **kw):
        self._write(dict(ev="life", msg=msg, **kw))

    def stderr(self, line):
        self._write(dict(ev="stderr", preview=line[:PREVIEW_MAX], bytes=len(line)))

    def frame(self, direction, raw):
        """direction: 'c2s' (client->server) or 's2c' (server->client). raw = decoded str line."""
        try:
            msg = json.loads(raw)
        except Exception:
            self._write(dict(ev="raw", dir=direction, bytes=len(raw), preview=raw[:PREVIEW_MAX]))
            return
        mid = msg.get("id")
        method = msg.get("method")
        # request/notification (has method); response (has result/error, no method)
        if method is not None:
            payload = msg.get("params")
            ev = "req" if mid is not None else "notify"
            rec = dict(ev=ev, dir=direction, method=method, bytes=len(raw),
                       preview=_preview(payload))
            if mid is not None:
                rec["id"] = mid
                self.pending[_k(mid)] = (method, time.monotonic())
            self._write(rec)
        else:
            # a response to a prior request
            is_err = "error" in msg
            method, dt = None, None
            info = self.pending.pop(_k(mid), None)
            if info:
                method, t0 = info
                dt = round((time.monotonic() - t0) * 1000, 1)
            body = msg.get("error") if is_err else msg.get("result")
            self._write(dict(ev="resp", dir=direction, id=mid, method=method, dt_ms=dt,
                             is_error=is_err, bytes=len(raw), preview=_preview(body)))


def _k(mid):
    return json.dumps(mid, sort_keys=True) if not isinstance(mid, (str, int)) else str(mid)


def _preview(obj):
    if obj is None:
        return None
    try:
        s = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    except Exception:
        s = str(obj)
    return s[:PREVIEW_MAX] + (" …[+%d]" % (len(s) - PREVIEW_MAX) if len(s) > PREVIEW_MAX else "")


def _pump(src, dst, act, direction, close_dst=False):
    """Forward newline-delimited frames src->dst byte-exact, tee a copy to the activity log.
    close_dst: propagate EOF by closing dst when src ends -- ONLY for client->child (so the child sees
    EOF and exits); never for child->our-stdout (closing our own stdout would break the final flush)."""
    try:
        for line in iter(src.readline, b""):
            try:
                dst.write(line)
                dst.flush()
            except Exception:
                break  # downstream closed -> stop; the other pump / waiter handles teardown
            try:
                act.frame(direction, line.decode("utf-8", "replace").rstrip("\r\n"))
            except Exception:
                pass
    except Exception:
        pass
    # src hit EOF: propagate the close downstream ONLY when asked (client->child), so the child exits.
    if close_dst:
        try:
            dst.close()
        except Exception:
            pass


def _pump_stderr(src, act):
    try:
        for line in iter(src.readline, b""):
            txt = line.decode("utf-8", "replace").rstrip("\r\n")
            if txt:
                act.stderr(txt)
            try:
                sys.stderr.buffer.write(line)
                sys.stderr.buffer.flush()
            except Exception:
                pass
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, help="server name (used for the log filename)")
    ap.add_argument("--logdir", required=True, help="dir for <label>.jsonl activity log")
    ap.add_argument("cmd", nargs=argparse.REMAINDER, help="-- real server command + args")
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        sys.stderr.write("mcp_proxy_log: no server command given after --\n")
        sys.exit(2)

    os.makedirs(a.logdir, exist_ok=True)
    act = Activity(os.path.join(a.logdir, a.label + ".jsonl"), a.label)
    act.life("start", cmd=cmd, pid=os.getpid())

    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, bufsize=0)
    except Exception as e:
        act.life("spawn_failed", error=str(e))
        sys.stderr.write("mcp_proxy_log: failed to spawn %r: %s\n" % (cmd, e))
        sys.exit(1)

    stdin_b = sys.stdin.buffer if hasattr(sys.stdin, "buffer") else sys.stdin
    stdout_b = sys.stdout.buffer if hasattr(sys.stdout, "buffer") else sys.stdout

    threads = [
        threading.Thread(target=_pump, args=(stdin_b, proc.stdin, act, "c2s"), kwargs={"close_dst": True}, daemon=True),
        threading.Thread(target=_pump, args=(proc.stdout, stdout_b, act, "s2c"), daemon=True),
        threading.Thread(target=_pump_stderr, args=(proc.stderr, act), daemon=True),
    ]
    for t in threads:
        t.start()

    rc = proc.wait()
    act.life("exit", returncode=rc)
    # give the s2c/stderr pumps a beat to flush the tail, then hard-exit: the c2s pump is a daemon
    # thread blocked on stdin.readline (nothing more coming), and a normal interpreter finalize would
    # try to acquire its buffered-reader lock and abort with a fatal error. os._exit skips finalizers.
    for t in threads[1:]:
        t.join(timeout=1.0)
    try:
        sys.stdout.flush(); sys.stderr.flush()
    except Exception:
        pass
    os._exit(rc if rc is not None else 0)


if __name__ == "__main__":
    main()
