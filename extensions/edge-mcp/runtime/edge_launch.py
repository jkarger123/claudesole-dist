#!/usr/bin/env python3
"""edge_launch.py <server-id> -- resolve a registered edge server's transport (proxy-wrapped ssh or node-local,
with the vault SSH key materialized to a 0600 temp file) and exec it. This is the `.mcp.json` `command` that
gives a Claude Code session an edge server as a NATIVE MCP tool.

OPT-IN by design: this is wired into a session's mcp config ONLY when that session needs the edge server -- it
is NOT put in the global deployment .mcp.json, because a global entry would make EVERY session try to reach a
possibly-asleep remote laptop. Runs the recipe pre-launch (e.g. ensure the browser is up) first.
Every call still flows through the transparency proxy (build_transport_cmd wraps it)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import edge_registry as R


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("usage: edge_launch.py <server-id>\n"); sys.exit(2)
    sid = sys.argv[1]
    reg = R.load_registry(R.REGISTRY)
    server = R.get_server(reg, sid)
    if not server:
        sys.stderr.write("edge_launch: unknown server %r\n" % sid); sys.exit(1)
    try:
        import edge_recipes
        host = R.get_host(reg, server.get("host_id"))
        edge_recipes.pre_launch(reg, host, server)      # e.g. browser-attach ensures Chrome is up
    except Exception:
        pass
    cmd = R.build_transport_cmd(reg, server, R.ACTIVITY_DIR)
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()


def mcp_entry(sid):
    """Return the .mcp.json server entry that launches edge server `sid` as a native MCP tool. Callers wire this
    into a SPECIFIC session's mcp config (never the global one)."""
    return {"command": sys.executable, "args": [os.path.join(HERE, "edge_launch.py"), sid]}
