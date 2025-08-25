# 🎯 TinyIntent Interactive CLI Guide

## Overview

TinyIntent now includes a **Claude-style interactive CLI** that provides a conversational interface for natural language queries. Simply type `tinyintent` to start an interactive session.

## Getting Started

### 1. Start Interactive Mode

```bash
tinyintent
```

This automatically:
- ✅ **Starts Ollama service** (if available and not running)
- ✅ **Initializes SmallIntent router** for intelligent query routing  
- ✅ **Loads all helpers** for action processing
- ✅ **Sets up secure environment** with auto-generated credentials

### 2. Interface Overview

```
🎯 TinyIntent Interactive CLI

Type your queries naturally - TinyIntent will route them intelligently:
• Information requests → Local AI generation  
• Helper actions → Weather, trading, logs, etc.
• System commands → Helper management

Commands:
• /help - Show this help
• /status - Show system status
• /helper list - List installed helpers
• /quit - Exit TinyIntent

Ready to assist! What would you like to do?

TinyIntent > 
```

## Usage Examples

### Natural Language Queries

```bash
TinyIntent > what's the weather in 78624?
# Routes to weather helper, returns real weather data

TinyIntent > what is machine learning?  
# Routes to local LLM for generation

TinyIntent > show me my crypto positions
# Routes to bot_guard helper for trading data

TinyIntent > check recent error logs
# Routes to log_tailer helper for system monitoring
```

### System Commands

```bash
TinyIntent > /status
# Shows system status (Ollama, router, helpers)

TinyIntent > /helper list  
# Lists all installed helper packages

TinyIntent > /helper search weather
# Search for weather-related helpers

TinyIntent > /helper info weather_helper
# Get detailed information about a helper

TinyIntent > /quit
# Exit interactive mode
```

## Intelligent Routing

TinyIntent automatically routes your queries using **SmallIntent.mlmodel**:

### 🤖 **Generation Route** (`gen`)
- **Questions**: "What is...", "How does...", "Why..."
- **Explanations**: "Tell me about...", "Explain..."  
- **General knowledge**: Science, history, programming concepts
- **Processed by**: Local Ollama models (llama3.2:3b default)

### ⚡ **Action Route** (`act`) 
- **Weather**: "weather", "temperature", "forecast", "rain"
- **Trading**: "crypto", "positions", "trade", "close", "buy", "sell"
- **System**: "logs", "error", "check", "tail", "status"
- **Traffic**: "traffic", "route", "directions", "drive"
- **Processed by**: Specific helper packages

### 🔄 **Fallback Logic**
- Router unavailable → Simple keyword matching
- Low confidence → Enhanced fallback routing
- Helper keywords prioritized over question words

## Service Management

### Automatic Ollama Management
- **Auto-start**: Ollama service starts automatically if not running
- **Health checks**: Monitors service status  
- **Graceful shutdown**: Stops Ollama when exiting (if we started it)
- **Fallback**: Continues without Ollama if unavailable

### Manual Service Control
```bash
# Check if Ollama is running
ollama list

# Start Ollama manually  
ollama serve

# Install models
ollama pull llama3.2:3b
ollama pull qwen2.5:32b-instruct-q4_K_M
```

## Configuration

### Environment Variables
```bash
export OLLAMA_MODEL="qwen2.5:32b-instruct-q4_K_M"  # Change default model
export TINYINTENT_EXECUTION_ENABLED=1               # Enable helper execution
export TINYINTENT_LOG_LEVEL=info                   # Increase logging
```

### Model Configuration
Edit `models.yaml` to configure available models:
```yaml
models:
  small: "llama3.2:3b" 
  medium: "qwen2.5:32b-instruct-q4_K_M"
  large: "llama3.1:70b"
```

## Server Mode vs Interactive Mode

### Interactive Mode (Default)
```bash
tinyintent                    # Interactive CLI
tinyintent interactive        # Explicit interactive mode
```
- ✅ Conversational interface
- ✅ Auto-starts Ollama
- ✅ Natural language queries
- ✅ Built-in helper management

### Server Mode  
```bash  
tinyintent serve              # HTTP server mode
tinyintent --port 9000        # Custom port
tinyintent --host 127.0.0.1   # Custom host
```
- ✅ iPhone Shortcut integration
- ✅ HTTP API endpoints
- ✅ Multiple client support
- ✅ Background service

## Troubleshooting

### Common Issues

**❌ "Generation failed: 504 timeout"**
```bash
# Ollama not running or model not available
ollama serve
ollama pull llama3.2:3b
```

**❌ "Helper execution failed: Missing environment variables"**  
```bash
# For trading helpers, set required API credentials
export EXCHANGE_API_KEY=your_key
export EXCHANGE_SECRET=your_secret
export TINYINTENT_EXECUTION_ENABLED=1
```

**❌ "Router not available"**
```bash
# SmallIntent model missing - fallback routing will be used
make router-train  # Train router model
# OR continue with fallback (still functional)
```

### Debug Mode
```bash
# Enable verbose logging
TINYINTENT_LOG_LEVEL=debug tinyintent

# Check system status
tinyintent status
```

## Advanced Features

### Helper Development
```bash
TinyIntent > /helper generate
# Interactive helper creation wizard

TinyIntent > /helper install ./my_custom_helper/
# Install local helper packages
```

### Multi-Modal Support
- **Text queries**: Natural language processing
- **Voice integration**: iPhone Shortcut compatibility  
- **Location awareness**: GPS coordinate integration
- **File processing**: Helper-specific file operations

### Learning System
- **Episode collection**: Automatic query logging
- **Model retraining**: Continuous improvement
- **Edge case detection**: Low-confidence routing analysis

## Examples Session

```
🎯 TinyIntent Interactive CLI
Ready to assist! What would you like to do?

TinyIntent > what's the weather like?
🌤️ Currently 85°F feels like 88°F and partly cloudy in Austin, Texas

TinyIntent > what is artificial intelligence?
🤖 Artificial intelligence (AI) refers to computer systems that can perform tasks typically requiring human intelligence...

TinyIntent > /helper search crypto
🔍 Found 1 helper: bot_guard (Trading, High Risk)

TinyIntent > /status  
🔍 System Status
  Ollama: ✅ Running
  SmallIntent Router: ✅ Available  
  ML Models: ✅ Loaded
  Installed Helpers: 5/5

TinyIntent > /quit
👋 Goodbye!
```

## Integration with iPhone Shortcuts

The interactive mode complements (doesn't replace) iPhone Shortcuts:

- **Interactive CLI**: Desktop/terminal usage
- **iPhone Shortcuts**: Voice commands via HTTP API  
- **Same backend**: Both use identical routing and helper systems
- **Unified experience**: Consistent responses across interfaces

For iPhone setup, use: `tinyintent serve` and follow the existing Shortcut configuration guide.

---

## 🚀 Ready to Use!

Simply type `tinyintent` to start your interactive TinyIntent session. The system will handle service startup, routing, and helper execution automatically!