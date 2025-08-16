# TinyIntent M0 — Product Requirements Document

**Version:** 2.0 (M0 Fresh Boot)  
**Status:** Local-Only Baseline  
**Author:** Claude Code  

## 1. Overview & Goals

TinyIntent M0 is a minimal, production-grade local baseline for routing voice/text inputs to local LLM generation or action previews. This is a dramatically simplified version focused on core functionality.

### Primary Goals

- **Local-Only Operation**: Zero cloud dependencies or network calls
- **Binary Classification**: `gen` (generation) vs `act` (action preview)
- **Phone Integration**: iPhone Shortcut → Mac bridge via LAN/Tailscale
- **Production Ready**: Authentication, health checks, service management

## 2. Core Routes (v2 Simplified)

### 2.1 Generation Route (`gen`)
- **Purpose**: Text generation via local Ollama
- **Models**: qwen2.5:32b-instruct-q4_K_M → llama3.1:8b-instruct-q5_K_M (fallback)
- **Response**: `{"text": "...", "model": "...", "latency_ms": 123}`
- **Privacy**: `local_only`

### 2.2 Action Route (`act`)  
- **Purpose**: Action planning preview (NO execution)
- **Response**: `{"action": "preview", "params": {...}, "summary": "...", "confirm_required": true}`
- **Execution**: None (preview only for M0)

### 2.3 Auto Route (`auto`)
- **Purpose**: Automatic classification to `gen` or `act`
- **Method**: Router binary if available, fallback to keyword heuristics
- **Heuristics**: Action keywords (restart, tail, start, stop, logs, errors) → `act`, else → `gen`

## 3. Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  iPhone Voice   │    │   TinyIntent     │    │   Local LLM     │
│     Shortcut    │───▶│     Bridge      │───▶│     Ollama      │
└─────────────────┘    │  (Flask/8787)   │    │  qwen2.5:32b   │
                       │                  │    │  llama3.1:8b   │
┌─────────────────┐    │  Authentication  │    └─────────────────┘
│   CLI Helper    │───▶│  Health Checks   │    
│    bin/ti       │    │  Route Logic     │    ┌─────────────────┐
└─────────────────┘    └──────────────────┘    │ Action Preview  │
                                               │ (No Execution)  │
                                               └─────────────────┘
```

## 4. Components

### 4.1 Bridge (`bridge/tinyrpc.py`)
- **Framework**: Flask
- **Binding**: `TINYINTENT_BIND` (default: 127.0.0.1, configurable to 0.0.0.0)
- **Port**: `TINYINTENT_PORT` (default: 8787)
- **Endpoints**:
  - `GET /healthz` → Status, uptime, version (no auth required)
  - `GET /readyz` → Dependency checks (no auth required)  
  - `POST /route` → Main routing endpoint (auth required)

### 4.2 Authentication
- **Method**: `X-TinyIntent-Secret` header
- **Config**: `TINYINTENT_SECRET` in launchd plist
- **Error Codes**: `missing_header`, `secret_not_configured`, `mismatch`
- **Dev Bypass**: `ALLOW_DEV_LOCAL=1` for localhost (default: off)

### 4.3 CLI Helper (`bin/ti`)
- **Usage**: `echo "text" | bin/ti -r auto --json`
- **Options**: `-r/--route`, `-m/--message`, `--json`, `--host`, `--port`
- **Auth**: Reads secret from plist automatically

### 4.4 Service Management
- **Method**: launchd via `launchd/com.tinyintent.tinyrpc.plist`
- **Bootstrap**: `bash scripts/bootstrap_fresh.sh`
- **Lifecycle**: `make bridge`, `make bridge-stop`, `make bridge-logs`

## 5. Environment Configuration

Set in `launchd/com.tinyintent.tinyrpc.plist`:

```
TINYINTENT_BIND=0.0.0.0           # Phone access
TINYINTENT_PORT=8787              # Service port
TINYINTENT_SECRET=<24-char>       # Auth secret
OLLAMA_BIN=/opt/homebrew/bin/ollama
LOCAL_MODEL_PREF=auto             # auto|8b|32b|70b
PATH=/usr/local/bin:/usr/bin:/bin
```

## 6. iPhone Integration

### 6.1 Shortcut Configuration
- **URL**: `http://<LAN_IP>:8787/route`
- **Method**: POST
- **Headers**: 
  - `Content-Type: application/json`
  - `X-TinyIntent-Secret: <SECRET>`
- **Body**: `{"text": "[DICTATED_TEXT]", "route": "auto"}`

### 6.2 Network Access
- **LAN**: Direct IP access when on same network
- **Tailscale**: Global access via Tailscale overlay network
- **Security**: All requests require secret header

## 7. Testing & Validation

### 7.1 Health Checks
```bash
bash tests/health.sh       # /healthz and /readyz endpoints
bash tests/auth.sh         # Authentication flows
bash tests/bind.sh         # Port/binding configuration
bash tests/routes.smoke.sh # Route functionality
```

### 7.2 Manual Testing
```bash
# CLI testing
echo "summarize quantum computing" | bin/ti -r gen
echo "restart nginx service" | bin/ti -r act --json

# Direct curl testing  
curl -H "X-TinyIntent-Secret: $SECRET" \
     -H "Content-Type: application/json" \
     -d '{"text":"test","route":"auto"}' \
     http://127.0.0.1:8787/route
```

## 8. Error Handling

### 8.1 HTTP Status Codes
- **200**: Success
- **400**: Invalid input (bad JSON, missing text, invalid route)
- **401**: Authentication failure
- **500**: Server error (Ollama unavailable, model failure)

### 8.2 Dependency Failures
```json
{
  "error": "missing_dependency",
  "dep": "ollama",
  "code": "not_found", 
  "tried": ["/opt/homebrew/bin/ollama", "/usr/local/bin/ollama"],
  "hint": "Set OLLAMA_BIN or extend PATH in launchd plist"
}
```

## 9. Security Model

### 9.1 Local-Only Operation
- **No Cloud Calls**: All LLM inference via local Ollama
- **No Data Upload**: Text never leaves local machine
- **Privacy**: `privacy: "local_only"` in all responses

### 9.2 Authentication
- **Shared Secret**: 24-character alphanumeric string
- **Rotation**: `bash scripts/rotate_secret.sh`
- **Storage**: launchd plist (git-ignored)

### 9.3 Network Security
- **Default Binding**: 127.0.0.1 (localhost only)
- **Phone Access**: Requires explicit 0.0.0.0 binding
- **No TLS**: Assumed secure network (LAN/Tailscale)

## 10. Operational Requirements

### 10.1 Dependencies
- **Python 3.8+**: Flask runtime
- **Ollama**: Local LLM models
- **macOS**: launchd service management
- **curl/jq**: Testing tools

### 10.2 Performance
- **Bridge Latency**: <100ms for routing decisions
- **LLM Response**: 2-60s depending on model/query
- **Health Checks**: <10ms response time

### 10.3 Resource Usage
- **Memory**: ~50MB bridge + Ollama model memory
- **Disk**: Minimal (logs rotate)
- **Network**: LAN-only traffic for phone integration

## 11. Future Considerations (Out of Scope for M0)

- **Action Execution**: M0 provides preview only
- **Model Training**: Router binary assumed present
- **Advanced Auth**: OAuth, API keys, rate limiting
- **TLS/HTTPS**: Currently plain HTTP
- **Multi-User**: Single-user design

## 12. Success Criteria

- ✅ **2-Minute Setup**: Bootstrap script completes successfully
- ✅ **iPhone Integration**: Voice dictation → Mac execution  
- ✅ **Local Privacy**: Zero external network calls
- ✅ **Production Ready**: Service starts, health checks pass
- ✅ **Test Coverage**: All test suites pass

This M0 baseline provides the foundation for more advanced features while maintaining simplicity and reliability.