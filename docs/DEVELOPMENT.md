# 🛠️ TinyIntent Development Guide

This guide covers development workflows, debugging, troubleshooting, and best practices for working with TinyIntent.

## 🚀 Development Environment Setup

### Quick Setup

```bash
# Clone and setup
git clone <your-fork>
cd tinyintent

# Install development environment
./install.sh

# Install development dependencies
pip install -e ".[test,dev]"

# Verify setup
tinyintent --help
make doctor
```

### Development Dependencies

```bash
# Core development tools
pip install black flake8 mypy pytest pytest-asyncio

# Additional testing tools
pip install httpx pytest-mock pytest-cov

# Documentation tools
pip install mkdocs mkdocs-material

# Pre-commit hooks
pip install pre-commit
pre-commit install
```

## 🔧 Development Workflow

### Daily Development

```bash
# Start development server with auto-reload
tinyintent --reload --verbose

# Run tests during development
make test-quick          # Fast unit tests only
make test               # Full test suite
python -m pytest tests/unit/ -v  # Specific test category

# Code quality checks
make lint               # Linting with flake8
make format             # Formatting with black
make typecheck          # Type checking with mypy
```

### Feature Development Process

1. **Create feature branch**
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Develop with tests**
   ```bash
   # Write tests first (TDD recommended)
   touch tests/test_your_feature.py
   
   # Implement feature
   # Run tests frequently
   python -m pytest tests/test_your_feature.py -v
   ```

3. **Validate changes**
   ```bash
   make test              # Full test suite
   make lint              # Code quality
   make doctor            # System health
   ```

4. **Commit and push**
   ```bash
   git add .
   git commit -m "🎯 Feature: Add your feature description"
   git push origin feat/your-feature-name
   ```

## 🧪 Testing Strategy

### Test Categories

#### Unit Tests (`tests/`)
```bash
# Run all unit tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_security_fixes.py -v

# Run with coverage
python -m pytest tests/ --cov=bridge --cov=helpers --cov=tinyintent
```

#### Integration Tests (`tests/integration/`)
```bash
# Run integration tests (requires running server)
python -m pytest tests/integration/ -v

# Test specific integration
python -m pytest tests/integration/test_shortcut_endpoint.py -v
```

#### Smoke Tests (`tests/*.sh`)
```bash
# Full system validation
./tests/health.sh         # System health
./tests/auth.sh          # Authentication flows
./tests/routes.smoke.sh  # API endpoint validation
./tests/helpers_smoke.sh # Helper framework
./tests/router_smoke.sh  # Router model testing
```

### Writing Tests

#### Unit Test Example
```python
import pytest
from bridge.validation import validate_text_input, ValidationError

def test_validate_text_input_success():
    """Test successful text validation."""
    result = validate_text_input("Hello world")
    assert result == "Hello world"

def test_validate_text_input_injection_detection():
    """Test script injection detection."""
    with pytest.raises(ValidationError) as exc_info:
        validate_text_input("<script>alert('xss')</script>")
    
    assert "dangerous content" in str(exc_info.value)

@pytest.mark.asyncio
async def test_async_function():
    """Test async functions."""
    result = await some_async_function()
    assert result is not None
```

#### Integration Test Example
```python
import httpx
import pytest
from bridge.tinyrpc import app

@pytest.mark.asyncio
async def test_shortcut_endpoint():
    """Test iPhone shortcut endpoint integration."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/shortcut/route",
            json={"text": "test command"},
            headers={"X-Shortcut-Token": "test-token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "speak" in data
```

### Test Data Management

```python
# Use fixtures for common test data
@pytest.fixture
def sample_helper_manifest():
    return {
        "name": "test_helper",
        "version": "1.0.0",
        "description": "Test helper",
        "capabilities": ["filesystem"],
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"}
    }

@pytest.fixture
def mock_ollama_client():
    with patch('bridge.gen_client.async_ollama_client') as mock:
        mock.generate_async.return_value = ("Test response", 100)
        yield mock
```

## 🐛 Debugging & Troubleshooting

### Debug Mode Setup

```bash
# Enable debug logging
export TINYINTENT_LOG_LEVEL=debug
tinyintent --verbose

# Or use debug flag
tinyintent --verbose --reload
```

### Common Debugging Scenarios

#### 1. Authentication Issues
```python
# Debug authentication in code
logger.debug("Auth check", 
            provided_token=provided_token[:8] + "...",
            expected_length=len(expected_token),
            client_ip=request.client.host)
```

#### 2. Helper Execution Problems
```bash
# Debug helper execution
export TINYINTENT_LOG_LEVEL=debug
# Check helper logs in execution response
# Verify sandbox permissions and resource limits
```

#### 3. Router Model Issues
```bash
# Check router model availability
ls -la router/SmallIntent.mlmodel

# Test router directly
./router/runner/run_router.swift "test input"

# Retrain if needed
make router-train
```

#### 4. Database Issues
```python
# Debug SQLite issues
import sqlite3
conn = sqlite3.connect('data/episodes/staging.db')
cursor = conn.execute("SELECT * FROM events ORDER BY created_at DESC LIMIT 10")
print(cursor.fetchall())
```

### Debugging Tools

#### Python Debugger
```python
# Add breakpoint in code
import pdb; pdb.set_trace()

# Or use modern debugger
import ipdb; ipdb.set_trace()

# For async code
import aioipdb; await aioipdb.set_trace()
```

#### HTTP Request Debugging
```bash
# Test API endpoints directly
curl -X POST http://localhost:8787/shortcut/route \
  -H "X-Shortcut-Token: your-token" \
  -H "Content-Type: application/json" \
  -d '{"text": "test command"}'

# With debug headers
curl -v -X POST http://localhost:8787/health
```

#### Log Analysis
```bash
# Watch logs in real-time
tail -f bridge/logs/audit.log | jq .

# Search for specific events
grep "authentication_failed" bridge/logs/audit.log | jq .

# Analyze error patterns
grep "error" bridge/logs/audit.log | jq '.error' | sort | uniq -c
```

## 🔍 Performance Profiling

### Response Time Analysis
```python
import time
import cProfile
import pstats

# Profile specific function
def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Your function call here
    result = your_function()
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats(10)
    
    return result
```

### Memory Usage Monitoring
```python
import tracemalloc
import psutil
import os

# Monitor memory usage
def monitor_memory():
    process = psutil.Process(os.getpid())
    memory_info = process.memory_info()
    print(f"RSS: {memory_info.rss / 1024 / 1024:.2f} MB")
    print(f"VMS: {memory_info.vms / 1024 / 1024:.2f} MB")

# Trace memory allocations
tracemalloc.start()
# ... your code ...
current, peak = tracemalloc.get_traced_memory()
print(f"Current memory usage: {current / 1024 / 1024:.2f} MB")
print(f"Peak memory usage: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

### Database Performance
```python
# SQLite query profiling
import sqlite3
import time

def profile_query(query):
    start_time = time.time()
    with sqlite3.connect('data/episodes/staging.db') as conn:
        cursor = conn.execute(query)
        results = cursor.fetchall()
    end_time = time.time()
    
    print(f"Query took {end_time - start_time:.3f} seconds")
    print(f"Returned {len(results)} rows")
    return results
```

## 🏗️ Architecture Patterns

### Adding New API Endpoints

1. **Create route module** in `bridge/routes/`
   ```python
   # bridge/routes/my_feature.py
   from fastapi import APIRouter, Depends
   from ..security import verify_auth
   
   router = APIRouter(prefix="/my-feature", tags=["my-feature"])
   
   @router.get("/status")
   async def get_status(auth: bool = Depends(verify_auth)):
       return {"status": "ok"}
   ```

2. **Register in main app**
   ```python
   # bridge/tinyrpc.py
   from .routes import my_feature
   
   app.include_router(my_feature.router)
   ```

3. **Add tests**
   ```python
   # tests/test_my_feature.py
   import pytest
   from bridge.tinyrpc import app
   
   @pytest.mark.asyncio
   async def test_my_feature_status():
       # Test implementation
       pass
   ```

### Adding New Helpers

1. **Create helper directory**
   ```bash
   mkdir helpers/my_helper
   ```

2. **Create manifest**
   ```yaml
   # helpers/my_helper/helper.yaml
   name: my_helper
   version: 1.0.0
   description: "My custom helper"
   capabilities: ["filesystem"]
   input_schema_file: input.schema.json
   output_schema_file: output.schema.json
   ```

3. **Implement helper logic**
   ```python
   # helpers/my_helper/main.py
   import json
   import sys
   
   def main():
       input_data = json.load(sys.stdin)
       # Process input
       result = {"status": "success", "data": input_data}
       json.dump(result, sys.stdout)
   
   if __name__ == "__main__":
       main()
   ```

4. **Register helper**
   ```yaml
   # helpers/registry.yaml
   helpers:
     my_helper:
       directory: my_helper
       runtime: python
       executable: main.py
   ```

### Database Schema Evolution

```python
# data/episodes/migrations/001_add_new_table.py
def upgrade(conn):
    conn.execute("""
        CREATE TABLE new_table (
            id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

def downgrade(conn):
    conn.execute("DROP TABLE new_table")
```

## 🔧 Configuration Management

### Environment Variables

```bash
# Development settings
export TINYINTENT_LOG_LEVEL=debug
export TINYINTENT_EXECUTION_ENABLED=1
export TINYINTENT_ALLOW_DEV_LOCAL=1

# Production settings
export TINYINTENT_LOG_LEVEL=warning
export TINYINTENT_EXECUTION_ENABLED=1
export TINYINTENT_ALLOW_DEV_LOCAL=0
```

### Configuration Validation

```python
# Validate configuration in code
from tinyintent.config import settings

def validate_development_config():
    """Validate configuration for development."""
    assert settings.security.secret is not None
    assert len(settings.security.secret) >= 32
    assert settings.is_development()
    
    print("✅ Development configuration valid")
```

## 📊 Monitoring & Metrics

### Application Metrics

```python
# Custom metrics collection
class MetricsCollector:
    def __init__(self):
        self.request_count = 0
        self.error_count = 0
        self.response_times = []
    
    def record_request(self, response_time_ms):
        self.request_count += 1
        self.response_times.append(response_time_ms)
    
    def record_error(self):
        self.error_count += 1
    
    def get_stats(self):
        avg_response_time = sum(self.response_times) / len(self.response_times)
        return {
            "requests": self.request_count,
            "errors": self.error_count,
            "error_rate": self.error_count / self.request_count,
            "avg_response_time_ms": avg_response_time
        }
```

### Health Monitoring

```python
# Custom health checks
async def check_database_health():
    """Check database connectivity."""
    try:
        with sqlite3.connect('data/episodes/staging.db', timeout=5) as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}

async def check_ollama_health():
    """Check Ollama service."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=5)
            response.raise_for_status()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

## 🚀 Deployment Considerations

### Local Development
- Use `--reload` for auto-restart on file changes
- Enable debug logging for detailed troubleshooting
- Use development secrets (auto-generated)

### Production Deployment
- Use production secrets (manually configured)
- Enable comprehensive audit logging
- Set up log rotation and monitoring
- Configure resource limits appropriately

### Performance Tuning

```python
# Optimize for your use case
PRODUCTION_SETTINGS = {
    "TINYINTENT_LOG_LEVEL": "warning",
    "GEN_TIMEOUT_S": "30",
    "GEN_MAX_RETRIES": "3",
    "GEN_CONCURRENCY": "4",
    "HELPER_DEFAULT_TIMEOUT": "30",
    "HELPER_MAX_MEMORY_MB": "512"
}
```

---

This development guide should help you work effectively with TinyIntent. For additional help, refer to the main documentation or reach out to the community.