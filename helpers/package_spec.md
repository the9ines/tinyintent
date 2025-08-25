# TinyIntent Helper Package Specification v1.0

## Overview

TinyIntent Helper Packages are self-contained, versioned units that extend TinyIntent's capabilities. Similar to VSCode extensions, they can be installed, updated, and removed independently.

## Package Structure

```
my_helper_package/
├── package.json          # Package metadata (required)
├── helper.yaml          # Helper manifest (required)
├── main.py|main.js      # Entry point (required)
├── input.schema.json    # Input validation (required)
├── output.schema.json   # Output validation (required)
├── README.md            # Documentation (recommended)
├── CHANGELOG.md         # Version history (recommended)
├── provenance.json      # Cryptographic signatures (auto-generated)
├── assets/              # Static files (optional)
│   ├── icons/
│   └── docs/
├── tests/               # Test suite (optional)
│   ├── test_main.py
│   └── fixtures/
└── lib/                 # Dependencies/libraries (optional)
```

## package.json Format

```json
{
  "name": "weather_helper",
  "version": "1.2.3",
  "description": "Real-time weather data using Open-Meteo API",
  "author": "TinyIntent Core Team <core@tinyintent.ai>",
  "license": "MIT",
  "keywords": ["weather", "api", "location"],
  "homepage": "https://tinyintent.ai/helpers/weather",
  "repository": {
    "type": "git",
    "url": "https://github.com/tinyintent/helpers-weather.git"
  },
  "bugs": "https://github.com/tinyintent/helpers-weather/issues",
  "tinyintent": {
    "spec_version": "1.0",
    "category": "information",
    "risk_level": "low",
    "capabilities": ["network"],
    "supported_versions": [">=2.0.0"],
    "entry_point": "./main.py",
    "language": "python",
    "requires_approval": false,
    "can_execute": true,
    "lifecycle": {
      "state": "trusted",
      "since": "2025-08-23"
    },
    "limits": {
      "preview_per_min": 120,
      "exec_per_min": 60,
      "daily_exec_budget": 1000
    }
  },
  "dependencies": {
    "requests": ">=2.25.0",
    "pydantic": ">=1.8.0"
  },
  "engines": {
    "python": ">=3.8",
    "tinyintent": ">=2.0.0"
  }
}
```

## Installation Sources

### 1. Local Packages
- Installed in `~/.tinyintent/packages/`
- Developed locally or manually installed

### 2. Official Registry
- Curated packages from TinyIntent team
- Hosted at `registry.tinyintent.ai`
- Cryptographically signed

### 3. Community Registry  
- User-contributed packages
- GitHub/npm-style publishing
- Community moderation

### 4. Direct GitHub/Git
- Install directly from repositories
- `tinyintent helper install github:user/repo`

## Package Management Commands

```bash
# Search available packages
tinyintent helper search weather
tinyintent helper search --category information

# Install packages
tinyintent helper install weather_helper
tinyintent helper install github:user/custom_helper
tinyintent helper install ./local_package/

# Manage packages
tinyintent helper list
tinyintent helper info weather_helper
tinyintent helper update weather_helper
tinyintent helper remove weather_helper

# Generate new packages
tinyintent helper generate
tinyintent helper generate --template python
tinyintent helper generate --from-description "crypto price checker"
```

## Security Model

### Capability System
- Packages declare required capabilities
- Network, filesystem, database access controlled
- User approval for high-risk packages

### Cryptographic Signatures
- All packages signed with Ed25519
- Tamper detection via provenance.json
- Official packages have verified signatures

### Sandboxing
- Process isolation for execution
- Resource limits (CPU, memory, time)
- File system restrictions

## Registry Architecture

### Core Registry (registry.py)
```python
class MultiSourceRegistry:
    def __init__(self):
        self.sources = [
            LocalPackageSource("~/.tinyintent/packages"),
            OfficialRegistrySource("registry.tinyintent.ai"),  
            GitHubSource()
        ]
        
    def discover_packages(self) -> List[HelperPackage]
    def install_package(self, spec: str) -> InstallResult
    def update_package(self, name: str) -> UpdateResult
```

### Package Lifecycle
1. **Discovery**: Find packages from multiple sources
2. **Validation**: Verify signatures and schemas
3. **Installation**: Download and validate dependencies
4. **Registration**: Add to active helper registry
5. **Execution**: Sandboxed helper execution
6. **Updates**: Version management and migration

## Migration Plan

### Phase 1: Package Current Helpers
- Convert existing helpers to package format
- Add package.json metadata
- Preserve existing functionality

### Phase 2: Multi-Source Registry
- Implement package sources
- Add installation/removal commands
- Create migration tools

### Phase 3: LLM Generation
- AI-powered package creation
- Template-based generation
- Interactive specification builder

### Phase 4: Marketplace
- Web interface for package discovery
- Community ratings and reviews
- Automated testing and validation

## Compatibility

### Backward Compatibility
- Existing helpers continue to work
- Gradual migration to package format
- Registry.yaml remains supported

### Forward Compatibility
- Versioned package specification
- Extensible metadata format
- Plugin architecture for new features

## Examples

See `examples/` directory for complete package examples:
- `weather_package/` - Information helper with API calls
- `crypto_trader_package/` - High-risk trading helper
- `log_analyzer_package/` - System monitoring helper