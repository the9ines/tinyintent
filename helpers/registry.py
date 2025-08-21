
"""
TinyIntent Helper Registry

Manages the registry of available helpers from registry.yaml.
Handles loading, validation of registry entries, and provides a queryable interface
to the rest of the system.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from .manifest import HelperManifest, _is_valid_semver, _is_valid_date
try:
    from tinyintent.bridge.logs.sanitize import sanitize_env
except ImportError:
    # Fallback for standalone usage
    def sanitize_env(env_dict):
        return env_dict

# Import audit logger (M6.2) - with fallback for standalone helper usage
AUDIT_LOGGER_AVAILABLE = False
get_audit_logger = None

try:
    from tinyintent.bridge.logs.audit import get_audit_logger
    AUDIT_LOGGER_AVAILABLE = True
except ImportError:
    # For standalone usage, create a simple mock
    def mock_audit_logger():
        class MockLogger:
            def log_entry(self, entry):
                pass
        return MockLogger()
    get_audit_logger = mock_audit_logger

class HelperRegistryEntry:
    """Represents a helper entry from registry.yaml with validation state."""
    
    def __init__(self, helper_id: str, registry_data: Dict[str, Any]):
        self.helper_id = helper_id
        self.name = registry_data.get("name", helper_id)
        self.description = registry_data.get("description", "")
        self.enabled = registry_data.get("enabled", True)
        self.category = registry_data.get("category", "unknown")
        self.risk_level = registry_data.get("risk_level", "medium")
        self.can_execute = registry_data.get("can_execute", True)
        self.manifest_path = registry_data.get("manifest_path", f"helpers/{helper_id}/helper.yaml")
        self.requires_approval = registry_data.get("requires_approval", False)
        self.required_envs = registry_data.get("required_envs", [])
        self.safety_notes = registry_data.get("safety_notes", "")
        self.capabilities = registry_data.get("capabilities", [])  # M6.5: Capability isolation
        
        # M8.3: Helper Lifecycle & Versioning metadata
        self.version = registry_data.get("version")
        self.added = registry_data.get("added")
        self.updated = registry_data.get("updated") 
        self.maintainer = registry_data.get("maintainer")
        
        # M8.6: Health Check Configuration
        self.healthcheck = registry_data.get("healthcheck")
        
        # M10.2: Agent Lifecycle Governance
        self.lifecycle = self._load_lifecycle(registry_data)
        
        # Validation state
        self.is_valid = True
        self.validation_errors = []
        self.env_validation_passed = True
        self.missing_envs = []
        
        # Perform validation
        self._validate_environment()
        self._validate_enabled()
        self._validate_version_metadata()
        self._validate_lifecycle()
    
    def _validate_environment(self):
        """Validate that required environment variables are present."""
        missing = []
        for env_var in self.required_envs:
            if env_var not in os.environ:
                missing.append(env_var)
        
        if missing:
            self.env_validation_passed = False
            self.missing_envs = missing
            self.can_execute = False  # Automatically disable execution
            error_msg = f"Missing required environment variables: {', '.join(missing)}"
            self.validation_errors.append(error_msg)
            self.is_valid = False
    
    def _validate_enabled(self):
        """Validate that helper is enabled."""
        if not self.enabled:
            self.can_execute = False
            error_msg = "Helper is disabled in registry"
            self.validation_errors.append(error_msg)
            self.is_valid = False
    
    def _validate_version_metadata(self):
        """M8.3: Validate version metadata if present."""
        # Validate version format
        if self.version and not _is_valid_semver(self.version):
            error_msg = f"Invalid version format: {self.version} (must be valid semantic version)"
            self.validation_errors.append(error_msg)
            self.is_valid = False
        
        # Validate date formats
        if self.added and not _is_valid_date(self.added):
            error_msg = f"Invalid added date format: {self.added} (must be YYYY-MM-DD)"
            self.validation_errors.append(error_msg)
            self.is_valid = False
            
        if self.updated and not _is_valid_date(self.updated):
            error_msg = f"Invalid updated date format: {self.updated} (must be YYYY-MM-DD)"
            self.validation_errors.append(error_msg)
            self.is_valid = False
        
        # Date consistency check
        if self.added and self.updated:
            try:
                from datetime import datetime
                added_date = datetime.strptime(self.added, '%Y-%m-%d')
                updated_date = datetime.strptime(self.updated, '%Y-%m-%d')
                if updated_date < added_date:
                    error_msg = f"Updated date ({self.updated}) cannot be before added date ({self.added})"
                    self.validation_errors.append(error_msg)
                    self.is_valid = False
            except ValueError:
                pass  # Date format errors already caught above
    
    def _load_lifecycle(self, registry_data: Dict[str, Any]) -> Dict[str, Any]:
        """M10.2: Load lifecycle configuration with defaults."""
        from .manifest import get_helper_lifecycle, determine_default_lifecycle_state
        
        lifecycle_data = registry_data.get("lifecycle", {})
        
        # Apply defaults if missing
        if not lifecycle_data:
            default_state = determine_default_lifecycle_state(registry_data)
            from datetime import datetime
            lifecycle_data = {
                "state": default_state,
                "since": datetime.now().strftime('%Y-%m-%d'),
                "notes": f"Default {default_state} state"
            }
        
        return lifecycle_data
    
    def _validate_lifecycle(self):
        """M10.2: Validate lifecycle configuration."""
        from .manifest import validate_lifecycle_state
        
        if not self.lifecycle:
            return  # Optional field
        
        is_valid, errors = validate_lifecycle_state(self.lifecycle)
        if not is_valid:
            self.validation_errors.extend(errors)
            self.is_valid = False
    
    def is_lifecycle_state(self, state: str) -> bool:
        """M10.2: Check if helper is in a specific lifecycle state."""
        return self.lifecycle.get("state") == state
    
    def is_retired(self) -> bool:
        """M10.2: Check if helper is retired."""
        return self.is_lifecycle_state("retired")
    
    def is_deprecated(self) -> bool:
        """M10.2: Check if helper is deprecated."""
        return self.is_lifecycle_state("deprecated")
    
    def is_trusted(self) -> bool:
        """M10.2: Check if helper is trusted."""
        return self.is_lifecycle_state("trusted")
    
    def is_draft(self) -> bool:
        """M10.2: Check if helper is in draft state."""
        return self.is_lifecycle_state("draft")
    
    def can_be_routed(self) -> bool:
        """M10.2: Check if helper can be routed (not retired)."""
        return not self.is_retired() and self.is_valid
    
    def has_capability(self, capability: str) -> bool:
        """Check if helper has a specific capability."""
        return capability in self.capabilities
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get validation summary for this registry entry."""
        summary = {
            "helper_id": self.helper_id,
            "name": self.name,
            "description": self.description,
            "is_valid": self.is_valid,
            "can_execute": self.can_execute,
            "env_validation_passed": self.env_validation_passed,
            "missing_envs": self.missing_envs,
            "validation_errors": self.validation_errors,
            "required_envs": self.required_envs,
            "safety_notes": self.safety_notes,
            "capabilities": self.capabilities,  # M6.5: Include capabilities in summary
            "category": self.category,
            "risk_level": self.risk_level,
            "lifecycle": self.lifecycle,  # M10.2: Include lifecycle information
            "can_be_routed": self.can_be_routed()  # M10.2: Include routing status
        }
        
        # M8.3: Include version metadata if present
        if self.version:
            summary["version"] = self.version
        if self.added:
            summary["added"] = self.added
        if self.updated:
            summary["updated"] = self.updated
        if self.maintainer:
            summary["maintainer"] = self.maintainer
        
        # M8.6: Include health check configuration if present
        if self.healthcheck:
            summary["healthcheck"] = self.healthcheck
        
        return summary

class HelperRegistry:
    """Manages the registry of available helpers."""
    
    def __init__(self, helpers_dir: Optional[str] = None):
        """Initialize helper registry."""
        if helpers_dir is None:
            # Default to helpers/ in project root
            project_root = Path(__file__).parent.parent
            self.helpers_dir = project_root / "helpers"
        else:
            self.helpers_dir = Path(helpers_dir)
        
        self.registry_file = self.helpers_dir / "registry.yaml"
        self.helpers: Dict[str, HelperManifest] = {}
        self.registry_entries: Dict[str, HelperRegistryEntry] = {}
        self.audit_log = Path(__file__).parent.parent / "bridge" / "logs" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
        self.load_registry()
    
    def load_registry(self):
        """Load helper registry from registry.yaml with validation."""
        try:
            if not self.registry_file.exists():
                print(f"Warning: Registry file not found: {self.registry_file}")
                return
            
            with open(self.registry_file, 'r') as f:
                registry_data = yaml.safe_load(f)
            
            helpers_data = registry_data.get("helpers", {})
            
            # Handle both dict and list formats
            if isinstance(helpers_data, dict):
                # Dict format: {helper_id: {info}}
                for helper_id, helper_info in helpers_data.items():
                    self._load_helper_with_validation(helper_id, helper_info)
            else:
                # List format: [{id: helper_id, ...}]
                for helper_info in helpers_data:
                    helper_id = helper_info.get("id")
                    if helper_id:
                        self._load_helper_with_validation(helper_id, helper_info)
            
            # Summary
            valid_helpers = len([h for h in self.registry_entries.values() if h.is_valid])
            total_helpers = len(self.registry_entries)
            print(f"Loaded {valid_helpers}/{total_helpers} helpers ({len(self.helpers)} with manifests)")
            
            # Log any validation failures
            invalid_helpers = [h for h in self.registry_entries.values() if not h.is_valid]
            for helper_entry in invalid_helpers:
                self._log_validation_failure(helper_entry)
            
        except Exception as e:
            print(f"Error loading helper registry: {e}")
    
    def _load_helper_with_validation(self, helper_id: str, helper_info: Dict[str, Any]):
        """Load helper with registry-level and manifest validation."""
        try:
            # Create registry entry with validation
            registry_entry = HelperRegistryEntry(helper_id, helper_info)
            self.registry_entries[helper_id] = registry_entry
            
            # Skip if disabled
            if not registry_entry.enabled:
                return
            
            # Skip if registry validation failed
            if not registry_entry.is_valid:
                return
            
            # Try to load helper manifest
            try:
                self._load_helper(helper_id)
            except Exception as e:
                # Mark as invalid due to manifest issues
                registry_entry.is_valid = False
                registry_entry.validation_errors.append(f"Manifest loading failed: {e}")
                print(f"Warning: Failed to load helper {helper_id}: {e}")
                
        except Exception as e:
            print(f"Warning: Failed to process helper {helper_id}: {e}")
    
    def _log_validation_failure(self, helper_entry: HelperRegistryEntry):
        """Log helper validation failure to audit log with integrity chaining."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Sanitize environment variable names for logging
        current_env = sanitize_env(dict(os.environ))
        
        audit_entry = {
            "ts": timestamp,
            "action": "helper_validation_failure",
            "helper_id": helper_entry.helper_id,
            "validation_errors": helper_entry.validation_errors,
            "missing_envs": helper_entry.missing_envs,
            "required_envs": helper_entry.required_envs,
            "success": False,
            "sanitized_env": current_env  # Log sanitized environment for debugging
        }
        
        try:
            if AUDIT_LOGGER_AVAILABLE and get_audit_logger:
                # Use integrity audit logger if available
                get_audit_logger().log_entry(audit_entry)
            else:
                # Fallback to direct file writing for standalone usage
                with open(self.audit_log, 'a') as f:
                    f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write validation audit log: {e}")
    
    def _load_helper(self, helper_id: str):
        """Load individual helper manifest."""
        helper_dir = self.helpers_dir / helper_id
        manifest_file = helper_dir / "helper.yaml"
        
        if not manifest_file.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_file}")
        
        with open(manifest_file, 'r') as f:
            manifest_data = yaml.safe_load(f)
        
        helper = HelperManifest(helper_id, manifest_data, helper_dir)
        self.helpers[helper_id] = helper
    
    def get_helper(self, helper_id: str) -> Optional[HelperManifest]:
        """Get helper by ID if it's valid and has a loaded manifest."""
        return self.helpers.get(helper_id)
    
    def get_registry_entry(self, helper_id: str) -> Optional[HelperRegistryEntry]:
        """Get registry entry by ID (includes validation state)."""
        return self.registry_entries.get(helper_id)
    
    def is_helper_valid(self, helper_id: str) -> bool:
        """Check if helper passed all validation checks."""
        entry = self.registry_entries.get(helper_id)
        return entry.is_valid if entry else False
    
    def get_helper_validation_errors(self, helper_id: str) -> List[str]:
        """Get validation errors for a helper."""
        entry = self.registry_entries.get(helper_id)
        return entry.validation_errors if entry else [f"Helper {helper_id} not found"]
    
    def list_helpers(self) -> List[str]:
        """List all available helper IDs (only valid ones with loaded manifests)."""
        return list(self.helpers.keys())
    
    def list_all_helpers(self) -> List[str]:
        """List all helper IDs from registry (including invalid ones)."""
        return list(self.registry_entries.keys())
    
    def get_validation_summary(self) -> Dict[str, Any]:
        """Get comprehensive validation summary for all helpers."""
        return {
            "total_helpers": len(self.registry_entries),
            "valid_helpers": len([h for h in self.registry_entries.values() if h.is_valid]),
            "loaded_manifests": len(self.helpers),
            "helpers": {
                helper_id: entry.get_validation_summary()
                for helper_id, entry in self.registry_entries.items()
            }
        }
    
    def reload(self):
        """Reload all helpers from registry."""
        self.helpers.clear()
        self.registry_entries.clear()
        self.load_registry()
    
    def can_route_helper(self, helper_id: str) -> bool:
        """M10.2: Check if helper can be routed (not retired, valid)."""
        entry = self.registry_entries.get(helper_id)
        return entry.can_be_routed() if entry else False
    
    def is_helper_deprecated(self, helper_id: str) -> bool:
        """M10.2: Check if helper is deprecated."""
        entry = self.registry_entries.get(helper_id)
        return entry.is_deprecated() if entry else False
    
    def is_helper_retired(self, helper_id: str) -> bool:
        """M10.2: Check if helper is retired."""
        entry = self.registry_entries.get(helper_id)
        return entry.is_retired() if entry else False
    
    def get_helper_lifecycle(self, helper_id: str) -> Optional[Dict[str, Any]]:
        """M10.2: Get helper lifecycle information."""
        entry = self.registry_entries.get(helper_id)
        return entry.lifecycle if entry else None
    
    def update_helper_lifecycle(self, helper_id: str, state: str, notes: str = None) -> bool:
        """
        M10.2: Update helper lifecycle state in helper.yaml.
        
        Args:
            helper_id: Helper identifier
            state: New lifecycle state
            notes: Optional notes about the change
            
        Returns:
            True if update succeeded, False otherwise
        """
        from datetime import datetime
        
        entry = self.registry_entries.get(helper_id)
        if not entry:
            return False
        
        # Update helper.yaml file directly
        helper_dir = Path(entry.manifest_path).parent
        helper_yaml = helper_dir / "helper.yaml"
        
        if not helper_yaml.exists():
            return False
        
        try:
            # Load current helper.yaml
            with open(helper_yaml, 'r') as f:
                helper_data = yaml.safe_load(f)
            
            # Update lifecycle section
            if "lifecycle" not in helper_data:
                helper_data["lifecycle"] = {}
            
            helper_data["lifecycle"]["state"] = state
            helper_data["lifecycle"]["since"] = datetime.now().strftime('%Y-%m-%d')
            if notes:
                helper_data["lifecycle"]["notes"] = notes
            
            # Write back to file (preserve formatting as much as possible)
            with open(helper_yaml, 'w') as f:
                yaml.dump(helper_data, f, default_flow_style=False, indent=2)
            
            # Update in-memory state
            entry.lifecycle["state"] = state
            entry.lifecycle["since"] = helper_data["lifecycle"]["since"]
            if notes:
                entry.lifecycle["notes"] = notes
            
            return True
            
        except Exception as e:
            if AUDIT_LOGGER_AVAILABLE:
                audit_logger = get_audit_logger()
                audit_logger.log_entry({
                    "action": "helper_lifecycle_update_failed",
                    "helper_id": helper_id,
                    "error": str(e),
                    "success": False
                })
            return False
    
    def get_helpers_by_lifecycle_state(self, state: str) -> List[str]:
        """M10.2: Get list of helpers in specific lifecycle state."""
        return [
            helper_id for helper_id, entry in self.registry_entries.items()
            if entry.is_lifecycle_state(state)
        ]
