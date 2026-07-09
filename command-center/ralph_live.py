#!/usr/bin/env python3
"""RALPH LIVE VIEW -- the second tab for a Ralph loop.

The runner (ralph_runner.py) streams the CURRENT iteration's claude activity (stream-json) to
<loopdir>/live.jsonl, truncating it at the start of each iteration. This script runs in the tmux session
`ralph-<name>-live` and simply FOLLOWS that file, pretty-printing each event as it happens -- so you can WATCH
whatever the current iteration is doing, live, in its own terminal tab. It auto-refreshes every iteration (it
notices the file was truncated and starts the next iteration's view). Pure stdlib.

Usage:  ralph_live.py <loop-name>
"""
import json, os, sys, time, textwrap

CC_HOME = os.environ.get("CC_HOME") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = sys.argv[1] if len(sys.argv) > 1 else ""
LOOPDIR = os.path.join(CC_HOME, "data", "ralph", NAME)
LIVE = os.path.join(LOOPDIR, "live.jsonl")

def c(s, code): return "\033[%sm%s\033[0m" % (code, s)
DIM = "2"; BOLD = "1"; CYAN = "36"; GREEN = "32"; RED = "31"; YELLOW = "33"

def _brief(inp):
    inp = inp or {}
    for k in ("command", "file_path", "path", "pattern", "url", "description", "query", "prompt"):
        v = inp.get(k)
        if v: return str(v).replace("\n", " ")[:88]
    ks = list(inp.keys())
    return (str(inp.get(ks[0]))[:70] if ks else "")

def render(e):
    t = e.get("type")
    if t == "cc_iter":
        ts = time.strftime("%H:%M:%S", time.localtime(e.get("ts", time.time())))
        print(); print(c("=" * 60, CYAN))
        print(c("  iteration %s   %s" % (e.get("iter"), ts), "1;36")); print(c("=" * 60, CYAN))
    elif t == "system" and e.get("subtype") == "init":
        print(c("  session started  model=%s  cwd=%s" % (e.get("model", "?"), os.path.basename(e.get("cwd", ""))), DIM))
    elif t == "assistant":
        for b in (e.get("message", {}).get("content") or []):
            if b.get("type") == "text":
                tx = (b.get("text") or "").strip()
                if tx:
                    for ln in (textwrap.wrap(tx, 104) or [""]): print("  " + ln)
            elif b.get("type") == "tool_use":
                print(c("  > " + str(b.get("name", "")), "1;33") + "  " + c(_brief(b.get("input")), DIM))
            elif b.get("type") == "thinking":
                th = (b.get("thinking") or "").strip().replace("\n", " ")
                if th: print(c("  * " + th[:104], DIM))
    elif t == "user":
        for b in (e.get("message", {}).get("content") or []):
            if b.get("type") == "tool_result":
                print(c("     x error" if b.get("is_error") else "     ok", RED if b.get("is_error") else GREEN))
    elif t == "result":
        dur = (e.get("duration_ms") or 0) / 1000.0
        tail = "  %s turns  %.1fs" % (e.get("num_turns"), dur)
        if e.get("total_cost_usd"): tail += "  $%.4f" % e["total_cost_usd"]
        print(c("  == iteration done (%s) ==%s" % (e.get("subtype", ""), tail), GREEN))

def main():
    print(c("Ralph live -- %s" % NAME, "1;36"))
    print(c("watching the current iteration (this view refreshes each iteration)", DIM)); print()
    off = 0; ino = None; buf = ""; idle_note = False
    while True:
        try:
            if not os.path.exists(LIVE):
                if not idle_note: print(c("  waiting for the loop to start an iteration...", DIM)); idle_note = True
                time.sleep(1); continue
            st = os.stat(LIVE)
            if ino is None: ino = st.st_ino
            if st.st_ino != ino or st.st_size < off:      # truncated/rotated -> a new iteration started
                off = 0; ino = st.st_ino; buf = ""
            if st.st_size > off:
                idle_note = False
                with open(LIVE, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(off); buf += f.read(); off = f.tell()
                while "\n" in buf:
                    ln, buf = buf.split("\n", 1); ln = ln.strip()
                    if not ln: continue
                    try: e = json.loads(ln)
                    except Exception: continue
                    try: render(e)
                    except Exception: pass
                sys.stdout.flush()
            time.sleep(0.4)
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(1)

if __name__ == "__main__":
    main()
