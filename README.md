# TinyIntent Router v2

Local-first AI routing agent with binary gen/act classification. Zero external dependencies.

## Quick Start

```bash
# Build the project
make build

# Test the agent
echo "summarize this code locally" | agent/neuro_agent

# Run with structured logging
echo "research quantum cryptography" | agent/neuro_agent --json

# Test all routes
make test
```

## What You'll See When It Runs

### Human-Readable Feedback (stderr)
When you run TinyIntent, you'll see a one-liner summary like this:

```
route=local_only model=qwen2.5:32b-instruct-q4_K_M tokens_in=45 tokens_out=127 latency_ms=2341 privacy=local_only
```

### Structured JSON Logs (stdout with --json)
For automation and monitoring, use `--json` flag to get structured output:

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
  "source": "neuro_agent",
  "dry_run": false
}
```

## Usage Examples

### Direct Command Line
```bash
# Local-only processing (privacy-first)
echo "summarize this code locally" | agent/neuro_agent

# Action planning tasks
echo "research quantum cryptography with citations" | agent/neuro_agent

# Multi-step planning with larger models
echo "brainstorm comprehensive project plan" | agent/neuro_agent
```

### With Options
```bash
# JSON logging mode
agent/neuro_agent --json < input.txt

# Quiet mode (minimal output)
agent/neuro_agent --quiet "quick question"

# Dry run (show plan without execution)
agent/neuro_agent --dry-run "test input"

# Override route classification
ROUTE=local_only agent/neuro_agent "force local processing"

# Model size preference (8b/32b/70b/auto)
LOCAL_MODEL_PREF=70b agent/neuro_agent "complex mathematical proof"
LOCAL_MODEL_PREF=8b agent/neuro_agent "quick summary"

# Auto selection (default): ≤300 tokens→8B, 301-1200→32B, >1200→70B
# Keywords like "theorem", "proof", "chain-of-thought" bump to 70B
```

### iPhone Shortcut Integration
TinyIntent supports voice input via iPhone Shortcuts that POST to the Mac bridge:

```bash
# Start the bridge service
make bridge

# Test the bridge endpoint
make iphone-test
```

### Remote via Tailscale (M4.1)
TinyIntent supports worldwide access via Tailscale overlay network:

```bash
# iPhone calls Mac from anywhere in the world
# Endpoint: http://<TAILSCALE-IP>:8787/route
# Example: http://100.64.1.5:8787/route

# Required: X-TinyIntent-Secret header for authentication
curl -H "X-TinyIntent-Secret: your-secret-here" \
     -H "Content-Type: application/json" \
     -d '{"text":"test from remote","route":"local_only"}' \
     http://100.64.1.5:8787/route

# Security controls (environment variables):
# TAILSCALE_ONLY=1     - Only accept Tailscale IPs (100.64.0.0/10)
# RATE_LIMIT_RPS=3     - Max requests per second per IP
# MAX_BODY_KB=32       - Request size limit in KB

# Enhanced logging includes:
# - remote_addr: Source IP address
# - tailscale: boolean (true for 100.64.0.0/10 IPs)
# - allowed: boolean (passed security checks)
# - body_size_kb: Request payload size
```

## Health & Readiness

Monitor the bridge service with JSON health endpoints:

```bash
# Health check (always returns 200 if service is up)
curl http://127.0.0.1:8787/healthz | jq .

# Readiness check (200 when all local checks pass, 503 otherwise)
curl http://127.0.0.1:8787/readyz | jq .
```

The readiness endpoint checks environment variables, router binary availability, and Ollama presence. Useful for deployment automation and CI/CD pipelines.

## Authentication

The bridge service requires authentication via the `X-TinyIntent-Secret` header:

```bash
# All requests to /route must include the secret header
curl -H "X-TinyIntent-Secret: your-secret-here" \
     -H "Content-Type: application/json" \
     -d '{"text":"test message","route":"local_only"}' \
     http://127.0.0.1:8787/route
```

**Secret Management:**
- Rotate secrets with: `bash scripts/rotate_secret.sh`
- Secrets are stored in `launchd/com.tinyintent.tinyrpc.plist`
- Use PlistBuddy to view: `/usr/libexec/PlistBuddy -c "Print :EnvironmentVariables:TINYINTENT_SECRET" launchd/com.tinyintent.tinyrpc.plist`

**Development Mode** (localhost only):
```bash
# Enable dev bypass for localhost requests without auth (default: off)
export ALLOW_DEV_LOCAL=1
```

When `ALLOW_DEV_LOCAL=1`, requests from 127.0.0.1 or ::1 bypass authentication. This setting only applies to localhost and never affects remote connections.

## If you see 'missing_dependency: ollama'

The bridge service requires `ollama` to be accessible. If you get a 500 error with `"error":"missing_dependency"`, use the doctor script:

```bash
bash scripts/doctor.sh
```

**Two ways to fix:**

1. **Set OLLAMA_BIN** (recommended):
   ```bash
   # Add explicit path to plist
   /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables:OLLAMA_BIN string /opt/homebrew/bin/ollama" launchd/com.tinyintent.tinyrpc.plist
   ```

2. **Extend PATH** in plist:
   ```bash
   # Update PATH to include ollama location
   /usr/libexec/PlistBuddy -c "Set :EnvironmentVariables:PATH /opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" launchd/com.tinyintent.tinyrpc.plist
   ```

After changes: `make bridge-stop && make bridge && make bridge-logs`

## Security before testing

Before deploying or testing, ensure proper security hygiene:

```bash
# 1. Rotate secret to ensure no live secrets in repo
bash scripts/rotate_secret.sh

# 2. Install pre-commit hook to prevent future secret leaks
chmod +x dev/git-hooks/pre-commit
ln -sf ../../dev/git-hooks/pre-commit .git/hooks/pre-commit

# 3. Verify secrets guard passes
bash tests/secrets_guard.sh
```

**Important reminders:**
- The real plist (`launchd/com.tinyintent.tinyrpc.plist`) is git-ignored
- Only the sample plist is tracked in git
- Use `scripts/rotate_secret.sh` to generate new secrets safely

## Paths

TinyIntent uses dynamic project root detection to avoid hardcoded paths:

- **Python**: `PROJECT_ROOT = Path(__file__).resolve().parents[1]`
- **Bash**: `PROJECT_ROOT="$(cd "$(dirname "$0")/.."; pwd -P)"`
- **Documentation standard**: `/Users/oberfelder/projects/smallintent` (lowercase `projects`)

This ensures the project works regardless of installation location.

## Route Types (Router v2)

- **gen**: Local generation tasks (text, summaries, explanations)
- **act**: Action planning with preview (multi-step tasks, research)
- **auto**: Automatic classification (default)

All routes execute locally with `privacy: local_only`.

## Development

```bash
# Run smoke tests
bash tests/routes.smoke.sh

# Build and test
make clean && make build && make test

# Clean artifacts
make clean
```

For detailed setup and development instructions, see [PRD.md](PRD.md).