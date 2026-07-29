# 🧠 TinyIntent v2.0.0 – Claude Agent Context

TinyIntent is a multi-domain voice automation platform - the Swiss Army Knife of Voice Automation. One voice interface enables unlimited automation possibilities across weather, system monitoring, network infrastructure, trading, DevOps, and more.

---

## 🔒 Key Rules

- **Multi-domain automation focus.** No LLM generation - practical task automation across domains.
- **Router must be ANE-accelerated.** SmallIntent.mlmodel runs via CoreML on macOS.
- **Helpers are sandboxed.** All automation tasks go through schema-validated helpers.
- **Critical actions require two-step approval.** (e.g., closing crypto positions, network changes)
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

## 📂 Multi-Domain Automation Architecture

```
/Users/oberfelder/Projects/tinyintent/
├── tinyintent/              # Main CLI package
│   ├── cli.py              # Streamlined CLI entry point
│   ├── config.py           # Configuration management
│   └── interactive.py      # Interactive automation CLI
├── bridge/                 # FastAPI service core
│   ├── routes/             # Modular route organization
│   │   ├── shortcut.py     # M11.0 iPhone Shortcut API
│   │   ├── health.py       # Health check endpoints
│   │   ├── helpers.py      # Helper ecosystem management
│   │   ├── agents.py       # Agent lifecycle
│   │   └── system.py       # System operations
│   ├── tinyrpc.py          # Main FastAPI app
│   ├── security.py         # Authentication & authorization
│   ├── provenance.py       # Agent signing & tamper detection
│   └── location_service.py # GPS/location awareness
├── router/                 # SmallIntent.mlmodel routing
│   ├── SmallIntent.mlmodel # CoreML intent classifier
│   ├── train_router.swift  # Model training
│   └── data/               # Training datasets
├── helpers/                # Multi-domain automation helpers
│   ├── weather/            # Weather data & forecasting
│   ├── system_monitor/     # CPU, memory, disk monitoring
│   ├── network_monitor/    # Enterprise network infrastructure
│   ├── bot_guard/          # Crypto trading automation
│   ├── log_tailer/         # System log analysis
│   ├── traffic/            # Traffic conditions & routing
│   ├── registry.py         # Helper ecosystem management
│   └── executor.py         # Sandboxed execution engine
├── data/episodes/          # Episode logging & learning
├── tests/                  # Comprehensive test suites
├── scripts/                # Utility & automation scripts
├── docs/                   # Documentation
├── install.sh              # One-command installation
└── pyproject.toml          # Python packaging
```

## 📱 iPhone Voice Automation Integration

**URL**: `http://YOUR_IP:8787/shortcut/route`  
**Auth**: `X-Shortcut-Token: [secure-token]`

**Voice Commands**: 
- "What's the weather in Austin?" → Weather automation
- "Check my system performance" → System monitoring
- "Are there network anomalies?" → Network infrastructure analysis  
- "Show my trading positions" → Financial automation
- "Check error logs" → DevOps automation

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