# TinyIntent v2

A Mac-first, local-only AI platform for routing and executing personal assistant tasks—like managing crypto bots—using CoreML, Ollama, and sandboxed helpers.

## 🚀 Quick Start

```bash
# Setup the environment
make setup

# Start the bridge service
make bridgesrv

# Train the intent router
make router-train

# Run health checks
make doctor
```

## 📁 Project Structure

```
tinyintent/
├── bridge/          # FastAPI service for routing
├── router/          # Intent classification (gen vs act)
├── helpers/         # Sandboxed task execution
├── data/            # Episodes and training datasets
├── scripts/         # Utility scripts
├── tests/           # Smoke tests and validation
└── launchd/         # macOS service configuration
```

## 🎯 Core Components

### Bridge Service
- **Port**: 8787
- **Auth**: `X-TinyIntent-Secret` header
- **Endpoints**: `/route`, `/feedback`, `/readyz`

### Router
- **Models**: 
  - `SmallIntent.mlmodel` (macOS, ≤16MB)
  - `TinyIntent.mlmodel` (mobile, ≤5MB)
- **Classes**: `gen` (generative) vs `act` (action)
- **Training**: Python + transformers → ONNX → CoreML
- **Pipeline**: `make learn` produces versioned CoreML artifacts

### Helpers
- **Runtime**: Node.js sandboxed execution
- **Schema**: JSON schema validation
- **Registry**: YAML-based helper discovery

## 🧪 Testing

```bash
# Run all tests
make test

# Individual test suites
./tests/health.sh        # Project structure
./tests/auth.sh          # Authentication
./tests/routes.smoke.sh  # API endpoints
./tests/router_smoke.sh  # Model training
./tests/helpers_smoke.sh # Helper framework
```

## 🤖 Model Training & Deployment

### Generate and Deploy CoreML Models

```bash
# Full learning pipeline: export episodes → train → evaluate
make learn

# Individual steps
make router-train    # Train and produce SmallIntent.mlmodel + TinyIntent.mlmodel
make router-eval     # Evaluate models with precision/recall metrics
make promote         # Promote model to active use if criteria met
```

### Check Training Status

```bash
# Check model and training status via API
curl -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
  http://localhost:8787/router/train_summary

# Or run system health check
make doctor
```

The `/router/train_summary` endpoint returns:
- Training metrics (accuracy, precision/recall, F1 scores)
- Model artifacts status (SmallIntent.mlmodel, TinyIntent.mlmodel)
- Calibration curves and confidence statistics
- Deployment readiness status

## 🔐 Security

- All inference runs locally (no cloud calls)
- Helpers execute in sandboxed environments
- Critical actions require two-step approval
- Full audit logging for all actions

## 📚 Key Files

- `Makefile` - Build targets and automation
- `models.yaml` - Ollama model configuration
- `CLAUDE.md` - AI assistant context
- `PRD.md` - Product requirements document

## 🛠️ Development

```bash
# Check system health
make doctor

# Rotate API secret
./scripts/rotate_secret.sh

# Export episode data
./scripts/export_episodes.sh

# Print service URLs
./scripts/print_urls_and_secret.sh
```

## 📊 Monitoring

- **Logs**: `bridge/logs/`
- **Episodes**: `data/episodes/events.ndjson`
- **Health**: `bridge/selfheal.py`

---

**Note**: This is a local-first platform. No data leaves your Mac.