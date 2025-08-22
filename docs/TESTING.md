# 🧪 TinyIntent Testing Guide

This document covers TinyIntent's comprehensive testing strategy, how to run tests, write new tests, and ensure quality across the codebase.

## 🎯 Testing Philosophy

### Testing Principles

1. **🔄 Test-Driven Development**: Write tests before implementation when possible
2. **🎯 Comprehensive Coverage**: Unit, integration, and end-to-end testing
3. **🛡️ Security-First Testing**: All security features must be tested
4. **⚡ Fast Feedback**: Quick test execution for development workflows
5. **🏗️ Production Simulation**: Tests should mirror production conditions

### Testing Pyramid

```
           ╭─────────────────╮
          ╱  E2E Tests (5%)   ╲     Slow, High-level, UI/Voice
         ╱                    ╲
        ╱─────────────────────╱
       ╱  Integration (20%)   ╲     Medium, API, Database
      ╱                       ╲
     ╱────────────────────────╱
    ╱     Unit Tests (75%)     ╲     Fast, Low-level, Logic
   ╱                           ╲
  ╱─────────────────────────────╲
```

## 🏃‍♂️ Quick Start

### Running Tests

```bash
# Run all tests
make test

# Quick unit tests only
make test-quick

# Specific test categories
python -m pytest tests/unit/ -v              # Unit tests
python -m pytest tests/integration/ -v       # Integration tests
./tests/health.sh                           # System health
./tests/auth.sh                             # Authentication
./tests/routes.smoke.sh                     # API endpoints
./tests/helpers_smoke.sh                    # Helper framework
./tests/router_smoke.sh                     # Router model

# Run with coverage
python -m pytest tests/ --cov=bridge --cov=helpers --cov=tinyintent --cov-report=html
```

### Test Development Workflow

```bash
# 1. Create test file
touch tests/test_my_feature.py

# 2. Write failing test (TDD)
# 3. Implement feature
# 4. Run specific test
python -m pytest tests/test_my_feature.py -v

# 5. Run full suite
make test
```

## 📋 Test Categories

### 1. Unit Tests (`tests/`)

**Purpose**: Test individual functions and classes in isolation

```python
# Example: tests/test_validation.py
import pytest
from bridge.validation import validate_text_input, ValidationError

def test_validate_text_input_success():
    """Test successful text validation."""
    result = validate_text_input("Hello world")
    assert result == "Hello world"

def test_validate_text_input_strips_whitespace():
    """Test whitespace stripping."""
    result = validate_text_input("  hello  ")
    assert result == "hello"

def test_validate_text_input_length_limit():
    """Test length limit enforcement."""
    with pytest.raises(ValidationError) as exc_info:
        validate_text_input("x" * 1001, max_length=1000)
    
    assert "exceeds maximum length" in str(exc_info.value)

def test_validate_text_input_injection_detection():
    """Test script injection detection."""
    malicious_inputs = [
        "<script>alert('xss')</script>",
        "javascript:alert(1)",
        "__import__('os').system('rm -rf /')",
        "{{ config.items() }}"
    ]
    
    for malicious_input in malicious_inputs:
        with pytest.raises(ValidationError) as exc_info:
            validate_text_input(malicious_input)
        assert "dangerous content" in str(exc_info.value)
```

**Running Unit Tests**:
```bash
python -m pytest tests/ -v --tb=short
python -m pytest tests/test_validation.py::test_validate_text_input_success -v
```

### 2. Integration Tests (`tests/integration/`)

**Purpose**: Test interactions between components

```python
# Example: tests/integration/test_shortcut_endpoint.py
import pytest
import httpx
from bridge.tinyrpc import app

@pytest.mark.asyncio
async def test_shortcut_ping():
    """Test shortcut ping endpoint."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/shortcut/ping",
            headers={"X-Shortcut-Token": "test-token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "ts" in data

@pytest.mark.asyncio
async def test_shortcut_route_success():
    """Test successful shortcut routing."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/shortcut/route",
            json={
                "text": "Show me system health",
                "return_format": "text"
            },
            headers={"X-Shortcut-Token": "test-token"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "speak" in data
    assert isinstance(data["speak"], str)

@pytest.mark.asyncio
async def test_shortcut_route_authentication_required():
    """Test authentication requirement."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/shortcut/route",
            json={"text": "test"}
        )
    
    assert response.status_code == 401
```

**Running Integration Tests**:
```bash
python -m pytest tests/integration/ -v
python -m pytest tests/integration/test_shortcut_endpoint.py -v
```

### 3. Security Tests (`tests/test_security_fixes.py`)

**Purpose**: Validate security controls and vulnerability fixes

```python
# Example: tests/test_security_fixes.py
import pytest
import time
from unittest.mock import patch
from bridge.security import constant_time_compare, verify_csrf_token
from bridge.validation import validate_text_input, ValidationError

class TestAuthenticationSecurity:
    """Test authentication security fixes."""
    
    def test_constant_time_comparison(self):
        """Test timing attack prevention."""
        correct_secret = "correct-secret-123"
        incorrect_secret = "wrong-secret-456"
        
        # Measure timing for multiple comparisons
        iterations = 1000
        correct_times = []
        incorrect_times = []
        
        for _ in range(iterations):
            start = time.perf_counter()
            constant_time_compare(correct_secret, correct_secret)
            correct_times.append(time.perf_counter() - start)
            
            start = time.perf_counter()
            constant_time_compare(correct_secret, incorrect_secret)
            incorrect_times.append(time.perf_counter() - start)
        
        # Statistical analysis
        correct_avg = sum(correct_times) / len(correct_times)
        incorrect_avg = sum(incorrect_times) / len(incorrect_times)
        
        # Timing difference should be negligible (within microseconds)
        timing_diff = abs(correct_avg - incorrect_avg)
        assert timing_diff < 0.0001, f"Timing difference too large: {timing_diff}"

class TestInputValidation:
    """Test input validation security."""
    
    @pytest.mark.parametrize("malicious_input", [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert(1)>",
        "javascript:alert(1)",
        "'; DROP TABLE users; --",
        "{{ config.items() }}",
        "__import__('os').system('rm -rf /')",
        "eval('malicious code')",
        "document.cookie",
        "$('body').html('hacked')"
    ])
    def test_injection_detection(self, malicious_input):
        """Test detection of various injection attempts."""
        with pytest.raises(ValidationError) as exc_info:
            validate_text_input(malicious_input)
        
        assert "dangerous content" in str(exc_info.value).lower()

class TestCSRFProtection:
    """Test CSRF protection mechanisms."""
    
    def test_csrf_token_generation(self):
        """Test CSRF token generation."""
        from bridge.security import csrf_protection
        
        token1 = csrf_protection.generate_csrf_token("session1")
        token2 = csrf_protection.generate_csrf_token("session2")
        
        assert token1 != token2
        assert len(token1) > 20  # Sufficient entropy
        assert len(token2) > 20

    def test_csrf_token_validation(self):
        """Test CSRF token validation."""
        from bridge.security import csrf_protection
        
        session_id = "test-session"
        token = csrf_protection.generate_csrf_token(session_id)
        
        # Valid token should pass
        assert csrf_protection.verify_csrf_token(token, session_id) is True
        
        # Invalid token should fail
        assert csrf_protection.verify_csrf_token("invalid-token", session_id) is False
        
        # Wrong session should fail
        assert csrf_protection.verify_csrf_token(token, "wrong-session") is False
```

**Running Security Tests**:
```bash
python -m pytest tests/test_security_fixes.py -v
python tests/test_security_fixes.py  # Direct execution
./scripts/validate_security_fixes.py  # Comprehensive security validation
```

### 4. Smoke Tests (`tests/*.sh`)

**Purpose**: End-to-end system validation

#### Health Check (`tests/health.sh`)
```bash
#!/bin/bash
set -euo pipefail

echo "🏥 TinyIntent Health Check"

# Test server startup
echo "Starting TinyIntent..."
tinyintent --quiet &
SERVER_PID=$!
sleep 3

# Test endpoints
echo "Testing health endpoint..."
curl -f http://localhost:8787/health

echo "Testing shortcut ping..."
curl -f -H "X-Shortcut-Token: test-token" http://localhost:8787/shortcut/ping

# Cleanup
kill $SERVER_PID
echo "✅ Health check passed"
```

#### Authentication Test (`tests/auth.sh`)
```bash
#!/bin/bash
set -euo pipefail

echo "🔒 Authentication Test"

# Test valid authentication
echo "Testing valid authentication..."
response=$(curl -s -H "X-Shortcut-Token: valid-token" http://localhost:8787/shortcut/ping)
echo $response | grep -q '"ok":true'

# Test invalid authentication
echo "Testing invalid authentication..."
response=$(curl -s -w "%{http_code}" -H "X-Shortcut-Token: invalid-token" http://localhost:8787/shortcut/ping)
echo $response | grep -q "401"

echo "✅ Authentication test passed"
```

**Running Smoke Tests**:
```bash
./tests/health.sh
./tests/auth.sh
./tests/routes.smoke.sh
./tests/helpers_smoke.sh
./tests/router_smoke.sh
```

## 🔧 Test Configuration

### Test Settings (`tests/conftest.py`)

```python
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Set test environment
os.environ["TINYINTENT_SECRET"] = "test-secret-for-testing-32chars"
os.environ["SHORTCUT_TOKEN"] = "test-shortcut-token"
os.environ["TINYINTENT_EXECUTION_ENABLED"] = "1"
os.environ["TINYINTENT_ALLOW_DEV_LOCAL"] = "1"
os.environ["TINYINTENT_LOG_LEVEL"] = "debug"

@pytest.fixture
def temp_dir():
    """Provide temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_ollama_client():
    """Mock Ollama client for testing."""
    with patch('bridge.gen_client.async_ollama_client') as mock:
        mock.generate_async.return_value = ("Test response", 100)
        mock.health_check.return_value = True
        yield mock

@pytest.fixture
def sample_helper_manifest():
    """Sample helper manifest for testing."""
    return {
        "name": "test_helper",
        "version": "1.0.0",
        "description": "Test helper for unit tests",
        "capabilities": ["filesystem"],
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string"}
            },
            "required": ["operation"]
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "result": {"type": "string"}
            }
        }
    }

@pytest.fixture
def mock_audit_logger():
    """Mock audit logger to avoid file I/O in tests."""
    with patch('bridge.logs.audit.get_audit_logger') as mock:
        mock_logger = Mock()
        mock.return_value = mock_logger
        yield mock_logger

@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    # Reset any global state that might affect tests
    yield
    # Cleanup after test
```

### Test Data (`tests/fixtures/`)

```python
# tests/fixtures/sample_data.py
SAMPLE_ROUTER_REQUESTS = [
    ("What is the weather like?", "gen"),
    ("Show me system logs", "act"),
    ("Close my trading positions", "act"),
    ("Explain how AI works", "gen"),
    ("Check server health", "act")
]

SAMPLE_HELPER_INPUTS = {
    "log_tailer": {
        "operation": "tail",
        "log_path": "/var/log/system.log",
        "lines": 10
    },
    "bot_guard": {
        "operation": "get_positions",
        "symbol": "BTC/USDT"
    }
}

MALICIOUS_INPUTS = [
    "<script>alert('xss')</script>",
    "'; DROP TABLE users; --",
    "{{ config.items() }}",
    "__import__('os').system('rm -rf /')",
    "eval('malicious code')",
    "javascript:alert(1)"
]
```

## 📊 Test Coverage

### Coverage Configuration (`.coveragerc`)

```ini
[run]
source = bridge, helpers, tinyintent
omit = 
    */tests/*
    */venv/*
    */__pycache__/*
    */migrations/*
    setup.py

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
    if TYPE_CHECKING:

[html]
directory = htmlcov
```

### Running Coverage Analysis

```bash
# Generate coverage report
python -m pytest tests/ --cov=bridge --cov=helpers --cov=tinyintent --cov-report=html

# View coverage in browser
open htmlcov/index.html

# Coverage with missing lines
python -m pytest tests/ --cov=bridge --cov-report=term-missing

# Fail if coverage below threshold
python -m pytest tests/ --cov=bridge --cov-fail-under=80
```

### Coverage Targets

| Component | Target Coverage | Current |
|-----------|----------------|---------|
| Bridge Core | 90% | 85% |
| Security | 95% | 92% |
| Validation | 95% | 88% |
| Helpers | 80% | 75% |
| CLI | 70% | 65% |

## 🧩 Testing Patterns

### Testing Async Functions

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_function():
    """Test async function."""
    result = await some_async_function()
    assert result is not None

@pytest.mark.asyncio
async def test_async_with_timeout():
    """Test async function with timeout."""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_async_function(), timeout=1.0)
```

### Testing with Mocks

```python
from unittest.mock import Mock, patch, AsyncMock

def test_with_mock():
    """Test using mock objects."""
    mock_service = Mock()
    mock_service.get_data.return_value = {"test": "data"}
    
    result = function_using_service(mock_service)
    
    mock_service.get_data.assert_called_once()
    assert result["test"] == "data"

@patch('module.external_service')
def test_with_patch(mock_service):
    """Test using patch decorator."""
    mock_service.return_value = "mocked result"
    
    result = function_calling_external_service()
    
    assert result == "mocked result"

@pytest.mark.asyncio
async def test_async_mock():
    """Test async functions with mocks."""
    with patch('module.async_function', new_callable=AsyncMock) as mock_async:
        mock_async.return_value = "async result"
        
        result = await function_calling_async()
        
        assert result == "async result"
        mock_async.assert_called_once()
```

### Testing Error Conditions

```python
def test_error_handling():
    """Test error handling."""
    with pytest.raises(ValueError) as exc_info:
        function_that_should_raise_error()
    
    assert "expected error message" in str(exc_info.value)

def test_warning_handling():
    """Test warning handling."""
    with pytest.warns(UserWarning, match="expected warning"):
        function_that_issues_warning()

def test_no_exception():
    """Test that no exception is raised."""
    try:
        function_that_should_not_raise()
    except Exception as e:
        pytest.fail(f"Unexpected exception: {e}")
```

### Parametrized Tests

```python
@pytest.mark.parametrize("input_value,expected_output", [
    ("hello", "HELLO"),
    ("world", "WORLD"),
    ("", ""),
    ("123", "123")
])
def test_uppercase_function(input_value, expected_output):
    """Test uppercase function with multiple inputs."""
    result = uppercase_function(input_value)
    assert result == expected_output

@pytest.mark.parametrize("malicious_input", [
    "<script>alert('xss')</script>",
    "'; DROP TABLE users; --",
    "{{ config.items() }}"
])
def test_injection_detection(malicious_input):
    """Test injection detection with various inputs."""
    with pytest.raises(ValidationError):
        validate_input(malicious_input)
```

## 🚀 Performance Testing

### Response Time Testing

```python
import time
import pytest

def test_response_time():
    """Test function response time."""
    start_time = time.time()
    
    result = function_under_test()
    
    end_time = time.time()
    response_time = end_time - start_time
    
    assert response_time < 1.0  # Should complete within 1 second
    assert result is not None

@pytest.mark.performance
def test_bulk_operations():
    """Test performance with bulk operations."""
    items = [f"item_{i}" for i in range(1000)]
    
    start_time = time.time()
    results = [process_item(item) for item in items]
    end_time = time.time()
    
    total_time = end_time - start_time
    avg_time_per_item = total_time / len(items)
    
    assert len(results) == 1000
    assert avg_time_per_item < 0.001  # Less than 1ms per item
```

### Memory Usage Testing

```python
import tracemalloc

def test_memory_usage():
    """Test memory usage of function."""
    tracemalloc.start()
    
    result = memory_intensive_function()
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Convert to MB
    peak_mb = peak / 1024 / 1024
    
    assert peak_mb < 100  # Should use less than 100MB
    assert result is not None
```

## 🔍 Test Debugging

### Debugging Failed Tests

```bash
# Run specific failing test with verbose output
python -m pytest tests/test_failing.py::test_specific_failure -v -s

# Run with debugger on failure
python -m pytest tests/test_failing.py --pdb

# Run with print statements visible
python -m pytest tests/test_failing.py -s

# Show full traceback
python -m pytest tests/test_failing.py --tb=long
```

### Test Data Inspection

```python
def test_with_debugging():
    """Test with debugging information."""
    result = function_under_test()
    
    # Add debugging output
    print(f"Result: {result}")
    print(f"Type: {type(result)}")
    
    # Use pytest's debug helper
    pytest.set_trace()  # Debugger breakpoint
    
    assert result is not None
```

## 📋 Test Maintenance

### Keeping Tests Current

1. **Regular test review**: Review tests when code changes
2. **Update test data**: Keep test fixtures current
3. **Remove obsolete tests**: Delete tests for removed features
4. **Add regression tests**: Add tests for bug fixes

### Test Performance

```bash
# Identify slow tests
python -m pytest tests/ --durations=10

# Run only fast tests during development
python -m pytest tests/ -m "not slow"

# Mark slow tests
@pytest.mark.slow
def test_slow_operation():
    pass
```

### Continuous Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: 3.9
    
    - name: Install dependencies
      run: |
        pip install -e ".[test]"
    
    - name: Run tests
      run: |
        python -m pytest tests/ --cov=bridge --cov=helpers --cov=tinyintent
    
    - name: Run security tests
      run: |
        python tests/test_security_fixes.py
    
    - name: Run smoke tests
      run: |
        ./tests/health.sh
```

---

This comprehensive testing guide ensures TinyIntent maintains high quality and security standards while providing fast feedback for developers. Remember: good tests are the foundation of reliable software!