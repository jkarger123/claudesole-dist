#!/usr/bin/env python3
"""verify_update.py -- supply-chain gate for cc-update (deep-audit P1-8).

Before cc-update.sh overlays framework code from an upstream, verify that the upstream is AUTHENTIC against the
trust root ALREADY on THIS box (superadmin.pub / recovery.pub) -- NOT the incoming copy. Two checks:
  1. the upstream's core.sig.json is signed by a currently-trusted owner key (Ed25519); and
  2. every framework file the update will install hash-matches that signed manifest (so the code about to run is
     exactly what the owner signed -- a swapped server.py or a swapped-in new trust root is caught).

Same canonicalization + key handling as server.py's core_sign/_sa_canon (must match byte-for-byte or it fails).

Usage:  verify_update.py <upstream_dir> <cc_home>
Exit codes (cc-update.sh maps these to its update_verify policy):
  0  VERIFIED   -- signed by a trusted key AND all signed files match. Safe to apply.
  1  FAILED     -- a signature is PRESENT but invalid, or a signed file's hash MISMATCHES (tampering / broken
                   build / untrusted signer). Never bypass this with --allow-unsigned.
  2  UNVERIFIED -- cannot verify: no core.sig upstream, no local trust root, or cryptography missing (a
                   standalone / self-authored upstream). --allow-unsigned may choose to proceed anyway.
"""
import base64, hashlib, json, os, sys

def _canon(payload):  # MUST match server.py _sa_canon exactly
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))

def _load_pub(path):
    try:
        from cryptography.hazmat.primitives import serialization
        with open(path, "rb") as f:
            return serialization.load_pem_public_key(f.read())
    except Exception:
        return None

def main(argv):
    if len(argv) < 3:
        print("verify_update: usage: verify_update.py <upstream_dir> <cc_home>"); return 2
    up, home = argv[1], argv[2]
    try:
        import cryptography  # noqa: F401
    except Exception:
        print("verify_update: UNVERIFIED -- 'cryptography' not installed, cannot check the upstream signature "
              "(install it: python3 -m pip install --user --break-system-packages cryptography)")
        return 2

    # trust root = keys ALREADY on this box (honor the same env/config overrides server.py uses)
    pub_paths = [os.environ.get("MESH_SUPERADMIN_PUBKEY") or os.path.join(home, "superadmin.pub"),
                 os.environ.get("CF_RECOVERY_PUBKEY") or os.path.join(home, "recovery.pub")]
    trusted = [k for k in (_load_pub(p) for p in pub_paths) if k is not None]
    if not trusted:
        print("verify_update: UNVERIFIED -- no local trust root (superadmin.pub) on this box, so the upstream "
              "cannot be authenticated. A standalone install without a trust root can proceed with --allow-unsigned.")
        return 2

    sig_path = os.path.join(up, "core.sig.json")
    if not os.path.isfile(sig_path):
        print("verify_update: UNVERIFIED -- the upstream ships NO core.sig.json (unsigned build). A managed node "
              "should only accept signed updates; a self-authored upstream can proceed with --allow-unsigned.")
        return 2
    try:
        doc = json.load(open(sig_path))
        payload = doc.get("payload") or {}
        sig = base64.b64decode(doc.get("sig", "") or "")
    except Exception as e:
        print("verify_update: FAILED -- upstream core.sig.json is unreadable/malformed (%s)" % e); return 1
    if not payload or not sig:
        print("verify_update: FAILED -- upstream core.sig.json has no payload/signature"); return 1

    # (1) signature must verify against a currently-trusted owner key
    msg = _canon(payload).encode()
    ok = False
    for pub in trusted:
        try:
            pub.verify(sig, msg); ok = True; break
        except Exception:
            continue
    if not ok:
        print("verify_update: FAILED -- upstream core.sig is NOT signed by a trusted owner key "
              "(superadmin.pub/recovery.pub on this box). Refusing a possibly-forged or mis-pointed upstream.")
        return 1

    # (2) every signed file the update will install must hash-match the signed manifest
    files = payload.get("files") or {}
    if not files:
        print("verify_update: FAILED -- signed manifest lists no files"); return 1
    mismatched, missing = [], []
    for rel, want in files.items():
        p = os.path.join(up, rel)
        if not os.path.isfile(p):
            missing.append(rel); continue
        try:
            got = hashlib.sha256(open(p, "rb").read()).hexdigest()
        except Exception:
            missing.append(rel); continue
        if got != want:
            mismatched.append(rel)
    if mismatched:
        print("verify_update: FAILED -- %d upstream file(s) do NOT match the signed hashes (tampered or the "
              "build was not re-signed): %s" % (len(mismatched), ", ".join(sorted(mismatched)[:8])))
        return 1
    # missing signed files are tolerated (a file legitimately removed between versions) but reported
    tail = (" (%d signed file(s) absent upstream -- removed between versions: %s)"
            % (len(missing), ", ".join(sorted(missing)[:5]))) if missing else ""
    print("verify_update: VERIFIED -- upstream v%s signed by a trusted owner key; %d/%d signed files match%s"
          % (payload.get("version", "?"), len(files) - len(missing), len(files), tail))
    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
