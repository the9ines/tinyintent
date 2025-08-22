# 🤝 Contributing to TinyIntent

Welcome! TinyIntent is a voice-activated AI platform that connects iPhones to local AI models. This guide will help you get started with contributing to the project.

## 🚀 Quick Start for Developers

### Prerequisites
- **macOS** (required for CoreML router training)
- **Python 3.9+** with pip
- **Node.js 18+** (for helper execution)
- **Xcode Command Line Tools** (for Swift router training)
- **Ollama** running locally on port 11434

### Setup Development Environment

```bash
# Clone and enter project
git clone <your-fork-url>
cd tinyintent

# Install in development mode
./install.sh

# Install development dependencies
pip install -e ".[test,dev]"

# Verify installation
tinyintent --help
make doctor  # System health check
```

## 🏗️ Project Architecture

### Core Components

```
tinyintent/
├── tinyintent/          # CLI package (user interface)
├── bridge/              # FastAPI backend (main service)
│   ├── routes/         # API endpoints by feature
│   ├── security.py     # Authentication & authorization  
│   ├── validation.py   # Input validation & sanitization
│   └── logs/          # Audit logging system
├── router/             # Intent classification (CoreML)
├── helpers/            # Sandboxed task execution
├── data/episodes/      # Request logging & training data
└── tests/              # Comprehensive test suite
```

### Request Flow
```
iPhone → Shortcut API → Bridge → Router → Helper → Response
  ↓         ↓            ↓        ↓        ↓        ↓
Voice → /shortcut/route → FastAPI → CoreML → Sandbox → JSON
```

## 🧪 Testing Strategy

### Running Tests

```bash
# Full test suite
make test

# Individual test categories
./tests/health.sh              # System health
./tests/auth.sh               # Authentication
./tests/routes.smoke.sh       # API endpoints
./tests/helpers_smoke.sh      # Helper framework
./tests/router_smoke.sh       # Router model

# Python unit tests
python -m pytest tests/ -v

# Integration tests
python -m pytest tests/integration/ -v
```

### Test Categories

1. **Unit Tests** (`tests/`) - Individual component testing
2. **Integration Tests** (`tests/integration/`) - Cross-component workflows
3. **Smoke Tests** (`tests/*.sh`) - End-to-end system validation
4. **Security Tests** (`tests/test_security_fixes.py`) - Security validation

## 🔧 Development Workflow

### Code Quality Standards

- **Python**: Black formatting, flake8 linting, mypy type checking
- **Documentation**: Comprehensive docstrings for all public APIs
- **Security**: All changes must maintain security model integrity
- **Testing**: New features require corresponding tests

### Making Changes

1. **Create feature branch** from `main`
2. **Make changes** following coding standards
3. **Add tests** for new functionality
4. **Run test suite** to ensure no regressions
5. **Update documentation** if needed
6. **Submit pull request** with clear description

### Commit Message Format

```
🎯 Component: Brief description

- Specific change 1
- Specific change 2

Fixes #issue-number
```

Examples:
- `🔒 Security: Add input validation for helper parameters`
- `📱 Shortcut API: Improve TTS response formatting`
- `🧠 Router: Update training data for better classification`

## 🛡️ Security Guidelines

### Security-First Development

- **Input validation**: All user inputs must be validated and sanitized
- **Authentication**: Maintain multi-layer auth (tokens + secrets)
- **Sandboxing**: Helpers must run in isolated environments
- **Audit logging**: All security-relevant events must be logged
- **No secrets in code**: Use environment variables or secure storage

### Security Testing

```bash
# Run security test suite
python tests/test_security_fixes.py

# Manual security validation
./scripts/validate_security_fixes.py
```

## 📱 iPhone Shortcut Development

### Testing Shortcut Integration

1. **Start local server**: `tinyintent`
2. **Get your token**: `tinyintent show-credentials`
3. **Configure shortcut** with your local IP and token
4. **Test voice commands** and verify responses

### Shortcut API Guidelines

- **Keep responses concise** for voice output
- **Handle errors gracefully** with user-friendly messages
- **Optimize for TTS** (Text-to-Speech) delivery
- **Respect length limits** for voice responses

## 🤖 Helper Development

### Creating New Helpers

1. **Create helper directory**: `helpers/my_helper/`
2. **Add manifest**: `helper.yaml` with metadata
3. **Implement logic**: `main.js` or `main.py`
4. **Define schemas**: `input.schema.json`, `output.schema.json`
5. **Add health check**: `health.js` or `health.py`
6. **Register helper**: Update `helpers/registry.yaml`

### Helper Requirements

- **Sandboxed execution**: Must run in isolated environment
- **Schema validation**: Input/output must match declared schemas
- **Error handling**: Graceful error responses
- **Resource limits**: Respect CPU/memory/timeout constraints
- **Security**: No access to sensitive system resources

## 🧠 Router Model Development

### Training New Models

```bash
# Prepare training data
# Edit router/data/intents.tsv

# Train new model
make router-train

# Evaluate model performance
make router-eval

# Deploy if metrics are good
make router-deploy
```

### Router Guidelines

- **Keep models small**: Target <100MB for fast loading
- **Optimize for Apple Neural Engine**: Use CoreML optimization
- **Validate accuracy**: Aim for >90% intent classification accuracy
- **Test edge cases**: Handle unclear or ambiguous inputs

## 🐛 Debugging & Troubleshooting

### Debug Mode

```bash
# Start with verbose logging
tinyintent --verbose

# Enable debug logging in code
export TINYINTENT_LOG_LEVEL=debug
```

### Common Issues

- **"Module not found"**: Ensure you're in project directory and ran `./install.sh`
- **"Connection refused"**: Check firewall settings and Ollama service
- **"Helper execution failed"**: Check helper logs and resource limits
- **"Router model not found"**: Run `make router-train` to create model

### Log Locations

- **Bridge logs**: Console output (structured JSON in production)
- **Audit logs**: `bridge/logs/audit.log`
- **Helper logs**: Captured in execution responses
- **Error logs**: `bridge/logs/stderr.log`

## 📚 Documentation

### Required Documentation

- **Code changes**: Update relevant docstrings
- **New features**: Add to README.md and user documentation
- **API changes**: Update FastAPI documentation
- **Security changes**: Update SECURITY.md

### Documentation Standards

- **Clear examples**: Include code examples for complex features
- **User perspective**: Write from the user's point of view
- **Keep current**: Update docs with code changes
- **Link references**: Cross-reference related documentation

## 🔄 Release Process

### Version Management

- **Semantic versioning**: MAJOR.MINOR.PATCH
- **Feature releases**: Minor version bump
- **Bug fixes**: Patch version bump
- **Breaking changes**: Major version bump

### Release Checklist

1. **Update version** in `pyproject.toml`
2. **Update CHANGELOG.md** with changes
3. **Run full test suite**
4. **Update documentation**
5. **Create release tag**
6. **Deploy to production**

## 🤝 Getting Help

### Communication Channels

- **Issues**: GitHub Issues for bugs and feature requests
- **Discussions**: GitHub Discussions for questions
- **Security**: Email security@tinyintent.com for security issues

### Issue Templates

- **Bug reports**: Include steps to reproduce, expected vs actual behavior
- **Feature requests**: Include use case, proposed solution, alternatives
- **Security issues**: Use private security advisory process

## 📋 Coding Standards

### Python Style

```python
# Use type hints
def process_request(text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """Process user request with optional session tracking."""
    pass

# Use docstrings
class HelperExecutor:
    """Executes helpers in sandboxed environments with resource limits."""
    
    def execute(self, helper_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute helper with given input data.
        
        Args:
            helper_id: Unique identifier for the helper
            input_data: Validated input parameters
            
        Returns:
            Helper execution result with status and data
            
        Raises:
            SecurityError: If helper violates security constraints
            ValidationError: If input data is invalid
        """
        pass
```

### Error Handling

```python
# Use specific exceptions
from tinyintent.exceptions import ValidationError, SecurityError

# Log errors with context
logger.error("Helper execution failed", 
            helper_id=helper_id, 
            error=str(e),
            session_id=session_id)

# Return user-friendly error messages
return {"error": "Unable to process request", "error_code": "HELPER_FAILED"}
```

---

Thank you for contributing to TinyIntent! Your contributions help make voice-activated AI more accessible and secure for everyone.