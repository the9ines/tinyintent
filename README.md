# TinyIntent

A lightweight, local-first routing agent for macOS that intelligently routes prompts to appropriate backends (Claude CLI, Ollama) based on context and privacy requirements.

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

# Send to Claude for complex tasks
echo "research quantum cryptography with citations" | agent/neuro_agent

# Plan locally, then execute on Claude
echo "brainstorm steps then ask Claude to draft proposal" | agent/neuro_agent
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

## Route Types

- **local_only**: Privacy-first processing using local Ollama models (32B → 8B fallback)
- **send_claude**: Direct routing to Claude CLI for complex tasks requiring latest knowledge
- **plan_then_claude**: Local refinement with Ollama, then final execution on Claude

## Development

```bash
# Run smoke tests
bash tests/routes.smoke.sh

# Build and test
make clean && make build && make test

# Clean artifacts
make clean
```

For detailed setup and development instructions, see [PRD.md](PRD.md) and [claude.md](claude.md).