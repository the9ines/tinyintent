# 🏗️ TinyIntent Architecture

This document provides a comprehensive technical overview of TinyIntent's architecture, designed for developers who need to understand how the system works internally.

## 🎯 System Overview

TinyIntent is a **voice-activated AI platform** that enables iPhone users to control local AI models through natural language. The system prioritizes **local-first operation**, **security**, and **modularity**.

### Core Principles

- **🔒 Local-First**: All AI inference happens locally (no cloud calls)
- **📱 Voice-Optimized**: Designed specifically for iPhone Shortcuts + Siri
- **🛡️ Security-First**: Multi-layer security with sandboxing and audit logging
- **🧩 Modular**: Clear separation of concerns with pluggable components

## 📊 High-Level Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   iPhone    │    │   Bridge    │    │   Router    │    │   Helpers   │
│  (Shortcuts)│    │  (FastAPI)  │    │  (CoreML)   │    │ (Sandboxed) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       │ HTTP POST         │ Intent            │ Schema            │
       │ /shortcut/route   │ Classification    │ Validation        │
       ▼                   ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        Request Flow                                     │
│                                                                         │
│ Voice → Shortcut → Bridge → Security → Router → Helper → Response       │
│   │        │        │        │          │        │        │           │
│   │        │        │        │          │        │        └─ JSON      │
│   │        │        │        │          │        └─ Sandbox Execution │
│   │        │        │        │          └─ gen|act Classification     │
│   │        │        │        └─ Auth + Validation + Rate Limiting     │
│   │        │        └─ FastAPI + Audit Logging                       │
│   │        └─ HTTP Request                                            │
│   └─ Dictated Text                                                    │
└─────────────────────────────────────────────────────────────────────────┘
```

## 🧩 Component Architecture

### 1. CLI Layer (`tinyintent/`)

**Purpose**: User interface and configuration management

```python
tinyintent/
├── cli.py              # Main CLI entry point
├── config.py           # Configuration management with Pydantic
├── credentials.py      # Secure credential generation and storage
├── simple_server.py    # Fallback server for basic functionality
└── health.py           # System health checks
```

**Key Features**:
- **Auto-configuration**: Generates secure credentials automatically
- **Environment management**: Handles all environment variable setup
- **Graceful fallback**: Falls back to simple server if full bridge unavailable
- **Developer experience**: `--quiet`, `--verbose`, `--reload` modes

### 2. Bridge Layer (`bridge/`)

**Purpose**: Core FastAPI service handling all requests

```python
bridge/
├── tinyrpc.py          # Main FastAPI application
├── routes/             # Modular API endpoints
│   ├── shortcut.py     # iPhone Shortcut integration (M11.0)
│   ├── health.py       # Health check endpoints
│   ├── helpers.py      # Helper management APIs
│   ├── agents.py       # Agent lifecycle management
│   └── system.py       # System administration
├── security.py         # Multi-layer security framework
├── validation.py       # Input validation and sanitization
├── sandbox_security.py # Sandboxing security enforcement
├── secret_manager.py   # Scoped secret management
├── gen_client.py       # Ollama client with circuit breaker
├── provenance.py       # Agent signing and tamper detection
└── logs/               # Audit logging system
```

**Security Architecture**:
```
┌─────────────────────────────────────────────────────────┐
│                   Security Layers                      │
├─────────────────────────────────────────────────────────┤
│ 1. Authentication: X-TinyIntent-Secret + timing attack │
│    prevention with constant-time comparison             │
├─────────────────────────────────────────────────────────┤
│ 2. Authorization: CSRF protection for state-changing   │
│    operations with token validation                     │
├─────────────────────────────────────────────────────────┤
│ 3. Input Validation: Script injection detection,       │
│    schema validation, length limits                     │
├─────────────────────────────────────────────────────────┤
│ 4. Rate Limiting: Per-session and global rate limits   │
│    with rolling windows                                 │
├─────────────────────────────────────────────────────────┤
│ 5. Sandboxing: Isolated execution with CPU/memory/     │
│    filesystem/network restrictions                      │
├─────────────────────────────────────────────────────────┤
│ 6. Audit Logging: Comprehensive event logging with     │
│    integrity chains and tamper detection               │
└─────────────────────────────────────────────────────────┘
```

### 3. Router Layer (`router/`)

**Purpose**: Intent classification using local CoreML models

```python
router/
├── SmallIntent.mlmodel     # CoreML intent classifier (70-85MB)
├── train_router.swift      # Model training with CreateML
├── eval_router.swift       # Model evaluation and metrics
├── data/                   # Training datasets
│   ├── intents.tsv        # Intent classification data
│   └── eval_results.json  # Evaluation metrics
└── train_summary.json     # Training results and performance
```

**Classification Flow**:
```
User Input: "Show me recent error logs"
     ↓
CoreML Model Processing (SmallIntent.mlmodel)
     ↓
Intent Classification: { route: "act", confidence: 0.94 }
     ↓
Route Decision: Execute helper for log analysis
```

**Performance Characteristics**:
- **Inference Speed**: <10ms on Apple Silicon (Neural Engine optimized)
- **Model Size**: ~70-85MB (INT8 quantized CoreML)
- **Accuracy**: >90% on validation set
- **Fallback**: Heuristic classification if model unavailable

### 4. Helper Layer (`helpers/`)

**Purpose**: Sandboxed execution of specific tasks

```python
helpers/
├── registry.py          # Helper discovery and validation
├── executor.py          # Sandboxed execution engine
├── manifest.py          # Helper metadata management
├── sdk.py              # Helper development SDK
├── sandbox.py          # Sandboxing implementation
├── bot_guard/          # Crypto trading helper
│   ├── main.js         # Node.js implementation
│   ├── helper.yaml     # Helper metadata
│   ├── input.schema.json
│   └── output.schema.json
└── log_tailer/         # System log analysis helper
    ├── main.py         # Python implementation
    ├── helper.yaml     # Helper metadata
    ├── input.schema.json
    └── output.schema.json
```

**Sandboxing Architecture**:
```
┌─────────────────────────────────────────────────────────┐
│                  Helper Sandbox                        │
├─────────────────────────────────────────────────────────┤
│ Resource Limits:                                        │
│ • CPU: 10 seconds max execution time                    │
│ • Memory: 256MB max memory usage                       │
│ • File Descriptors: 50 max open files                  │
│ • Network: Disabled by default                         │
├─────────────────────────────────────────────────────────┤
│ Filesystem Isolation:                                   │
│ • Isolated working directory per execution              │
│ • No access to sensitive system paths                   │
│ • Temporary file cleanup after execution               │
├─────────────────────────────────────────────────────────┤
│ Process Isolation:                                      │
│ • Separate process per helper execution                 │
│ • Process tree cleanup on timeout                      │
│ • Signal handling for graceful termination             │
└─────────────────────────────────────────────────────────┘
```

### 5. Data Layer (`data/episodes/`)

**Purpose**: Request logging, training data collection, and agent staging

```python
data/episodes/
├── episodes.py         # Episode logging and storage
├── schema.py          # Data schemas and validation
├── staging.db         # SQLite database for agent staging
└── logger.py          # Async logging implementation
```

**Data Flow**:
```
Request → Bridge → Episode Logger → SQLite/JSON → Training Data
   ↓         ↓           ↓              ↓             ↓
 Voice   FastAPI   Async Logger   Structured   Model Training
 Input   Handler   Background     Storage      Data Pipeline
```

## 🔐 Security Model

### Multi-Layer Security Architecture

#### Layer 1: Network Security
- **Token-based authentication** for iPhone Shortcuts
- **API secret authentication** for advanced operations
- **Constant-time comparison** to prevent timing attacks
- **Rate limiting** with per-session and global limits

#### Layer 2: Input Security
- **Comprehensive input validation** with schema enforcement
- **Script injection detection** using pattern matching
- **Length limits** to prevent buffer overflow attacks
- **Type validation** for all parameters

#### Layer 3: Execution Security
- **Process sandboxing** with isolated working directories
- **Resource limits** (CPU, memory, file descriptors)
- **Network isolation** (disabled by default for helpers)
- **Capability-based access control** for helper permissions

#### Layer 4: Data Security
- **Scoped secret management** with encryption
- **Audit logging** with integrity chains
- **Provenance tracking** with cryptographic signing
- **Emergency kill switches** for immediate execution shutdown

### Security Event Flow
```
Request → Auth Check → Input Validation → Rate Limit Check → 
Helper Execution → Audit Logging → Response
     ↓         ↓            ↓              ↓              ↓
 403 Forbidden  400 Bad    429 Too Many   Security     Tamper
 if invalid    Request if  Requests if    Violation    Detection
 credentials   malicious   rate limited   Logging      Alerts
```

## 📱 iPhone Integration (M11.0)

### Shortcut API Design

**Endpoint**: `POST /shortcut/route`

**Authentication**: `X-Shortcut-Token` header

**Request Flow**:
```javascript
// iPhone Shortcuts Request
{
  "text": "Show me recent error logs",
  "session_id": "optional-session-id",
  "mode": "preview|execute", 
  "return_format": "text|json"
}

// TinyIntent Response
{
  "speak": "Found 3 recent error logs from the last hour...",
  "truncated": false,
  "data": {
    "status": "success",
    "logs": [...],
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

**Voice Optimization**:
- **Response length limits**: Truncate at 280 characters for TTS
- **Clear error messages**: User-friendly error responses
- **Session tracking**: Optional session continuity
- **Format flexibility**: Text for voice, JSON for advanced shortcuts

## 🧠 AI/ML Architecture

### Router Model Pipeline

```
Training Data → CreateML → CoreML → Deployment
     ↓             ↓         ↓         ↓
 intents.tsv   Swift     Model     Neural Engine
 (episodes)   Training   Export    Inference
```

**Model Characteristics**:
- **Input**: Text sequences up to 128 tokens
- **Output**: `gen` (generative) or `act` (action) classification
- **Architecture**: Transformer-based text classifier
- **Optimization**: INT8 quantization for Neural Engine
- **Evaluation**: Precision, recall, F1 score tracking

### Generation Pipeline

```
User Input → Router → Ollama → Response Formatting → Voice Output
     ↓         ↓        ↓           ↓                 ↓
  "What is   "gen"   llama3.1    "The weather     iPhone TTS
   weather?"         8B model    today is..."     Playback
```

**Components**:
- **Circuit Breaker**: Prevents cascade failures from Ollama
- **Async Client**: Non-blocking generation with timeouts
- **Retry Logic**: Exponential backoff for transient failures
- **Task Management**: Cancellation support for long requests

## 🔄 Request Lifecycle

### Complete Request Flow

```
1. iPhone Shortcuts
   ├─ Voice Input: "Show me system logs"
   ├─ HTTP POST: /shortcut/route
   └─ Headers: X-Shortcut-Token

2. Bridge Authentication
   ├─ Token Validation (constant-time)
   ├─ Rate Limit Check
   └─ CSRF Protection

3. Input Processing
   ├─ JSON Parsing
   ├─ Schema Validation
   ├─ Input Sanitization
   └─ Length Limit Check

4. Intent Classification
   ├─ CoreML Model Inference
   ├─ Confidence Threshold Check
   └─ Route Decision: gen|act

5. Helper Execution (if act)
   ├─ Helper Selection: log_tailer
   ├─ Sandbox Creation
   ├─ Resource Limit Setup
   ├─ Schema Validation
   ├─ Process Execution
   └─ Output Capture

6. Response Generation
   ├─ Output Formatting
   ├─ Voice Optimization
   ├─ Error Handling
   └─ JSON Response

7. Audit Logging
   ├─ Request/Response Logging
   ├─ Security Event Logging
   ├─ Performance Metrics
   └─ Error Tracking

8. iPhone Response
   ├─ JSON Parsing
   ├─ Text Extraction
   └─ TTS Playback
```

### Error Handling Strategy

```
Error Type → Detection → Response → Recovery
    ↓           ↓          ↓         ↓
Auth Failure → Token    → 401     → Re-authenticate
             Validation   Error     
Input Error → Schema    → 400     → Fix input format
            Validation   Error     
Rate Limit → Counter    → 429     → Wait and retry
           Check        Error     
Helper Error→ Execution → 500     → Fallback response
            Failure      Error     
System Error→ Health    → 503     → Service restart
            Check        Error     
```

## 📊 Performance Characteristics

### Latency Targets

| Component | Target | Actual | Notes |
|-----------|--------|--------|-------|
| Router Inference | <10ms | ~5ms | Neural Engine optimized |
| Helper Execution | <5s | 1-3s | Sandboxed process startup |
| Total Request | <10s | 3-7s | End-to-end including voice |
| Authentication | <1ms | <1ms | Constant-time comparison |

### Throughput Characteristics

| Metric | Limit | Monitoring |
|--------|--------|------------|
| Requests/session/min | 60 | Rate limiter |
| Global requests/min | 500 | Circuit breaker |
| Helper executions/min | 10 | Resource manager |
| Concurrent helpers | 4 | Process pool |

### Resource Usage

| Component | CPU | Memory | Disk |
|-----------|-----|--------|------|
| Bridge (FastAPI) | 5-15% | 50-100MB | Minimal |
| Router (CoreML) | 1-3% | 200MB | 70MB model |
| Helper (sandbox) | 10-30% | 50-256MB | Isolated dirs |
| Total System | 20-50% | 300-600MB | <1GB |

## 🔧 Configuration Management

### Configuration Hierarchy

```
1. Environment Variables (highest priority)
   ├─ TINYINTENT_SECRET
   ├─ SHORTCUT_TOKEN
   └─ TINYINTENT_LOG_LEVEL

2. Configuration Files
   ├─ ~/.tinyintent/credentials.json
   ├─ models.yaml
   └─ helpers/registry.yaml

3. Defaults (lowest priority)
   ├─ Development-friendly defaults
   ├─ Auto-generated credentials
   └─ Fallback configurations
```

### Security Configuration

```python
# Security settings with validation
class SecuritySettings(BaseSettings):
    secret: str = Field(..., min_length=32)  # Required API secret
    allow_dev_local: bool = Field(True)      # Development bypass
    rate_limit_session: int = Field(60)      # Per-session limit
    rate_limit_global: int = Field(500)      # Global limit
    csrf_token_expiry: int = Field(3600)     # CSRF token TTL
```

## 🚀 Deployment Architecture

### Development Mode
```
Developer Machine:
├─ tinyintent (CLI)
├─ Bridge (FastAPI) on localhost:8787
├─ Ollama on localhost:11434
├─ iPhone on same WiFi network
└─ Direct HTTP communication
```

### Production Mode
```
Mac Server:
├─ tinyintent as launchd service
├─ Bridge with production secrets
├─ Ollama with optimized models
├─ Tailscale for secure networking
└─ iPhone over encrypted tunnel
```

### Scaling Considerations

- **Single-node design**: Optimized for personal/small team use
- **Local-first**: No external dependencies required
- **Resource-aware**: Designed for standard Mac hardware
- **Network-efficient**: Minimal bandwidth usage

---

This architecture provides a robust, secure, and maintainable foundation for voice-activated AI while maintaining simplicity and developer-friendliness.