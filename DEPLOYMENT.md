# TinyIntent Deployment Guide

This guide covers deployment options for TinyIntent in various environments.

## Prerequisites

- Python 3.11+
- Docker (for containerized deployment)
- Ollama server
- At least 4GB RAM and 2GB free disk space
- **CoreML model artifacts** (generated via `make learn` - see Model Generation section)

## Environment Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your configuration:
   - Set a strong `TINYINTENT_SECRET` (minimum 32 characters)
   - Configure Ollama URL if not using localhost
   - Set `TINYINTENT_EXECUTION_ENABLED=1` to enable helper execution
   - Adjust rate limits and resource constraints as needed

## Model Generation (Required Before Deployment)

**⚠️ CRITICAL**: TinyIntent requires CoreML model artifacts before the bridge can start. These models are not included in the repository and must be generated locally.

### Generate Required Models

```bash
# Generate both SmallIntent.mlmodel and TinyIntent.mlmodel
make learn

# Verify models were created
make doctor

# Expected output:
#   ✅ SmallIntent.mlmodel present (macOS optimized, ≤52MB)
#   ✅ TinyIntent.mlmodel present (mobile optimized, ≤10MB)
```

### Model Files Required

The following files must exist in `router/` before starting the bridge:

- `router/SmallIntent.mlmodel` - Main router model for macOS (ANE accelerated)
- `router/TinyIntent.mlmodel` - Compact version for mobile/constrained environments  
- `router/train_summary.json` - Training metadata and performance metrics

If these files are missing, the bridge will **fail to start** with model loading errors.

### First-Time Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate models (this will take several minutes)
make learn

# 3. Verify system readiness
make doctor

# 4. Start the bridge service
make bridgesrv
```

## Development Deployment

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Start the service:
   ```bash
   make bridgesrv
   ```
   or
   ```bash
   python -m tinyintent.bridge.tinyrpc
   ```

3. Verify deployment:
   ```bash
   curl http://localhost:8787/healthz
   ```

## Production Deployment

### Option 1: Docker Compose (Recommended)

1. Set environment variables:
   ```bash
   export TINYINTENT_SECRET="your-production-secret-key-here"
   export GRAFANA_PASSWORD="your-grafana-password"
   ```

2. Start all services:
   ```bash
   docker-compose up -d
   ```

3. Check service health:
   ```bash
   docker-compose ps
   curl http://localhost:8787/healthz
   ```

### Option 2: Systemd Service

1. Create service user:
   ```bash
   sudo useradd --system --create-home --shell /bin/false tinyintent
   ```

2. Install application:
   ```bash
   sudo -u tinyintent git clone https://github.com/tinyintent/tinyintent.git /home/tinyintent/app
   cd /home/tinyintent/app
   sudo -u tinyintent python -m venv venv
   sudo -u tinyintent ./venv/bin/pip install -r requirements.txt
   ```

3. Create systemd service file `/etc/systemd/system/tinyintent.service`:
   ```ini
   [Unit]
   Description=TinyIntent Bridge Service
   After=network.target
   Requires=network.target

   [Service]
   Type=exec
   User=tinyintent
   Group=tinyintent
   WorkingDirectory=/home/tinyintent/app
   Environment=PATH=/home/tinyintent/app/venv/bin
   EnvironmentFile=/home/tinyintent/app/.env
   ExecStart=/home/tinyintent/app/venv/bin/python -m tinyintent.bridge.tinyrpc
   ExecReload=/bin/kill -HUP $MAINPID
   Restart=always
   RestartSec=5
   
   # Security settings
   NoNewPrivileges=true
   PrivateTmp=true
   ProtectSystem=strict
   ProtectHome=true
   ReadWritePaths=/home/tinyintent/app/data /home/tinyintent/app/logs

   [Install]
   WantedBy=multi-user.target
   ```

4. Enable and start service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable tinyintent
   sudo systemctl start tinyintent
   ```

### Option 3: Manual Production Setup

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create production directories:
   ```bash
   mkdir -p data/episodes logs backups
   ```

3. Set environment variables in `.env` file

4. Start with production settings:
   ```bash
   TINYINTENT_ENVIRONMENT=production \
   TINYINTENT_WORKERS=4 \
   TINYINTENT_BIND=0.0.0.0 \
   python -m tinyintent.bridge.tinyrpc
   ```

## Security Considerations

### Authentication
- Use a strong, randomly generated `TINYINTENT_SECRET`
- Disable `ALLOW_DEV_LOCAL` in production
- Use HTTPS in production (reverse proxy recommended)

### Network Security
- Bind to localhost (`127.0.0.1`) if using a reverse proxy
- Use firewall rules to restrict access
- Consider VPN for remote access

### Helper Execution
- Start with `EXECUTION_ENABLED=0` until security review is complete
- Review all helpers before enabling execution
- Set appropriate resource limits for helpers
- Monitor helper execution logs

### File Permissions
- Run as non-root user
- Restrict file system access using sandboxing
- Regular backup of audit logs and episode data

## Model Training and Deployment

### Generating CoreML Models

The TinyIntent router uses locally trained CoreML models for intent classification. Generate them using:

```bash
# Full automated learning pipeline
make learn

# Individual steps
make router-train    # Train PyTorch → ONNX → CoreML conversion
make router-eval     # Evaluate model performance
make promote         # Promote if evaluation passes criteria
```

This produces versioned CoreML artifacts:
- `router/SmallIntent.mlmodel` - macOS optimized (~70-85MB INT8 CoreML)
- `router/TinyIntent.mlmodel` - Mobile optimized (≤5MB)
- `router/train_summary.json` - Training metadata and metrics

### Training Status Monitoring

Check training and model status via API:

```bash
# Get comprehensive training summary
curl -H "X-TinyIntent-Secret: $TINYINTENT_SECRET" \
  http://localhost:8787/router/train_summary

# Example response includes:
# - Training metrics (accuracy, precision/recall, F1)
# - Model artifact status and file sizes
# - Calibration statistics and confidence curves
# - Deployment readiness indicators
# - Sample predictions with confidence scores
```

### Model Validation Gates

The training pipeline includes automatic validation:
- **Size constraints**: SmallIntent 50-100MB (target 70-85MB), TinyIntent ≤5MB
- **Performance gates**: Minimum accuracy, F1 score thresholds
- **Calibration quality**: ECE (Expected Calibration Error) limits
- **Latency requirements**: P95 inference time under 50ms

### Deployment Prerequisites

Before enabling the router in production:

1. **Verify model artifacts exist**:
   ```bash
   ls -la router/*.mlmodel
   # Should show SmallIntent.mlmodel and TinyIntent.mlmodel
   ```

2. **Check model performance**:
   ```bash
   curl -s -H "X-TinyIntent-Secret: $SECRET" \
     http://localhost:8787/router/train_summary | \
     jq '.evaluation_results.promotion_eligible'
   ```

3. **Validate model sizes meet constraints**:
   ```bash
   curl -s -H "X-TinyIntent-Secret: $SECRET" \
     http://localhost:8787/router/train_summary | \
     jq '.current_models'
   ```

### Training Data Management

- Training data is stored in `router/data/intents.tsv`
- Episode data can be exported using `make export-episodes`
- Models are retrained automatically via `make learn`
- Training metadata includes unique training IDs for versioning

## Monitoring and Maintenance

### Health Checks
- GET `/healthz` - Basic health check
- GET `/readyz` - Readiness check
- GET `/doctor` - Comprehensive system health
- GET `/router/train_summary` - Training status and model artifacts

### Log Management
- Audit logs rotate automatically
- Monitor disk space for episode data
- Set up log retention policies

### Backup Strategy
```bash
# Backup episode data
make backup-data

# Manual backup
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/
```

### Updates
1. Stop the service
2. Backup current installation
3. Pull latest changes
4. Update dependencies
5. Run database migrations if needed
6. Restart service
7. Verify health

## Troubleshooting

### Service Won't Start
1. Check environment variables
2. Verify Ollama connectivity
3. Check file permissions
4. Review logs for errors

### Performance Issues
1. Monitor resource usage
2. Check helper execution patterns
3. Review rate limiting settings
4. Consider scaling with multiple workers

### Helper Execution Problems
1. Check helper manifests
2. Verify sandbox constraints
3. Review capability permissions
4. Check environment variables

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TINYINTENT_SECRET` | Required | Authentication secret |
| `TINYINTENT_ENVIRONMENT` | development | Environment mode |
| `TINYINTENT_BIND` | 127.0.0.1 | Server bind address |
| `TINYINTENT_PORT` | 8787 | Server port |
| `TINYINTENT_EXECUTION_ENABLED` | 0 | Enable helper execution |
| `HELPER_RATE_LIMIT` | 10 | Helper executions per minute |
| `MODEL_OLLAMA_URL` | http://localhost:11434 | Ollama server URL |

See `.env.example` for complete configuration options.

## Support

For deployment issues:
1. Check the troubleshooting section
2. Review application logs
3. Run system health checks
4. Consult the project documentation