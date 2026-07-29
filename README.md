# TinyIntent M0 — Fresh Boot

Minimal, production-grade local baseline that starts, binds on 0.0.0.0 (configurable), authenticates via header, resolves Ollama reliably under launchd, and supports `auto|gen|act` with a preview-only ACT flow.

## 2-Minute Quickstart

```bash
git checkout -b reboot/m0-fresh-boot
bash scripts/bootstrap_fresh.sh
bash tests/health.sh
echo "summarize tinyintent" | bin/ti -r auto --json
```

## What You Get

- **Bridge**: Flask app on 0.0.0.0:8787 with authentication
- **Routes**: `gen` (local LLM), `act` (preview only), `auto` (classification)
- **CLI**: `bin/ti` helper for testing
- **Health**: `/healthz` and `/readyz` endpoints
- **Tests**: Complete test suite for validation

## iPhone Shortcut Setup

After bootstrap, get connection info:

```bash
bash scripts/print_urls_and_secret.sh
```

Configure iPhone Shortcut:
- **URL**: `http://<LAN_IP>:8787/route`
- **Header**: `X-TinyIntent-Secret: <SECRET>`
- **Body**: `{"text":"[DICTATED_TEXT]","route":"auto"}`

## Architecture

```
[iPhone Voice] → [Auto Classification] → [gen: Local LLM | act: Preview Only]
[Mac CLI]      → [TinyIntent Bridge]  → [Ollama qwen2.5:32b / llama3.1:8b]
```

## Routes

- **`gen`**: Text generation via Ollama (fallback: qwen2.5:32b → llama3.1:8b)
- **`act`**: Action preview only (`confirm_required: true`)  
- **`auto`**: Router binary classification, fallback to heuristics

## Authentication

All routes require `X-TinyIntent-Secret` header except `/healthz` and `/readyz`.

```bash
# Get secret
/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" launchd/com.tinyintent.tinyrpc.plist

# Test with curl
curl -H "X-TinyIntent-Secret: <SECRET>" \
     -H "Content-Type: application/json" \
     -d '{"text":"test message","route":"gen"}' \
     http://127.0.0.1:8787/route
```

## Environment Variables

Set in `launchd/com.tinyintent.tinyrpc.plist`:

```bash
TINYINTENT_BIND=0.0.0.0     # Bind address (default: 127.0.0.1)
TINYINTENT_PORT=8787        # Port (default: 8787)
TINYINTENT_SECRET=<secret>  # Required auth secret
OLLAMA_BIN=/path/to/ollama  # Ollama binary path
LOCAL_MODEL_PREF=auto       # Model preference: auto|8b|32b|70b
```

## Testing

```bash
# Health checks
bash tests/health.sh
bash tests/auth.sh
bash tests/bind.sh
bash tests/routes.smoke.sh

# CLI helper
echo "explain quantum computing" | bin/ti -r gen
echo "restart the service" | bin/ti -r act --json
```

## Configuration

The bridge binds to 0.0.0.0 by default for phone access. For localhost-only:

```bash
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_BIND 127.0.0.1" launchd/com.tinyintent.tinyrpc.plist
make bridge-stop && make bridge
```

## Troubleshooting

**If you see `router_classification_failed: rc=...`**:
```bash
make router-clean
make train
make build
make router-smoke
```
Or use the one-command rebuild kit:
```bash
make router-rebuild
```
- `rc=2` usually means "model missing or not readable"
- Ensure Xcode Command Line Tools are installed: `xcode-select --install`

**Router rebuild kit commands**:
- `make router-clean` - Remove compiled models and artifacts
- `make router-rebuild` - Complete rebuild with verification
- `make router-smoke` - Quick validation tests

**Missing Ollama dependency**:
```bash
bash scripts/doctor.sh
```

**Service not starting**:
```bash
make bridge-logs
```

**Authentication issues**:
```bash
bash scripts/rotate_secret.sh
```

## Development

```bash
# Build router (if needed)
make build

# Bridge lifecycle
make bridge-stop
make bridge
make bridge-logs

# Update secret
bash scripts/rotate_secret.sh
```

## Security

- Authentication required via `X-TinyIntent-Secret` header
- Local-only operation (no cloud calls)
- Real plist with secrets is git-ignored
- Secret rotation via `scripts/rotate_secret.sh`

## File Structure

```
smallintent/
├── bin/ti                          # CLI helper
├── bridge/
│   ├── tinyrpc.py                 # Flask bridge (simplified)
│   └── resolve.py                 # Ollama resolver
├── scripts/
│   ├── bootstrap_fresh.sh         # Complete setup
│   └── print_urls_and_secret.sh   # Connection info
├── tests/                         # Test suite
└── launchd/                       # Service configuration
```

This is the minimal M0 baseline. For advanced features, see [PRD.md](PRD.md).