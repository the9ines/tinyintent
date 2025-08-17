"""
Models configuration resolver for TinyIntent.
Reads models.yaml and resolves environment variable overrides.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Optional


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
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent / "helpers"))
        
        try:
            from sdk import helper_registry
            self.registry = helper_registry
            self.available = True
        except ImportError:
            self.registry = None
            self.available = False
    
    def is_helper_available(self, helper_id: str) -> bool:
        """Check if helper is available and valid."""
        if not self.available or not self.registry:
            return False
        return self.registry.is_helper_valid(helper_id)
    
    def get_helper_error(self, helper_id: str) -> Optional[str]:
        """Get error message for invalid helper."""
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
        if not self.available or not self.registry:
            return {
                "available": False,
                "error": "Helpers framework not available"
            }
        
        return {
            "available": True,
            **self.registry.get_validation_summary()
        }