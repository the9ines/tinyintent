"""
Models configuration resolver for TinyIntent.
Reads models.yaml and resolves environment variable overrides.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Optional, Any


class ModelResolver:
    """Resolves model configurations from models.yaml and environment variables."""
    
    def __init__(self, models_yaml_path: Optional[str] = None):
        """Initialize with path to models.yaml file."""
        if models_yaml_path is None:
            # Default to models.yaml in repo root
            self.models_yaml_path = Path(__file__).parent.parent / "models.yaml"
        else:
            self.models_yaml_path = Path(models_yaml_path)
        
        self._models = {}
        self._load_models()
    
    def _load_models(self) -> None:
        """Load models from yaml file."""
        try:
            with open(self.models_yaml_path, 'r') as f:
                config = yaml.safe_load(f)
                self._models = config.get('roles', {})
        except (FileNotFoundError, yaml.YAMLError) as e:
            print(f"Warning: Could not load models.yaml: {e}")
            self._models = {}
    
    def get_model(self, role: str) -> Optional[str]:
        """Get model for a specific role, with environment variable override."""
        # Check environment variable override first
        env_var = f"MODEL_{role.upper()}"
        env_override = os.getenv(env_var)
        if env_override:
            return env_override
        
        # Fall back to models.yaml
        return self._models.get(role)
    
    def get_all_models(self) -> Dict[str, str]:
        """Get all configured models with environment overrides applied."""
        result = {}
        for role in ['small', 'medium', 'large']:
            model = self.get_model(role)
            if model:
                result[role] = model
        return result
    
    def reload(self) -> None:
        """Reload models from yaml file."""
        self._load_models()
    
    def get_missing_models(self) -> list[str]:
        """Get list of missing models (placeholder for future ollama integration)."""
        # TODO: Integrate with ollama to check which models are actually available
        return []


class HelperResolver:
    """Resolves and validates helper configurations."""
    
    def __init__(self):
        """Initialize helper resolver."""
        # Import helpers here to avoid circular imports
        import sys
        import threading
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent / "helpers"))
        
        # M8.2: Thread-safe helper registry for hot reload
        self.lock = threading.RLock()
        
        try:
            from sdk import helper_registry, validate_helper_manifest
            self.registry = helper_registry
            self.validate_helper_manifest = validate_helper_manifest
            self.available = True
            
            # M8.1: Validate all helper manifests on startup
            self.load_helpers()
            
        except ImportError as e:
            print(f"Warning: Helpers framework not available: {e}")
            self.registry = None
            self.validate_helper_manifest = None
            self.available = False
    
    def load_helpers(self):
        """M8.2: Load and validate helpers with thread-safe registry reload."""
        with self.lock:
            return self._load_helpers_internal()
    
    def _load_helpers_internal(self):
        """Internal helper loading logic - assumes lock is already held."""
        if not self.available or not self.registry:
            return {
                "enabled": [],
                "disabled": [],
                "errors": {"framework_unavailable": "Helpers framework not available"},
                "total": 0
            }
        
        helpers_dir = Path(__file__).parent.parent / "helpers"
        if not helpers_dir.exists():
            print("Warning: Helpers directory not found")
            return {
                "enabled": [],
                "disabled": [],
                "errors": {"helpers_dir_missing": "Helpers directory not found"},
                "total": 0
            }
        
        # First trigger registry reload to clear old state
        try:
            self.registry.reload()
        except Exception as e:
            print(f"Warning: Registry reload failed: {e}")
        
        validation_summary = {
            "enabled": [],
            "disabled": [],
            "errors": {},
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "enabled_metadata": {}  # M8.3: Metadata for enabled helpers
        }
        
        # Iterate over all potential helper directories
        for helper_dir in helpers_dir.iterdir():
            if not helper_dir.is_dir() or helper_dir.name.startswith('.'):
                continue
            
            # Skip non-helper directories  
            if helper_dir.name in ['__pycache__', 'sdk.py', 'registry.yaml']:
                continue
            
            validation_summary["total"] += 1
            helper_id = helper_dir.name
            
            try:
                # Validate helper manifest
                result = self.validate_helper_manifest(helper_dir)
                
                if result["valid"]:
                    validation_summary["valid"] += 1
                    validation_summary["enabled"].append(helper_id)
                    
                    # M8.3: Collect metadata for enabled helpers
                    if self.registry:
                        registry_entry = self.registry.get_registry_entry(helper_id)
                        if registry_entry:
                            metadata = {}
                            if registry_entry.version:
                                metadata["version"] = registry_entry.version
                            if registry_entry.updated:
                                metadata["updated"] = registry_entry.updated
                            if registry_entry.maintainer:
                                metadata["maintainer"] = registry_entry.maintainer
                            if registry_entry.added:
                                metadata["added"] = registry_entry.added
                            if metadata:
                                validation_summary["enabled_metadata"][helper_id] = metadata
                    
                    # Log warnings if any
                    if result["warnings"]:
                        print(f"Helper {helper_id}: {len(result['warnings'])} warnings")
                        for warning in result["warnings"]:
                            print(f"  WARNING: {warning}")
                else:
                    validation_summary["invalid"] += 1
                    validation_summary["disabled"].append(helper_id)
                    validation_summary["errors"][helper_id] = result["errors"]
                    self._log_manifest_validation_failure(helper_id, result)
                    
            except Exception as e:
                validation_summary["invalid"] += 1
                validation_summary["disabled"].append(helper_id)
                validation_summary["errors"][helper_id] = [f"Validation exception: {e}"]
                print(f"Helper {helper_id}: Validation exception - {e}")
                self._log_manifest_validation_failure(helper_id, {
                    "valid": False,
                    "errors": [f"Validation exception: {e}"],
                    "warnings": [],
                    "helper_id": helper_id
                })
        
        print(f"Helper manifest validation: {validation_summary['valid']}/{validation_summary['total']} valid")
        
        # Log reload event to audit log
        self._log_helper_reload_event(validation_summary)
        
        return {
            "enabled": validation_summary["enabled"],
            "disabled": validation_summary["disabled"],
            "errors": validation_summary["errors"],
            "total": validation_summary["total"],
            "enabled_metadata": validation_summary["enabled_metadata"]  # M8.3: Include metadata
        }
    
    def _log_manifest_validation_failure(self, helper_id: str, validation_result: Dict[str, Any]):
        """Log structured warning for manifest validation failure."""
        import json
        from datetime import datetime
        
        # Create structured audit log entry
        audit_entry = {
            "ts": datetime.utcnow().isoformat() + 'Z',
            "action": "helper_manifest_validation_failure", 
            "helper_id": helper_id,
            "validation_errors": validation_result.get("errors", []),
            "warnings": validation_result.get("warnings", []),
            "success": False,
            "component": "bridge.resolve",
            "event_type": "startup_validation"
        }
        
        # Log to console for immediate feedback
        print(f"Helper {helper_id}: DISABLED - {len(validation_result['errors'])} errors")
        for error in validation_result["errors"]:
            print(f"  ERROR: {error}")
        
        # Try to write to audit log
        try:
            audit_log_path = Path(__file__).parent / "logs" / "audit.log"
            audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(audit_log_path, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
                
        except Exception as e:
            print(f"Warning: Failed to write manifest validation audit log: {e}")
    
    def _log_helper_reload_event(self, validation_summary: Dict[str, Any]):
        """Log helper reload event to audit log."""
        import json
        from datetime import datetime
        
        audit_entry = {
            "ts": datetime.utcnow().isoformat() + 'Z',
            "action": "helper_reload",
            "enabled_helpers": validation_summary["enabled"],
            "disabled_helpers": validation_summary["disabled"], 
            "total_helpers": validation_summary["total"],
            "valid_helpers": validation_summary["valid"],
            "invalid_helpers": validation_summary["invalid"],
            "success": True,
            "component": "bridge.resolve",
            "event_type": "hot_reload"
        }
        
        try:
            audit_log_path = Path(__file__).parent / "logs" / "audit.log"
            audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(audit_log_path, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
                
        except Exception as e:
            print(f"Warning: Failed to write helper reload audit log: {e}")
    
    def is_helper_available(self, helper_id: str) -> bool:
        """Check if helper is available and valid."""
        with self.lock:
            if not self.available or not self.registry:
                return False
            return self.registry.is_helper_valid(helper_id)
    
    def get_helper_error(self, helper_id: str) -> Optional[str]:
        """Get error message for invalid helper."""
        with self.lock:
            if not self.available:
                return "Helpers framework not available"
            if not self.registry:
                return "Helper registry not loaded"
            
            if not self.registry.get_registry_entry(helper_id):
                return f"Helper '{helper_id}' not found in registry"
            
            if not self.registry.is_helper_valid(helper_id):
                errors = self.registry.get_helper_validation_errors(helper_id)
                return f"Helper validation failed: {'; '.join(errors)}"
            
            return None
    
    def validate_helper_request(self, helper_id: str) -> Dict[str, Any]:
        """
        Validate helper request and return error response if invalid.
        
        Returns:
            dict: Error response if invalid, empty dict if valid
        """
        error = self.get_helper_error(helper_id)
        if error:
            return {
                "error": "helper_validation_failed",
                "detail": error,
                "helper_id": helper_id
            }
        return {}
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get validation summary for all helpers."""
        with self.lock:
            if not self.available or not self.registry:
                return {
                    "available": False,
                    "error": "Helpers framework not available"
                }
            
            return {
                "available": True,
                **self.registry.get_validation_summary()
            }


# M8.2: Global thread-safe helper resolver instance for hot reload
helper_resolver = HelperResolver()