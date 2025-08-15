# TinyIntent — Updated PRD (v1.6 + M4.1 Complete)

**Audience:** Senior ICs & PM
**Author:** Claude (updated for v1.6/M4.1)
**Status:** Final  

## 1. Overview & Goals

TinyIntent is a lightweight, local-first routing agent for macOS.  
It intercepts prompts (keyboard or iPhone voice) and routes them to:

- Claude CLI
- Ollama (local refinement/full response)
- Core ML classifier (ANE-optimized DistilBERT, <10ms)

**Current State (v1.6/M4.1):**
Production-ready system with **iPhone Shortcut flow** where the phone listens to your voice, runs the TinyIntent classifier **on-device**, and sends a small `{text, route}` payload to the Mac via secure HTTP (LAN or Tailscale). The Mac's `neuro_agent` then executes with intelligent **local model selection** (8B/32B/70B).

**M4.1 Features:**
- **70B Model Selector**: Auto-selects between 8B/32B/70B Ollama models based on content complexity and keywords
- **Worldwide Access**: Tailscale overlay network for global iPhone→Mac connectivity
- **Enhanced UX**: One-liner stderr + structured JSON stdout with detailed selection reasoning
- **Bridge Hardening**: Rate limiting, Tailscale-only mode, request size caps, comprehensive auth

### Primary Goals

- **Offline-First Routing** via ANE-optimized DistilBERT classifier
- **Flawless v1 flow** for:
  - Local Mac CLI input
  - Remote iPhone voice input via Shortcut → Mac bridge
- **Reliable "Hands"**: Claude CLI, Ollama
- **Reproducibility**: Deterministic builds via `Makefile`

## 2. Personas

- **Local Dev**: offline code summaries
- **Voice-First User**: speaks into iPhone, wants auto-routing & execution on Mac
- **Privacy-Sensitive User**: refine & execute locally

## 3. Functional Requirements

### 3.1 Router: `TinyIntent.mlmodel` (or TinyIntent.mlpackage)

- Backbone: ANE-optimized `prajjwal1/bert-tiny` (PyTorch → Core ML, INT8 ~4.2MB)
- Input: raw text
- Output: `send_claude` | `plan_then_claude` | `local_only`
- **Route-only decision**: classifier determines routing; model selection happens in neuro_agent

### 3.2 Trainer: `router/train_intent.py`

- Reads `router/data/intents.tsv` (text<TAB>label)
- 90/10 split, prints accuracy + confusion matrix
- Backbone: `prajjwal1/bert-tiny` (2 layers, H=128)
- Quantize + optimize for ANE
- Export to `router/TinyIntent.mlmodel` (or TinyIntent.mlpackage)

### 3.3 Runtime (M2): `router/TinyIntentMain.swift`

- Loads `.mlmodel` (or `.mlpackage`) from `router/`
- `MLModelConfiguration.computeUnits = .cpuAndNeuralEngine`
- CLI usage: `tinyintent "your prompt"` OR stdin
- Prints predicted label to stdout; errors to stderr

### 3.4 Hands: `agent/neuro_agent` (bash)

- **Route Execution**:
  - `send_claude`: Claude CLI
  - `plan_then_claude`: **Local refine** (Ollama) → **Cloud final** (Claude CLI)
  - `local_only`: **Strictly no outbound calls** (Ollama only)

- **Local Model Selector (M4.1)**:

| Model Size | Ollama ID | Selection Logic |
|------------|-----------|------------------|
| **8B** | `llama3.1:8b-instruct-q5_K_M` | ≤300 tokens |
| **32B** | `qwen2.5:32b-instruct-q4_K_M` | 301-1200 tokens (default) |
| **70B** | `llama3.1:70b-instruct-q4_K_M` | >1200 tokens OR keywords |

- **Environment Override**: `LOCAL_MODEL_PREF ∈ {8b,32b,70b,auto}` (default: `auto`)
- **Keyword Bump to 70B**: `["chain-of-thought","theorem","proof","formal spec","complex plan","optimize algorithm","write compiler","multi-agent orchestration","mathematical proof"]`
- **Fallback Chain**: 70B → 32B → 8B (if model unavailable)
- **Applies to**: `local_only` route and **local refine** phase of `plan_then_claude`

### 3.5 UX & Logging (M4.1)

- **Human-readable (stderr)**:
```
route=local_only model=qwen2.5:32b-instruct-q4_K_M tokens_in=45 tokens_out=127 latency_ms=2341 privacy=local_only model_size=32B reason=length=850:32b remote=local
```

- **Structured JSON (stdout with --json)**:
```json
{
  "timestamp": "2025-01-15T10:30:45.123Z",
  "route": "local_only",
  "model_name": "qwen2.5:32b-instruct-q4_K_M",
  "model_size": "32B",
  "tokens_in": 45,
  "tokens_out": 127,
  "duration_ms": 2341,
  "privacy_mode": "local_only",
  "reclassified": false,
  "selection_reason": "length=850:32b",
  "remote_addr": "local",
  "tailscale": false,
  "allowed": true,
  "source": "neuro_agent",
  "dry_run": false
}
```

- `--dry-run`: show plan only

### 3.6 iPhone Shortcut Flow & Networking

- **Shortcut (on iPhone)**  
  1) Dictate Text (on‑device)  
  2) Run Core ML Model (TinyIntent **iOS** DistilBERT export) → one of:
     `send_claude`, `plan_then_claude`, `local_only`  
  3) POST `{text, route}` to the Mac bridge endpoint with header `X-TinyIntent-Secret: <secret>`

- **Mac Bridge (`tinyrpc`)**  
  - Minimal HTTP server (Flask)  
  - Default bind: `127.0.0.1:8787` (local only), launchd-managed
  - **Global Access**: Tailscale overlay network `http://<TAILSCALE-IP>:8787/route`
  - Optional LAN via `TINYINTENT_BIND=0.0.0.0` + `ALLOW_LAN=1`
  - Requires `X-TinyIntent-Secret` header; rejects if missing/invalid  
  - Validates payload (text ≤ 8192 chars; label in whitelist)  
  - Invokes `agent/neuro_agent` (or `--dry-run` if `TINYINTENT_DRYRUN=1`)  
  - Logs one compact line per request to stderr and to `bridge/logs/tinyrpc.log`

- **Security & Hardening (M4.1)**  
  - Shared secret header required  
  - Label whitelist enforced  
  - Size caps on input  
  - LAN/Tailscale exposure **opt‑in** via env vars
  - **Rate limiting**: `RATE_LIMIT_RPS` (default 3) per-IP token bucket → 429
  - **Tailscale-only**: `TAILSCALE_ONLY=1` restricts to `100.64.0.0/10` → 403
  - **Size limits**: `MAX_BODY_KB` (default 32) → 413
  - **Privacy**: Never log raw prompt text (length/hash OK)

- **Optional Double‑Check**  
  - If `DOUBLE_CHECK=1`, Mac re‑classifies with `router/tinyintent` and may override iPhone route unless `FORCE_IPHONE=1`.

## 4. Non-Functional Requirements

- Router latency: <10ms p50
- iPhone Shortcut end-to-end: <2s
- `.mlmodel` size: <5 MB
- Model selection: <50ms additional overhead
- Clean, readable errors
- Reproducible with `make`

## 5. Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------||
| `TINYINTENT_SECRET` | *required* | Bridge authentication |
| `TINYINTENT_DRYRUN` | `0` | `1` = simulate, no exec |
| `LOCAL_MODEL_PREF` | `auto` | `8b`\|`32b`\|`70b`\|`auto` |
| `TAILSCALE_ONLY` | `0` | `1` = restrict to 100.64.0.0/10 |
| `RATE_LIMIT_RPS` | `3` | Requests/sec per IP |
| `MAX_BODY_KB` | `32` | Request size limit |
| `DOUBLE_CHECK` | `0` | `1` = reclassify on Mac |
| `FORCE_IPHONE` | `0` | `1` = trust iPhone route |
| `TINYINTENT_BIND` | `127.0.0.1` | Bridge bind address |
| `ALLOW_LAN` | `0` | `1` = allow 0.0.0.0 bind |
| `PATH` | `/opt/homebrew/bin:...` | Binary search path |

## 6. Testing Coverage

- **Smoke tests** assert presence of `exec:` commands for dry-run validation
- **JSON validation** with `jq -e` for all required fields
- **Model selector** overrides (8b/32b/70b) and auto thresholds
- **Two-phase** `plan_then_claude` with different models per phase
- **Bridge hardening** error codes: 401 (auth), 413 (size), 429 (rate), 403 (Tailscale)
- **Keyword detection** bumping to 70B model
- **Fallback chains** when models unavailable

## 7. Data

- 60+ labeled examples, 20 per class
- Favor `local_only` for ambiguous cases

## 8. Security & Privacy

- No outbound calls for `local_only`
- Shared secret auth for iPhone→Mac POST
- Logs to `~/.agent_sessions/`

## 9. Ops

- `Makefile`:
  - `make train`: train/export PyTorch → Core ML
  - `make build`: build Swift runtime
  - `make test`: run runtime on samples
  - `make agent`: run full agent
  - `make clean`: clean artifacts
  - `make ios-model` — export iOS‑targeted `.mlmodel` for Shortcuts  
  - `make bridge-venv` — create Python venv and install Flask  
  - `make bridge` — start `tinyrpc` via **launchd**  
  - `make bridge-stop` — stop `tinyrpc`  
  - `make bridge-logs` — tail bridge logs  
  - `make iphone-test` — cURL a sample POST to bridge
- Routes log to `stderr`

## 10. Architecture

```
[iPhone Voice]   [Mac CLI]
↓              ↓
[iPhone Shortcut (DistilBERT Core ML)]
↓
[POST {text, route}]
↓
[tinyrpc.py] → [neuro_agent]
↓
[Mac ANE runtime check] (optional second classify)
↓
[Claude CLI / Ollama]
↓
[stdout]
```

## 11. Risks

- Terminal quirks on blank line submit
- Model misroutes → dataset bias
- Ollama/Claude errors → handle gracefully

## 12. Milestones

- M1: PyTorch training + export (done)
- M2: Swift ANE runtime + neuro_agent
- M3: iPhone Shortcut + Mac bridge
- M4: Local model selector + enhanced UX/logging (done)
- M4.1: Bridge hardening + Tailscale networking (done)

## 13. Success

- ≥85% router accuracy
- >95% valid response rate
- <1% crash rate

## 14. Acceptance Criteria

- `make clean && make train && make build && make test` works
- `.mlmodel` <5 MB
- TUI supports model switching + dry runs (v2)
- 70B model selector with keyword detection works
- Tailscale global access functional