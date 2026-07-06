#!/usr/bin/env python3
"""AI Video Studio -- PROVIDER REGISTRY + capability resolution.

The studio is API-AGNOSTIC: each capability it needs (understand footage / plan the edit / generate video /
generate images / text-to-speech) can be served by whichever provider the deployment has a KEY for. This module
knows what each provider can do and, given the set of vault key NAMES the deployment holds, resolves which
providers are available and which one to use per capability. It reads ONLY key names (never values) -- the actual
secret is resolved at run time from the vault by name.

Capabilities:
  understand  -- watch clips/images, describe them, find the best moments (vision LLM)
  plan        -- turn the user's prompt + the analysis into a structured edit plan (LLM)
  image       -- generate still images (title cards, posters)
  video       -- generate net-new video clips (B-roll, intros)
  tts         -- text-to-speech (the announcer / narrator voice)
"""

CAPS = ["understand", "plan", "image", "video", "tts", "autoedit"]
# NOTE two DISTINCT families of video AI (learned the hard way 2026-07-05):
#   GENERATIVE (video/image caps: Veo, Imagen, Omni) -- rebuild pixels -> REFUSE real children (Prohibited Use
#     policy; tested + confirmed blocked on real toddler footage). Great for products/pets/synthetic, not kids.
#   CONTENT-AWARE EDITORS ("autoedit" cap: OpusClip, VEED) -- an LLM+vision model WATCHES real footage, finds the
#     highlights, cuts to the beat, renders -- WITHOUT regenerating anyone. These accept real family footage.
#   So for an "epic edit" of real people (esp. kids), route to an autoedit provider, NOT a generative one.

# Each provider: which vault key NAME(s) unlock it (any one), and the default model per capability it can do.
PROVIDERS = {
    # ---- BUILT-IN analytical editor (OUR engine: motion/highlight detection + beat-sync auto-cut + speed ramps).
    # No key, ALWAYS available. This is the real-footage path (works on kids -- no generative model, no block). ----
    "builtin": {
        "label": "Studio Editor (built-in)",
        "keys": [],   # empty -> always available (no API key required)
        "caps": {"autoedit": "studio-beatcut"},
    },
    "gemini": {
        "label": "Google Gemini",
        "keys": ["GEMINI_API_KEY", "GOOGLE_AI_API_KEY"],
        "caps": {
            "understand": "gemini-2.5-flash",
            "plan":       "gemini-2.5-pro",
            "image":      "imagen-4.0-generate-001",
            "video":      "veo-3.1-generate-preview",
            "tts":        "gemini-2.5-flash-preview-tts",
        },
    },
    "openai": {
        "label": "OpenAI",
        "keys": ["OPENAI_API_KEY"],
        "caps": {
            "understand": "gpt-4o",
            "plan":       "gpt-4o",
            "image":      "gpt-image-1",
            "tts":        "gpt-4o-mini-tts",
        },
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "keys": ["ANTHROPIC_API_KEY"],
        "caps": {
            "understand": "claude-opus-4-8",
            "plan":       "claude-opus-4-8",
        },
    },
    "elevenlabs": {
        "label": "ElevenLabs",
        "keys": ["ELEVENLABS_API_KEY", "ELEVEN_API_KEY"],
        "caps": {"tts": "eleven_multilingual_v2"},
    },
    "runway": {
        "label": "Runway",
        "keys": ["RUNWAY_API_KEY", "RUNWAYML_API_SECRET"],
        "caps": {"video": "gen3a_turbo"},  # generative -> blocks kids
    },
    # ---- CONTENT-AWARE EDITORS (analytical AI: watch -> cut -> render; accept real family footage) ----
    "opusclip": {
        "label": "OpusClip",
        "keys": ["OPUSCLIP_API_KEY", "OPUS_API_KEY"],
        "caps": {"autoedit": "opusclip-montage"},
    },
    "veed": {
        "label": "VEED",
        "keys": ["VEED_API_KEY"],
        "caps": {"autoedit": "veed-edit"},
    },
}

# When more than one provider can do a capability, prefer in this order (Gemini first -- covers the most and is
# our set-up default). Purely a default; the user can override per capability in the lens.
PREFERENCE = ["opusclip", "veed", "builtin", "gemini", "openai", "anthropic", "elevenlabs", "runway"]


def _norm(names):
    return {str(n).strip().upper() for n in (names or []) if str(n).strip()}


def available_providers(vault_key_names):
    """Given the vault key NAMES the deployment holds, return the providers that are unlocked, each with the
    key that unlocked it and the capabilities it can serve. (Names only -- never touches secret values.)"""
    have = _norm(vault_key_names)
    out = {}
    for pid, p in PROVIDERS.items():
        if not p["keys"]:                                   # keyless provider (our built-in engine) -> always on
            out[pid] = {"label": p["label"], "key": None, "caps": dict(p["caps"])}
            continue
        unlock = next((k for k in p["keys"] if k.upper() in have), None)
        if unlock:
            out[pid] = {"label": p["label"], "key": unlock, "caps": dict(p["caps"])}
    return out


def resolve(vault_key_names, overrides=None):
    """Resolve a full plan: for each capability, pick the provider to use (respecting any user overrides, else the
    preference order among available providers). Returns what's usable, what's missing, and the picks."""
    avail = available_providers(vault_key_names)
    overrides = overrides or {}
    picks, missing = {}, []
    for cap in CAPS:
        chosen = overrides.get(cap)
        if chosen and chosen in avail and cap in avail[chosen]["caps"]:
            pid = chosen
        else:
            pid = next((p for p in PREFERENCE if p in avail and cap in avail[p]["caps"]), None)
        if pid:
            picks[cap] = {"provider": pid, "label": avail[pid]["label"],
                          "model": avail[pid]["caps"][cap], "key": avail[pid]["key"]}
        else:
            missing.append(cap)
    return {
        "available": {pid: {"label": v["label"], "key": v["key"], "caps": sorted(v["caps"].keys())}
                      for pid, v in avail.items()},
        "picks": picks,
        "missing_caps": missing,
        # can we do the core job (edit existing clips with a voiceover) vs the full generative studio?
        "can_edit": all(c in picks for c in ("understand", "plan")),
        "can_generate_video": "video" in picks,        # generative (blocks kids)
        "can_autoedit": "autoedit" in picks,            # content-aware editor (works on real footage incl. kids)
        "can_voiceover": "tts" in picks,
    }


if __name__ == "__main__":
    import json, sys
    names = sys.argv[1:] or []
    print(json.dumps(resolve(names), indent=2))
