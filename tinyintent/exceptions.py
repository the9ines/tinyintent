"""
TinyIntent Exception Hierarchy

Centralized exception classes for consistent error handling across the platform.
"""

from typing import Any, Dict, Optional


class TinyIntentError(Exception):
    """Base exception for all TinyIntent errors."""
    
    def __init__(self, message: str, error_code: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code or self.__class__.__name__.upper()
        self.details = details or {}


class ConfigurationError(TinyIntentError):
    """Configuration validation or loading error."""
    pass


class SecurityError(TinyIntentError):
    """Security-related error."""
    pass


class AuthenticationError(SecurityError):
    """Authentication failed."""
    pass


class AuthorizationError(SecurityError):
    """Authorization failed."""
    pass


class RateLimitError(SecurityError):
    """Rate limit exceeded."""
    
    def __init__(self, message: str, current_count: int, limit: int, window_seconds: int, **kwargs):
        super().__init__(message, **kwargs)
        self.current_count = current_count
        self.limit = limit
        self.window_seconds = window_seconds


class HelperError(TinyIntentError):
    """Helper framework error."""
    pass


class HelperValidationError(HelperError):
    """Helper validation failed."""
    pass


class HelperExecutionError(HelperError):
    """Helper execution failed."""
    pass


class HelperTimeoutError(HelperExecutionError):
    """Helper execution timed out."""
    pass


class HelperEnvironmentError(HelperError):
    """Helper environment configuration error."""
    pass


class SandboxError(HelperError):
    """Sandbox-related error."""
    pass


class SandboxViolationError(SandboxError):
    """Sandbox security violation."""
    
    def __init__(self, message: str, violation_type: str, **kwargs):
        super().__init__(message, **kwargs)
        self.violation_type = violation_type


class CapabilityViolationError(SandboxError):
    """Capability restriction violation."""
    
    def __init__(self, message: str, capability: str, operation: str, **kwargs):
        super().__init__(message, **kwargs)
        self.capability = capability
        self.operation = operation


class RouterError(TinyIntentError):
    """Router-related error."""
    pass


class ModelError(TinyIntentError):
    """Model loading or inference error."""
    pass


class DataError(TinyIntentError):
    """Data processing or storage error."""
    pass


class AuditError(TinyIntentError):
    """Audit logging error."""
    pass


class IntegrityError(AuditError):
    """Data integrity check failed."""
    pass