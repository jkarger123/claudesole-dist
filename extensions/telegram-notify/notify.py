#!/usr/bin/env python3
"""telegram-notify payload: push a message to the configured Telegram chat. Self-contained (no server
import) so Ralph loops, cron jobs, or agents can call it directly:  python3 notify.py "your message"

Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from the environment, or the deployment's gitignored
.env.claudefather. Exits 0 on send, 1 if not configured / send failed. Never prints a stack trace or the
token. ASCII only."""
import os, sys, urllib.request, urllib.parse

# self-locate the deployment root: this is <CC_HOME>/extensions/telegram-notify/notify.py (portable)
DEPLOY_ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env.claudefather")

def env(key):
    v = os.environ.get(key)
    if v:
        return v
    try:
        for line in open(DEPLOY_ENV, encoding="utf-8", errors="replace"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, val = line.split("=", 1)
                if k.strip() == key:
                    return val.strip().strip('"').strip("'")
    except Exception:
        pass
    return None

def main():
    text = " ".join(sys.argv[1:]).strip() or "(empty)"
    tok, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("telegram-notify: not configured -- set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID (run Set up)")
        sys.exit(1)
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % tok, data=data)
        with urllib.request.urlopen(req, timeout=10) as r:
            if getattr(r, "status", 200) == 200:
                print("sent"); sys.exit(0)
        print("telegram-notify: Telegram API returned non-200"); sys.exit(1)
    except Exception as e:
        print("telegram-notify: send failed -- %s" % str(e)[:120]); sys.exit(1)

if __name__ == "__main__":
    main()
