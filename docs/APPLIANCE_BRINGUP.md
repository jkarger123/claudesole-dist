# Mac mini → ClaudeFather Appliance — bring-up runbook

The turnkey path to stand up a customer appliance on a fresh Mac. Produces a HARDENED box: the framework
CORE is read-only to the runtime user, updates + self-heal run privileged, and the install is marked
`edition: appliance` (locked). Full architecture + threat model: `docs/HARDENING.md`. IP protection (license +
obfuscation), a separate layer: `docs/IP_PROTECTION.md`.

## 0. What you need
- A Mac (mini) you've done first-boot setup on, with ONE admin account (the "installer" account).
- Xcode command line tools: `xcode-select --install`.
- `pip3 install --user cryptography` (the healer verifies the signed dist with it).
- Network (to clone the public dist).

## 1. Get the framework bundle onto the box
Clone the public dist (or copy a bundle you've prepared):
```
git clone https://github.com/jkarger123/claudesole-dist.git ~/cf-bundle/claudefather
cd ~/cf-bundle/claudefather
```

## 2. Run the hardened installer (as admin, with sudo)
```
sudo bash cf-appliance-install.sh            # add --immutable for chflags(schg) on core (max on-box integrity)
```
It will:
1. Create the non-admin runtime user `cfrun` (hidden, no shell, not in admin).
2. Copy the framework to `/Library/ClaudeFather/core` — **root-owned, read-only to cfrun**.
3. Put all writable state under `/Library/ClaudeFather/runtime` (state, deliverables, custom, secrets) — cfrun-owned.
4. Write an `edition: appliance` `cc.config.json` (writable paths redirected out of core).
5. Install two launchd services: the **runtime** (as cfrun) and the **healer/updater** (as root, every 30 min).
6. Health-check `http://localhost:8800/`.

## 3. Set the box's secrets + PIN
The runtime user owns its secrets file (outside the read-only core):
```
sudo -u cfrun nano /Library/ClaudeFather/runtime/.env.claudefather   # or: printf 'KEY=VALUE\n' | sudo tee -a ...
```
Set at least the dashboard auth token (PIN) in `cc.config.json`'s `auth_token` (edit as root in the core, then
re-lock perms — or pre-bake it before step 2). Restart: `sudo launchctl kickstart -k system/com.claudefather.runtime`.

## 4. Verify it's actually hardened
```
curl -s http://localhost:8800/api/health        # -> "edition":"appliance","integrity":"clean"
# prove the core is read-only to the runtime user (this MUST fail with Permission denied):
sudo -u cfrun touch /Library/ClaudeFather/core/command-center/server.py
# integrity posture:
curl -s -H "Cookie: cc_auth=<PIN>" http://localhost:8800/api/core-integrity
```
A correct appliance: health shows `edition appliance`; the cfrun write is DENIED; integrity is `clean`.

## 5. (Default standalone) updates + self-heal
Nothing to do — the healer pulls the signed dist every 30 min, verifies the signature, and restores any
drifted/updated core file (a customer edit to core is overwritten on the next run). To force a pass now:
```
sudo launchctl kickstart -k system/com.claudefather.healer
tail -n 40 /Library/ClaudeFather/runtime/state/healer.log
```

## 6. (Optional) enroll as a MANAGED tenant under our Mission Control
For remote support/governance (the premium model): set in `cc.config.json` `mesh_token` (the family token) +
the MC peer URL, and register the box in our MC peers. Then we can push signed superadmin actions + see it in
the portfolio. Default is standalone (no phone-home) — skip this for a self-managed customer.

## Layout reference
```
/Library/ClaudeFather/
  core/        <- framework, root:wheel, READ-ONLY to cfrun (server.py, extensions, presets, ...)
  runtime/     <- cfrun-owned, WRITABLE: state/ deliverables/ custom/ .env.claudefather .mcp.json
  dist/        <- signed public dist clone (the healer's verified source), root-owned
/Library/LaunchDaemons/
  com.claudefather.runtime.plist   <- the server, as cfrun
  com.claudefather.healer.plist    <- update+self-heal, as root, every 30m
```

## Updating the appliance's framework (you, the authoring side)
Ship as normal (the fleet ship flow in the root CLAUDE.md, including the **re-sign core** step). The appliance's
healer pulls the new signed dist within 30 min and applies it privileged. No per-box action needed.

## Uninstall
`sudo launchctl bootout system/com.claudefather.runtime; sudo launchctl bootout system/com.claudefather.healer`
then `sudo chflags -R noschg /Library/ClaudeFather 2>/dev/null; sudo rm -rf /Library/ClaudeFather /Library/LaunchDaemons/com.claudefather.*` and `sudo sysadminctl -deleteUser cfrun`.
