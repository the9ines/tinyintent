
TinyIntent v2: Mac-First Local Intelligence Platform

This document outlines the product requirements and implementation plan for TinyIntent v2, a Mac-first, local-only intelligence platform. The project's core purpose is to provide an on-device, private, and extensible AI agent for managing personal operations, starting with crypto bot risk management.

Project Framing

* * Platform: Mac-first via a macOS service/app. Initial phone interaction uses a simple iOS Shortcut as a transport layer. A native iOS app is a later milestone.
* * * * * * Inference: Absolutely no cloud inference. All LLMs run locally on the Mac via Ollama.
* * Repo: Single monorepo located at /Users/oberfelder/projects/tinyintent.
* * Bridge: The bridge service listens on port 8787 for both LAN and Tailscale connections.


Capabilities


Intent Router (Core ML)

The system uses a lean Core ML model for fast, local intent routing.
* * * * SmallIntent (macOS): An ANE/NPU-accelerated .mlmodel for macOS, limited to ≤ 16 MB. This ships first and handles initial routing.
* * TinyIntent (iOS): A separate, even smaller .mlmodel (≤ 5 MB) for a native iOS app, to be developed as a later milestone.
* * Router Runner: A command-line binary that accepts text via stdin and outputs a label (gen or act). A return code of 0 indicates success. If the router fails (rc ≠ 0) or is missing, the system uses a heuristic fallback and logs the reason.

Pluggable Local LLM Roles

The system is designed to allow model swapping without code changes.
* * Configuration: A top-level models.yaml file defines roles, mapping them to specific Ollama tags.YAMLroles:
*   small: llama3.1:8b-instruct-q5_K_M
*   medium: qwen2.5:32b-instruct-q4_K_M
*   large: llama3.1:70b-instruct-q4_K_M
* 
* * Overrides:
    *     * Environment: Environment variables MODEL_SMALL, MODEL_MEDIUM, and MODEL_LARGE can override the models.yaml defaults.
    *     * Per-request: The POST /route endpoint supports llm_pref ("small"|"medium"|"large") or llm_model ("<ollama-tag>") for on-demand model selection.
* * Management:
    *     * Hot Reload: A POST /admin/reload-models endpoint on localhost triggers a live reload of the model registry.
    *     * Readiness Check: The /readyz endpoint includes models_present and a missing_models list. The make doctor command prints the effective model mapping and suggests ollama pull commands for missing models.


Bridge APIs (Contracts)

The bridge serves as the central API gateway. All non-health/readiness endpoints require an X-TinyIntent-Secret header.
* GET /healthz: Returns a simple status JSON.
* GET /readyz: Returns a 200 or 503 with a JSON payload of checks, including env_valid, ollama_present, router_binary, and models_present.
* POST /route:
    *     * Input: {text, route=auto|gen|act, llm_pref?, llm_model?}
    *     * auto route: Uses the router. If a heuristic fallback is used, the response attaches _router_fallback: true.
    *     * gen route: Returns a JSON payload with the generated text, model name, and optional performance metrics (tokens?, latency_ms?).
    *     * act route: Delegates to the Helpers Orchestrator. Returns a preview or execution result JSON that is strictly schema-validated. Invalid input results in a 400 error.
* POST /feedback: Finalizes an episode with feedback.
* POST /admin/reload-models: Triggers a hot reload of models.yaml. (localhost-only)
* POST /admin/reload-helpers: Triggers a hot reload of helper manifests. (localhost-only)


Helpers Orchestrator

This component manages specialized, short-lived subprocesses to perform actions.
* * Spawning: Spawns sandboxed helpers from an allow-list, each with strict resource caps.
* * Manifests: Helpers are defined by helpers/<id>/helper.yaml manifest files.
    * purpose: A brief description.
    * input/output schemas: JSON schemas for validation.
    * commands: A list of allowed binaries and arguments.
    * timeouts, cpu/mem caps, network_policy.
* * Initial Helpers:
    * ssh_ops: For safe SSH runbooks (e.g., restart a bot, tail logs).
    * bot_guard: For crypto bot risk controls (e.g., preview/execute closing a position).
    * log_tailer: For retrieving the last N error lines from logs.
* * Modes & Guardrails:
    *     * Preview: The default mode. Returns a strict JSON of intended actions.
    *     * Execute: Available only for helpers explicitly marked as executable. Requires one of the following:
        2. Two-step approval: The initial preview request returns an approval token, which is then sent back in a subsequent execute request.
        4.         4. Emergency Close: A special flow for the bot_guard helper, gated by a one-time code and a specific confirmation phrase.
* * Logging: All helper actions, inputs, and results are appended to bridge/logs/audit.log.
* * Hot Reload: The helpers/registry.yaml file lists all helpers, and POST /admin/reload-helpers triggers a live reload.


Continuous Monitoring

An always-on system using macOS LaunchAgent watchers.
* * Watchers:
    * Bot heartbeat/latency/PNL drift.
    * VPS health (CPU, disk, updates).
    * Auth-fail bursts.
    * Log anomalies (regex-based).
    * Open ports, basic DDoS hints.
* * Responses: Threshold breaches trigger advisories (macOS notifications) and route events. Limited auto-mitigations (e.g., bot restart) are only allowed with explicit approval, except in a pre-defined emergency flow.


Experience Store & Offline Learning

All events are logged locally for analysis and model improvement.
* * Data Capture: Every request and result is appended to data/episodes/events.ndjson and mirrored in a local SQLite database.
* * Event Schema: ts, session_id, text, route_pred, route_final, model_used, latency_ms, helper_id?, helper_input?, preview_json?, executed?, success?, feedback?, error_code?, labels[], hash.
* * Offline Loop: The make learn script mines episodes, updates training data (router/data/intents*.tsv), retrains the SmallIntent model, evaluates it against gates, and promotes it to the bridge if it passes. No online weight updates occur.


Security & Key Management

* * Auth: X-TinyIntent-Secret is required on all core endpoints.
* * Dev Bypass: An optional dev-only loopback bypass is enabled with ALLOW_DEV_LOCAL=1 if the request has no X-Forwarded-For header.
* * * * Key Storage: SSH uses the user’s standard ~/.ssh/config and agent. Exchange API keys are stored securely in the macOS Keychain, with trade-only permissions and withdrawals disabled.
* * Auditing: All exec paths are rate-limited, require two-step approvals (unless in emergency mode), and are logged with arguments and exit codes.


Environment Variables

Variable	Description	Default	Example
Server			
TINYINTENT_BIND	Bind address for the server.	0.0.0.0	127.0.0.1
TINYINTENT_PORT	Port for the server.	8787	8080
TINYINTENT_SECRET	Secret for API auth. Required.	None	a32b2f...
ALLOW_DEV_LOCAL	Bypass secret auth for localhost.	0	1
Models			
MODEL_SMALL	Override tag for small model.	llama3.1:8b...	llama3.1:8b...
MODEL_MEDIUM	Override tag for medium model.	qwen2.5:32b...	qwen2.5:32b...
MODEL_LARGE	Override tag for large model.	llama3.1:70b...	llama3.1:70b...
Helpers			
HELPERS_ENABLED	Enable helper orchestration.	1	0
HELPERS_DIR	Directory for helper manifests.	helpers/	./helpers
ALLOW_EXECUTION	Allow execute mode.	0	1
EMERGENCY_CODE_SOURCE	Path to file for emergency codes.	None	/path/to/codes
Watchers			
WATCHERS_ENABLED	Enable continuous monitoring.	1	0
WATCHERS_CONFIG	Path to watcher configs.	watchers/	./watchers
Data			
RETENTION_DAYS	Max days to retain event data.	30	90
EPISODES_DB_PATH	Path for the SQLite database.	data/episodes/events.db	/tmp/events.db

Sequence Diagrams & Examples


Two-Step Approval for Guarded Execution

This flow is critical for actions with real-world consequences, like closing a bot position.
1. Preview Request
JSON



{
  "text": "Close my bot position on ETH.",
  "route": "act",
  "llm_pref": "small"
}
2. Preview Response
JSON



{
  "status": "success",
  "action": "preview",
  "helper_id": "bot_guard",
  "preview_json": {
    "operation": "close_position",
    "symbol": "ETH/USDT"
  },
  "approval_token": "a1b2c3d4e5f6g7h8"
}
3. Execute Request
JSON



{
  "text": "Close my bot position on ETH.",
  "route": "act",
  "approval_token": "a1b2c3d4e5f6g7h8",
  "execute": true
}
4. Execute Response
JSON



{
  "status": "success",
  "action": "execute",
  "helper_id": "bot_guard",
  "result": {
    "status": "ok",
    "message": "Position closed successfully."
  }
}


Emergency Close Flow

This single-step flow is for critical situations.
1. Emergency Request
JSON



{
  "text": "Emergency, close all positions now.",
  "route": "act",
  "helper_id": "bot_guard",
  "emergency_code": "007-ABC-42",
  "confirmation_phrase": "confirm emergency close"
}


Sample Helper Manifest

helpers/bot_guard/helper.yaml
YAML



purpose: "Crypto bot risk management and emergency controls."
schema:
  input: "./input.schema.json"
  output: "./output.schema.json"
capabilities:
  preview: true
  execute: true
  emergency_close: true
sandbox:
  commands:
    - "/usr/bin/node"
    - "./main.js"
  network: "isolated"
  timeouts:
    - name: "default"
      seconds: 5
    - name: "execute"
      seconds: 15
  cpu:
    max_ms: 1000
  mem:
    max_mb: 50
environment:
  required:
    - "EXCHANGE_API_KEY"
    - "EXCHANGE_SECRET"
    - "EXCHANGE_PASSPHRASE"


Repository Layout

tinyintent/
├─ PRD.md
├─ README.md
├─ claude.md
├─ models.yaml
├─ Makefile
├─ launchd/
│  └─ com.tinyintent.tinyrpc.sample.plist
├─ bridge/
│  ├─ tinyrpc.py
│  ├─ resolve.py
│  └─ logs/
├─ data/
│  ├─ episodes/
│  └─ datasets/
├─ helpers/
│  ├─ registry.yaml
│  ├─ sdk.py
│  └─ <helper_id>/
├─ router/
│  ├─ runner/
│  ├─ SmallIntent.mlmodel
│  ├─ TinyIntent.mlmodel
│  └─ data/
├─ scripts/
│  ├─ rotate_secret.sh
│  ├─ print_urls_and_secret.sh
│  └─ ...
└─ tests/
   ├─ health.sh
   ├─ auth.sh
   └─ ...


Milestones


M1: Bridge MVP

* * Deliverables: Basic tinyrpc.py server, GET /healthz, GET /readyz (with basic checks), POST /route (gen/act), models.yaml resolver, X-TinyIntent-Secret auth, ALLOW_DEV_LOCAL bypass.
* * Tests: health.sh, auth.sh, routes.smoke.sh.
* * Definition of Done: All core endpoints operational and tested with secrets, model resolution works, readyz reflects system state.

M2: Experience Store

* * Deliverables: data/episodes directory, events.ndjson logging, SQLite mirror, POST /feedback endpoint, scripts/export_episodes.sh.
* * Tests: New tests for feedback endpoint and episode logging.
* * Definition of Done: Every request is logged to NDJSON and SQLite with the full schema. Feedback finalizes episodes.

M3: Router v1 (SmallIntent)

* * Deliverables: router/runner binary, initial SmallIntent.mlmodel (git-ignored), make router-train, make router-eval scripts.
* * Tests: router_smoke.sh and a new set of evaluation tests to check accuracy and latency.
* * Definition of Done: auto routing works, router is fast (≤ 2ms), and the build process for the router model is fully automated.

M4: Helpers Framework v1

* * Deliverables: Helpers Orchestrator, helpers/sdk.py, helpers/registry.yaml, manifest loader, sandbox spawning, POST /route with act (preview only), POST /admin/reload-helpers.
* * Tests: helpers_smoke.sh to test manifest loading, preview mode, and hot reloading.
* * Definition of Done: act route returns a valid preview JSON from a spawned helper, and helpers are reloaded without service restart.

M5: Guarded Execution

* * Deliverables: Two-step approval flow (token-based), emergency close feature (one-time code + phrase), Keychain integration for secure API keys, enhanced audit logging.
* * Tests: New end-to-end tests for the approval flow, emergency close, and auditing.
* * Definition of Done: Executing sensitive actions requires an explicit token, and all executions are logged in audit.log with their arguments.

M6: Continuous Monitoring

* * Deliverables: LaunchAgent configuration sample, initial watcher scripts, thresholds for advisories, limited auto-mitigation logic.
* * Tests: watchers_smoke.sh to test basic watcher functionality and notification triggers.
* * Definition of Done: Watchers run as a macOS service, trigger advisories on threshold breaches, and log their actions.

M7: Eval & Retrain Kit

* * Deliverables: make learn script to mine data, make router-eval with metric and size gates, scripts for promoting a new model.
* * Tests: Automated evaluation scripts that fail if the new model is slower or less accurate.
* * Definition of Done: A new model can be trained, evaluated, and promoted to production with a single command, gated by performance metrics.

M8: Packaging & iOS

* * Deliverables: Final LaunchAgent configuration, build scripts, make doctor for diagnosing issues, documentation for firewall/Tailscale setup, optional TinyIntent.mlmodel and native iOS app for late-stage testing.
* * Tests: Integration tests with a sample iOS Shortcut.
* * Definition of Done: A user can easily install and run the service, and a basic iOS Shortcut can communicate with the Mac service.


SLOs & Acceptance

* * Router Latency: p95 router inference latency ≤ 2 ms on a Mac Studio.
* * Act-Preview: p95 round-trip latency for act-preview with the medium model ≤ 1.2 s.
* * Readiness: /readyz returns a 200 status with models_present=true and helpers/registry ready on a properly configured machine.
* * Security: Guarded execution requires an approval token. The emergency flow is restricted to close position and is fully audited.


Risk & Mitigation

* * Risk: Helper sandboxing is insufficient, leading to privilege escalation.
    *     * Mitigation: Strict allow-listing of binaries, input schema validation, and running helpers with minimal permissions.
* * Risk: Noisy monitoring leads to alert fatigue.
    *     * Mitigation: Implement configurable thresholds, alert backoff policies, and a tiered notification system.
* * Risk: Model drift causes the router to misclassify intents.
    *     * Mitigation: The offline learning loop and evaluation gates prevent misbehaving models from being promoted to production.
