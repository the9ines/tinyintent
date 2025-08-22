"""
Enhanced Sandbox Security Module

Provides additional security measures for helper sandbox environments
to prevent escape vectors and strengthen isolation.
"""

import os
import re
import json
import hashlib
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
import structlog

logger = structlog.get_logger()


class SandboxSecurityViolation(Exception):
    """Raised when a sandbox security violation is detected."""
    def __init__(self, message: str, violation_type: str, details: Dict[str, Any] = None):
        super().__init__(message)
        self.violation_type = violation_type
        self.details = details or {}


class SandboxSecurityEnforcer:
    """Enhanced security enforcement for helper sandbox environments."""
    
    def __init__(self):
        # Dangerous command patterns that should never be executed
        self.dangerous_commands = {
            # Shell escape attempts
            r';\s*bash', r';\s*sh', r'\|\s*bash', r'\|\s*sh',
            r'`[^`]*`', r'\$\([^)]*\)',  # Command substitution
            
            # File system manipulation
            r'rm\s+-rf\s+/', r'chmod\s+777', r'chown\s+root',
            r'mount\s+', r'umount\s+', r'sudo\s+',
            
            # Network operations
            r'wget\s+', r'curl\s+', r'nc\s+', r'netcat\s+',
            r'telnet\s+', r'ssh\s+', r'scp\s+', r'rsync\s+',
            
            # Process manipulation
            r'kill\s+-9', r'pkill\s+', r'killall\s+',
            r'ps\s+aux', r'top\s+', r'htop\s+',
            
            # System information
            r'uname\s+-a', r'id\s+', r'whoami\s+', r'passwd\s+',
            r'/etc/passwd', r'/etc/shadow', r'/proc/',
            
            # Compilation and execution
            r'gcc\s+', r'g\+\+\s+', r'make\s+', r'cmake\s+',
            r'python\s+-c', r'python3\s+-c', r'node\s+-e',
            
            # Package management
            r'apt\s+', r'yum\s+', r'pip\s+install', r'npm\s+install'
        }
        
        # Allowed file extensions for reading
        self.allowed_read_extensions = {
            '.txt', '.log', '.json', '.yaml', '.yml', '.csv',
            '.md', '.rst', '.html', '.xml', '.ini', '.conf',
            '.cfg', '.properties', '.env'
        }
        
        # Allowed file extensions for writing (very restricted)
        self.allowed_write_extensions = {
            '.tmp', '.log', '.out', '.json'
        }
        
        # Blocked environment variables that could be dangerous
        self.dangerous_env_vars = {
            'LD_PRELOAD', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH',
            'PATH', 'PYTHONPATH', 'NODE_PATH', 'CLASSPATH',
            'SHELL', 'EDITOR', 'BROWSER'
        }
    
    def validate_command(self, command: List[str]) -> None:
        """
        Validate that a command is safe to execute in sandbox.
        
        Args:
            command: Command array to validate
            
        Raises:
            SandboxSecurityViolation: If command is dangerous
        """
        if not command:
            raise SandboxSecurityViolation(
                "Empty command not allowed",
                "EMPTY_COMMAND"
            )
        
        # Join command for pattern matching
        full_command = ' '.join(command)
        
        # Check against dangerous patterns
        for pattern in self.dangerous_commands:
            if re.search(pattern, full_command, re.IGNORECASE):
                raise SandboxSecurityViolation(
                    f"Dangerous command pattern detected: {pattern}",
                    "DANGEROUS_COMMAND",
                    {"command": full_command, "pattern": pattern}
                )
        
        # Validate individual arguments
        for i, arg in enumerate(command):
            if self._is_dangerous_argument(arg):
                raise SandboxSecurityViolation(
                    f"Dangerous argument detected: {arg}",
                    "DANGEROUS_ARGUMENT",
                    {"command": full_command, "argument": arg, "position": i}
                )
    
    def validate_file_access(self, file_path: str, operation: str, workspace_path: str) -> None:
        """
        Validate file access operations.
        
        Args:
            file_path: Path to file being accessed
            operation: Type of operation (read, write, execute)
            workspace_path: Sandbox workspace path
            
        Raises:
            SandboxSecurityViolation: If file access is not allowed
        """
        try:
            path = Path(file_path).resolve()
        except (ValueError, OSError) as e:
            raise SandboxSecurityViolation(
                f"Invalid file path: {file_path}",
                "INVALID_PATH",
                {"path": file_path, "error": str(e)}
            )
        
        # Ensure path is within workspace or explicitly allowed directories
        workspace = Path(workspace_path).resolve()
        
        # Check if path is within workspace
        try:
            path.relative_to(workspace)
        except ValueError:
            # Path is outside workspace - check if it's in allowed system paths
            if not self._is_allowed_system_path(path, operation):
                raise SandboxSecurityViolation(
                    f"File access outside workspace not allowed: {path}",
                    "PATH_ESCAPE",
                    {"path": str(path), "workspace": str(workspace), "operation": operation}
                )
        
        # Validate file extension for operation
        if operation == "read" and path.suffix not in self.allowed_read_extensions:
            if not self._is_allowed_special_file(path):
                raise SandboxSecurityViolation(
                    f"Reading file with extension {path.suffix} not allowed",
                    "FORBIDDEN_EXTENSION",
                    {"path": str(path), "extension": path.suffix, "operation": operation}
                )
        
        elif operation == "write" and path.suffix not in self.allowed_write_extensions:
            raise SandboxSecurityViolation(
                f"Writing file with extension {path.suffix} not allowed",
                "FORBIDDEN_EXTENSION",
                {"path": str(path), "extension": path.suffix, "operation": operation}
            )
        
        elif operation == "execute":
            # Execute operations should be very restricted
            raise SandboxSecurityViolation(
                "File execution not allowed in sandbox",
                "EXECUTION_FORBIDDEN",
                {"path": str(path)}
            )
    
    def sanitize_environment(self, env: Dict[str, str], workspace_path: str) -> Dict[str, str]:
        """
        Sanitize environment variables for sandbox execution.
        
        Args:
            env: Original environment dictionary
            workspace_path: Sandbox workspace path
            
        Returns:
            Sanitized environment dictionary
        """
        sanitized_env = {}
        
        # Only allow safe environment variables
        safe_vars = {
            'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ', 'USER', 'LOGNAME',
            'TMPDIR', 'TEMP', 'TMP', 'HOME',
            # TinyIntent specific
            'TINYINTENT_WORKSPACE', 'TINYINTENT_NETWORK_DISABLED', 
            'TINYINTENT_FILESYSTEM_RESTRICTED'
        }
        
        for key, value in env.items():
            # Skip dangerous environment variables
            if key in self.dangerous_env_vars:
                logger.warning("Blocked dangerous environment variable", var=key)
                continue
            
            # Only allow safe variables or TinyIntent-specific ones
            if key in safe_vars or key.startswith('TINYINTENT_'):
                # Validate value
                if self._is_safe_env_value(value):
                    sanitized_env[key] = value
                else:
                    logger.warning("Blocked dangerous environment value", var=key, value=value[:50])
        
        # Ensure critical sandbox variables are set
        sanitized_env['TINYINTENT_WORKSPACE'] = workspace_path
        sanitized_env['HOME'] = workspace_path
        sanitized_env['TMPDIR'] = workspace_path
        sanitized_env['TEMP'] = workspace_path
        sanitized_env['TMP'] = workspace_path
        
        return sanitized_env
    
    def validate_helper_input(self, helper_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and sanitize helper input for security.
        
        Args:
            helper_input: Raw helper input
            
        Returns:
            Sanitized helper input
            
        Raises:
            SandboxSecurityViolation: If input contains dangerous content
        """
        if not isinstance(helper_input, dict):
            raise SandboxSecurityViolation(
                "Helper input must be a dictionary",
                "INVALID_INPUT_TYPE",
                {"type": type(helper_input).__name__}
            )
        
        sanitized_input = {}
        
        for key, value in helper_input.items():
            # Validate key
            if not self._is_safe_key(key):
                raise SandboxSecurityViolation(
                    f"Dangerous key in helper input: {key}",
                    "DANGEROUS_INPUT_KEY",
                    {"key": key}
                )
            
            # Validate and sanitize value
            sanitized_value = self._sanitize_input_value(value, key)
            sanitized_input[key] = sanitized_value
        
        return sanitized_input
    
    def create_security_profile(self, helper_id: str, capabilities: List[str]) -> Dict[str, Any]:
        """
        Create a security profile for a helper based on its capabilities.
        
        Args:
            helper_id: Helper identifier
            capabilities: List of granted capabilities
            
        Returns:
            Security profile dictionary
        """
        profile = {
            "helper_id": helper_id,
            "capabilities": capabilities,
            "restrictions": {
                "network_disabled": "network" not in capabilities,
                "filesystem_restricted": "filesystem" not in capabilities,
                "execution_forbidden": True,  # Always forbidden
                "max_file_size": 10 * 1024 * 1024,  # 10MB
                "allowed_protocols": [] if "network" not in capabilities else ["http", "https"],
                "blocked_domains": ["localhost", "127.0.0.1", "::1", "169.254.0.0/16"],  # Block local access
            },
            "monitoring": {
                "log_all_operations": True,
                "alert_on_violations": True,
                "track_resource_usage": True
            },
            "created_at": os.path.getmtime(__file__)
        }
        
        return profile
    
    def _is_dangerous_argument(self, arg: str) -> bool:
        """Check if a command argument is potentially dangerous."""
        dangerous_patterns = [
            r'^-{1,2}(rm|delete|force)$',  # Dangerous flags
            r'^\$\{.*\}$',  # Variable expansion
            r'^.*[;&|].*$',  # Command chaining
            r'^/etc/', r'^/proc/', r'^/sys/',  # System directories
            r'^/dev/', r'^/tmp/', r'^/var/',  # Potentially dangerous directories
            r'^\.\./.*',  # Parent directory traversal
        ]
        
        for pattern in dangerous_patterns:
            if re.match(pattern, arg, re.IGNORECASE):
                return True
        
        return False
    
    def _is_allowed_system_path(self, path: Path, operation: str) -> bool:
        """Check if a system path is allowed for the given operation."""
        # Very restrictive - only allow reading from specific system paths
        if operation == "read":
            allowed_system_dirs = {
                "/usr/share/zoneinfo/",  # Timezone data
                "/etc/localtime",  # Local time config
            }
            
            for allowed_dir in allowed_system_dirs:
                try:
                    path.relative_to(allowed_dir)
                    return True
                except ValueError:
                    continue
        
        # No system paths allowed for write or execute
        return False
    
    def _is_allowed_special_file(self, path: Path) -> bool:
        """Check if a file without typical extension is allowed."""
        # Allow specific system files for reading
        allowed_special_files = {
            "/etc/localtime",
            "/dev/null",
            "/dev/zero",
        }
        
        return str(path) in allowed_special_files
    
    def _is_safe_env_value(self, value: str) -> bool:
        """Check if an environment variable value is safe."""
        if not isinstance(value, str):
            return False
        
        # Check length
        if len(value) > 1000:
            return False
        
        # Check for dangerous patterns
        dangerous_patterns = [
            r'[;&|]',  # Command separators
            r'\$\([^)]*\)',  # Command substitution
            r'`[^`]*`',  # Backtick command substitution
            r'\.\./',  # Directory traversal
            r'/etc/', r'/proc/', r'/sys/', r'/dev/',  # System directories
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, value):
                return False
        
        return True
    
    def _is_safe_key(self, key: str) -> bool:
        """Check if an input key is safe."""
        if not isinstance(key, str):
            return False
        
        # Check length
        if len(key) > 100:
            return False
        
        # Only allow alphanumeric and safe characters
        if not re.match(r'^[a-zA-Z0-9_.-]+$', key):
            return False
        
        # Block dangerous key names
        dangerous_keys = {
            '__proto__', 'constructor', 'prototype',
            'eval', 'exec', 'system', 'subprocess',
            'import', '__import__', 'require'
        }
        
        return key.lower() not in dangerous_keys
    
    def _sanitize_input_value(self, value: Any, key: str) -> Any:
        """Sanitize an input value based on its type and key."""
        if isinstance(value, str):
            # String sanitization
            if len(value) > 10000:  # Limit string length
                raise SandboxSecurityViolation(
                    f"String value too long for key {key}",
                    "VALUE_TOO_LONG",
                    {"key": key, "length": len(value)}
                )
            
            # Check for dangerous patterns
            dangerous_patterns = [
                r'<script[\s>]',  # Script tags
                r'javascript:',  # JavaScript URLs
                r'eval\s*\(',  # Eval calls
                r'system\s*\(',  # System calls
                r'exec\s*\(',  # Exec calls
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, value, re.IGNORECASE):
                    raise SandboxSecurityViolation(
                        f"Dangerous pattern in value for key {key}",
                        "DANGEROUS_INPUT_VALUE",
                        {"key": key, "pattern": pattern}
                    )
            
            return value
        
        elif isinstance(value, (int, float)):
            # Numeric validation
            if abs(value) > 1e10:  # Reasonable numeric limit
                raise SandboxSecurityViolation(
                    f"Numeric value too large for key {key}",
                    "VALUE_TOO_LARGE",
                    {"key": key, "value": value}
                )
            return value
        
        elif isinstance(value, bool):
            return value
        
        elif isinstance(value, dict):
            # Recursive sanitization for nested objects
            return {k: self._sanitize_input_value(v, f"{key}.{k}") for k, v in value.items()}
        
        elif isinstance(value, list):
            # Sanitize list items
            if len(value) > 100:  # Limit list size
                raise SandboxSecurityViolation(
                    f"List too long for key {key}",
                    "LIST_TOO_LONG",
                    {"key": key, "length": len(value)}
                )
            return [self._sanitize_input_value(item, f"{key}[{i}]") for i, item in enumerate(value)]
        
        else:
            # Reject unsupported types
            raise SandboxSecurityViolation(
                f"Unsupported value type for key {key}",
                "UNSUPPORTED_TYPE",
                {"key": key, "type": type(value).__name__}
            )


# Global security enforcer instance
sandbox_security = SandboxSecurityEnforcer()