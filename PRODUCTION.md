# 🚀 TinyIntent Production Deployment Guide

This guide ensures secure, reliable production deployment of TinyIntent v2.0.0.

## 🔒 Critical Security Requirements

### 1. Generate Secure Secrets

**REQUIRED**: Replace all default secrets before production deployment.

```bash
# Generate secure production secret (64+ characters)
python3 -c "
import secrets
import string
chars = string.ascii_letters + string.digits + '!@#$%^&*()_+-=[]{}|;:,.<>?'
secret = ''.join(secrets.choice(chars) for _ in range(64))
print(f'TINYINTENT_SECRET={secret}')
"

# Generate secure shortcut token
python3 -c "
import secrets
import string
token = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))
print(f'SHORTCUT_TOKEN={token}')
"
```

### 2. Environment Configuration

Create a `.env` file or set environment variables:

```bash
# Required production variables
export TINYINTENT_SECRET="YOUR_64_CHAR_SECURE_SECRET_HERE"
export SHORTCUT_TOKEN="YOUR_32_CHAR_TOKEN_HERE"
export TINYINTENT_ENVIRONMENT="production"
export TINYINTENT_EXECUTION_ENABLED="1"

# Server configuration
export TINYINTENT_BIND="127.0.0.1"  # Restrict to localhost for security
export TINYINTENT_PORT="8787"
export TINYINTENT_LOG_LEVEL="warning"  # Reduce log verbosity

# Disable development features
export TINYINTENT_ALLOW_DEV_LOCAL="0"
export NODE_ENV="production"

# Ollama configuration
export OLLAMA_HOST="http://localhost:11434"
export GEN_TIMEOUT_S="30"
export GEN_MAX_RETRIES="3"

# Optional: Helper configuration (if using bot_guard)
export EXCHANGE_API_KEY="your_exchange_api_key"
export EXCHANGE_SECRET="your_exchange_secret"
export EXCHANGE_PASSPHRASE="your_passphrase"

# Optional: SSH operations (if using ssh_ops)
export SSH_HOST="your_server_host"
export SSH_USER="your_ssh_user"
export SSH_KEY_PATH="/path/to/ssh/key"
```

## 📦 Installation & Setup

### 1. System Requirements

- **macOS 13+** (for Apple Neural Engine support)
- **Python 3.9+**
- **Ollama** (for local LLM)
- **Swift** (for router training)

### 2. Install TinyIntent

```bash
# Clone repository
git clone <repository-url>
cd tinyintent

# Install dependencies
pip3 install -e .

# Verify installation
tinyintent status
```

### 3. Verify Security

```bash
# Check for security warnings
tinyintent status

# Expected output: No security warnings
# ❌ If you see: "SECURITY WARNING: Using default secret!" 
#    → Set TINYINTENT_SECRET immediately

# ❌ If you see: "Using default shortcut token"
#    → Set SHORTCUT_TOKEN for production
```

## 🚀 Production Startup

### 1. Quick Start

```bash
# Start with production environment
export TINYINTENT_SECRET="your_secure_secret"
export SHORTCUT_TOKEN="your_secure_token"
export TINYINTENT_ENVIRONMENT="production"

tinyintent --host 127.0.0.1 --port 8787
```

### 2. Advanced Configuration

```bash
# Production with custom settings
TINYINTENT_BIND="127.0.0.1" \
TINYINTENT_LOG_LEVEL="warning" \
TINYINTENT_ALLOW_DEV_LOCAL="0" \
tinyintent --port 8787
```

### 3. Systemd Service (Linux)

Create `/etc/systemd/system/tinyintent.service`:

```ini
[Unit]
Description=TinyIntent Bridge Service
After=network.target

[Service]
Type=simple
User=tinyintent
WorkingDirectory=/opt/tinyintent
Environment=TINYINTENT_SECRET=your_secure_secret
Environment=SHORTCUT_TOKEN=your_secure_token
Environment=TINYINTENT_ENVIRONMENT=production
Environment=TINYINTENT_BIND=127.0.0.1
Environment=TINYINTENT_PORT=8787
ExecStart=/usr/local/bin/tinyintent
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable tinyintent
sudo systemctl start tinyintent
sudo systemctl status tinyintent
```

## 🏥 Production Health Monitoring

### 1. Health Check Endpoints

```bash
# Basic health
curl http://127.0.0.1:8787/health/

# Readiness check
curl http://127.0.0.1:8787/health/ready

# System diagnostics
curl http://127.0.0.1:8787/system/doctor
```

### 2. Expected Responses

**Healthy System:**
```json
{
  "ok": true,
  "ts": "2025-08-22T16:00:00Z",
  "service": "TinyIntent Bridge",
  "version": "2.0.0",
  "uptime_seconds": 3600
}
```

**System Doctor:**
```json
{
  "healthy": true,
  "checks": {
    "router": {"status": "ok", "model_available": true},
    "helpers": {"status": "ok", "total_registered": 3},
    "storage": {"status": "ok"},
    "configuration": {"status": "ok"}
  }
}
```

### 3. Monitoring Script

```bash
#!/bin/bash
# monitor_tinyintent.sh

HEALTH_URL="http://127.0.0.1:8787/health/"

while true; do
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)
    
    if [ "$HTTP_CODE" -eq 200 ]; then
        echo "$(date): TinyIntent healthy (HTTP $HTTP_CODE)"
    else
        echo "$(date): TinyIntent unhealthy (HTTP $HTTP_CODE)" >&2
        # Add alerting logic here
    fi
    
    sleep 60
done
```

## 📱 iPhone Shortcut Setup

### 1. Shortcut Configuration

1. Open **iOS Shortcuts** app
2. Create new shortcut with these actions:
   - **Dictate Text**
   - **Get Contents of URL** (POST)
   - **Speak Text**

### 2. HTTP Request Settings

```
URL: http://YOUR_SERVER_IP:8787/shortcut/route
Method: POST
Headers: 
  - X-Shortcut-Token: YOUR_SECURE_TOKEN
  - Content-Type: application/json
Body: {"text": "[Dictated Text]"}
```

### 3. Response Handling

Use **Get Value** action to extract `speak` field from JSON response.

## 🔧 Helper Configuration

### 1. Bot Guard (Trading)

```bash
export EXCHANGE_API_KEY="your_api_key"
export EXCHANGE_SECRET="your_secret"
export EXCHANGE_PASSPHRASE="your_passphrase"
```

### 2. SSH Operations

```bash
export SSH_HOST="your.server.com"
export SSH_USER="your_username"
export SSH_KEY_PATH="/path/to/private/key"
```

### 3. Log Tailer

No additional configuration required.

## 🚨 Security Checklist

- [ ] **TINYINTENT_SECRET** set to 64+ character secure random string
- [ ] **SHORTCUT_TOKEN** changed from default
- [ ] **TINYINTENT_ENVIRONMENT** set to "production"
- [ ] **TINYINTENT_ALLOW_DEV_LOCAL** set to "0"
- [ ] Server bound to **127.0.0.1** (not 0.0.0.0)
- [ ] Firewall configured to restrict access
- [ ] All helper API keys secured
- [ ] Audit logs monitoring enabled
- [ ] Regular security updates scheduled

## 🔧 Troubleshooting

### Issue: "Full TinyIntent app not available"

**Solution**: This error has been fixed in v2.0.0. Ensure you're using the latest version:

```bash
pip3 install -e . --upgrade
tinyintent --version
```

### Issue: Helper configuration required

**Solution**: Check helper health and configure required environment variables:

```bash
curl http://127.0.0.1:8787/helpers/health
# Configure missing environment variables shown in response
```

### Issue: Router model not found

**Solution**: Train or download the SmallIntent model:

```bash
make router-train  # Train new model
# OR
# Download pre-trained model (if available)
```

### Issue: Ollama connection failed

**Solution**: Ensure Ollama is running:

```bash
ollama serve &
curl http://localhost:11434/api/tags
```

## 📊 Performance Optimization

### 1. Resource Limits

For production deployment, consider:

- **Memory**: 2GB+ recommended
- **CPU**: 4+ cores for Apple Silicon ANE
- **Storage**: 10GB+ for models and logs

### 2. Router Performance

The SmallIntent model targets:
- **Size**: 70-85MB INT8 CoreML
- **Latency**: ≤20ms on Apple Neural Engine
- **Accuracy**: 90%+ on intent classification

### 3. Scaling

TinyIntent runs as a single process. For high availability:

1. Use multiple instances behind a load balancer
2. Share model files via NFS or similar
3. Use external database for episode storage

## 📝 Logging & Auditing

### 1. Audit Logs

Located at: `bridge/logs/audit.log`

Monitor for:
- Authentication failures
- Helper execution attempts
- Emergency kill switch activations

### 2. Log Rotation

Automatic rotation at 50MB or SIGHUP signal.

### 3. Log Analysis

```bash
# Recent activity
tail -f bridge/logs/audit.log

# Authentication failures
grep "auth_failed" bridge/logs/audit.log

# Helper executions
grep "helper_execute" bridge/logs/audit.log
```

## 🆘 Emergency Procedures

### 1. Emergency Stop

```bash
# Immediate shutdown
pkill tinyintent

# Or use emergency endpoint
curl -X POST http://127.0.0.1:8787/system/emergency/kill
```

### 2. Disable Helper Execution

```bash
export TINYINTENT_EXECUTION_ENABLED="0"
# Restart TinyIntent
```

### 3. Incident Response

1. Stop TinyIntent service
2. Preserve audit logs
3. Review recent activity
4. Update security credentials
5. Restart with updated configuration

---

## ✅ Production Readiness Verification

Run this checklist before going live:

```bash
# 1. Check security warnings
tinyintent status | grep -i warning

# 2. Verify health endpoints
curl -f http://127.0.0.1:8787/health/

# 3. Test authentication
curl -X POST http://127.0.0.1:8787/shortcut/route \
  -H "X-Shortcut-Token: INVALID" \
  -d '{"text":"test"}' 
# Expected: 401/403 error

# 4. Test core functionality
curl -X POST http://127.0.0.1:8787/shortcut/route \
  -H "X-Shortcut-Token: YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text":"test message"}'
# Expected: JSON response with "speak" field

# 5. Check system doctor
curl http://127.0.0.1:8787/system/doctor | jq '.healthy'
# Expected: true
```

**✅ If all checks pass, TinyIntent is production-ready!**

---

*TinyIntent v2.0.0 Production Deployment Guide*
*Generated: $(date)*