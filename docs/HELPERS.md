# 🤖 TinyIntent Helper Development Guide

This guide covers how to create, develop, and deploy custom helpers for TinyIntent's voice-activated AI platform.

## 🎯 What are Helpers?

Helpers are **sandboxed executables** that perform specific tasks in response to voice commands. They run in isolated environments with strict resource limits and security controls.

### Helper Characteristics

- **🏰 Sandboxed**: Isolated execution with CPU/memory/filesystem limits
- **📋 Schema-driven**: Strict input/output validation via JSON schemas
- **🔒 Security-first**: Capability-based permissions and audit logging
- **🌐 Multi-language**: Support for Python, Node.js, and other runtimes
- **📊 Observable**: Comprehensive logging and metrics collection

### Example Voice Flows

```
Voice: "Show me recent error logs"
  ↓
Router: classifies as "act" 
  ↓
Helper: log_tailer executes with {"operation": "tail", "level": "ERROR"}
  ↓
Response: "Found 3 errors in the last hour: Connection timeout..."
```

## 🏗️ Helper Architecture

### Directory Structure

```
helpers/my_helper/
├── helper.yaml           # Helper metadata and configuration
├── main.py              # Primary executable (Python example)
├── main.js              # Alternative executable (Node.js example)
├── input.schema.json    # Input validation schema
├── output.schema.json   # Output validation schema
├── health.py           # Health check script
└── README.md           # Helper documentation
```

### Registry Integration

```yaml
# helpers/registry.yaml
helpers:
  my_helper:
    directory: my_helper
    runtime: python       # python|node|bash
    executable: main.py
    enabled: true
    lifecycle_state: draft  # draft|trusted|deprecated|retired
```

## 📋 Helper Manifest (`helper.yaml`)

### Complete Example

```yaml
# helpers/my_helper/helper.yaml
name: my_helper
version: 1.2.0
description: "Custom helper for demonstrating TinyIntent capabilities"
author: "Your Name <your.email@example.com>"
license: "MIT"

# Runtime configuration
runtime: python
executable: main.py
timeout_seconds: 30
max_memory_mb: 256

# Security capabilities
capabilities:
  - filesystem    # Read/write to isolated working directory
  - network      # Network access (disabled by default)
  - environment  # Access to environment variables

# Schema files
input_schema_file: input.schema.json
output_schema_file: output.schema.json

# Health check
health_check:
  script: health.py
  timeout_seconds: 5

# Lifecycle management
lifecycle:
  state: draft
  since: "2024-01-15"
  notes: "Initial development version"

# Metrics and monitoring
metrics:
  success_rate_threshold: 0.95
  latency_threshold_ms: 5000
  error_budget: 0.05

# Documentation
documentation:
  examples:
    - input: {"operation": "status"}
      output: {"status": "healthy", "uptime": "5 days"}
  use_cases:
    - "Check system status"
    - "Monitor application health"
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique helper identifier |
| `version` | string | Semantic version (MAJOR.MINOR.PATCH) |
| `description` | string | Brief helper description |
| `runtime` | string | Execution runtime (python, node, bash) |
| `executable` | string | Main executable file |

### Optional Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `timeout_seconds` | int | 30 | Maximum execution time |
| `max_memory_mb` | int | 256 | Memory limit |
| `capabilities` | list | [] | Required capabilities |
| `lifecycle.state` | string | "draft" | Helper lifecycle state |

## 🔒 Security Model

### Capability System

```yaml
capabilities:
  - filesystem    # Read/write isolated working directory
  - network      # HTTP/HTTPS requests (disabled by default)
  - environment  # Access to scoped environment variables
  - process      # Spawn child processes (restricted)
```

### Sandbox Constraints

| Resource | Limit | Enforcement |
|----------|--------|-------------|
| CPU Time | 30 seconds | `RLIMIT_CPU` |
| Memory | 256 MB | `RLIMIT_AS` |
| File Descriptors | 50 | `RLIMIT_NOFILE` |
| Working Directory | Isolated temp dir | chroot-like isolation |
| Network | Disabled by default | Environment filtering |

### Security Validation

```python
# Automatic security checks before execution
def validate_helper_security(helper_manifest):
    """Validate helper security requirements."""
    
    # Check capabilities
    allowed_capabilities = {"filesystem", "network", "environment", "process"}
    requested = set(helper_manifest.get("capabilities", []))
    invalid = requested - allowed_capabilities
    if invalid:
        raise SecurityError(f"Invalid capabilities: {invalid}")
    
    # Validate resource limits
    timeout = helper_manifest.get("timeout_seconds", 30)
    if timeout > 60:
        raise SecurityError("Timeout cannot exceed 60 seconds")
    
    memory_mb = helper_manifest.get("max_memory_mb", 256)
    if memory_mb > 1024:
        raise SecurityError("Memory limit cannot exceed 1024 MB")
```

## 🐍 Python Helper Example

### Basic Helper (`main.py`)

```python
#!/usr/bin/env python3
"""
Example TinyIntent Helper in Python

This helper demonstrates the basic structure and patterns for
developing Python-based helpers.
"""

import json
import sys
import os
import logging
from typing import Dict, Any
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def process_request(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process the input request and return a response.
    
    Args:
        input_data: Validated input data from JSON schema
        
    Returns:
        Dict containing response data matching output schema
    """
    operation = input_data.get("operation", "unknown")
    
    logger.info(f"Processing operation: {operation}")
    
    if operation == "status":
        return handle_status_request(input_data)
    elif operation == "info":
        return handle_info_request(input_data)
    else:
        return {
            "status": "error",
            "error_code": "UNKNOWN_OPERATION",
            "message": f"Unknown operation: {operation}",
            "supported_operations": ["status", "info"]
        }

def handle_status_request(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle status check request."""
    try:
        # Simulated status check
        status_info = {
            "status": "healthy",
            "timestamp": "2024-01-15T10:30:00Z",
            "uptime": "5 days, 3 hours",
            "memory_usage": "45%",
            "cpu_usage": "12%"
        }
        
        return {
            "status": "success",
            "data": status_info,
            "message": "Status check completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "error_code": "STATUS_CHECK_FAILED",
            "message": str(e)
        }

def handle_info_request(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Handle information request."""
    info_type = input_data.get("info_type", "general")
    
    info_data = {
        "helper_name": "my_helper",
        "version": "1.2.0",
        "runtime": "python",
        "capabilities": ["filesystem", "environment"],
        "working_directory": str(Path.cwd()),
        "environment_vars": len(os.environ)
    }
    
    if info_type == "detailed":
        info_data.update({
            "python_version": sys.version,
            "process_id": os.getpid(),
            "user_id": os.getuid() if hasattr(os, 'getuid') else "unknown"
        })
    
    return {
        "status": "success",
        "data": info_data,
        "message": f"Retrieved {info_type} information"
    }

def validate_environment():
    """Validate the execution environment."""
    required_vars = ["TINYINTENT_HELPER_ID", "TINYINTENT_SESSION_ID"]
    missing_vars = [var for var in required_vars if var not in os.environ]
    
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {missing_vars}")

def main():
    """Main entry point for the helper."""
    try:
        # Validate environment
        validate_environment()
        
        # Read input from stdin
        input_text = sys.stdin.read().strip()
        if not input_text:
            raise ValueError("No input data provided")
        
        # Parse JSON input
        try:
            input_data = json.loads(input_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON input: {e}")
        
        # Process request
        logger.info("Starting request processing")
        result = process_request(input_data)
        
        # Output JSON result
        json.dump(result, sys.stdout, indent=2)
        
        # Log completion
        logger.info("Request processing completed successfully")
        
    except Exception as e:
        # Error response
        error_response = {
            "status": "error",
            "error_code": "HELPER_EXECUTION_ERROR",
            "message": str(e)
        }
        
        json.dump(error_response, sys.stdout, indent=2)
        logger.error(f"Helper execution failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Input Schema (`input.schema.json`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "My Helper Input Schema",
  "description": "Input validation schema for my_helper",
  
  "properties": {
    "operation": {
      "type": "string",
      "enum": ["status", "info"],
      "description": "Operation to perform"
    },
    "info_type": {
      "type": "string",
      "enum": ["general", "detailed"],
      "default": "general",
      "description": "Type of information to retrieve (for info operation)"
    },
    "parameters": {
      "type": "object",
      "description": "Additional operation parameters",
      "additionalProperties": true
    }
  },
  
  "required": ["operation"],
  "additionalProperties": false,
  
  "examples": [
    {
      "operation": "status"
    },
    {
      "operation": "info",
      "info_type": "detailed"
    }
  ]
}
```

### Output Schema (`output.schema.json`)

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "title": "My Helper Output Schema",
  "description": "Output validation schema for my_helper",
  
  "properties": {
    "status": {
      "type": "string",
      "enum": ["success", "error"],
      "description": "Execution status"
    },
    "data": {
      "type": "object",
      "description": "Response data (present on success)",
      "additionalProperties": true
    },
    "message": {
      "type": "string",
      "description": "Human-readable response message"
    },
    "error_code": {
      "type": "string",
      "description": "Error code (present on error)",
      "pattern": "^[A-Z_]+$"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time",
      "description": "Response timestamp"
    }
  },
  
  "required": ["status", "message"],
  
  "allOf": [
    {
      "if": {
        "properties": { "status": { "const": "success" } }
      },
      "then": {
        "required": ["data"]
      }
    },
    {
      "if": {
        "properties": { "status": { "const": "error" } }
      },
      "then": {
        "required": ["error_code"]
      }
    }
  ],
  
  "examples": [
    {
      "status": "success",
      "data": {
        "uptime": "5 days",
        "memory_usage": "45%"
      },
      "message": "Status check completed"
    },
    {
      "status": "error",
      "error_code": "UNKNOWN_OPERATION",
      "message": "Operation not supported"
    }
  ]
}
```

### Health Check (`health.py`)

```python
#!/usr/bin/env python3
"""
Health check script for my_helper

This script verifies that the helper is ready to execute.
It should complete quickly and return appropriate exit codes.
"""

import sys
import json
import os
from pathlib import Path

def check_dependencies():
    """Check required dependencies."""
    try:
        import json
        import os
        import sys
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        return False

def check_files():
    """Check required files exist."""
    required_files = ["main.py", "input.schema.json", "output.schema.json"]
    missing_files = []
    
    for file_name in required_files:
        if not Path(file_name).exists():
            missing_files.append(file_name)
    
    if missing_files:
        print(f"Missing files: {missing_files}")
        return False
    
    return True

def check_schemas():
    """Validate JSON schemas."""
    try:
        with open("input.schema.json") as f:
            json.load(f)
        
        with open("output.schema.json") as f:
            json.load(f)
        
        return True
    except json.JSONDecodeError as e:
        print(f"Invalid schema: {e}")
        return False
    except FileNotFoundError as e:
        print(f"Schema file not found: {e}")
        return False

def main():
    """Perform health checks."""
    checks = [
        ("Dependencies", check_dependencies),
        ("Required Files", check_files),
        ("JSON Schemas", check_schemas)
    ]
    
    all_passed = True
    
    for check_name, check_func in checks:
        passed = check_func()
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {check_name}")
        
        if not passed:
            all_passed = False
    
    if all_passed:
        print("✅ All health checks passed")
        sys.exit(0)
    else:
        print("❌ Some health checks failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

## 🟨 Node.js Helper Example

### Basic Helper (`main.js`)

```javascript
#!/usr/bin/env node
/**
 * Example TinyIntent Helper in Node.js
 * 
 * This helper demonstrates Node.js-based helper development
 * with async/await patterns and proper error handling.
 */

const fs = require('fs').promises;
const path = require('path');

class HelperExecutor {
    constructor() {
        this.helperId = process.env.TINYINTENT_HELPER_ID || 'unknown';
        this.sessionId = process.env.TINYINTENT_SESSION_ID || 'unknown';
    }

    /**
     * Process the input request
     * @param {Object} inputData - Validated input data
     * @returns {Object} Response data
     */
    async processRequest(inputData) {
        const operation = inputData.operation || 'unknown';
        
        console.log(`Processing operation: ${operation}`);
        
        switch (operation) {
            case 'status':
                return await this.handleStatusRequest(inputData);
            case 'files':
                return await this.handleFilesRequest(inputData);
            default:
                return {
                    status: 'error',
                    error_code: 'UNKNOWN_OPERATION',
                    message: `Unknown operation: ${operation}`,
                    supported_operations: ['status', 'files']
                };
        }
    }

    /**
     * Handle status check request
     * @param {Object} inputData - Input parameters
     * @returns {Object} Status response
     */
    async handleStatusRequest(inputData) {
        try {
            const statusInfo = {
                status: 'healthy',
                timestamp: new Date().toISOString(),
                node_version: process.version,
                platform: process.platform,
                memory_usage: process.memoryUsage(),
                uptime: process.uptime()
            };

            return {
                status: 'success',
                data: statusInfo,
                message: 'Status check completed successfully'
            };
        } catch (error) {
            console.error(`Status check failed: ${error}`);
            return {
                status: 'error',
                error_code: 'STATUS_CHECK_FAILED',
                message: error.message
            };
        }
    }

    /**
     * Handle files listing request
     * @param {Object} inputData - Input parameters
     * @returns {Object} Files response
     */
    async handleFilesRequest(inputData) {
        try {
            const targetPath = inputData.path || '.';
            const files = await fs.readdir(targetPath);
            
            const fileDetails = await Promise.all(
                files.map(async (file) => {
                    const filePath = path.join(targetPath, file);
                    const stats = await fs.stat(filePath);
                    
                    return {
                        name: file,
                        size: stats.size,
                        modified: stats.mtime.toISOString(),
                        is_directory: stats.isDirectory()
                    };
                })
            );

            return {
                status: 'success',
                data: {
                    path: path.resolve(targetPath),
                    files: fileDetails,
                    count: fileDetails.length
                },
                message: `Listed ${fileDetails.length} files in ${targetPath}`
            };
        } catch (error) {
            console.error(`Files request failed: ${error}`);
            return {
                status: 'error',
                error_code: 'FILES_REQUEST_FAILED',
                message: error.message
            };
        }
    }

    /**
     * Validate the execution environment
     */
    validateEnvironment() {
        const requiredVars = ['TINYINTENT_HELPER_ID', 'TINYINTENT_SESSION_ID'];
        const missingVars = requiredVars.filter(varName => !process.env[varName]);
        
        if (missingVars.length > 0) {
            throw new Error(`Missing required environment variables: ${missingVars.join(', ')}`);
        }
    }

    /**
     * Read input from stdin
     * @returns {Promise<Object>} Parsed input data
     */
    async readInput() {
        return new Promise((resolve, reject) => {
            let inputData = '';
            
            process.stdin.setEncoding('utf8');
            
            process.stdin.on('data', (chunk) => {
                inputData += chunk;
            });
            
            process.stdin.on('end', () => {
                try {
                    if (!inputData.trim()) {
                        reject(new Error('No input data provided'));
                        return;
                    }
                    
                    const parsed = JSON.parse(inputData);
                    resolve(parsed);
                } catch (error) {
                    reject(new Error(`Invalid JSON input: ${error.message}`));
                }
            });
            
            process.stdin.on('error', (error) => {
                reject(new Error(`Input read error: ${error.message}`));
            });
        });
    }

    /**
     * Main execution function
     */
    async run() {
        try {
            // Validate environment
            this.validateEnvironment();
            
            // Read and parse input
            const inputData = await this.readInput();
            
            // Process request
            console.log('Starting request processing');
            const result = await this.processRequest(inputData);
            
            // Output JSON result
            console.log(JSON.stringify(result, null, 2));
            
            console.log('Request processing completed successfully');
            
        } catch (error) {
            // Error response
            const errorResponse = {
                status: 'error',
                error_code: 'HELPER_EXECUTION_ERROR',
                message: error.message
            };
            
            console.log(JSON.stringify(errorResponse, null, 2));
            console.error(`Helper execution failed: ${error}`);
            process.exit(1);
        }
    }
}

// Execute if this file is run directly
if (require.main === module) {
    const executor = new HelperExecutor();
    executor.run();
}

module.exports = HelperExecutor;
```

## 🧪 Testing Helpers

### Unit Testing

```python
# tests/test_my_helper.py
import json
import subprocess
import pytest
from pathlib import Path

class TestMyHelper:
    """Test suite for my_helper."""
    
    @pytest.fixture
    def helper_path(self):
        """Path to helper directory."""
        return Path(__file__).parent.parent / "helpers" / "my_helper"
    
    def execute_helper(self, helper_path, input_data):
        """Execute helper with given input."""
        process = subprocess.Popen(
            ["python", "main.py"],
            cwd=helper_path,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={
                "TINYINTENT_HELPER_ID": "my_helper",
                "TINYINTENT_SESSION_ID": "test-session"
            }
        )
        
        stdout, stderr = process.communicate(input=json.dumps(input_data))
        
        return {
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "output": json.loads(stdout) if stdout else None
        }
    
    def test_status_operation(self, helper_path):
        """Test status operation."""
        input_data = {"operation": "status"}
        result = self.execute_helper(helper_path, input_data)
        
        assert result["returncode"] == 0
        assert result["output"]["status"] == "success"
        assert "data" in result["output"]
        assert result["output"]["data"]["status"] == "healthy"
    
    def test_info_operation(self, helper_path):
        """Test info operation."""
        input_data = {"operation": "info", "info_type": "general"}
        result = self.execute_helper(helper_path, input_data)
        
        assert result["returncode"] == 0
        assert result["output"]["status"] == "success"
        assert result["output"]["data"]["helper_name"] == "my_helper"
    
    def test_unknown_operation(self, helper_path):
        """Test unknown operation handling."""
        input_data = {"operation": "unknown"}
        result = self.execute_helper(helper_path, input_data)
        
        assert result["returncode"] == 0
        assert result["output"]["status"] == "error"
        assert result["output"]["error_code"] == "UNKNOWN_OPERATION"
    
    def test_invalid_input(self, helper_path):
        """Test invalid input handling."""
        # Missing required operation field
        input_data = {"invalid": "data"}
        result = self.execute_helper(helper_path, input_data)
        
        # Should handle gracefully
        assert result["returncode"] == 0
        assert result["output"]["status"] == "error"
    
    def test_health_check(self, helper_path):
        """Test health check script."""
        process = subprocess.run(
            ["python", "health.py"],
            cwd=helper_path,
            capture_output=True,
            text=True
        )
        
        assert process.returncode == 0
        assert "All health checks passed" in process.stdout
```

### Integration Testing

```python
# tests/integration/test_helper_integration.py
import pytest
import httpx
from bridge.tinyrpc import app

@pytest.mark.asyncio
async def test_helper_execution_via_api():
    """Test helper execution through API."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/helpers/my_helper/execute",
            json={
                "input": {"operation": "status"},
                "dry_run": False
            },
            headers={"X-TinyIntent-Secret": "test-secret"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["helper_output"]["status"] == "success"

@pytest.mark.asyncio 
async def test_helper_preview_mode():
    """Test helper preview mode."""
    async with httpx.AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/helpers/my_helper/preview",
            json={"input": {"operation": "status"}},
            headers={"X-TinyIntent-Secret": "test-secret"}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "preview"
    assert data["dry_run"] is True
```

## 🚀 Deployment & Lifecycle

### Helper Registration

```bash
# Add helper to registry
# Edit helpers/registry.yaml

# Validate helper
python -m helpers.manifest validate helpers/my_helper/

# Test helper execution
python -m helpers.executor test my_helper '{"operation": "status"}'

# Deploy helper
# Helper is automatically available after registry update
```

### Lifecycle Management

```yaml
# Update lifecycle state in helper.yaml
lifecycle:
  state: trusted      # Promote from draft to trusted
  since: "2024-01-20"
  notes: "Passed security review and testing"
```

### Monitoring & Metrics

```python
# helpers/my_helper/metrics.py
def collect_metrics():
    """Collect helper-specific metrics."""
    return {
        "execution_count": get_execution_count(),
        "average_latency_ms": get_average_latency(),
        "error_rate": get_error_rate(),
        "last_execution": get_last_execution_time()
    }
```

## 🔧 Best Practices

### Security Best Practices

1. **Input Validation**: Always validate inputs against schemas
2. **Error Handling**: Never expose internal errors to users
3. **Resource Limits**: Respect memory and CPU constraints
4. **Logging**: Log security-relevant events
5. **Secrets**: Use scoped secret management

### Performance Best Practices

1. **Fast Startup**: Minimize initialization time
2. **Memory Efficiency**: Clean up resources properly
3. **Caching**: Cache expensive operations when appropriate
4. **Async Operations**: Use async patterns for I/O
5. **Timeout Handling**: Always respect timeout limits

### Code Quality Best Practices

1. **Documentation**: Document all public functions
2. **Testing**: Comprehensive unit and integration tests
3. **Error Messages**: Clear, actionable error messages
4. **Schema Design**: Well-defined input/output schemas
5. **Versioning**: Use semantic versioning

## 🐛 Troubleshooting

### Common Issues

#### Helper Not Found
```bash
# Check registry
python -m helpers.registry list

# Validate manifest
python -m helpers.manifest validate helpers/my_helper/
```

#### Execution Timeout
```python
# Optimize slow operations
async def optimized_operation():
    # Use async patterns for I/O
    # Break work into smaller chunks
    # Implement progress reporting
```

#### Schema Validation Errors
```bash
# Validate schemas
python -m jsonschema -i input.json helpers/my_helper/input.schema.json

# Test with example data
echo '{"operation": "status"}' | python helpers/my_helper/main.py
```

#### Permission Denied
```yaml
# Add required capabilities to helper.yaml
capabilities:
  - filesystem  # For file operations
  - network     # For HTTP requests
```

### Debugging Tips

1. **Use debug logging** in helper code
2. **Test schemas separately** before integration
3. **Check environment variables** in execution context
4. **Validate file permissions** and paths
5. **Monitor resource usage** during execution

---

This guide provides everything you need to create powerful, secure helpers for TinyIntent. Start with the Python example and customize it for your specific use case!