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