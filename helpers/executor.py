
"""
TinyIntent Helper Executor

Handles the secure execution of helpers, including preview and execute modes.
It integrates with the sandbox for resource isolation and the registry for validation.
Also manages rate limiting for helper executions.
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

# Add project root to path for imports
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import bridge modules with fallbacks
try:
    from bridge.logs.audit import get_audit_logger
    from bridge.logs.sanitize import sanitize_dict, sanitize_text
    from bridge.sandbox_security import sandbox_security, SandboxSecurityViolation
    from bridge.secret_manager import get_secret_manager, SecretViolation
except ImportError:
    # Fallbacks for development
    def get_audit_logger():
        return None
    
    def sanitize_dict(d):
        return d
    
    def sanitize_text(t):
        return t
    
    class MockSecurityViolation(Exception):
        def __init__(self, message, violation_type="UNKNOWN", details=None):
            super().__init__(message)
            self.violation_type = violation_type
            self.details = details or {}
    
    SandboxSecurityViolation = MockSecurityViolation
    
    class MockSecretViolation(Exception):
        def __init__(self, message, secret_name="", helper_id="", required_scope=""):
            super().__init__(message)
            self.secret_name = secret_name
            self.helper_id = helper_id
            self.required_scope = required_scope
    
    SecretViolation = MockSecretViolation
    
    class MockSandboxSecurity:
        def validate_helper_input(self, data):
            return data
        def create_security_profile(self, helper_id, capabilities):
            return {"helper_id": helper_id, "capabilities": capabilities}
        def validate_command(self, cmd):
            pass
        def sanitize_environment(self, env, workspace):
            return env
    
    sandbox_security = MockSandboxSecurity()
    
    class MockSecretManager:
        def create_scoped_environment(self, helper_id, trust_level, env):
            return env
    
    def get_secret_manager():
        return MockSecretManager()

try:
    from tinyintent.config import settings
except ImportError:
    # Fallback settings
    class MockSettings:
        pass
    settings = MockSettings()
from .manifest import HelperManifest
from .registry import HelperRegistry
from .sandbox import (
    CapabilityViolationError,
    HelperSandbox,
    SandboxViolationError,
)

logger = structlog.get_logger()


class HelperExecutionError(Exception):
    """Base exception for helper execution errors."""
    pass


class HelperValidationError(HelperExecutionError):
    """Helper validation failed."""
    pass


class HelperRateLimitError(HelperExecutionError):
    """Exception raised when helper execution rate limit is exceeded."""
    
    def __init__(self, message: str, helper_id: str, current_count: int, limit: int, window_seconds: int):
        super().__init__(message)
        self.error_code = "HELPER_RATE_LIMIT"
        self.helper_id = helper_id
        self.current_count = current_count
        self.limit = limit
        self.window_seconds = window_seconds


class HelperTimeoutError(HelperExecutionError):
    """Helper execution timed out."""
    pass


class HelperEnvironmentError(HelperExecutionError):
    """Helper environment configuration error."""
    pass

class HelperRateLimiter:
    """Manages rate limiting for helper executions."""
    
    def __init__(self, default_limit: int = 10, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        
        # Thread-safe access to counters
        import threading
        self.lock = threading.Lock()
        
        # Helper execution tracking: {helper_id: [(timestamp, count), ...]}
        self.helper_executions: Dict[str, list[tuple]] = {}
    
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
    default_limit=settings.helpers.rate_limit,
    window_seconds=settings.helpers.rate_limit_window
)

class HelperExecutor:
    """Executes helpers in sandboxed environments."""
    
    def __init__(self, registry: HelperRegistry):
        self.registry = registry
        self.audit_log = Path(__file__).parent.parent / "bridge" / "logs" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
    
    def preview(self, helper_id: str, input_data: Dict[str, Any], 
                session_id: str = None, execution_mode: str = "preview") -> Dict[str, Any]:
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
        
        # M10.3: Shadow and canary runs must always be dry_run=True for safety
        is_staging_mode = execution_mode in ["shadow", "canary"]
        
        # Log audit entry with execution mode
        self._log_audit("preview" if not is_staging_mode else execution_mode, 
                       helper_id, input_data, session_id, 
                       execution_mode=execution_mode)
        
        # Execute helper in preview mode (always dry_run for staging)
        try:
            result = self._execute_helper(helper, input_data, mode="preview", 
                                        execution_mode=execution_mode)
            
            # Validate output
            if not helper.validate_output(result):
                raise ValueError(f"Output validation failed for helper {helper_id}")
            
            response = {
                "status": "success",
                "action": "preview" if not is_staging_mode else execution_mode,
                "helper_id": helper_id,
                "preview_json": result,
                "execution_mode": execution_mode
            }
            
            # Only add approval token for regular preview (not staging)
            if not is_staging_mode:
                response["approval_token"] = self._generate_approval_token()
            
            return response
            
        except Exception as e:
            self._log_audit(f"preview_error" if not is_staging_mode else f"{execution_mode}_error", 
                           helper_id, input_data, session_id, error=str(e),
                           execution_mode=execution_mode)
            raise
    
    def execute(self, helper_id: str, input_data: Dict[str, Any], 
                session_id: str = None, token_id: str = None, 
                idempotency_key: str = None) -> Dict[str, Any]:
        """Execute helper in execution mode."""
        # Check if helper is valid in registry
        if not self.registry.is_helper_valid(helper_id):
            validation_errors = self.registry.get_helper_validation_errors(helper_id)
            raise ValueError(f"Helper {helper_id} failed validation: {'; '.join(validation_errors)}")
        
        # M10.5: Check provenance before execution
        registry_entry = self.registry.get_registry_entry(helper_id)
        if registry_entry and not registry_entry.provenance_ok:
            # Create a special exception type for provenance errors
            error = ValueError(f"Provenance verification failed: {registry_entry.provenance_reason}")
            error.error_code = "PROVENANCE_INVALID"
            raise error
        
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
                       mode: str = "preview", execution_mode: str = "preview") -> Dict[str, Any]:
        """Execute helper subprocess with enhanced sandbox constraints."""
        
        # Enhanced security validation
        try:
            # Validate helper input for security threats
            sanitized_input = sandbox_security.validate_helper_input(input_data)
            
            # Get capabilities from registry for capability isolation
            registry_entry = self.registry.get_registry_entry(helper.helper_id)
            capabilities = registry_entry.capabilities if registry_entry else []
            
            # Create security profile for this execution
            security_profile = sandbox_security.create_security_profile(helper.helper_id, capabilities)
            
            # Log security profile creation
            self._log_audit(
                "security_profile_created", 
                helper.helper_id, 
                {"capabilities": capabilities},
                extra_data={"security_profile": security_profile}
            )
            
        except SandboxSecurityViolation as e:
            self._log_audit(
                "security_violation",
                helper.helper_id,
                input_data,
                error=f"Security validation failed: {e}",
                extra_data={"violation_type": e.violation_type, "details": e.details}
            )
            raise HelperExecutionError(f"Security validation failed: {e}")
        
        # Use sanitized input for execution
        input_data = sanitized_input
        
        # Prepare environment
        env = os.environ.copy()
        
        # Use secret manager for secure credential access
        secret_manager = get_secret_manager()
        required_env = helper.environment.get("required", [])
        
        # Get helper trust level from registry
        helper_trust_level = "draft"  # Default
        if registry_entry and hasattr(registry_entry, 'lifecycle'):
            helper_trust_level = registry_entry.lifecycle.get('state', 'draft')
        
        # Create scoped environment with secrets
        try:
            env = secret_manager.create_scoped_environment(
                helper.helper_id, 
                helper_trust_level, 
                env
            )
        except SecretViolation as e:
            self._log_audit(
                "secret_access_denied",
                helper.helper_id,
                input_data,
                error=f"Secret access denied: {e}",
                extra_data={"secret_name": e.secret_name, "required_scope": e.required_scope}
            )
            raise HelperExecutionError(f"Secret access denied: {e}")
        
        # Check for missing required environment variables (including secrets)
        missing_vars = []
        for env_var in required_env:
            # Check both regular env and scoped secrets
            scoped_secret_name = f"TINYINTENT_SECRET_{env_var.upper()}"
            if env_var not in env and scoped_secret_name not in env:
                missing_vars.append(env_var)
        
        if missing_vars:
            # Log missing variables for security audit
            self._log_audit(
                "missing_credentials",
                helper.helper_id,
                input_data,
                error=f"Required credentials missing: {', '.join(missing_vars)}",
                extra_data={"missing_vars": missing_vars, "helper_trust_level": helper_trust_level}
            )
            
            # For execute mode, raise with missing_vars info for 409 error
            error = ValueError(f"Required environment variable(s) missing: {', '.join(missing_vars)}")
            error.missing_vars = missing_vars
            raise error
        
        # Prepare command with enhanced security validation
        commands = helper.sandbox.get("commands", [])
        if not commands:
            raise ValueError(f"No commands defined for helper {helper.helper_id}")
        
        # Use first command as main executable
        cmd = [commands[0]]
        if len(commands) > 1:
            cmd.extend(commands[1:])
        
        # Enhanced command validation
        try:
            sandbox_security.validate_command(cmd)
        except SandboxSecurityViolation as e:
            self._log_audit(
                "command_security_violation",
                helper.helper_id,
                input_data,
                error=f"Command validation failed: {e}",
                extra_data={"command": cmd, "violation_type": e.violation_type}
            )
            raise HelperExecutionError(f"Command security validation failed: {e}")
        
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
        
        # M10.7: Configure hardened sandbox limits from helper manifest and mode
        timeout = helper.get_timeout(mode)
        cpu_limit = helper.sandbox.get("cpu", {}).get("max_ms", 5000) // 1000  # Convert ms to seconds (more restrictive)
        memory_limit = helper.sandbox.get("mem", {}).get("max_mb", 128)  # More restrictive default
        
        # M10.7: Enhanced sandbox limits with configurable timeout
        sandbox_timeout_ms = int(os.getenv('SANDBOX_TIMEOUT_MS', '3000'))
        execution_time = min(timeout, sandbox_timeout_ms // 1000)  # Use min of config and manifest
        
        # Apply stricter limits for execute mode
        if mode == "execute":
            # M10.7: Execute mode gets slightly more time but same resource limits
            sandbox.set_limits(
                cpu_time=min(cpu_limit + 2, 8),  # Cap at 8s max for execute
                memory_mb=min(memory_limit, 256),  # Cap at 256MB max
                execution_time=max(execution_time, 5),  # At least 5s for execute
                output_size=256 * 1024,  # 256KB max output (more restrictive)
                file_descriptors=32,  # Limit FDs for execute mode
                processes=2  # Limit processes for execute mode
            )
        else:
            # M10.7: Preview mode gets more restrictive limits
            sandbox.set_limits(
                cpu_time=min(cpu_limit, 3),  # Max 3s for preview
                memory_mb=min(memory_limit, 64),  # Max 64MB for preview
                execution_time=execution_time,
                output_size=128 * 1024,  # 128KB max output for preview
                file_descriptors=16,  # Even fewer FDs for preview
                processes=1  # Single process for preview
            )
        
        try:
            # Enhanced environment sanitization
            workspace_path = str(sandbox._create_temp_workspace())
            sanitized_env = sandbox_security.sanitize_environment(env, workspace_path)
            
            # Log environment sanitization
            self._log_audit(
                "environment_sanitized",
                helper.helper_id,
                input_data,
                extra_data={
                    "original_env_count": len(env),
                    "sanitized_env_count": len(sanitized_env),
                    "workspace_path": workspace_path
                }
            )
            
            # Execute in sandbox with sanitized environment
            return sandbox.execute(cmd, input_json, sanitized_env, helper.helper_dir)
            
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
    
    def _log_audit(self, action: str, helper_id: str, input_data: Dict[str, Any], 
                   session_id: str = None, error: str = None, token_id: str = None,
                   idempotency_key: str = None, execution_mode: str = None):
        """Log audit entry for helper execution with integrity chaining."""
        from datetime import datetime
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        # Sanitize input_data to remove potential sensitive information
        sanitized_input = sanitize_dict(input_data)
        
        audit_entry = {
            "ts": timestamp,
            "session_id": session_id or "unknown",
            "action": action,
            "helper_id": helper_id,
            "input_hash": hash(json.dumps(sanitized_input, sort_keys=True)),
            "sanitized_input": sanitized_input,
            "success": error is None,
            "error": sanitize_text(error) if error else None
        }
        
        if token_id:
            audit_entry["token_id"] = token_id
        if idempotency_key:
            audit_entry["idempotency_key"] = idempotency_key
        if execution_mode:
            audit_entry["execution_mode"] = execution_mode
        
        try:
            audit_logger = get_audit_logger()
            if audit_logger:
                # Use integrity audit logger if available
                audit_logger.log_entry(audit_entry)
            else:
                # Fallback to direct file writing for standalone usage
                with open(self.audit_log, 'a') as f:
                    f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            print(f"Warning: Failed to write audit log: {e}")
