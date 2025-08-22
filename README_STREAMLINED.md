# 🎯 TinyIntent - Voice-Activated AI Assistant

A streamlined, production-ready AI platform that connects your iPhone to local AI models via voice commands.

## ⚡ Quick Start

```bash
# Install
./install.sh

# Start TinyIntent
tinyintent

# Your server is now running at http://YOUR_IP:8787
```

## 📱 iPhone Setup

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

## 🚀 Features

- 🧠 **SmallIntent.mlmodel** - Local CoreML routing
- 📱 **iPhone Shortcut Integration** - Voice commands via Siri
- 🔒 **Security Framework** - Authentication, sandboxing, audit logging
- 🤖 **Helper System** - Extensible action execution
- 📊 **System Monitoring** - Health checks and metrics
- 🌐 **Tailscale Ready** - Works anywhere with secure networking

## 🛠️ Commands

```bash
tinyintent              # Start server (default: port 8787)
tinyintent --port 9000  # Start on custom port
tinyintent status       # Show system status
tinyintent --help       # Show all options
```

## 📋 Voice Commands

Try saying these to your iPhone:

- *"Show me recent error logs"*
- *"Check system health"*
- *"What's my server status?"*

## 🔧 Configuration

Environment variables (auto-configured with defaults):

```bash
TINYINTENT_PORT=8787                              # Server port
SHORTCUT_TOKEN=tinyintent-shortcut-token-123      # iPhone auth token
TINYINTENT_EXECUTION_ENABLED=1                    # Enable helper execution
```

## 📚 API Endpoints

- `GET /health` - Health check
- `GET /shortcut/ping` - iPhone Shortcut health check
- `POST /shortcut/route` - Voice command routing
- `GET /docs` - Interactive API documentation

## 🧠 System Architecture

```
iPhone (Siri) → Shortcuts → TinyIntent Bridge → SmallIntent.mlmodel → Helpers → Response
```

## 🔍 Troubleshooting

**"Command not found"**: Run `./install.sh` first
**"Connection refused"**: Check firewall and network settings
**"Invalid token"**: Verify `X-Shortcut-Token` header matches configuration

## 📖 Full Documentation

See `docs/` directory for complete documentation including:
- Advanced configuration
- Helper development
- Security guidelines
- Deployment options

---

**TinyIntent v2.0.0** - Built with ❤️ for voice-first AI interaction