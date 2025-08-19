"""
TinyIntent Helpers SDK - M4: Helpers Framework v1

Provides helper manifest loading, schema validation, and sandbox constraints.
Manages the lifecycle of sandboxed helpers for action execution.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import yaml
import jsonschema
from datetime import datetime

# Import resource limits (graceful fallback for non-Unix systems)
try:
    import resource
    RESOURCE_LIMITS_AVAILABLE = True
except ImportError:
    RESOURCE_LIMITS_AVAILABLE = False

# Load environment variables from .env file if it exists
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value.strip('"').strip("'")

# Load .env file on module import
load_env_file()


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
    
    # Warnings for best practices
    if "metadata" not in manifest:
        result["warnings"].append("Missing metadata section (recommended)")
    
    if "environment" not in manifest:
        result["warnings"].append("Missing environment section (recommended)")
    
    # M8.3: Validate version metadata if present
    if "version" in manifest:
        version = manifest["version"]
        if not _is_valid_semver(version):
            result["errors"].append(f"Invalid version format: {version} (must be valid semantic version)")
            result["valid"] = False
    
    if "added" in manifest:
        added_date = manifest["added"]
        if not _is_valid_date(added_date):
            result["errors"].append(f"Invalid added date format: {added_date} (must be YYYY-MM-DD)")
            result["valid"] = False
    
    if "updated" in manifest:
        updated_date = manifest["updated"]
        if not _is_valid_date(updated_date):
            result["errors"].append(f"Invalid updated date format: {updated_date} (must be YYYY-MM-DD)")
            result["valid"] = False
    
    # M8.3: Date consistency validation
    if "added" in manifest and "updated" in manifest:
        try:
            from datetime import datetime
            added_date = datetime.strptime(manifest["added"], '%Y-%m-%d')
            updated_date = datetime.strptime(manifest["updated"], '%Y-%m-%d')
            if updated_date < added_date:
                result["errors"].append(f"Updated date ({manifest['updated']}) cannot be before added date ({manifest['added']})")
                result["valid"] = False
        except ValueError:
            pass  # Date format errors already caught above
    
    # M8.3: Additional lifecycle warnings
    if "version" not in manifest:
        result["warnings"].append("Missing version field (recommended for tracking)")
    
    if "maintainer" not in manifest:
        result["warnings"].append("Missing maintainer field (recommended for support)")
    
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


def sanitize_env(env_dict: Dict[str, str]) -> Dict[str, str]:
    """
    Sanitize environment dictionary by redacting sensitive keys.
    
    This function prevents secrets from being exposed in logs, errors, or responses
    by replacing values of sensitive environment variables with "****".
    
    Args:
        env_dict: Dictionary of environment variables
        
    Returns:
        Dictionary with sensitive values redacted
    """
    if not isinstance(env_dict, dict):
        return env_dict
    
    # Define sensitive key patterns (case-insensitive)
    sensitive_patterns = [
        r'.*_key$',          # *_KEY
        r'.*_secret$',       # *_SECRET  
        r'.*password.*',     # *PASSWORD*
        r'.*token.*',        # *TOKEN*
        r'.*auth.*',         # *AUTH*
        r'.*credential.*',   # *CREDENTIAL*
        r'.*passphrase.*',   # *PASSPHRASE*
        r'.*private.*',      # *PRIVATE*
        r'.*cert.*',         # *CERT*
        r'.*api_key.*',      # *API_KEY*
        r'.*secret_key.*',   # *SECRET_KEY*
        r'.*access_key.*',   # *ACCESS_KEY*
    ]
    
    # Compile patterns for efficiency
    compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in sensitive_patterns]
    
    sanitized = {}
    for key, value in env_dict.items():
        # Check if key matches any sensitive pattern
        is_sensitive = any(pattern.match(key) for pattern in compiled_patterns)
        
        if is_sensitive:
            sanitized[key] = "****"
        else:
            sanitized[key] = value
    
    return sanitized

# Import audit logger (M6.2) - with fallback for standalone helper usage
try:
    import sys
    bridge_path = Path(__file__).parent.parent / "bridge"
    if str(bridge_path) not in sys.path:
        sys.path.append(str(bridge_path))
    from logs.rotate import get_audit_logger
    AUDIT_LOGGER_AVAILABLE = True
except ImportError:
    AUDIT_LOGGER_AVAILABLE = False
    get_audit_logger = None

# Import centralized sanitization
try:
    from sanitize import sanitize_dict, sanitize_text, sanitize_env
    CENTRALIZED_SANITIZATION = True
except ImportError:
    CENTRALIZED_SANITIZATION = False


class SandboxViolationError(Exception):
    """Exception raised when helper execution violates sandbox limits."""
    
    def __init__(self, message: str, error_code: str, details: Dict[str, Any] = None):
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


class CapabilityViolationError(Exception):
    """Exception raised when helper execution violates capability restrictions."""
    
    def __init__(self, message: str, capability: str, operation: str, details: Dict[str, Any] = None):
        super().__init__(message)
        self.error_code = "CAPABILITY_VIOLATION"
        self.capability = capability
        self.operation = operation
        self.details = details or {}


class HelperRateLimitError(Exception):
    """Exception raised when helper execution rate limit is exceeded."""
    
    def __init__(self, message: str, helper_id: str, current_count: int, limit: int, window_seconds: int):
        super().__init__(message)
        self.error_code = "HELPER_RATE_LIMIT"
        self.helper_id = helper_id
        self.current_count = current_count
        self.limit = limit
        self.window_seconds = window_seconds


class HelperRateLimiter:
    """Manages rate limiting for helper executions."""
    
    def __init__(self, default_limit: int = 10, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        
        # Thread-safe access to counters
        import threading
        self.lock = threading.Lock()
        
        # Helper execution tracking: {helper_id: [(timestamp, count), ...]}
        self.helper_executions: Dict[str, List[tuple]] = {}
    
    def check_helper_rate_limit(self, helper_id: str, limit: Optional[int] = None) -> bool:
        """
        Check if helper execution should be rate limited.
        
        Args:
            helper_id: ID of the helper
            limit: Custom limit for this helper (uses default if None)
            
        Returns:
            bool: True if execution is allowed, False if rate limited
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        effective_limit = limit if limit is not None else self.default_limit
        
        with self.lock:
            # Initialize tracking for helper if not exists
            if helper_id not in self.helper_executions:
                self.helper_executions[helper_id] = []
            
            # Clean up expired entries for this helper
            self.helper_executions[helper_id] = [
                entry for entry in self.helper_executions[helper_id]
                if entry[0] > cutoff_time
            ]
            
            # Count current executions in window
            current_count = sum(
                count for timestamp, count in self.helper_executions[helper_id]
                if timestamp > cutoff_time
            )
            
            # Check if limit exceeded
            if current_count >= effective_limit:
                raise HelperRateLimitError(
                    f"Helper {helper_id} rate limit exceeded: {current_count}/{effective_limit} executions in {self.window_seconds}s",
                    helper_id=helper_id,
                    current_count=current_count,
                    limit=effective_limit,
                    window_seconds=self.window_seconds
                )
            
            # Add this execution to tracking
            self.helper_executions[helper_id].append((current_time, 1))
            
            return True
    
    def get_helper_stats(self, helper_id: str) -> Dict[str, Any]:
        """Get current rate limiting stats for a specific helper."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            if helper_id not in self.helper_executions:
                return {
                    "helper_id": helper_id,
                    "current_count": 0,
                    "limit": self.default_limit,
                    "window_seconds": self.window_seconds,
                    "remaining": self.default_limit
                }
            
            # Count current executions
            current_count = sum(
                count for timestamp, count in self.helper_executions[helper_id]
                if timestamp > cutoff_time
            )
            
            return {
                "helper_id": helper_id,
                "current_count": current_count,
                "limit": self.default_limit,
                "window_seconds": self.window_seconds,
                "remaining": max(0, self.default_limit - current_count)
            }
    
    def get_all_stats(self) -> Dict[str, Any]:
        """Get rate limiting stats for all helpers."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            helper_stats = {}
            total_executions = 0
            
            for helper_id in self.helper_executions:
                current_count = sum(
                    count for timestamp, count in self.helper_executions[helper_id]
                    if timestamp > cutoff_time
                )
                if current_count > 0:
                    helper_stats[helper_id] = {
                        "current_count": current_count,
                        "limit": self.default_limit,
                        "remaining": max(0, self.default_limit - current_count)
                    }
                    total_executions += current_count
            
            return {
                "default_limit": self.default_limit,
                "window_seconds": self.window_seconds,
                "total_executions": total_executions,
                "active_helpers": len(helper_stats),
                "helper_stats": helper_stats
            }


# Global helper rate limiter instance
helper_rate_limiter = HelperRateLimiter(
    default_limit=int(os.getenv("HELPER_RATE_LIMIT", "10")),
    window_seconds=int(os.getenv("HELPER_RATE_LIMIT_WINDOW", "60"))
)


class HelperSandbox:
    """Enhanced sandbox for helper execution with resource limits and capability isolation."""
    
    def __init__(self, helper_id: str, audit_log_path: Path, capabilities: List[str] = None):
        self.helper_id = helper_id
        self.audit_log_path = audit_log_path
        self.capabilities = capabilities or []  # M6.5: Helper capabilities
        
        # Default sandbox limits
        self.max_cpu_time = 10  # seconds
        self.max_memory_mb = 256  # MB
        self.max_execution_time = 15  # seconds (wall clock time)
        self.max_output_size = 1024 * 1024  # 1MB
        
    def set_limits(self, cpu_time: int = None, memory_mb: int = None, 
                   execution_time: int = None, output_size: int = None):
        """Set sandbox resource limits."""
        if cpu_time is not None:
            self.max_cpu_time = cpu_time
        if memory_mb is not None:
            self.max_memory_mb = memory_mb
        if execution_time is not None:
            self.max_execution_time = execution_time
        if output_size is not None:
            self.max_output_size = output_size
    
    def _enforce_capability_restrictions(self, env: Dict[str, str]) -> Dict[str, str]:
        """
        Enforce capability restrictions on environment and prepare restrictive environment.
        
        Args:
            env: Original environment dictionary
            
        Returns:
            Modified environment dictionary with capability restrictions applied
        """
        restricted_env = env.copy()
        
        # Network capability enforcement
        if "network" not in self.capabilities:
            # Remove network-related environment variables
            network_env_vars = [
                'http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY',
                'ftp_proxy', 'FTP_PROXY', 'no_proxy', 'NO_PROXY',
                'all_proxy', 'ALL_PROXY', 'socks_proxy', 'SOCKS_PROXY'
            ]
            for var in network_env_vars:
                restricted_env.pop(var, None)
            
            # Add environment flag to indicate network restrictions
            restricted_env['TINYINTENT_NETWORK_DISABLED'] = '1'
        
        # Filesystem capability enforcement
        if "filesystem" not in self.capabilities:
            # Add environment flag to indicate filesystem restrictions
            restricted_env['TINYINTENT_FILESYSTEM_RESTRICTED'] = '1'
            # Set a restricted temporary directory
            import tempfile
            restricted_temp = tempfile.mkdtemp(prefix=f"helper_{self.helper_id}_")
            restricted_env['TMPDIR'] = restricted_temp
            restricted_env['TEMP'] = restricted_temp
            restricted_env['TMP'] = restricted_temp
        
        return restricted_env
    
    def _check_capability_violation(self, operation: str, capability: str) -> None:
        """
        Check if an operation violates capability restrictions.
        
        Args:
            operation: Description of the operation being attempted
            capability: Required capability for the operation
            
        Raises:
            CapabilityViolationError: If capability not granted
        """
        if capability not in self.capabilities:
            raise CapabilityViolationError(
                f"Helper {self.helper_id} attempted {operation} without {capability} capability",
                capability=capability,
                operation=operation,
                details={
                    "helper_id": self.helper_id,
                    "granted_capabilities": self.capabilities,
                    "required_capability": capability
                }
            )
    
    def _create_preexec_fn(self):
        """Create preexec function to set resource limits on child process."""
        if not RESOURCE_LIMITS_AVAILABLE:
            return None
            
        def preexec():
            try:
                # Set CPU time limit
                resource.setrlimit(resource.RLIMIT_CPU, (self.max_cpu_time, self.max_cpu_time))
                
                # Set memory limit (virtual memory)
                max_memory_bytes = self.max_memory_mb * 1024 * 1024
                try:
                    resource.setrlimit(resource.RLIMIT_AS, (max_memory_bytes, max_memory_bytes))
                except (OSError, ValueError):
                    # Some systems don't support RLIMIT_AS or have different behavior
                    try:
                        # Try RSS limit instead
                        resource.setrlimit(resource.RLIMIT_RSS, (max_memory_bytes, max_memory_bytes))
                    except (OSError, ValueError):
                        # If neither works, just log and continue
                        pass
                
                # Set file size limit to prevent large outputs
                resource.setrlimit(resource.RLIMIT_FSIZE, (self.max_output_size, self.max_output_size))
                
                # Set process priority to lower value (nice)
                try:
                    os.nice(5)  # Lower priority
                except OSError:
                    pass  # Not critical if this fails
                    
            except Exception:
                # Don't fail the entire execution if limits can't be set
                # This ensures compatibility across different systems
                pass
        
        return preexec
    
    def execute(self, cmd: List[str], input_data: str, env: Dict[str, str], 
                cwd: Path) -> Dict[str, Any]:
        """
        Execute command in sandboxed environment with resource limits and capability isolation.
        
        Returns:
            dict: Execution result or structured error
        """
        # M6.5: Apply capability restrictions to environment
        restricted_env = self._enforce_capability_restrictions(env)
        
        preexec_fn = self._create_preexec_fn()
        process = None
        
        try:
            # Start the process with capability-restricted environment
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=restricted_env,  # Use restricted environment
                cwd=cwd,
                preexec_fn=preexec_fn
            )
            
            # Set wall clock timeout
            try:
                stdout, stderr = process.communicate(
                    input=input_data, 
                    timeout=self.max_execution_time
                )
            except subprocess.TimeoutExpired:
                # Kill the process
                process.kill()
                try:
                    stdout, stderr = process.communicate(timeout=1)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    process.terminate()
                    stdout, stderr = "", "Process forcibly terminated"
                
                error_details = {
                    "timeout_seconds": self.max_execution_time,
                    "helper_id": self.helper_id
                }
                self._log_sandbox_violation("TIMEOUT", f"Helper execution exceeded {self.max_execution_time}s timeout", error_details)
                
                raise SandboxViolationError(
                    f"Helper execution timed out after {self.max_execution_time}s",
                    "SANDBOX_TIMEOUT",
                    error_details
                )
            
            # Check exit code for resource limit violations
            if process.returncode != 0:
                # Check for specific resource limit signals
                if process.returncode == -signal.SIGXCPU:
                    # CPU time limit exceeded
                    error_details = {
                        "cpu_limit_seconds": self.max_cpu_time,
                        "helper_id": self.helper_id,
                        "stderr": stderr
                    }
                    self._log_sandbox_violation("CPU_LIMIT", f"Helper exceeded CPU time limit of {self.max_cpu_time}s", error_details)
                    
                    raise SandboxViolationError(
                        f"Helper exceeded CPU time limit of {self.max_cpu_time}s",
                        "SANDBOX_CPU_LIMIT",
                        error_details
                    )
                
                elif process.returncode == -signal.SIGKILL or "killed" in stderr.lower():
                    # Likely memory limit exceeded (OOM killer)
                    error_details = {
                        "memory_limit_mb": self.max_memory_mb,
                        "helper_id": self.helper_id,
                        "stderr": stderr
                    }
                    self._log_sandbox_violation("MEMORY_LIMIT", f"Helper likely exceeded memory limit of {self.max_memory_mb}MB", error_details)
                    
                    raise SandboxViolationError(
                        f"Helper exceeded memory limit of {self.max_memory_mb}MB",
                        "SANDBOX_MEMORY_LIMIT", 
                        error_details
                    )
                
                # Regular execution failure
                raise RuntimeError(f"Helper execution failed: {stderr}")
            
            # Check output size
            if len(stdout) > self.max_output_size:
                error_details = {
                    "output_size": len(stdout),
                    "max_output_size": self.max_output_size,
                    "helper_id": self.helper_id
                }
                self._log_sandbox_violation("OUTPUT_SIZE", f"Helper output exceeded limit of {self.max_output_size} bytes", error_details)
                
                raise SandboxViolationError(
                    f"Helper output exceeded size limit of {self.max_output_size} bytes",
                    "SANDBOX_OUTPUT_SIZE",
                    error_details
                )
            
            # Parse and return result
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                raise ValueError(f"Helper returned invalid JSON: {stdout}")
                
        except SandboxViolationError:
            # Re-raise sandbox violations as-is
            raise
        except Exception as e:
            # Handle other execution errors
            if process and process.poll() is None:
                process.kill()
            raise e
    
    def _log_sandbox_violation(self, violation_type: str, message: str, details: Dict[str, Any]):
        """Log sandbox violation to audit log with integrity chaining."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        audit_entry = {
            "ts": timestamp,
            "action": "sandbox_violation",
            "violation_type": violation_type,
            "helper_id": self.helper_id,
            "message": message,
            "details": details,
            "success": False
        }
        
        try:
            if AUDIT_LOGGER_AVAILABLE and get_audit_logger:
                # Use integrity audit logger if available
                get_audit_logger().log_entry(audit_entry)
            else:
                # Fallback to direct file writing for standalone usage
                with open(self.audit_log_path, 'a') as f:
                    f.write(json.dumps(audit_entry) + '\n')
        except Exception:
            # Don't fail the entire operation if audit logging fails
            pass


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
        
        # Validation state
        self.is_valid = True
        self.validation_errors = []
        self.env_validation_passed = True
        self.missing_envs = []
        
        # Perform validation
        self._validate_environment()
        self._validate_enabled()
        self._validate_version_metadata()
    
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
            "risk_level": self.risk_level
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
        if CENTRALIZED_SANITIZATION:
            current_env = sanitize_env(dict(os.environ))
        else:
            current_env = sanitize_env(dict(os.environ))  # Use local function
        
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


class HelperExecutor:
    """Executes helpers in sandboxed environments."""
    
    def __init__(self, registry: HelperRegistry):
        self.registry = registry
        self.audit_log = Path(__file__).parent.parent / "bridge" / "logs" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
    
    def preview(self, helper_id: str, input_data: Dict[str, Any], 
                session_id: str = None) -> Dict[str, Any]:
        """Execute helper in preview mode."""
        # Check if helper is valid in registry
        if not self.registry.is_helper_valid(helper_id):
            validation_errors = self.registry.get_helper_validation_errors(helper_id)
            raise ValueError(f"Helper {helper_id} failed validation: {'; '.join(validation_errors)}")
        
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
    
    def execute(self, helper_id: str, input_data: Dict[str, Any], 
                session_id: str = None, token_id: str = None, 
                idempotency_key: str = None) -> Dict[str, Any]:
        """Execute helper in execution mode."""
        # Check if helper is valid in registry
        if not self.registry.is_helper_valid(helper_id):
            validation_errors = self.registry.get_helper_validation_errors(helper_id)
            raise ValueError(f"Helper {helper_id} failed validation: {'; '.join(validation_errors)}")
        
        helper = self.registry.get_helper(helper_id)
        if not helper:
            raise ValueError(f"Helper not found: {helper_id}")
        
        if not helper.can_execute():
            raise ValueError(f"Helper {helper_id} does not support execution mode")
        
        # Validate input
        if not helper.validate_input(input_data):
            raise ValueError(f"Input validation failed for helper {helper_id}")
        
        # Log audit entry
        self._log_audit("execute", helper_id, input_data, session_id, 
                       token_id=token_id, idempotency_key=idempotency_key)
        
        # Execute helper in execution mode
        try:
            result = self._execute_helper(helper, input_data, mode="execute")
            
            # Validate output against schema
            if not helper.validate_output(result):
                self._log_audit("execute_error", helper_id, input_data, session_id, 
                               token_id=token_id, idempotency_key=idempotency_key,
                               error="Output schema validation failed")
                raise ValueError("Output schema validation failed")
            
            return {
                "status": "success",
                "action": "execute",
                "helper_id": helper_id,
                "result": result
            }
            
        except Exception as e:
            self._log_audit("execute_error", helper_id, input_data, session_id, 
                           token_id=token_id, idempotency_key=idempotency_key,
                           error=str(e))
            raise
    
    def _execute_helper(self, helper: HelperManifest, input_data: Dict[str, Any], 
                       mode: str = "preview") -> Dict[str, Any]:
        """Execute helper subprocess with enhanced sandbox constraints."""
        
        # Prepare environment
        env = os.environ.copy()
        
        # Ensure exchange credentials are loaded for helpers that need them
        exchange_vars = ["EXCHANGE_API_KEY", "EXCHANGE_SECRET", "EXCHANGE_PASSPHRASE"]
        required_env = helper.environment.get("required", [])
        
        # Check if any exchange vars are required
        needs_exchange = any(var in required_env for var in exchange_vars)
        if needs_exchange:
            # Reload .env file to get latest credentials
            load_env_file()
            # Update env dict with current environment
            env = os.environ.copy()
        
        # Check for missing required environment variables
        missing_vars = []
        for env_var in required_env:
            if env_var not in env:
                missing_vars.append(env_var)
        
        if missing_vars:
            # For execute mode, raise with missing_vars info for 409 error
            error = ValueError(f"Required environment variable(s) missing: {', '.join(missing_vars)}")
            error.missing_vars = missing_vars
            raise error
        
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
        
        # M6.6: Check helper rate limit (only for execute mode)
        if mode == "execute":
            try:
                helper_rate_limiter.check_helper_rate_limit(helper.helper_id)
            except HelperRateLimitError as e:
                self._log_audit("rate_limit_exceeded", helper.helper_id, input_data, error=str(e))
                raise e
        
        # M6.5: Get capabilities from registry for capability isolation
        registry_entry = self.registry.get_registry_entry(helper.helper_id)
        capabilities = registry_entry.capabilities if registry_entry else []
        
        # Create enhanced sandbox with capability restrictions
        sandbox = HelperSandbox(helper.helper_id, self.audit_log, capabilities)
        
        # Configure sandbox limits from helper manifest and mode
        timeout = helper.get_timeout(mode)
        cpu_limit = helper.sandbox.get("cpu", {}).get("max_ms", 10000) // 1000  # Convert ms to seconds
        memory_limit = helper.sandbox.get("mem", {}).get("max_mb", 256)
        
        # Apply stricter limits for execute mode
        if mode == "execute":
            # Execute mode gets slightly more time but same resource limits
            sandbox.set_limits(
                cpu_time=max(cpu_limit, 15),  # At least 15s for execute
                memory_mb=memory_limit,
                execution_time=max(timeout, 20),  # Wall clock time
                output_size=1024 * 1024  # 1MB max output
            )
        else:
            # Preview mode gets default limits
            sandbox.set_limits(
                cpu_time=cpu_limit,
                memory_mb=memory_limit,
                execution_time=timeout,
                output_size=512 * 1024  # 512KB max output for preview
            )
        
        try:
            # Execute in sandbox
            return sandbox.execute(cmd, input_json, env, helper.helper_dir)
            
        except CapabilityViolationError as e:
            # M6.5: Handle capability violations
            self._log_audit(
                "capability_violation",
                helper.helper_id,
                input_data,
                error=f"{e.error_code}: {str(e)}"
            )
            
            # Re-raise as CapabilityViolationError for HTTP 403 handling
            raise e
            
        except SandboxViolationError as e:
            # Convert sandbox violations to structured errors
            self._log_audit(
                "sandbox_violation", 
                helper.helper_id, 
                input_data, 
                error=f"{e.error_code}: {str(e)}"
            )
            
            # Create structured error response
            error_response = {
                "error": "sandbox_violation",
                "error_code": e.error_code,
                "message": str(e),
                "details": e.details
            }
            
            # Re-raise as RuntimeError with structured info for HTTP 500
            raise RuntimeError(f"Sandbox violation: {e.error_code} - {str(e)}")
            
        except Exception as e:
            # Handle other execution errors
            self._log_audit(
                "execution_error",
                helper.helper_id,
                input_data,
                error=str(e)
            )
            raise
    
    def _generate_approval_token(self) -> str:
        """Generate approval token for two-step execution."""
        return str(uuid.uuid4()).replace("-", "")[:16]
    
    def _sanitize_input_data(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize input data by redacting sensitive fields.
        
        Args:
            input_data: Helper input data
            
        Returns:
            Sanitized input data with sensitive values redacted
        """
        if CENTRALIZED_SANITIZATION:
            return sanitize_dict(input_data)
        
        # Fallback to legacy local sanitization
        if not isinstance(input_data, dict):
            return input_data
        
        sanitized = {}
        for key, value in input_data.items():
            # Check if the key or value contains sensitive information
            key_lower = key.lower()
            
            # Sensitive key patterns
            sensitive_key_patterns = [
                'key', 'secret', 'password', 'token', 'auth', 'credential', 
                'passphrase', 'private', 'cert', 'api_key', 'access_key'
            ]
            
            is_sensitive_key = any(pattern in key_lower for pattern in sensitive_key_patterns)
            
            # Also check if value looks like a sensitive string (long alphanumeric, starts with certain prefixes)
            is_sensitive_value = False
            if isinstance(value, str) and len(value) > 10:
                # Check for common secret prefixes
                sensitive_prefixes = ['sk_', 'pk_', 'Bearer ', 'Basic ']
                is_sensitive_value = any(value.startswith(prefix) for prefix in sensitive_prefixes)
                # Also check for long alphanumeric strings that might be secrets (more conservative)
                if len(value) > 30 and value.replace('-', '').replace('_', '').isalnum():
                    is_sensitive_value = True
            
            if is_sensitive_key or is_sensitive_value:
                sanitized[key] = "****"
            elif isinstance(value, dict):
                # Recursively sanitize nested dictionaries
                sanitized[key] = self._sanitize_input_data(value)
            elif isinstance(value, list):
                # Sanitize list items
                sanitized[key] = [
                    self._sanitize_input_data(item) if isinstance(item, dict) else item 
                    for item in value
                ]
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_error_message(self, error_msg: str) -> str:
        """
        Sanitize error messages by redacting sensitive information.
        
        Args:
            error_msg: Error message
            
        Returns:
            Sanitized error message
        """
        if CENTRALIZED_SANITIZATION:
            return sanitize_text(error_msg)
        
        # Fallback to legacy local sanitization
        if not isinstance(error_msg, str):
            return error_msg
        
        # Define patterns for sensitive information in error messages
        sensitive_patterns = [
            # Specific known secret prefixes
            (r'sk_[A-Za-z0-9_]+', '****'),   # Secret keys starting with sk_
            (r'pk_[A-Za-z0-9_]+', '****'),   # Public keys starting with pk_
            (r'Bearer [A-Za-z0-9_.-]+', 'Bearer ****'),  # Bearer tokens
            (r'Basic [A-Za-z0-9+/=]+', 'Basic ****'),    # Basic auth
            (r'\bapi_[A-Za-z0-9_]{15,}\b', 'api_****'),          # API keys (long ones)
            (r'\bsecret_[A-Za-z0-9_]{10,}\b', 'secret_****'),    # Secret keys (long ones)
            # Environment variable patterns
            (r'[A-Z_]+(?:KEY|SECRET|PASSWORD|TOKEN)=[A-Za-z0-9_.-]{15,}', 
             'REDACTED_ENV=****'),
            # JSON-like patterns and plaintext patterns
            (r'token["\s:=]+[A-Za-z0-9_.-]{15,}', 'token": "****"'),  # JSON tokens
            (r'key["\s:=]+[A-Za-z0-9_.-]{15,}', 'key": "****"'),      # JSON keys
            (r'password["\s:=]+[A-Za-z0-9_.-]{10,}', 'password": "****"'),  # JSON passwords
            (r'\bpassword:\s+[A-Za-z0-9_.-]{10,}', 'password: ****'),  # Plain text passwords
            # Very long alphanumeric strings (40+ chars)
            (r'\b[A-Za-z0-9_]{40,}\b', '****'),
        ]
        
        sanitized_msg = error_msg
        for pattern, replacement in sensitive_patterns:
            sanitized_msg = re.sub(pattern, replacement, sanitized_msg, flags=re.IGNORECASE)
        
        return sanitized_msg
    
    def _log_audit(self, action: str, helper_id: str, input_data: Dict[str, Any], 
                   session_id: str = None, error: str = None, token_id: str = None,
                   idempotency_key: str = None):
        """Log audit entry for helper execution with integrity chaining."""
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Sanitize input_data to remove potential sensitive information
        sanitized_input = self._sanitize_input_data(input_data)
        
        audit_entry = {
            "ts": timestamp,
            "session_id": session_id or "unknown",
            "action": action,
            "helper_id": helper_id,
            "input_hash": hash(json.dumps(sanitized_input, sort_keys=True)),
            "sanitized_input": sanitized_input,
            "success": error is None,
            "error": self._sanitize_error_message(error) if error else None
        }
        
        if token_id:
            audit_entry["token_id"] = token_id
        if idempotency_key:
            audit_entry["idempotency_key"] = idempotency_key
        
        try:
            if AUDIT_LOGGER_AVAILABLE and get_audit_logger:
                # Use integrity audit logger if available
                get_audit_logger().log_entry(audit_entry)
            else:
                # Fallback to direct file writing for standalone usage
                with open(self.audit_log, 'a') as f:
                    f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write audit log: {e}")


# Global instances
helper_registry = HelperRegistry()
helper_executor = HelperExecutor(helper_registry)