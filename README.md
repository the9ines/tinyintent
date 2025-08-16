# TinyIntent (Mac-first, local-only)

- Start with **PRD.md** for scope.
- All inference is **local-only** via Ollama.
- Endpoints: `/healthz`, `/readyz`, `/route`, `/admin/reload-models`, `/feedback`.

Quickstart:
1) `make bootstrap`
2) Create LaunchAgent (next block) and load it
3) `bash tests/health.sh && bash tests/auth.sh && bash tests/routes.smoke.sh && bash tests/models_registry.sh`
4) `make doctor`

iOS Shortcut:
- URL: `http://<tailscale-or-LAN-ip>:8787/route`
- Headers: `Content-Type: application/json`, `X-TinyIntent-Secret: <value>`
- JSON: `{ "text": (Dictated Text), "route": "auto" }`
