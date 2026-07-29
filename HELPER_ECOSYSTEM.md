# 🤖 TinyIntent Helper Ecosystem

**Developer Guide for Building Multi-Domain Automation**

The TinyIntent helper framework enables unlimited automation domains through a standardized, secure, and extensible architecture. Build helpers for any use case - from weather data to enterprise network monitoring.

---

## 🏗️ Architecture Overview

### Helper Framework Components

```
helpers/
├── your_helper/               # Helper directory
│   ├── main.py               # Entry point executable
│   ├── helper.yaml           # Helper metadata & configuration
│   ├── package.json          # npm-style package metadata
│   ├── input.schema.json     # Input validation schema
│   ├── output.schema.json    # Output format schema
│   ├── health.py            # Health check implementation
│   └── provenance.json      # Cryptographic signature
├── registry.yaml            # Central helper registry
├── executor.py             # Sandboxed execution engine
└── sandbox.py              # Security isolation layer
```

### Execution Flow
1. **Voice Command** → iPhone Shortcut → TinyIntent Bridge
2. **Intent Routing** → SmallIntent.mlmodel classifies command
3. **Helper Selection** → Route to appropriate automation helper
4. **Sandboxed Execution** → Isolated, secure helper execution
5. **Response Processing** → Structured data → Voice response
6. **Audit Logging** → Complete execution audit trail

---

## 🚀 Quick Start: Build Your First Helper

### 1. Create Helper Directory Structure

```bash
mkdir helpers/my_automation
cd helpers/my_automation
```

### 2. Create Main Executable (`main.py`)

```python
#!/usr/bin/env python3
"""
My Automation Helper

Description of what your helper does.
"""

import json
import sys
from datetime import datetime

def main():
    """Main entry point - processes JSON input from command line."""
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No input provided"}))
        sys.exit(1)
    
    try:
        # Parse JSON input from command line argument
        input_data = json.loads(sys.argv[1])
        operation = input_data.get("operation", "default")
        
        # Your automation logic here
        result = {
            "status": "success",
            "operation": operation,
            "timestamp": datetime.now().isoformat(),
            "message": f"Completed {operation} successfully",
            "data": {
                "example_key": "example_value",
                "processed_input": input_data
            }
        }
        
        print(json.dumps(result, indent=2))
        
    except json.JSONDecodeError:
        print(json.dumps({"status": "error", "message": "Invalid JSON input"}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 3. Create Helper Metadata (`helper.yaml`)

```yaml
name: my_automation
display_name: "My Automation Helper"
description: "Description of what your helper automates"
purpose: "Specific purpose and use cases"
version: "1.0.0"
author: "Your Name"
category: automation
risk_level: low

capabilities:
  - network      # If you need network access
  - filesystem   # If you need file system access

operations:
  - name: default_operation
    description: "Default operation description"
    risk_level: low
    
  - name: advanced_operation  
    description: "Advanced operation description"
    risk_level: medium

# Optional: Voice command routing hints
keywords:
  - "automation"
  - "my helper"
  - "specific terms"

# Optional: Configuration parameters
config:
  timeout_seconds: 30
  max_retries: 3
```

### 4. Create Package Metadata (`package.json`)

```json
{
  "name": "my_automation_helper",
  "version": "1.0.0",
  "description": "My automation helper for TinyIntent platform",
  "author": "Your Name <your.email@domain.com>",
  "license": "MIT",
  "keywords": ["automation", "tinyintent", "helper"],
  "tinyintent": {
    "spec_version": "1.0",
    "category": "automation",
    "risk_level": "low",
    "capabilities": ["network"],
    "entry_point": "./main.py",
    "language": "python",
    "requires_approval": false,
    "can_execute": true,
    "lifecycle": {
      "state": "trusted",
      "since": "2025-08-25",
      "notes": "Custom automation helper"
    }
  },
  "dependencies": {
    "requests": ">=2.25.0"
  },
  "engines": {
    "python": ">=3.8",
    "tinyintent": ">=2.0.0"
  }
}
```

### 5. Register Your Helper (`helpers/registry.yaml`)

Add your helper to the central registry:

```yaml
helpers:
  my_automation:
    name: "My Automation Helper"
    description: "Custom automation for specific use cases"
    enabled: true
    category: "automation"
    risk_level: "low"
    can_execute: true
    manifest_path: "helpers/my_automation/helper.yaml"
    requires_approval: false
    capabilities:
      - "network"
    lifecycle:
      state: "trusted"
      since: "2025-08-25"
      notes: "Custom helper - production ready"
    healthcheck: "health.py"
```

---

## 📋 JSON Schema Validation

### Input Schema (`input.schema.json`)

Define and validate all possible inputs to your helper:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "My Automation Helper Input Schema",
  "type": "object",
  "properties": {
    "operation": {
      "type": "string",
      "enum": ["default_operation", "advanced_operation"],
      "description": "The operation to perform"
    },
    "parameters": {
      "type": "object",
      "properties": {
        "setting_a": {
          "type": "string",
          "minLength": 1,
          "maxLength": 100
        },
        "setting_b": {
          "type": "integer",
          "minimum": 1,
          "maximum": 1000
        }
      },
      "additionalProperties": false
    }
  },
  "required": ["operation"],
  "additionalProperties": false
}
```

### Output Schema (`output.schema.json`)

Define the structure of your helper's responses:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "My Automation Helper Output Schema",
  "type": "object",
  "properties": {
    "status": {
      "type": "string",
      "enum": ["success", "error", "warning"]
    },
    "operation": {
      "type": "string"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "message": {
      "type": "string"
    },
    "data": {
      "type": "object",
      "description": "Operation-specific response data"
    },
    "error": {
      "type": "string",
      "description": "Error message if status is error"
    }
  },
  "required": ["status", "operation", "timestamp", "message"],
  "additionalProperties": false
}
```

---

## 🏥 Health Checks

### Health Check Implementation (`health.py`)

```python
#!/usr/bin/env python3
"""
Health check for My Automation Helper
"""

import json
import sys

def check_dependencies():
    """Check if required dependencies are available."""
    results = {
        "status": "success",
        "checks": [],
        "recommendations": []
    }
    
    # Check required Python packages
    try:
        import requests
        results["checks"].append("requests library: AVAILABLE")
    except ImportError:
        results["checks"].append("requests library: MISSING")
        results["recommendations"].append("Install requests: pip install requests")
        results["status"] = "error"
    
    return results

def check_configuration():
    """Validate configuration and settings."""
    return {
        "status": "success",
        "checks": ["Configuration validation: PASS"]
    }

def main():
    """Run all health checks."""
    health_results = {
        "helper_name": "my_automation",
        "version": "1.0.0",
        "timestamp": "2025-08-25T00:00:00Z",
        "overall_status": "success",
        "checks": {}
    }
    
    # Run health checks
    checks = {
        "dependencies": check_dependencies(),
        "configuration": check_configuration()
    }
    
    health_results["checks"] = checks
    
    # Determine overall status
    statuses = [check["status"] for check in checks.values()]
    if "error" in statuses:
        health_results["overall_status"] = "error"
    elif "warning" in statuses:
        health_results["overall_status"] = "warning"
    
    print(json.dumps(health_results, indent=2))
    
    # Exit with appropriate code
    sys.exit(0 if health_results["overall_status"] == "success" else 1)

if __name__ == "__main__":
    main()
```

---

## 🔒 Security & Sandboxing

### Capability System

Helpers declare required capabilities in their metadata:

- **`network`**: Internet and LAN access for API calls
- **`filesystem`**: Read/write access to files and directories  
- **`system`**: System-level operations and process management

### Sandbox Isolation

All helpers execute in isolated sandboxes with:
- **Resource Limits**: CPU, memory, execution time constraints
- **Network Isolation**: Controlled network access based on capabilities
- **Filesystem Restrictions**: Limited file system access
- **Process Control**: Restricted process creation and system calls

### Risk Assessment

- **`low`**: Information helpers, read-only operations
- **`medium`**: System monitoring, configuration changes
- **`high`**: Financial operations, critical system modifications

---

## 🔍 Real-World Examples

### Weather Helper (Information Domain)

```python
# Key features:
- External API integration (Open-Meteo)
- Location awareness (GPS coordinates)
- Natural language responses
- Zero approval required

# Voice commands:
"What's the weather like?"
"Will it rain today?"
```

### Network Monitor (Infrastructure Domain)

```python  
# Key features:
- Enterprise device monitoring (SNMP, APIs)
- ML-based anomaly detection
- Predictive failure analysis
- Automated configuration backups

# Voice commands:
"Are there network anomalies?"
"Check my network devices"
```

### System Monitor (Performance Domain)

```python
# Key features:
- Cross-platform system monitoring
- Real-time performance metrics
- Resource usage analysis
- Health status reporting

# Voice commands:
"Check system performance"
"How much CPU am I using?"
```

---

## 🎯 Helper Categories

### Information Helpers
- **Purpose**: Data retrieval and reporting
- **Risk Level**: Low
- **Examples**: Weather, news, reference data
- **Approval**: Not required

### Automation Helpers  
- **Purpose**: Task execution and system control
- **Risk Level**: Medium
- **Examples**: System monitoring, network management
- **Approval**: Optional based on risk

### Action Helpers
- **Purpose**: State-changing operations
- **Risk Level**: High  
- **Examples**: Trading, system administration
- **Approval**: Required for critical operations

---

## 🛠️ Development Tools

### Testing Your Helper

```bash
# Test helper directly
cd helpers/my_automation
python3 main.py '{"operation": "default_operation", "parameters": {"setting_a": "test"}}'

# Test via TinyIntent executor
python3 -c "
from helpers.executor import HelperExecutor
from helpers.registry import HelperRegistry

registry = HelperRegistry()
executor = HelperExecutor(registry)

result = executor.execute('my_automation', {
    'operation': 'default_operation',
    'parameters': {'setting_a': 'test'}
})

print(result)
"
```

### Generate Provenance (Security)

```bash
python3 -c "
from bridge.provenance import generate_and_save_provenance
from pathlib import Path

generate_and_save_provenance(
    helper_id='my_automation',
    helper_dir=Path('helpers/my_automation'),
    generator='custom-helper-development'
)
"
```

### Validate Schemas

```bash
# Install JSON schema validator
pip install jsonschema

# Validate input/output schemas
python3 -c "
import json
from jsonschema import validate

with open('helpers/my_automation/input.schema.json') as f:
    schema = json.load(f)

test_input = {'operation': 'default_operation'}
validate(test_input, schema)
print('✅ Schema validation passed')
"
```

---

## 📚 Advanced Features

### Multi-Language Support

Helpers can be written in any language:

```javascript
// Node.js helper example
const input = JSON.parse(process.argv[2]);

const result = {
    status: "success",
    operation: input.operation,
    timestamp: new Date().toISOString(),
    message: "Node.js helper executed successfully"
};

console.log(JSON.stringify(result, null, 2));
```

### Async Operations

For long-running tasks:

```python
import asyncio

async def long_running_task():
    # Simulate work
    await asyncio.sleep(5)
    return {"status": "completed"}

# Use asyncio.run() for async helpers
result = asyncio.run(long_running_task())
```

### Configuration Management

Environment-based configuration:

```python
import os

# Use environment variables for configuration
api_key = os.getenv('MY_HELPER_API_KEY')
timeout = int(os.getenv('MY_HELPER_TIMEOUT', '30'))
```

---

## 🚀 Publishing Your Helper

### Documentation Template

Create a `README.md` for your helper:

```markdown
# My Automation Helper

Brief description of what your helper does.

## Voice Commands
- "command example 1"
- "command example 2"

## Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Configure settings: Set environment variables
3. Test: `python3 main.py '{"operation": "test"}'`

## Operations
- `default_operation`: Description
- `advanced_operation`: Description

## Configuration
- `MY_HELPER_API_KEY`: API key for external service
- `MY_HELPER_TIMEOUT`: Request timeout in seconds
```

### Contributing to TinyIntent

1. **Fork Repository**: Create your helper in a fork
2. **Follow Standards**: Use schemas, health checks, provenance
3. **Test Thoroughly**: Validate all operations and edge cases
4. **Document Completely**: Clear usage examples and setup
5. **Submit PR**: Include helper in main TinyIntent repository

---

## 🎉 Helper Ecosystem Goals

**100+ Helper Vision**: TinyIntent aims to support hundreds of automation helpers across every domain:

- **Smart Home**: IoT device control, home automation
- **DevOps**: CI/CD, monitoring, deployment automation  
- **Business**: CRM integration, reporting, analytics
- **Content**: Blog publishing, social media, content management
- **Health**: Fitness tracking, health monitoring, wellness
- **Education**: Learning tools, research automation, study aids

**Community-Driven**: The helper ecosystem grows through community contributions, making TinyIntent the ultimate voice automation platform.

---

## 📞 Support & Resources

- **[TinyIntent Documentation](./README.md)** - Platform overview
- **[Automation Gallery](./AUTOMATION_GALLERY.md)** - Example use cases
- **[GitHub Issues](https://github.com/the9ines/tinyintent/issues)** - Bug reports and feature requests
- **[Contribution Guidelines](./CONTRIBUTING.md)** - How to contribute helpers

**Ready to build the next great automation helper?** Start with the quick start guide and join the growing TinyIntent ecosystem!