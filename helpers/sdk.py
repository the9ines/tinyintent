"""
TinyIntent Helpers SDK - M4: Helpers Framework v1

Provides helper manifest loading, schema validation, and sandbox constraints.
Manages the lifecycle of sandboxed helpers for action execution.
"""

import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import yaml
import jsonschema
from datetime import datetime


class HelperManifest:
    """Represents a helper manifest with validation."""
    
    def __init__(self, helper_id: str, manifest_data: Dict[str, Any], helper_dir: Path):
        self.helper_id = helper_id
        self.helper_dir = helper_dir
        self.manifest_data = manifest_data
        
        # Required fields
        self.purpose = manifest_data.get("purpose", "")
        self.schema = manifest_data.get("schema", {})
        self.capabilities = manifest_data.get("capabilities", {})
        self.sandbox = manifest_data.get("sandbox", {})
        self.environment = manifest_data.get("environment", {})
        
        # Load and validate schemas
        self.input_schema = self._load_schema("input")
        self.output_schema = self._load_schema("output")
        
        # Validate manifest structure
        self._validate_manifest()
    
    def _load_schema(self, schema_type: str) -> Optional[Dict[str, Any]]:
        """Load input or output JSON schema."""
        schema_path = self.schema.get(schema_type)
        if not schema_path:
            return None
        
        # Resolve relative paths
        if not schema_path.startswith("/"):
            schema_path = self.helper_dir / schema_path
        else:
            schema_path = Path(schema_path)
        
        try:
            with open(schema_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise ValueError(f"Invalid {schema_type} schema for {self.helper_id}: {e}")
    
    def _validate_manifest(self):
        """Validate manifest structure and required fields."""
        if not self.purpose:
            raise ValueError(f"Helper {self.helper_id}: purpose is required")
        
        if not self.capabilities:
            raise ValueError(f"Helper {self.helper_id}: capabilities are required")
        
        # Validate capabilities
        if not isinstance(self.capabilities.get("preview"), bool):
            raise ValueError(f"Helper {self.helper_id}: capabilities.preview must be boolean")
        
        # Validate sandbox configuration
        commands = self.sandbox.get("commands", [])
        if not commands:
            raise ValueError(f"Helper {self.helper_id}: sandbox.commands are required")
        
        # Validate timeouts
        timeouts = self.sandbox.get("timeouts", [])
        if timeouts:
            for timeout in timeouts:
                if not isinstance(timeout.get("seconds"), (int, float)):
                    raise ValueError(f"Helper {self.helper_id}: invalid timeout configuration")
    
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """Validate input data against input schema."""
        if not self.input_schema:
            return True
        
        try:
            jsonschema.validate(input_data, self.input_schema)
            return True
        except jsonschema.ValidationError:
            return False
    
    def validate_output(self, output_data: Dict[str, Any]) -> bool:
        """Validate output data against output schema."""
        if not self.output_schema:
            return True
        
        try:
            jsonschema.validate(output_data, self.output_schema)
            return True
        except jsonschema.ValidationError:
            return False
    
    def get_timeout(self, operation: str = "default") -> int:
        """Get timeout for specific operation."""
        timeouts = self.sandbox.get("timeouts", [])
        
        # Find specific timeout
        for timeout in timeouts:
            if timeout.get("name") == operation:
                return timeout.get("seconds", 5)
        
        # Return default timeout
        for timeout in timeouts:
            if timeout.get("name") == "default":
                return timeout.get("seconds", 5)
        
        return 5  # Fallback default
    
    def can_preview(self) -> bool:
        """Check if helper supports preview mode."""
        return self.capabilities.get("preview", False)
    
    def can_execute(self) -> bool:
        """Check if helper supports execute mode."""
        return self.capabilities.get("execute", False)
    
    def supports_emergency_close(self) -> bool:
        """Check if helper supports emergency close."""
        return self.capabilities.get("emergency_close", False)


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
        self.load_registry()
    
    def load_registry(self):
        """Load helper registry from registry.yaml."""
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
                    enabled = helper_info.get("enabled", True)
                    if not enabled:
                        continue
                    
                    try:
                        self._load_helper(helper_id)
                    except Exception as e:
                        print(f"Warning: Failed to load helper {helper_id}: {e}")
            else:
                # List format: [{id: helper_id, ...}]
                for helper_info in helpers_data:
                    helper_id = helper_info.get("id")
                    if not helper_id:
                        continue
                    
                    enabled = helper_info.get("enabled", True)
                    if not enabled:
                        continue
                    
                    try:
                        self._load_helper(helper_id)
                    except Exception as e:
                        print(f"Warning: Failed to load helper {helper_id}: {e}")
            
            print(f"Loaded {len(self.helpers)} helpers")
            
        except Exception as e:
            print(f"Error loading helper registry: {e}")
    
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
        """Get helper by ID."""
        return self.helpers.get(helper_id)
    
    def list_helpers(self) -> List[str]:
        """List all available helper IDs."""
        return list(self.helpers.keys())
    
    def reload(self):
        """Reload all helpers from registry."""
        self.helpers.clear()
        self.load_registry()


class HelperExecutor:
    """Executes helpers in sandboxed environments."""
    
    def __init__(self, registry: HelperRegistry):
        self.registry = registry
        self.audit_log = Path(__file__).parent.parent / "bridge" / "logs" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
    
    def preview(self, helper_id: str, input_data: Dict[str, Any], 
                session_id: str = None) -> Dict[str, Any]:
        """Execute helper in preview mode."""
        helper = self.registry.get_helper(helper_id)
        if not helper:
            raise ValueError(f"Helper not found: {helper_id}")
        
        if not helper.can_preview():
            raise ValueError(f"Helper {helper_id} does not support preview mode")
        
        # Validate input
        if not helper.validate_input(input_data):
            raise ValueError(f"Input validation failed for helper {helper_id}")
        
        # Log audit entry
        self._log_audit("preview", helper_id, input_data, session_id)
        
        # Execute helper in preview mode
        try:
            result = self._execute_helper(helper, input_data, mode="preview")
            
            # Validate output
            if not helper.validate_output(result):
                raise ValueError(f"Output validation failed for helper {helper_id}")
            
            return {
                "status": "success",
                "action": "preview", 
                "helper_id": helper_id,
                "preview_json": result,
                "approval_token": self._generate_approval_token()
            }
            
        except Exception as e:
            self._log_audit("preview_error", helper_id, input_data, session_id, error=str(e))
            raise
    
    def _execute_helper(self, helper: HelperManifest, input_data: Dict[str, Any], 
                       mode: str = "preview") -> Dict[str, Any]:
        """Execute helper subprocess with sandbox constraints."""
        
        # Prepare environment
        env = os.environ.copy()
        
        # Add required environment variables
        required_env = helper.environment.get("required", [])
        for env_var in required_env:
            if env_var not in env:
                raise ValueError(f"Required environment variable missing: {env_var}")
        
        # Prepare command
        commands = helper.sandbox.get("commands", [])
        if not commands:
            raise ValueError(f"No commands defined for helper {helper.helper_id}")
        
        # Use first command as main executable
        cmd = [commands[0]]
        if len(commands) > 1:
            cmd.extend(commands[1:])
        
        # Prepare input JSON
        input_json = json.dumps(input_data)
        
        # Get timeout
        timeout = helper.get_timeout(mode)
        
        try:
            # Execute subprocess with constraints
            result = subprocess.run(
                cmd,
                input=input_json,
                text=True,
                capture_output=True,
                timeout=timeout,
                cwd=helper.helper_dir,
                env=env
            )
            
            if result.returncode != 0:
                raise RuntimeError(f"Helper execution failed: {result.stderr}")
            
            # Parse output
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                raise ValueError(f"Helper returned invalid JSON: {result.stdout}")
        
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Helper execution timed out after {timeout}s")
    
    def _generate_approval_token(self) -> str:
        """Generate approval token for two-step execution."""
        return str(uuid.uuid4()).replace("-", "")[:16]
    
    def _log_audit(self, action: str, helper_id: str, input_data: Dict[str, Any], 
                   session_id: str = None, error: str = None):
        """Log audit entry for helper execution."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        audit_entry = {
            "ts": timestamp,
            "session_id": session_id or "unknown",
            "action": action,
            "helper_id": helper_id,
            "input_hash": hash(json.dumps(input_data, sort_keys=True)),
            "success": error is None,
            "error": error
        }
        
        try:
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write audit log: {e}")


# Global instances
helper_registry = HelperRegistry()
helper_executor = HelperExecutor(helper_registry)