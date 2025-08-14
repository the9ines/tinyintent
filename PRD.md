# TinyIntent — Updated PRD (v1.5 + iPhone→Mac Flow)

**Audience:** Senior ICs & PM  
**Author:** Gemini (updated for v1.5)  
**Status:** Final  

## 1. Overview & Goals

TinyIntent is a lightweight, local-first routing agent for macOS.  
It intercepts prompts (keyboard or iPhone voice) and routes them to:

- Claude CLI
- Ollama (local refinement/full response)
- Core ML classifier (ANE-optimized DistilBERT, <10ms)

**New for v1.5:**  
Supports **iPhone Shortcut flow** where the phone listens to your voice, runs the same TinyIntent DistilBERT classifier **on-device**, and sends a small `{text, route}` payload to the Mac via secure HTTP (LAN or Tailscale). The Mac's `neuro_agent` then executes the request with the proper backend.

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

- Backbone: ANE-optimized DistilBERT (PyTorch → Core ML, <5MB, 8-bit quantized)
- Input: raw text
- Output: `send_claude` | `plan_then_claude` | `local_only`

### 3.2 Trainer: `router/train_intent.py`

- Reads `router/data/intents.tsv` (text<TAB>label)
- 90/10 split, prints accuracy + confusion matrix
- Quantize + optimize for ANE
- Export to `router/TinyIntent.mlmodel` (or TinyIntent.mlpackage)

### 3.3 Runtime (M2): `router/TinyIntentMain.swift`

- Loads `.mlmodel` (or `.mlpackage`) from `router/`
- `MLModelConfiguration.computeUnits = .cpuAndNeuralEngine`
- CLI usage: `tinyintent "your prompt"` OR stdin
- Prints predicted label to stdout; errors to stderr

### 3.4 Hands: `agent/neuro_agent` (bash)

- Routes label:
  - `send_claude`: Claude CLI
  - `plan_then_claude`: Ollama → Claude
  - `local_only`: Ollama
- Fallback order:
  1. `qwen2.5:32b-instruct-q4_K_M`
  2. `llama3.1:8b-instruct-q5_K_M`
  3. exit
- `--dry-run`: show plan only

### 3.5 iPhone Shortcut Flow (v1, required)

- **Shortcut (on iPhone)**  
  1) Dictate Text (on‑device)  
  2) Run Core ML Model (TinyIntent **iOS** DistilBERT export) → one of:
     `send_claude`, `plan_then_claude`, `local_only`  
  3) POST `{text, route}` to the Mac bridge endpoint with header `X-TinyIntent-Secret: <secret>`

- **Mac Bridge (`tinyrpc`)**  
  - Minimal HTTP server (Flask)  
  - Default bind: `127.0.0.1:8787` (local only)  
  - Optional LAN/Tailscale via `TINYINTENT_BIND=0.0.0.0`  
  - Requires `X-TinyIntent-Secret` header; rejects if missing/invalid  
  - Validates payload (text ≤ 8192 chars; label in whitelist)  
  - Invokes `agent/neuro_agent` (or `--dry-run` if `TINYINTENT_DRYRUN=1`)  
  - Logs one compact line per request to stderr and to `bridge/logs/tinyrpc.log`

- **Security**  
  - Shared secret header required  
  - Label whitelist enforced  
  - Size caps on input  
  - LAN/Tailscale exposure **opt‑in** via env vars

- **Optional Double‑Check**  
  - If `DOUBLE_CHECK=1`, Mac re‑classifies with `router/tinyintent` and may override iPhone route unless `FORCE_IPHONE=1`.

## 4. Non-Functional Requirements

- Router latency: <10ms p50
- iPhone Shortcut end-to-end: <2s
- `.mlmodel` size: <5 MB
- Clean, readable errors
- Reproducible with `make`

## 5. Data

- 60+ labeled examples, 20 per class
- Favor `local_only` for ambiguous cases

## 6. Security & Privacy

- No outbound calls for `local_only`
- Shared secret auth for iPhone→Mac POST
- Logs to `~/.agent_sessions/`

## 7. Ops

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

## 8. Architecture

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

## 9. Risks

- Terminal quirks on blank line submit
- Model misroutes → dataset bias
- Ollama/Claude errors → handle gracefully

## 10. Milestones

- M1: PyTorch training + export (done)
- M2: Swift ANE runtime + neuro_agent
- M3: iPhone Shortcut + Mac bridge
- M4: TUI integration (v2)

## 11. Success

- ≥85% router accuracy
- >95% valid response rate
- <1% crash rate

## 12. Acceptance Criteria

- `make clean && make train && make build && make test` works
- `.mlmodel` <5 MB
- TUI supports model switching + dry runs (v2)