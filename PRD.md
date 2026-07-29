# 📄 TinyIntent v2.0.0: Multi-Domain Voice Automation Platform

This document outlines the product requirements and implementation plan for TinyIntent v2.0.0, a versatile voice automation platform that handles diverse tasks across multiple domains.

## 🎯 Project Overview

**Core Purpose**: Jack-of-all-trades voice automation platform that routes iPhone Siri commands to specialized helpers for practical task automation.

**Key Innovation**: Seamless voice interaction via iPhone Shortcuts → Smart routing → Multi-domain automation execution.

**Platform Identity**: Swiss Army Knife of Voice Automation - one voice interface, unlimited automation possibilities.

## 📋 Project Structure

```
/Users/oberfelder/Projects/tinyintent/  # Production streamlined structure
├── tinyintent/                         # Main CLI package  
├── bridge/routes/                      # Modular FastAPI routes
├── router/SmallIntent.mlmodel         # CoreML intent classifier
├── helpers/{bot_guard,log_tailer}/    # Sandboxed task executors
├── install.sh                         # One-command setup
└── pyproject.toml                     # Python packaging
```

**Usage**: Simply run `tinyintent` command to start server and use iPhone voice shortcuts immediately.

## 🚀 Platform Architecture

- **Platform**: Mac-first with streamlined CLI (`tinyintent` command)
- **iPhone Integration**: M11.0 Shortcut voice interface with optimized TTS
- **Inference**: Local-only via Ollama + CoreML (no cloud calls)
- **Router**: SmallIntent.mlmodel (CoreML, ANE-accelerated)
- **Repository**: Single monorepo with production packaging
- **Bridge**: FastAPI service on port 8787 (LAN + Tailscale ready)
## 🎪 Multi-Domain Automation Capabilities

### 📱 M11.0: iPhone Shortcut Voice Interface
- **Endpoint**: `POST /shortcut/route` with `X-Shortcut-Token` auth
- **Integration**: Seamless Siri voice command processing
- **Features**: Voice-optimized text formatting, TTS optimization, length limits
- **Flow**: Dictate Text → HTTP Request → Speak Response

### 🧑‍🧬 Intent Router (CoreML)
- **SmallIntent.mlmodel**: macOS model (~70-85MB INT8 CoreML), ANE-accelerated, seq_len=128
- **TinyIntent.mlmodel**: iOS model (≤5MB) – future milestone  
- **Router Runner**: Swift CLI returning `gen|act` with confidence
- **Fallback**: Heuristic classification if model fails
- **Performance**: Sub-10ms inference on Apple Silicon

### 🔧 Multi-Domain Helper Ecosystem
**Automation Domains**:
- **Weather & Location**: Real-time weather data with GPS awareness
- **System Monitoring**: CPU, memory, disk, network performance tracking  
- **Network Infrastructure**: Enterprise Cisco/Ubiquiti device monitoring with anomaly detection
- **Trading & Finance**: Crypto position monitoring and trade execution
- **DevOps & Logs**: System log analysis and infrastructure monitoring
- **Extensible Framework**: Add any automation domain via helper development
**Helper Categories**:
- **Information**: Weather, system stats, network status
- **Infrastructure**: Network monitoring, system administration, DevOps
- **Finance**: Trading, portfolio management, market analysis
- **Productivity**: Log analysis, task automation, monitoring

**Management**:
- `make doctor` provides helper readiness status
- `GET /system/doctor` provides helper ecosystem health API
- Hot-reload support for helper development
- Comprehensive helper validation and sandboxing

### 🌉 Modular Bridge API
**Health & Status**:
- `GET /health` - System status
- `GET /shortcut/ping` - iPhone Shortcut health check

**Core Routing**:
- `POST /route` - Routes voice commands to appropriate helpers
- `POST /feedback` - Attaches execution result metadata

**Management**:
- `POST /system/emergency/kill` - Emergency disable execution
- `GET /system/emergency/status` - Emergency status check
- `GET /router/metrics` - Confidence/latency monitoring
- `GET /router/train_summary` - Training summary and model deployment status
🛠 Helpers Orchestrator
Reflection Layer: Uses a small LLM to sanity-check helper previews (planned).
Sandboxing:
CPU, memory, timeout limits.
Capability isolation (network, filesystem).
Env validation (required_envs).
Guardrails:
Preview by default.
Execute requires approval tokens, EXECUTION_ENABLED=1, rate limiting, and idempotency.
Extensibility:
Manifest + schema validation (helper.yaml, input/output schemas).
Invalid helpers disabled at load.
Hot reload support (M8.2).
Initial helpers:
bot_guard: real exchange adapter (sandbox-only default).
log_tailer: returns last N error lines.
ssh_ops: (future) restart bots, tail logs.
👁 Continuous Monitoring
Watchers (planned M6): bot drift, auth fails, log anomalies, DDoS.
Audit + metrics pipeline already in place.
/health endpoint reports runner, Ollama, bridge.
📈 Experience Store & Offline Learning
Episodes logged:
data/episodes/events.ndjson
data/episodes/events.db
Schema includes: timestamp, session_id, action, route_pred, confidence, error codes.
make learn: mines episodes, retrains router, runs eval.
make promote: promotes models passing eval gates.
autopilot.py: full loop (learn → eval → promote) with daily launchd scheduling.
Conscious Memory Layer (planned M4.5+):
SQLite FTS index + NDJSON mirror
Tools: save_memory, query_memory, delete_memory
🔐 Security & Key Management
All endpoints require X-TinyIntent-Secret.
ALLOW_DEV_LOCAL=1 bypass for dev.
Keys stored in macOS Keychain.
Executions are logged, rate-limited, and auditable.
Secrets sanitized everywhere (bridge/sanitize).
Exchange API credentials loaded from .env (dev) or Keychain (prod).
🧬 Self-Modifying Agents (Future M9)
Auto-evolving helpers via introspection + code synthesis.
Reward signals: accuracy, resource use, user feedback, execution success, approval rates.
Early design only.
🧩 Self-Healing Logic (Future M9)
Monitors logs for failure patterns.
Matches known issues to fix recipes.
LLM-assisted patches with --approve mode.
Logs to logs/selfheal.log.

## 🎯 M10.1 Agent Evolution - Operator Usage

The Agent Evolution system automatically suggests new helpers based on abstain/fallback patterns:

### Discovery Phase
```bash
# Check for abstain patterns in the last 24 hours
curl -H "Authorization: Bearer $TINYINTENT_SECRET" \
  -X POST http://localhost:8787/agents/suggest \
  -H "Content-Type: application/json" \
  -d '{"window_hours": 24, "min_count": 8, "max_suggestions": 5}'
```

### Response Example
```json
{
  "suggestions": [
    {
      "spec": {
        "id": "web_scraper",
        "description": "Fetch data from web URLs based on abstain patterns",
        "language": "python",
        "capabilities": ["network"],
        "can_execute": false,
        "risk_level": "high",
        "inputs": {
          "type": "object",
          "properties": {
            "url": {"type": "string", "format": "uri"}
          },
          "required": ["url"]
        },
        "outputs": {
          "type": "object",
          "properties": {
            "data": {"type": "string"},
            "status": {"type": "string"}
          },
          "required": ["data"]
        }
      },
      "valid": true,
      "cluster_info": {
        "sample_count": 12,
        "representative_text": "Fetch data from https://api.example.com",
        "themes": ["web_interaction", "data_retrieval"],
        "confidence_score": 0.85
      }
    }
  ],
  "clusters_analyzed": 2,
  "total_abstain_events": 18,
  "window_hours": 24
}
```

### Creation Phase
```bash
# Create helper from approved suggestion
curl -H "Authorization: Bearer $TINYINTENT_SECRET" \
  -X POST http://localhost:8787/agents/create_from_suggestion \
  -H "Content-Type: application/json" \
  -d '{"spec": {...}}'  # Use spec from suggestion response
```

### Safety Features
- **Security Defaults**: All suggested helpers have `can_execute: false` and `risk_level: high`
- **Capability Inference**: Minimal capabilities inferred from request patterns
- **Suggestion Tracking**: Episodes labeled with `label_source: "suggestion"` for impact analysis
- **Validation**: All specs validated before creation, invalid specs marked with errors

## 🎯 M10.2 Agent Lifecycle Governance - Operator Usage

The Agent Lifecycle Governance system provides explicit controls and metrics for managing helpers over time with lifecycle states and pruning suggestions.

### Lifecycle States
- **draft**: New or experimental helpers, not yet production-ready
- **trusted**: Stable helpers safe for production use
- **deprecated**: Older helpers being phased out, still functional but with warnings
- **retired**: Helpers no longer available, blocked from execution

### View Helper Lifecycle Status
```bash
# Get lifecycle status and metrics for a specific helper
curl -H "Authorization: Bearer $TINYINTENT_SECRET" \
  http://localhost:8787/agents/lifecycle/bot_guard
```

### Response Example
```json
{
  "helper_id": "bot_guard",
  "lifecycle": {
    "state": "trusted",
    "since": "2024-12-15",
    "notes": "Core helper - production ready"
  },
  "metrics": {
    "total_calls": 156,
    "success_rate": 0.987,
    "last_used": "2025-08-21T10:30:00Z",
    "error_rate": 0.013,
    "avg_latency_ms": 245.6
  }
}
```

### Update Helper Lifecycle
```bash
# Deprecate a helper
curl -H "Authorization: Bearer $TINYINTENT_SECRET" \
  -X POST http://localhost:8787/agents/lifecycle/set \
  -H "Content-Type: application/json" \
  -d '{
    "helper_id": "old_helper",
    "state": "deprecated",
    "notes": "Use new_helper instead - will be retired Q1 2025"
  }'

# Retire a helper completely
curl -H "Authorization: Bearer $TINYINTENT_SECRET" \
  -X POST http://localhost:8787/agents/lifecycle/set \
  -H "Content-Type: application/json" \
  -d '{
    "helper_id": "legacy_helper", 
    "state": "retired",
    "notes": "No longer maintained, functionality moved to core_helper"
  }'
```

### Get Pruning Suggestions
```bash
# Get suggestions for helpers to deprecate or retire
curl -H "Authorization: Bearer $TINYINTENT_SECRET" \
  "http://localhost:8787/agents/prune_suggestions?min_days=30&min_calls=3&max_error_rate=0.4"
```

### Pruning Response Example
```json
{
  "suggestions": [
    {
      "helper_id": "unused_helper",
      "current_state": "trusted", 
      "suggested_action": "retire",
      "reason": "Low usage: 2 calls in 45 days",
      "metrics": {
        "total_calls": 2,
        "days_since_last_use": 45,
        "error_rate": 0.0
      }
    },
    {
      "helper_id": "error_prone_helper",
      "current_state": "trusted",
      "suggested_action": "deprecate", 
      "reason": "High error rate: 67% (4/6 calls)",
      "metrics": {
        "total_calls": 6,
        "days_since_last_use": 2,
        "error_rate": 0.67
      }
    }
  ],
  "criteria": {
    "min_days_unused": 30,
    "min_calls_threshold": 3,
    "max_error_rate": 0.4
  },
  "total_helpers_analyzed": 8
}
```

### Lifecycle Enforcement Behavior

#### Deprecated Helpers
- ✅ **Execution allowed** but with warnings
- 📋 **HTTP headers added**: `X-Helper-Deprecated: true`, `X-Helper-Status: deprecated`
- 📊 **Audit logging** of deprecated helper usage
- 🔔 **Operator alerts** to migrate to newer alternatives

#### Retired Helpers  
- ❌ **Execution blocked** with `410 Gone` responses
- 📋 **HTTP headers added**: `X-Helper-Status: retired`
- 📊 **Audit logging** of retirement violation attempts
- 🚫 **Complete unavailability** until manually restored

### Registry Configuration

Helpers can define lifecycle in `helpers/registry.yaml`:
```yaml
helpers:
  my_helper:
    # ... other config ...
    lifecycle:
      state: "trusted"      # draft|trusted|deprecated|retired
      since: "2024-12-15"   # ISO date when state was set
      notes: "Production ready - stable API"
```

### Safety Features
- **Backward Compatibility**: Helpers without lifecycle default to `trusted` state  
- **Audit Trail**: All lifecycle changes and violations logged
- **Graceful Degradation**: Deprecated helpers continue working with warnings
- **Operator Control**: Manual override capabilities for emergency situations
- **Metrics-Driven**: Pruning suggestions based on actual usage patterns

📁 Repository Layout
/Users/oberfelder/projects/tinyintent/
/Users/oberfelder/projects/tinyintent/
    1 /Users/oberfelder/projects/tinyintent/
    2 ├── PRD.md
    3 ├── README.md
    4 ├── claude.md
    5 ├── pyproject.toml
    6 ├── Makefile
    7 ├── models.yaml
    8 ├── launchd/
    9 │   └── com.tinyintent.tinyrpc.sample.plist
   10 ├── bridge/
   11 │   ├── tinyrpc.py
   12 │   ├── api_routes.py
   13 │   ├── security.py
   14 │   ├── gen_client.py
   15 │   ├── router_client.py
   16 │   ├── errors.py
   17 │   ├── resolve.py
   18 │   └── logs/
   19 │       ├── audit.py
   20 │       ├── sanitize.py
   21 │       └── util.py
   22 ├── data/
   23 │   ├── episodes/
   24 │   │   ├── __init__.py
   25 │   │   ├── logger.py
   26 │   │   ├── flush.py
   27 │   │   └── schema.py
   28 │   └── datasets/
   29 ├── helpers/
   30 │   ├── sdk.py
   31 │   ├── manifest.py
   32 │   ├── registry.py
   33 │   ├── sandbox.py
   34 │   ├── executor.py
   35 │   ├── registry.yaml
   36 │   ├── bot_guard/
   37 │   │   ├── helper.yaml
   38 │   │   ├── input.schema.json
   39 │   │   ├── output.schema.json
   40 │   │   └── main.js
   41 │   └── log_tailer/
   42 │       ├── helper.yaml
   43 │       ├── input.schema.json
   44 │       ├── output.schema.json
   45 │       └── main.js
   46 ├── router/
   47 │   ├── train_router.swift
   48 │   ├── eval_router.swift
   49 │   ├── SmallIntent.mlmodel
   50 │   ├── TinyIntent.mlmodel
   51 │   ├── runner/
   52 │   │   └── run_router.swift
   53 │   └── data/
   54 │       ├── intents.tsv
   55 │       └── intents_test.tsv
   56 ├── scripts/
   57 │   ├── rotate_secret.sh
   58 │   ├── print_urls_and_secret.sh
   59 │   ├── export_episodes.py
   60 │   ├── promote_model.py
   61 │   ├── autopilot.py
   62 │   └── ...
   63 ├── tests/
   64 │   ├── bridge/
   65 │   ├── helpers/
   66 │   ├── router/
   67 │   ├── integration/
   68 │   ├── health.sh
   69 │   ├── auth.sh
   70 │   ├── routes.smoke.sh
   71 │   ├── router_smoke.sh
   72 │   └── helpers_smoke.sh

🔢 Milestones
ID	Name	Summary
M1	Bridge MVP	Core server + routing endpoint with model resolution
M2	Experience Store	Structured local logging of all user requests/results
M3	Router v1 (SmallIntent)	CoreML model training + evaluation suite
M4	Helpers Framework v1	Manifest loader, runner, schema validation
M4.5	Guarded Execution	Approval-token system; emergency kill switch
M5	Eval & Retrain Kit	make learn + eval gates; autopilot retrain loop
M6	Security Hardening	Sandboxing, capability isolation, rate limiting, audit integrity
M7	Router Refinements	Async gen, calibration, abstain/fallback, metrics, circuit breaker
M8	Helper Improvements	Real bot_guard integration, manifest validation, dynamic reload support
M9	Self-Modifying Agents	Auto-evolving, reward-guided agent architecture for helpers
M10	Agent Evolution	Episode mining for automated helper suggestion and creation
M9	Self-Healing System	Self-healing agent with dry-run and approval modes for infrastructure

COMPLETED MILESTONES
M1 – Bridge MVP
Core server, config-based model resolution, and /route, /healthz, /readyz endpoints.
M1.1 – Server Scaffolding: tinyrpc.py FastAPI scaffold, env parsing, and X-TinyIntent-Secret authentication.
M1.2 – Ready Check Framework: /readyz returns router presence, model map status, and Ollama validation.
M1.3 – Config-Driven Model Mapping: models.yaml loader + support for MODEL_SMALL, MODEL_MEDIUM, MODEL_LARGE overrides.
M1.4 – Smoke Tests: health.sh, auth.sh, and routes.smoke.sh ensure API functionality.
M2 – Experience Store
Structured local logging of user requests/results into NDJSON and SQLite.
M2.1 – data/episodes/ Setup: Directory + SQLite + events.ndjson append logic.
M2.2 – Feedback Endpoint: POST /feedback saves user feedback tied to session ID.
M2.3 – Session Logger: Unique session IDs, action metadata logging, latency tracking.
M3 – Router v1 (SmallIntent)
CoreML model training, evaluation, and binary runner for fast intent classification.
M3.1 – Dataset Bootstrapping: Initial TSV intent samples for intents.tsv and intents_test.tsv.
M3.2 – Training Swift Code: train_router.swift trains a Digibert-based CreateML model.
M3.3 – Evaluation Logic: eval_router.swift with size and accuracy gates.
M3.4 – Runner Integration: run_router.swift used by bridge to route via ANE.
M3.5 – Promotion Flow: make learn, promote_model.py, and updated bridge integration.
M4 – Helpers Framework v1
Manifest-based helper execution framework.
M4.1 – Manifest Loader: helpers/registry.yaml and manifest parsing.
M4.2 – Schema Enforcement: JSON schema validation before execution.
M4.3 – sdk.py Runtime: Safe execution engine with command allowlisting and timeouts.
M4.4 – Log Tailer Helper: First implemented helper (basic test case).
M4.5 – Guarded Execution: Two-step approval flow, emergency close path, helper preview/execute split.
M5 – Execute Mode & Learning Loop
M5.0 – Execute Mode & Risk Controls: Approval-guarded execution, EXECUTION_ENABLED gate, idempotency, schema validation.
M5.1 – E2E Tests & Operator UX: Pytest coverage, reason codes, curl docstrings.
M5.2 – Episode Mining Integration: Log preview/execute into ndjson + SQLite.
M5.3 – Learning Loop Automation: export_episodes.py, make learn target.
M5.4 – Evaluation & Promotion: eval_router.swift outputs eval results; promote_model.py gates promotion.
M5.5 – Continuous Learning: autopilot.py, make autopilot, launchd template.
M6 – Security Hardening
M6.0 – Helper Registry Hardening: required_envs, safety_notes, disable missing-env helpers.
M6.1 – Helper Sandboxing: CPU/memory/time limits, SANDBOX_LIMIT errors, tests.
M6.2 – Audit Log Integrity: SHA256 hash chain, rotation at 50MB, continuity checks.
M6.3 – Emergency Kill Switch: /emergency/kill endpoint, persisted flag disables execution.
M6.4 – Secrets Management: Centralized sanitization, expanded redaction, scrubbed logs.
M6.5 – Capability Isolation: Per-helper capabilities (network, filesystem), violations return 403.
M6.6 – Rate Limiting: Per-session/global caps (429), per-helper exec caps.
M7 – Router Refinements
M7.0 – Router Refactor & Async Gen: Removed hardcoded routing; async Ollama with retries/backoff + semaphore.
M7.1 – Router Quality & Fallbacks: Confidence calibration, abstain/fallback policy, rich eval metrics.
M7.2 – Router Reliability Monitoring: /router/metrics endpoint, in-memory buffer, periodic flush.
M7.3 – Generation Resilience: Circuit breaker for Ollama gen, /health endpoint, cancel in-flight requests.
M7.4 – Self-Correction & Overrides: Abstain reasons, operator overrides, override-labeled episodes.
M7.5 – Retraining Safeguards: Export --dry-run, train_summary.json, /router/train_summary.
M8 – Helper Improvements
M8.0 – Bot Guard Integration: Real exchange adapter (sandbox-only), schema validation, integration tests.
M8.1 – Helper Extensibility: Manifest validation, disable invalid helpers, tests.
M8.2 – Dynamic Helper Discovery & Hot Reload (next): /helpers/reload endpoint, reload helpers without restart, structured audit + tests.

M10 – Agent Evolution
Episode mining system for automated helper suggestion and creation based on abstain/fallback patterns.
M10.1 – Episode Mining for Agent Suggestion: mine_abstain_clusters() analyzes fallback patterns, clusters similar requests via TF-IDF/k-means, POST /agents/suggest generates helper specs using Ollama, POST /agents/create_from_suggestion creates helpers with safety defaults (can_execute=false, risk_level=high), suggestion tracking in export_episodes.py with label_source tagging.
### M10.6 – CoreML Artifact Remediation
- Ensure `make learn` and `make promote` produce and persist `router/SmallIntent.mlmodel` and `router/TinyIntent.mlmodel`.
- Add `doctor` check for model presence. If infra is present but models missing, mark as **warning** with hint to run training.
- Update `DEPLOYMENT.md` and `README.md` with explicit operator steps for generating `.mlmodel` files.
- Add `.gitattributes` LFS tracking for `.mlmodel` files if size >100MB.

### M10.7 – Documentation Endpoints
- Implement `GET /router/train_summary` in `bridge/api_routes.py`.
- Return structured JSON from `router/train_summary.json` (accuracy, f1, latency, etc).
- Implement `GET /endpoints` for operator/auditor visibility of registered routes.
- Ensure FastAPI’s built-in `/docs`, `/redoc`, `/openapi.json` are exposed.
- Add integration tests confirming endpoint availability and responses.

### M10.8 – Doctor + Packaging Integration
- Extend `doctor` to report models, routes, and training metadata.
- Package `.mlmodel` and router data files in `pyproject.toml` under `package-data`.
- Verify `/doctor` endpoint surfaces the new checks.
- Add integration tests to cover missing models (warning), missing routes (failure).
