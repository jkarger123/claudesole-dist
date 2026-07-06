#!/usr/bin/env python3
"""GENERATIVE video/image via a BYO provider (Google Gemini / Veo). Text->video and image->video.

The API key is passed in (the server resolves it from the vault by name -- this module never reads the vault).
Prints ONE JSON line: {ok, path, bytes, model} or {ok:false, error, filtered?}.

IMPORTANT (learned the hard way): generative video REBUILDS pixels, so the provider's safety policy REFUSES real
people -- especially children (returns raiMediaFilteredReasons, no video). This path is for products, pets,
synthetic scenes, b-roll, landscapes, and text-prompt ideas -- NOT real family footage. The analytical editor
(the rest of the Studio) is the real-people path.

CLI:  generate.py --key <API_KEY> --prompt "..." --out /abs/out.mp4 [--model veo-3.1-fast-generate-preview]
                   [--aspect 16:9|9:16] [--image /abs/still.jpg] [--negative "..."]
"""
import os, sys, json, time, base64, argparse, urllib.request, urllib.error

GLBASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "veo-3.1-fast-generate-preview"


def _post(url, body):
    r = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(r, timeout=120))


def _get(url):
    return json.load(urllib.request.urlopen(urllib.request.Request(url), timeout=120))


def veo_generate(key, prompt, out_path, model=DEFAULT_MODEL, aspect="16:9",
                 image=None, negative=None, progress=None, timeout=600):
    """Text->video (or image->video if `image` is a path). Polls the long-running op, downloads the MP4.
    progress(pct) is an optional callback. Returns a dict."""
    if not key:
        return {"ok": False, "error": "no API key"}
    if not (prompt or image):
        return {"ok": False, "error": "need a prompt (or an image to animate)"}
    inst = {"prompt": prompt or ""}
    if image and os.path.exists(image):
        mime = "image/png" if image.lower().endswith(".png") else "image/jpeg"
        inst["image"] = {"bytesBase64Encoded": base64.b64encode(open(image, "rb").read()).decode(), "mimeType": mime}
    params = {"aspectRatio": aspect}
    if negative:
        params["negativePrompt"] = negative
    try:
        op = _post("%s/models/%s:predictLongRunning?key=%s" % (GLBASE, model, key),
                   {"instances": [inst], "parameters": params})
    except urllib.error.HTTPError as e:
        try: msg = json.load(e).get("error", {}).get("message", "")
        except Exception: msg = e.reason
        return {"ok": False, "error": "provider rejected the request: %s" % str(msg)[:200]}
    except Exception as e:
        return {"ok": False, "error": "could not reach the provider: %s" % str(e)[:160]}
    name = op.get("name")
    if not name:
        return {"ok": False, "error": "no operation returned: %s" % json.dumps(op)[:200]}
    waited = 0
    while waited < timeout:
        time.sleep(8); waited += 8
        if progress:
            try: progress(min(92, 15 + waited * 80 // timeout))
            except Exception: pass
        try:
            st = _get("%s/%s?key=%s" % (GLBASE, name, key))
        except Exception:
            continue                                   # transient poll error -> keep waiting
        if st.get("error"):
            return {"ok": False, "error": str(st["error"].get("message", st["error"]))[:200]}
        if not st.get("done"):
            continue
        gvr = (st.get("response") or {}).get("generateVideoResponse") or {}
        samples = gvr.get("generatedSamples") or []
        if not samples:
            filt = gvr.get("raiMediaFilteredReasons") or gvr.get("raiMediaFilteredCount")
            if filt:
                return {"ok": False, "filtered": True,
                        "error": "The provider's safety policy filtered this generation (generative video can't "
                                 "depict real people/children). Try a products/scenery/synthetic prompt. (%s)"
                                 % (filt if isinstance(filt, str) else json.dumps(filt))[:160]}
            return {"ok": False, "error": "no video returned: %s" % json.dumps(st)[:200]}
        uri = (samples[0].get("video") or {}).get("uri")
        if not uri:
            return {"ok": False, "error": "no video uri in response"}
        try:
            sep = "&" if "?" in uri else "?"
            data = urllib.request.urlopen(urllib.request.Request(uri + sep + "key=" + key), timeout=300).read()
        except Exception as e:
            return {"ok": False, "error": "could not download the generated video: %s" % str(e)[:160]}
        with open(out_path, "wb") as f:
            f.write(data)
        return {"ok": os.path.exists(out_path) and os.path.getsize(out_path) > 1000,
                "path": out_path, "bytes": len(data), "model": model}
    return {"ok": False, "error": "generation timed out after %ss" % timeout}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.environ.get("STUDIO_GEN_KEY", ""))   # prefer env so the key isn't in argv/ps
    ap.add_argument("--prompt", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--image", default="")
    ap.add_argument("--negative", default="")
    a = ap.parse_args()
    res = veo_generate(a.key, a.prompt, a.out, model=a.model, aspect=a.aspect,
                       image=(a.image or None), negative=(a.negative or None),
                       progress=lambda p: sys.stderr.write("progress %d\n" % p))
    print(json.dumps(res))
    sys.exit(0 if res.get("ok") else 1)


if __name__ == "__main__":
    main()
