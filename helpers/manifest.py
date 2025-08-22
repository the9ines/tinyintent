
"""
TinyIntent Helper Manifest

Handles loading, validation, and access to a helper's manifest (helper.yaml).
Ensures that manifests are well-formed and contain all required fields for safe execution.
"""

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Tuple

import yaml
import jsonschema

def validate_helper_manifest(helper_dir: Union[str, Path]) -> Dict[str, Any]:
    """
    M8.1: Validate helper manifest and schema files.
    
    Ensures:
    - helper.yaml, input.schema.json, output.schema.json exist
    - Required fields: id, description, can_execute, risk_level, capabilities
    - Schema files compile with jsonschema
    
    Args:
        helper_dir: Path to helper directory
        
    Returns:
        dict: Validation result with structure:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str],
                "helper_id": str
            }
    """
    helper_dir = Path(helper_dir)
    helper_id = helper_dir.name
    
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "helper_id": helper_id
    }
    
    # Check required files exist
    required_files = {
        "helper.yaml": helper_dir / "helper.yaml",
        "input.schema.json": helper_dir / "input.schema.json", 
        "output.schema.json": helper_dir / "output.schema.json"
    }
    
    for file_type, file_path in required_files.items():
        if not file_path.exists():
            result["errors"].append(f"Missing required file: {file_type}")
            result["valid"] = False
    
    # If missing core files, return early
    if not (helper_dir / "helper.yaml").exists():
        return result
    
    # Load and validate helper.yaml
    try:
        with open(helper_dir / "helper.yaml", 'r') as f:
            manifest = yaml.safe_load(f)
    except (yaml.YAMLError, FileNotFoundError) as e:
        result["errors"].append(f"Failed to parse helper.yaml: {e}")
        result["valid"] = False
        return result
    
    # Check required manifest fields
    required_fields = {
        "purpose": "purpose description",
        "capabilities": "capabilities configuration", 
        "sandbox": "sandbox configuration"
    }
    
    for field, description in required_fields.items():
        if field not in manifest:
            result["errors"].append(f"Missing required field: {field} ({description})")
            result["valid"] = False
    
    # Validate capabilities structure
    if "capabilities" in manifest:
        caps = manifest["capabilities"]
        if not isinstance(caps, dict):
            result["errors"].append("capabilities must be an object/dict")
            result["valid"] = False
        else:
            # Check for required capability fields
            required_caps = ["preview", "execute"]
            for cap in required_caps:
                if cap not in caps:
                    result["errors"].append(f"Missing required capability: {cap}")
                    result["valid"] = False
                elif not isinstance(caps[cap], bool):
                    result["errors"].append(f"Capability '{cap}' must be boolean")
                    result["valid"] = False
    
    # Validate sandbox configuration
    if "sandbox" in manifest:
        sandbox = manifest["sandbox"]
        if not isinstance(sandbox, dict):
            result["errors"].append("sandbox must be an object/dict")
            result["valid"] = False
        else:
            # Check for commands
            if "commands" not in sandbox:
                result["errors"].append("sandbox.commands is required")
                result["valid"] = False
            elif not isinstance(sandbox["commands"], list) or len(sandbox["commands"]) == 0:
                result["errors"].append("sandbox.commands must be non-empty array")
                result["valid"] = False
    
    # Validate metadata fields if present (from registry compatibility)
    if "metadata" in manifest:
        metadata = manifest["metadata"]
        if isinstance(metadata, dict):
            # Check risk_level format
            risk_level = metadata.get("risk_level", "medium")
            valid_risk_levels = ["low", "medium", "high"]
            if risk_level not in valid_risk_levels:
                result["errors"].append(f"Invalid risk_level: {risk_level}. Must be one of: {', '.join(valid_risk_levels)}")
                result["valid"] = False
    
    # Validate schema files compile with jsonschema
    for schema_type in ["input", "output"]:
        schema_file = helper_dir / f"{schema_type}.schema.json"
        if schema_file.exists():
            try:
                with open(schema_file, 'r') as f:
                    schema_data = json.load(f)
                
                # Validate it's a valid JSON Schema
                jsonschema.validators.Draft202012Validator.check_schema(schema_data)
                
            except json.JSONDecodeError as e:
                result["errors"].append(f"{schema_type}.schema.json: Invalid JSON - {e}")
                result["valid"] = False
            except jsonschema.SchemaError as e:
                result["errors"].append(f"{schema_type}.schema.json: Invalid JSON Schema - {e}")
                result["valid"] = False
            except Exception as e:
                result["errors"].append(f"{schema_type}.schema.json: Validation error - {e}")
                result["valid"] = False
    
    # Check for schema path references in manifest
    if "schema" in manifest:
        schema_config = manifest["schema"]
        if isinstance(schema_config, dict):
            for schema_type in ["input", "output"]:
                if schema_type in schema_config:
                    schema_path = schema_config[schema_type]
                    # Handle relative paths
                    if not schema_path.startswith("/"):
                        full_path = helper_dir / schema_path
                    else:
                        full_path = Path(schema_path)
                    
                    if not full_path.exists():
                        result["errors"].append(f"Schema path not found: {schema_path}")
                        result["valid"] = False
    
    # M10.7: Validate limits section if present
    if "limits" in manifest:
        limits = manifest["limits"]
        if not isinstance(limits, dict):
            result["errors"].append("limits must be an object/dict")
            result["valid"] = False
        else:
            # Validate individual limit fields
            valid_limit_fields = {
                "preview_per_min": "integer > 0",
                "exec_per_min": "integer > 0", 
                "daily_exec_budget": "integer > 0"
            }
            
            for field, description in valid_limit_fields.items():
                if field in limits:
                    try:
                        value = int(limits[field])
                        if value <= 0:
                            result["errors"].append(f"limits.{field} must be > 0, got {value}")
                            result["valid"] = False
                    except (ValueError, TypeError):
                        result["errors"].append(f"limits.{field} must be {description}, got {limits[field]}")
                        result["valid"] = False
    
    # Warnings for best practices
    if "metadata" not in manifest:
        result["warnings"].append("Missing metadata section (recommended)")
    
    if "environment" not in manifest:
        result["warnings"].append("Missing environment section (recommended)")
        
    if "limits" not in manifest:
        result["warnings"].append("Missing limits section (recommended for quota management)")
    
    # Check for executable permissions on main script
    if "sandbox" in manifest and "commands" in manifest["sandbox"]:
        commands = manifest["sandbox"]["commands"]
        if len(commands) > 1:
            # Second command is usually the script
            script_name = commands[1]
            script_path = helper_dir / script_name
            if script_path.exists() and not os.access(script_path, os.X_OK):
                result["warnings"].append(f"Script {script_name} is not executable")
    
    return result

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
        
        # M10.7: Agent Quotas & Cost Guardrails
        self.limits = manifest_data.get("limits", {})
        
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

def _is_valid_semver(version: str) -> bool:
    """
    M8.3: Validate semantic version format.
    
    Args:
        version: Version string to validate
        
    Returns:
        bool: True if valid semver, False otherwise
    """
    import re
    
    # Regex for semantic versioning that rejects leading zeros (major.minor.patch with optional pre-release and build)
    semver_pattern = r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$'
    
    return bool(re.match(semver_pattern, version))

def _is_valid_date(date_str: str) -> bool:
    """
    M8.3: Validate date format (YYYY-MM-DD).
    
    Args:
        date_str: Date string to validate
        
    Returns:
        bool: True if valid date format, False otherwise
    """
    import re
    from datetime import datetime
    
    # Check format first with regex
    date_pattern = r'^\d{4}-\d{2}-\d{2}$'
    if not re.match(date_pattern, date_str):
        return False
    
    # Try to parse the date to ensure it's valid
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False


def validate_agent_spec(spec: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    M10.0: Validate agent specification for agent generator.
    
    Validates JSON spec for creating new helpers with safe defaults.
    
    Args:
        spec: Agent specification dictionary
        
    Returns:
        tuple: (is_valid, error_list)
    """
    errors = []
    
    # Validate required fields
    required_fields = ["id", "description", "language"]
    for field in required_fields:
        if field not in spec:
            errors.append(f"Missing required field: {field}")
    
    # Validate helper ID format
    if "id" in spec:
        helper_id = spec["id"]
        if not isinstance(helper_id, str):
            errors.append("Field 'id' must be a string")
        else:
            # Validate ID format: ^[a-z0-9_]{3,40}$
            id_pattern = r'^[a-z0-9_]{3,40}$'
            if not re.match(id_pattern, helper_id):
                errors.append("Field 'id' must match pattern ^[a-z0-9_]{3,40}$ (lowercase letters, numbers, underscores, 3-40 chars)")
            
            # Check for path traversal attempts
            if ".." in helper_id or "/" in helper_id or "\\" in helper_id:
                errors.append("Field 'id' contains invalid path characters")
    
    # Validate description
    if "description" in spec:
        description = spec["description"]
        if not isinstance(description, str):
            errors.append("Field 'description' must be a string")
        elif not description.strip():
            errors.append("Field 'description' cannot be empty")
        elif len(description) > 500:
            errors.append("Field 'description' must be 500 characters or less")
    
    # Validate language
    if "language" in spec:
        language = spec["language"]
        valid_languages = {"python", "node"}
        if language not in valid_languages:
            errors.append(f"Field 'language' must be one of: {', '.join(valid_languages)}")
    
    # Validate capabilities (optional)
    if "capabilities" in spec:
        capabilities = spec["capabilities"]
        if not isinstance(capabilities, list):
            errors.append("Field 'capabilities' must be a list")
        else:
            valid_capabilities = {"network", "filesystem", "database", "compute"}
            for cap in capabilities:
                if not isinstance(cap, str):
                    errors.append("Capabilities must be strings")
                elif cap not in valid_capabilities:
                    errors.append(f"Invalid capability '{cap}'. Valid capabilities: {', '.join(valid_capabilities)}")
    
    # Validate can_execute (optional, must be false for safety)
    if "can_execute" in spec:
        can_execute = spec["can_execute"]
        if not isinstance(can_execute, bool):
            errors.append("Field 'can_execute' must be a boolean")
        elif can_execute is True:
            errors.append("Field 'can_execute' must be false for generated agents (safety requirement)")
    
    # Validate risk_level (optional)
    if "risk_level" in spec:
        risk_level = spec["risk_level"]
        valid_risk_levels = {"low", "medium", "high"}
        if risk_level not in valid_risk_levels:
            errors.append(f"Field 'risk_level' must be one of: {', '.join(valid_risk_levels)}")
    
    # Validate inputs schema (required)
    if "inputs" in spec:
        inputs_schema = spec["inputs"]
        if not isinstance(inputs_schema, dict):
            errors.append("Field 'inputs' must be a JSON Schema object")
        else:
            # Validate as JSON Schema
            try:
                jsonschema.Draft7Validator.check_schema(inputs_schema)
            except jsonschema.SchemaError as e:
                errors.append(f"Invalid inputs JSON Schema: {e.message}")
    else:
        errors.append("Missing required field: inputs")
    
    # Validate outputs schema (required)
    if "outputs" in spec:
        outputs_schema = spec["outputs"]
        if not isinstance(outputs_schema, dict):
            errors.append("Field 'outputs' must be a JSON Schema object")
        else:
            # Validate as JSON Schema
            try:
                jsonschema.Draft7Validator.check_schema(outputs_schema)
            except jsonschema.SchemaError as e:
                errors.append(f"Invalid outputs JSON Schema: {e.message}")
    else:
        errors.append("Missing required field: outputs")
    
    # Additional safety checks
    if "id" in spec and spec["id"].startswith("system_"):
        errors.append("Helper IDs cannot start with 'system_' (reserved prefix)")
    
    # Check for potentially dangerous helper names
    dangerous_names = {"admin", "root", "sudo", "exec", "eval", "shell", "cmd"}
    if "id" in spec and spec["id"] in dangerous_names:
        errors.append(f"Helper ID '{spec['id']}' is not allowed (security restriction)")
    
    return len(errors) == 0, errors


def infer_min_capabilities(spec: Dict[str, Any]) -> List[str]:
    """
    M10.1: Infer minimal capabilities from agent spec.
    
    Conservative inference that only adds capabilities when clearly required
    by the schema or description.
    
    Args:
        spec: Agent specification dictionary
        
    Returns:
        List of inferred capabilities
    """
    capabilities = set()
    
    # Analyze description for capability hints
    description = spec.get("description", "").lower()
    
    # Network capability indicators
    network_indicators = ["url", "http", "https", "api", "web", "website", "fetch", "download", "upload", "request", "endpoint", "service"]
    if any(indicator in description for indicator in network_indicators):
        capabilities.add("network")
    
    # Filesystem capability indicators
    filesystem_indicators = ["file", "document", "read", "write", "save", "load", "csv", "pdf", "json", "xml", "txt", "directory", "folder"]
    if any(indicator in description for indicator in filesystem_indicators):
        capabilities.add("filesystem")
    
    # Database capability indicators
    database_indicators = ["database", "sql", "query", "table", "record", "sqlite", "postgres", "mysql"]
    if any(indicator in description for indicator in database_indicators):
        capabilities.add("database")
    
    # Analyze input schema for capability requirements
    inputs_schema = spec.get("inputs", {})
    if isinstance(inputs_schema, dict):
        capabilities.update(_infer_capabilities_from_schema(inputs_schema, "input"))
    
    # Analyze output schema for capability requirements
    outputs_schema = spec.get("outputs", {})
    if isinstance(outputs_schema, dict):
        capabilities.update(_infer_capabilities_from_schema(outputs_schema, "output"))
    
    # Always return sorted list for consistency
    return sorted(list(capabilities))


def _infer_capabilities_from_schema(schema: Dict[str, Any], schema_type: str) -> set:
    """Infer capabilities from JSON schema structure."""
    capabilities = set()
    
    def analyze_properties(properties: Dict[str, Any]):
        """Recursively analyze schema properties."""
        for field_name, field_schema in properties.items():
            field_name_lower = field_name.lower()
            
            # Network indicators in field names
            if any(indicator in field_name_lower for indicator in ["url", "uri", "endpoint", "api", "web"]):
                capabilities.add("network")
            
            # Filesystem indicators in field names
            if any(indicator in field_name_lower for indicator in ["file", "path", "document", "csv", "json"]):
                capabilities.add("filesystem")
            
            # Database indicators in field names
            if any(indicator in field_name_lower for indicator in ["table", "query", "database", "sql"]):
                capabilities.add("database")
            
            # Analyze field format/type
            if isinstance(field_schema, dict):
                field_format = field_schema.get("format", "")
                field_type = field_schema.get("type", "")
                
                # URI format implies network capability
                if field_format in ["uri", "url", "hostname", "ipv4", "ipv6"]:
                    capabilities.add("network")
                
                # File path patterns
                if field_format in ["file-path", "directory-path"] or "path" in field_name_lower:
                    capabilities.add("filesystem")
                
                # Recursively analyze nested objects
                if field_type == "object" and "properties" in field_schema:
                    analyze_properties(field_schema["properties"])
                
                # Analyze array items
                if field_type == "array" and "items" in field_schema:
                    items_schema = field_schema["items"]
                    if isinstance(items_schema, dict) and "properties" in items_schema:
                        analyze_properties(items_schema["properties"])
    
    # Analyze top-level properties
    if "properties" in schema:
        analyze_properties(schema["properties"])
    
    return capabilities


def validate_lifecycle_state(lifecycle: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    M10.2: Validate helper lifecycle configuration.
    
    Args:
        lifecycle: Lifecycle configuration dictionary
        
    Returns:
        Tuple of (is_valid, errors)
    """
    errors = []
    
    if not isinstance(lifecycle, dict):
        errors.append("Lifecycle must be a dictionary")
        return False, errors
    
    # Validate state
    state = lifecycle.get("state")
    valid_states = {"draft", "trusted", "deprecated", "retired"}
    
    if not state:
        errors.append("Lifecycle state is required")
    elif state not in valid_states:
        errors.append(f"Invalid lifecycle state '{state}'. Must be one of: {', '.join(valid_states)}")
    
    # Validate since date
    since = lifecycle.get("since")
    if not since:
        errors.append("Lifecycle since date is required")
    else:
        # Validate ISO date format (YYYY-MM-DD)
        import re
        from datetime import datetime
        
        iso_date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
        if not iso_date_pattern.match(since):
            errors.append(f"Lifecycle since date '{since}' must be in ISO format (YYYY-MM-DD)")
        else:
            try:
                datetime.strptime(since, '%Y-%m-%d')
            except ValueError:
                errors.append(f"Lifecycle since date '{since}' is not a valid date")
    
    # Validate notes (optional but if present, must be string)
    notes = lifecycle.get("notes")
    if notes is not None and not isinstance(notes, str):
        errors.append("Lifecycle notes must be a string")
    
    return len(errors) == 0, errors


def determine_default_lifecycle_state(helper_spec: Dict[str, Any]) -> str:
    """
    M10.2: Determine default lifecycle state for helpers.
    
    Args:
        helper_spec: Helper specification
        
    Returns:
        Default lifecycle state ("draft" for generated, "trusted" for core/manual)
    """
    # Check for generator header indicating AI-generated helper
    if helper_spec.get("generator") or helper_spec.get("generated_by"):
        return "draft"
    
    # Check if this is from agent creation endpoints
    if helper_spec.get("created_via") == "agent_suggestion":
        return "draft"
    
    # Default to trusted for core/manual helpers
    return "trusted"


def get_helper_lifecycle(helper_manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    M10.2: Get helper lifecycle information with defaults.
    
    Args:
        helper_manifest: Loaded helper manifest
        
    Returns:
        Lifecycle information with defaults applied
    """
    from datetime import datetime
    
    lifecycle = helper_manifest.get("lifecycle", {})
    
    # Apply defaults if lifecycle is missing or incomplete
    default_state = determine_default_lifecycle_state(helper_manifest)
    
    return {
        "state": lifecycle.get("state", default_state),
        "since": lifecycle.get("since", datetime.now().strftime('%Y-%m-%d')),
        "notes": lifecycle.get("notes", f"Default {default_state} state")
    }
