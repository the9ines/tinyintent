# TinyIntent — Operating Guide & Prompt Library

## Repo & Workflow

- **Repo:** `git@github.com:the9ines/tinyintent.git`
- **Root:** `/Users/oberfelder/projects/smallintent`
- **Default branch:** `main`
- **Do NOT commit:** trained models (`router/TinyIntent*.ml*`), compiled bundles (`*.mlmodelc/`), logs, virtualenvs, or the real launchd plist with secrets.
- **Sample config:** `launchd/com.tinyintent.tinyrpc.sample.plist` → copy to `launchd/com.tinyintent.tinyrpc.plist` and set `TINYINTENT_SECRET`.
- **Commit style:** Conventional Commits (e.g., `feat: …`, `fix: …`, `chore: …`).
- **Typical workflow:**
  ```bash
  git checkout -b feat/<short-name>
  # edit files
  git add -A
  git commit -m "feat: add <thing>"
  git push -u origin HEAD
  # open PR on GitHub
  ```
- **Release (optional):**
  ```bash
  git tag -a v0.1.0 -m "v0.1.0"
  git push --tags
  ```

## 0) Header & Quick Facts

- **Project**: TinyIntent
- **Root**: `/Users/oberfelder/projects/smallintent/`
- **Router model (MLProgram)**: `router/TinyIntent.mlpackage` *(or legacy `router/TinyIntent.mlmodel`)*
- **iOS copy**: `router/TinyIntent_iOS.mlpackage`
- **Swift runner**: `router/tinyintent`
- **Bridge**: `bridge/tinyrpc.py` via launchd plist `launchd/com.tinyintent.tinyrpc.plist`
- **Agent**: `agent/neuro_agent`
- **Data**: `router/data/intents.tsv` (`text<TAB>label`, no header)
- **Labels (fixed)**: `send_claude`, `plan_then_claude`, `local_only`
- **Size budget**: **< 5 MB** package size
- **ANE config**: **`.cpuAndNeuralEngine`** everywhere
- **Current status**: **M1/M2 done; M3 in progress (bridge)**

## 1) Canonical File Tree (what should exist)

```
smallintent/
├── PRD.md
├── claude.md                <-- (this file)
├── Makefile
├── agent/
│   └── neuro_agent
├── router/
│   ├── data/intents.tsv
│   ├── train_intent.py
│   ├── TinyIntent.mlpackage   (or TinyIntent.mlmodel)
│   ├── TinyIntent_iOS.mlpackage
│   ├── Sources/TinyIntentMain/TinyIntentMain.swift
│   ├── export_ios_model.py
│   ├── Package.swift
│   └── tinyintent             (built binary)
├── bridge/
│   ├── tinyrpc.py
│   ├── requirements_bridge.txt
│   └── logs/
└── launchd/
    └── com.tinyintent.tinyrpc.plist
```

## 2) Golden Rules / Guardrails (no drift)

- **Backbone**: `prajjwal1/bert-tiny` (2 layers, H=128). Do **not** switch to DistilBERT/MiniLM unless explicitly instructed.
- **Quantization**: INT8 **weight** quantization on the Core ML MLProgram; hard-fail if package size ≥ 5 MB; also fail if < 100 KB (placeholder).
- **Save paths (strict)**: 
  - Router model → `router/TinyIntent.mlpackage` *(prefer)* or `router/TinyIntent.mlmodel` *(legacy)*.
  - iOS copy → `router/TinyIntent_iOS.mlpackage`.
- **Swift runner**:
  - Supports both `.mlpackage` and `.mlmodel`.
  - **Auto-compiles** to `.mlmodelc` before load.
  - Prints **only** the label token (one of the 3).
  - If model expects tokenized tensors (no string input), print clear error and exit 2.
- **Agent**:
  - `neuro_agent` honors `ROUTE` env (skip classify).
  - `--dry-run` **skips** dependency checks and prints planned commands.
  - Fallback order: `qwen2.5:32b-instruct-q4_K_M` → `llama3.1:8b-instruct-q5_K_M` → exit 2.
- **Bridge** (`tinyrpc.py`):
  - Default bind `127.0.0.1`; LAN only if `ALLOW_LAN=1` and `TINYINTENT_BIND=0.0.0.0`.
  - Require `X-TinyIntent-Secret` (non-empty, not placeholder).
  - `Content-Type: application/json`, size cap ≤ 40 KB, `text` ≤ 8192 chars.
  - Pass `ROUTE=<label>` and `TEXT_SOURCE=iphone` to `neuro_agent`.
  - Optional `DOUBLE_CHECK=1` reclassifies on Mac and may override unless `FORCE_IPHONE=1`.
  - One compact log line per request to stderr + `bridge/logs/tinyrpc.log`.
- **Never** reintroduce: TF-IDF, `.pkl`, Create ML classifiers, network calls in local-only paths, or model files outside `router/`.

## 3) PRD Reference (must link & embed)

- **Reference**: `/Users/oberfelder/projects/smallintent/PRD.md` (v1.5, includes iPhone→Mac v1 flow).
- **Embed**: Full contents embedded in Appendix A below for self-containment.

## 4) Day-to-Day Operator Cheatsheet (copy/paste commands)

**Model size & runtime smoke**
```bash
cd /Users/oberfelder/projects/smallintent
du -sh router/TinyIntent.mlpackage   # expect ~3–5M
echo "local summarization please" | router/tinyintent
```

**Bridge lifecycle**
```bash
make bridge-venv
make bridge-stop && make bridge
make bridge-logs
SECRET=$(/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" launchd/com.tinyintent.tinyrpc.plist)
curl -sS -X POST http://127.0.0.1:8787/route \
  -H "Content-Type: application/json" -H "X-TinyIntent-Secret: $SECRET" \
  -d '{"text":"local summarization please","route":"local_only"}'
```

**LAN enable**
```bash
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:ALLOW_LAN 1" launchd/com.tinyintent.tinyrpc.plist
/usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:TINYINTENT_BIND 0.0.0.0" launchd/com.tinyintent.tinyrpc.plist
make bridge-stop && make bridge
ipconfig getifaddr en0
```

**iOS model export**
```bash
make ios-model
du -sh router/TinyIntent_iOS.mlpackage
```

## 5) Troubleshooting Quick Refs

* **401 unauthorized**: Shortcut secret ≠ plist secret. Read with PlistBuddy and paste into Shortcut header.
* **415**: Missing `Content-Type: application/json`.
* **Runner says "expects tokenized tensors"**: That's OK for v1 (iPhone does classification). Set `ROUTE` in env or send via bridge.
* **Model too big (>5 MB)**: 8-bit quantization didn't apply. Re-run M1 INT8 exporter mini-prompt below.
* **Empty 43-byte files**: Accidentally saved `.mlmodel` placeholder. Use MLProgram `.mlpackage` path and include size gate.

## 6) Ready-to-Paste Mini-Prompts (for future tasks)

### A) **M1 INT8 exporter harden (only if size > 5 MB)**

> Use when `du -sh router/TinyIntent.mlpackage` ≥ 5M.

```
Harden M1 export for INT8 size budget:

- Backbone: BACKBONE="prajjwal1/bert-tiny"
- Convert Torch → Core ML with convert_to="mlprogram", inputs:
    input_ids: (1,192) int32; attention_mask: (1,192) int32
  compute_units=CPU_AND_NE
- Quantize: prefer coremltools.optimize.coreml.quantization_utils.quantize_weights(..., nbits=8, "linear"); fallback to legacy quantization_utils if needed.
- Save STRICTLY to router/TinyIntent.mlpackage, then size-gate via `du -sk`:
    fail if <100 KB or ≥5 MB.
- Print final size and run a MLModel load smoke after save.
- Do not change Makefile or other files.
```

### B) **M2 runtime loader resilience (only if runner fails to load)**

```
Patch router/TinyIntentMain.swift:
- Support both .mlpackage and .mlmodel; prefer .mlpackage.
- Auto-compile with MLModel.compileModel(at:) to .mlmodelc before load.
- If no string input (model expects tensors), print clear guidance & exit 2.
- Keep computeUnits = .cpuAndNeuralEngine.
```

### C) **M3 bridge hardening (security/logging)**

```
tinyrpc.py guards:
- Require X-TinyIntent-Secret (non-empty, not placeholder) or exit at startup.
- Content-Type must be application/json; else 415.
- request.content_length <= 40000; text <= 8192; labels whitelisted.
- Default bind 127.0.0.1; allow 0.0.0.0 only if ALLOW_LAN=1.
- Pass env ROUTE and TEXT_SOURCE=iphone into neuro_agent.
- DOUBLE_CHECK/ FORCE_IPHONE respected; compact log line to stderr + file.
```

### D) **neuro_agent dry-run behavior**

```
Ensure --dry-run is parsed first and skips dependency checks.
Honor ROUTE env to bypass local classify.
All plans and decisions log as a single compact stderr line.
```

## 7) Acceptance Checklists (what "done" looks like)

**M1**
* `router/TinyIntent.mlpackage` exists, **3–5 MB**.
* `make ios-model` produces `TinyIntent_iOS.mlpackage`, **3–5 MB**.
* Trainer prints accuracy + 3×3 confusion matrix.

**M2**
* `router/tinyintent` prints exactly one label from stdin test.
* Auto-compiles model; handles `.mlpackage` or `.mlmodel`.

**M3**
* `curl` to `127.0.0.1:8787/route` returns `{"ok":true,...}`.
* Logs show: `[tinyrpc] ip=... len=... route=... dry=1 status=ok`.
* Shortcut posts `{text, route}` and gets `ok:true`.

---

## Appendix A — Embedded PRD v1.5

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