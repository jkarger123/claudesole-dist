# ClaudeFather Dark -- setup walkthrough

Brief for the setup agent. ASCII only. Confirm exact endpoint/command at self-contained (no external service).

## What it does
A dark, high-contrast palette (deeper black, brighter gold, oxblood accent) for the dashboard UI.

## Why use it
A control center you stare at all day benefits from a tuned, low-eye-strain dark theme + consistent branding.

## How it works
Ships a theme.css scoped to [data-theme=claudefather-dark]. The server injects every installed theme's CSS into the page; you APPLY it by setting `theme: "claudefather-dark"` in the deployment cc.config (the page already renders data-theme from that).

## Prerequisites
- None (cosmetic).

## Setup steps
1. Install -> the palette is registered + injected.
2. Set `"theme": "claudefather-dark"` in this deployment's cc.config.json.
3. Restart the instance; the UI switches.

## Verify
Confirm the dashboard switches to the darker palette and contrast is comfortable.

## Usage
- A darker, higher-contrast control center for long sessions.

## Best practices / Safety
- Cosmetic only (no data access). Ensure adequate contrast. Reversible -- set theme back to godfather any time.
