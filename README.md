# 🎯 TinyIntent v2.0.0 - Voice-Activated AI Assistant

A streamlined, production-ready AI platform that connects your iPhone to local AI models via voice commands.

## ⚡ Quick Start

```bash
# Install TinyIntent (one-time setup)
./install.sh

# Start TinyIntent server
tinyintent

# Your server is now running at http://YOUR_IP:8787
# Ready for iPhone voice shortcuts!
```

## 📱 iPhone Voice Setup

1. **Open Shortcuts app** on your iPhone
2. **Create new shortcut** with these actions:
   - **Dictate Text** (Stop Listening: After Pause)
   - **Get Contents of URL**:
     - URL: `http://YOUR_IP:8787/shortcut/route`
     - Method: POST
     - Headers: `X-Shortcut-Token: tinyintent-shortcut-token-123`
     - JSON Body: `{"text": "[Dictated Text]", "return_format": "text"}`
   - **Get Text from Contents of URL** (extract `speak` field)
   - **Speak Text**

3. **Test**: Say *"Show me system logs"* and hear the response!

## 🎯 Simple Commands

```bash
tinyintent              # Start server (default: port 8787)
tinyintent --port 9000  # Start on custom port
tinyintent status       # Show system status
tinyintent --help       # Show all options
```

## 📁 Project Structure

```
tinyintent/
├── tinyintent/           # Main CLI package
│   ├── cli.py           # Streamlined CLI entry point
│   ├── config.py        # Configuration management
│   └── simple_server.py # Fallback server
├── bridge/              # FastAPI service core
│   ├── routes/          # Modular route organization
│   │   ├── shortcut.py  # iPhone Shortcut API (M11.0)
│   │   ├── health.py    # Health check endpoints
│   │   ├── helpers.py   # Helper management
│   │   ├── agents.py    # Agent lifecycle
│   │   └── system.py    # System operations
│   ├── tinyrpc.py       # Main FastAPI app
│   ├── security.py      # Authentication & authorization
│   └── provenance.py    # Agent signing & tamper detection
├── router/              # SmallIntent.mlmodel routing
│   ├── SmallIntent.mlmodel  # CoreML intent classifier
│   ├── train_router.swift  # Model training
│   └── data/            # Training datasets
├── helpers/             # Sandboxed task execution
│   ├── bot_guard/       # Crypto trading helper
│   ├── log_tailer/      # System log analysis
│   ├── registry.py      # Helper discovery
│   └── executor.py      # Sandboxed execution
├── data/episodes/       # Episode logging & storage
├── tests/               # Comprehensive test suites
├── scripts/             # Utility & automation scripts
├── docs/                # Documentation
├── install.sh           # One-command installation
└── pyproject.toml       # Python packaging
```

## 🚀 Key Features

- 🧠 **SmallIntent.mlmodel** - Local CoreML intent routing
- 📱 **iPhone Shortcut Integration** - Voice commands via Siri  
- 🔒 **Security Framework** - Authentication, sandboxing, audit logging
- 🤖 **Helper System** - Extensible action execution
- 📊 **System Monitoring** - Health checks and metrics
- 🌐 **Tailscale Ready** - Works anywhere with secure networking

## 🎯 Core Components

### 📱 iPhone Shortcut API (M11.0)
- **Endpoint**: `/shortcut/route`
- **Auth**: `X-Shortcut-Token` header
- **Features**: Voice-optimized text formatting, TTS optimization
- **Integration**: Seamless Siri voice command processing

### 🧠 SmallIntent Router  
- **Model**: `SmallIntent.mlmodel` (CoreML, runs on Neural Engine)
- **Classification**: `gen` (generative) vs `act` (action execution)
- **Training**: Swift + CreateML → CoreML artifacts
- **Performance**: Sub-10ms inference on Apple Silicon

### 🤖 Helper Framework
- **Runtime**: Node.js sandboxed execution with capability isolation
- **Security**: CPU/memory limits, filesystem restrictions, network controls
- **Registry**: YAML-based discovery with lifecycle management
- **Available Helpers**:
  - `bot_guard` - Crypto trading position management
  - `log_tailer` - System log analysis and monitoring

## 📋 Voice Commands

Try saying these to your iPhone:

- *"Show me recent error logs"*
- *"Check system health"*
- *"What's my server status?"*
- *"Get my trading positions"*

## 🧪 Testing & Development

```bash
# Run comprehensive test suite
make test

# Individual test suites
./tests/health.sh         # System health checks
./tests/auth.sh           # Authentication testing
./tests/routes.smoke.sh   # API endpoint validation
./tests/router_smoke.sh   # Router model testing
./tests/helpers_smoke.sh  # Helper framework testing

# Advanced commands
tinyintent --reload       # Development mode with auto-reload
make doctor              # System diagnostic report
make router-train        # Train new intent classification model
```

## 🔧 Configuration

Environment variables (auto-configured with defaults):

```bash
TINYINTENT_PORT=8787                              # Server port
SHORTCUT_TOKEN=tinyintent-shortcut-token-123      # iPhone auth token
TINYINTENT_EXECUTION_ENABLED=1                    # Enable helper execution
TINYINTENT_SECRET=your-secret-here                # API authentication
```

## 📚 API Documentation

- `GET /health` - Health check
- `GET /shortcut/ping` - iPhone Shortcut health check
- `POST /shortcut/route` - Voice command routing
- `GET /docs` - Interactive API documentation
- `GET /helpers` - Available helpers list
- `POST /helpers/{id}/preview` - Helper preview mode

## 🔐 Security & Privacy

- 🔒 **Local-First**: All inference runs locally (no cloud calls)
- 🛡️ **Sandboxed Execution**: Helpers run in isolated environments with CPU/memory limits
- 🔑 **Multi-Layer Auth**: Token-based authentication for iPhone + API secret for advanced access
- 📋 **Audit Logging**: Full request/response/error logging with tamper detection
- 🚦 **Lifecycle Gates**: Agent staging, approval workflows, and emergency kill switches
- 🔐 **Provenance Tracking**: Cryptographic signing and tamper-evidence for all agents

## 🧠 System Architecture

```
iPhone (Siri) → Shortcuts → TinyIntent Bridge → SmallIntent.mlmodel → Helpers → Response
```

## 🔍 Troubleshooting

**"Command not found"**: Run `./install.sh` first  
**"Connection refused"**: Check firewall and network settings  
**"Invalid token"**: Verify `X-Shortcut-Token` header matches configuration  
**"Module not found"**: Ensure you're in the TinyIntent project directory

## 📚 Documentation

- `README_STREAMLINED.md` - Quick start guide
- `docs/iOS_SHORTCUTS.md` - iPhone Shortcut setup
- `PRD.md` - Complete product requirements
- `CLAUDE.md` - AI assistant context

## 🛠️ Advanced Operations

```bash
# System diagnostics
make doctor

# Security operations  
./scripts/rotate_secret.sh      # Rotate API secret
./scripts/print_urls_and_secret.sh  # Show current config

# Data management
./scripts/export_episodes.sh    # Export training data
```

---

**TinyIntent v2.0.0** - Built with ❤️ for voice-first AI interaction

---

Built by [the9ines.com](https://the9ines.com)

**TinyIntent v2.0.0** - Voice-first AI interaction for your Mac

**Note**: This is a local-first platform. No data leaves your Mac.
