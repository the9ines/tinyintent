# 🧠 TinyIntent v2.0.0 – Claude Agent Context

TinyIntent is a streamlined, production-ready AI platform for voice-activated personal assistant tasks. Connect your iPhone to local AI models via simple voice commands.

---

## 🔒 Key Rules

- **No cloud inference.** All models run locally via Ollama.
- **Router must be ANE-accelerated.** SmallIntent.mlmodel runs via CoreML on macOS.
- **Helpers are sandboxed.** All `act` tasks must go through schema-validated helpers.
- **Critical actions require two-step approval.** (e.g., closing crypto positions)
- **Emergency flow is limited and fully audited.**
- **Claude does not run the system.** You are only used as a senior architect to help improve it when needed.

---

## ⚡ Streamlined Usage

```bash
# Install (one-time)
./install.sh

# Start TinyIntent
tinyintent              # Default: port 8787
tinyintent --port 9000  # Custom port
tinyintent status       # Show configuration
tinyintent --help       # All options

# Advanced operations
make router-train      # Train the SmallIntent model
make router-eval       # Evaluate the trained model (latency/accuracy)
make learn             # Mine episodes, retrain router, promote if valid
make doctor            # Show model/hardware readiness

## 📂 Streamlined File Structure

```
/Users/oberfelder/Projects/tinyintent/
├── tinyintent/              # Main CLI package
│   ├── cli.py              # Streamlined CLI entry point
│   ├── config.py           # Configuration management
│   └── simple_server.py    # Fallback server
├── bridge/                 # FastAPI service core
│   ├── routes/             # Modular route organization
│   │   ├── shortcut.py     # M11.0 iPhone Shortcut API
│   │   ├── health.py       # Health check endpoints
│   │   ├── helpers.py      # Helper management
│   │   ├── agents.py       # Agent lifecycle
│   │   └── system.py       # System operations
│   ├── tinyrpc.py          # Main FastAPI app
│   ├── security.py         # Authentication & authorization
│   ├── provenance.py       # Agent signing & tamper detection
│   └── logs/               # Audit logging
├── router/                 # SmallIntent.mlmodel routing
│   ├── SmallIntent.mlmodel # CoreML intent classifier
│   ├── train_router.swift  # Model training
│   └── data/               # Training datasets
├── helpers/                # Sandboxed task execution
│   ├── bot_guard/          # Crypto trading helper
│   ├── log_tailer/         # System log analysis
│   ├── registry.py         # Helper discovery
│   └── executor.py         # Sandboxed execution
├── data/episodes/          # Episode logging & storage
├── tests/                  # Comprehensive test suites
├── scripts/                # Utility & automation scripts
├── docs/                   # Documentation
├── install.sh              # One-command installation
├── pyproject.toml          # Python packaging
├── Makefile               # Build automation
└── models.yaml            # Ollama model configuration
```

## 📱 iPhone Shortcut Integration

**URL**: `http://YOUR_IP:8787/shortcut/route`  
**Auth**: `X-Shortcut-Token: tinyintent-shortcut-token-123`

**Setup**: Create Shortcut with Dictate Text → HTTP Request → Speak Response

---

## 🧠 What You're Expected to Help With
Claude, you're used for:
Improving Python bridge routing logic
Drafting router training code (Swift + CreateML)
Improving helper manifest schemas
Refactoring APIs and CLI ergonomics
Reviewing intent training data structure
Making robust automation scripts (Makefile, shell)
You do not handle UI, iOS, or devops tasks unless asked.
🗂️ Always start with
Read PRD.md before taking any action.