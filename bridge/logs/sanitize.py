"""
Centralized Sanitization Module for TinyIntent

Provides comprehensive sensitive data redaction across all system components.
"""

import re
from typing import Dict, Any, Mapping, Union, List


# Compiled regex patterns for performance
class SanitizationPatterns:
    """Pre-compiled regex patterns for sensitive data detection."""
    
    def __init__(self):
        # Sensitive key patterns (case-insensitive)
        self.sensitive_keys = re.compile(
            r'^(?:'
            # Core sensitive patterns
            r'API_KEY|KEY|SECRET|TOKEN|ACCESS_TOKEN|REFRESH_TOKEN|ID_TOKEN|'
            r'PASSWORD|PASS|PWD|PRIVATE_KEY|CLIENT_SECRET|AUTHORIZATION|'
            r'BEARER|WEBHOOK_SECRET|SIGNING_SECRET|CREDENTIALS|'
            # Service-specific prefixes
            r'AWS_.*|GCP_.*|GOOGLE_.*|STRIPE_.*|OPENAI_.*|SLACK_.*|DISCORD_.*|'
            # Exchange/trading specific
            r'EXCHANGE_.*|TRADING_.*|BINANCE_.*|COINBASE_.*'
            r')$', 
            re.IGNORECASE
        )
        
        # JWT pattern: three base64-like segments separated by dots
        self.jwt_pattern = re.compile(
            r'\b[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\b'
        )
        
        # Hex/Base64-like blobs (32-128 characters)
        self.hex_blob_pattern = re.compile(
            r'\b[A-Fa-f0-9]{32,128}\b'  # Hex strings
        )
        
        self.base64_blob_pattern = re.compile(
            r'\b[A-Za-z0-9+/]{32,128}={0,2}\b'  # Base64 strings
        )
        
        # PEM private key blocks
        self.pem_pattern = re.compile(
            r'-----BEGIN[^-]*PRIVATE KEY[^-]*-----.*?-----END[^-]*PRIVATE KEY[^-]*-----',
            re.DOTALL | re.IGNORECASE
        )
        
        # Specific token patterns
        self.bearer_pattern = re.compile(
            r'\bBearer\s+[A-Za-z0-9\-_+/=]{10,}', re.IGNORECASE
        )
        
        self.basic_auth_pattern = re.compile(
            r'\bBasic\s+[A-Za-z0-9+/=]+', re.IGNORECASE
        )
        
        # API key patterns with known prefixes
        self.api_key_prefixes = re.compile(
            r'\b(?:sk_|pk_|rk_|api_|key_)[A-Za-z0-9_\-]{10,}', re.IGNORECASE
        )
        
        # Environment variable patterns in text
        self.env_var_pattern = re.compile(
            r'[A-Z_]+(?:KEY|SECRET|TOKEN|PASSWORD)=[A-Za-z0-9_\-+/=]{15,}',
            re.IGNORECASE
        )
        
        # JSON-like patterns
        self.json_sensitive_pattern = re.compile(
            r'"[^"]*(?:key|secret|password|token|auth|credential)[^"]*"\s*:\s*"[^"]{15,}"',
            re.IGNORECASE
        )


# Global instance for pattern reuse
_patterns = SanitizationPatterns()

def sanitize_dict(d: Mapping[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a dictionary by redacting sensitive key-value pairs.
    
    Args:
        d: Dictionary to sanitize
        
    Returns:
        New dictionary with sensitive values redacted
    """
    if not isinstance(d, Mapping):
        return d
    
    sanitized = {}
    for key, value in d.items():
        # Check if key matches sensitive patterns
        if _patterns.sensitive_keys.match(str(key)):
            # Apply smart redaction based on value format
            sanitized[key] = _smart_redact_value(value)
        elif isinstance(value, Mapping):
            # Recursively sanitize nested dictionaries
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, (list, tuple)):
            # Sanitize list/tuple items
            sanitized[key] = _sanitize_sequence(value)
        elif isinstance(value, str):
            # Sanitize string values that might contain sensitive patterns
            sanitized[key] = sanitize_text(value)
        else:
            sanitized[key] = value
    
    return sanitized

def sanitize_text(s: str) -> str:
    """
    Sanitize text by redacting sensitive patterns.
    
    Args:
        s: Text to sanitize
        
    Returns:
        Text with sensitive patterns redacted
    """
    if not isinstance(s, str):
        return s
    
    text = s
    
    # Replace PEM private key blocks first (most specific)
    text = _patterns.pem_pattern.sub('<REDACTED-PEM>', text)
    
    # Replace JWT tokens
    text = _patterns.jwt_pattern.sub('****', text)
    
    # Replace Bearer tokens
    text = _patterns.bearer_pattern.sub('Bearer ****', text)
    
    # Replace Basic auth
    text = _patterns.basic_auth_pattern.sub('Basic ****', text)
    
    # Replace API key patterns
    text = _patterns.api_key_prefixes.sub('****', text)
    
    # Replace environment variable patterns
    text = _patterns.env_var_pattern.sub('REDACTED_ENV=****', text)
    
    # Replace JSON-like sensitive patterns
    text = _patterns.json_sensitive_pattern.sub('"****": "****"', text)
    
    # Replace hex blobs (32-128 chars)
    text = _patterns.hex_blob_pattern.sub('****', text)
    
    # Replace base64 blobs (32-128 chars)
    text = _patterns.base64_blob_pattern.sub('****', text)
    
    return text

def _smart_redact_value(value: Any) -> str:
    """
    Apply smart redaction based on value format.
    
    For token-like values, preserve prefix/suffix for debugging.
    For other values, use simple redaction.
    """
    if not isinstance(value, str):
        return "****"
    
    # If value looks like a token with clear structure, preserve some context
    if len(value) > 20:
        # Check for common token patterns
        if value.startswith(('sk_', 'pk_', 'rk_', 'Bearer ', 'Basic ')):
            # Preserve prefix and a bit of suffix for debugging
            if len(value) > 30:
                return f"{value[:6]}****{value[-4:]}"
            else:
                return "****"
        
        # For very long values, show first and last few chars
        if len(value) > 40:
            return f"{value[:4]}****{value[-4:]}"
    
    return "****"

def _sanitize_sequence(seq: Union[List, tuple]) -> Union[List, tuple]:
    """Sanitize items in a sequence (list or tuple)."""
    sanitized_items = []
    for item in seq:
        if isinstance(item, Mapping):
            sanitized_items.append(sanitize_dict(item))
        elif isinstance(item, str):
            sanitized_items.append(sanitize_text(item))
        elif isinstance(item, (list, tuple)):
            sanitized_items.append(_sanitize_sequence(item))
        else:
            sanitized_items.append(item)
    
    # Return same type as input
    return type(seq)(sanitized_items)

def safe_error_payload(exc: Exception) -> Dict[str, Any]:
    """
    Create a safe error payload from an exception with sanitized details.
    
    Args:
        exc: Exception to convert to safe payload
        
    Returns:
        Sanitized error dictionary safe for client responses
    """
    error_payload = {
        "error": exc.__class__.__name__,
        "message": sanitize_text(str(exc)),
    }
    
    # Add sanitized details if available
    if hasattr(exc, 'details') and isinstance(exc.details, dict):
        error_payload["details"] = sanitize_dict(exc.details)
    
    # Add sanitized args if they contain useful information
    if exc.args:
        sanitized_args = []
        for arg in exc.args:
            if isinstance(arg, str):
                sanitized_args.append(sanitize_text(arg))
            elif isinstance(arg, dict):
                sanitized_args.append(sanitize_dict(arg))
            else:
                sanitized_args.append(str(arg))
        error_payload["args"] = sanitized_args
    
    return error_payload

def is_sensitive_key(key: str) -> bool:
    """
    Check if a key name indicates sensitive data.
    
    Args:
        key: Key name to check
        
    Returns:
        True if key appears to contain sensitive data
    """
    return bool(_patterns.sensitive_keys.match(str(key)))

def get_sensitive_patterns_info() -> Dict[str, str]:
    """
    Get information about the sensitive patterns used for sanitization.
    
    Returns:
        Dictionary describing the patterns used
    """
    return {
        "sensitive_keys": "API_KEY, KEY, SECRET, TOKEN, PASSWORD, AWS_*, GCP_*, etc.",
        "jwt_tokens": "Three base64 segments separated by dots",
        "hex_blobs": "32-128 character hexadecimal strings",
        "base64_blobs": "32-128 character base64 strings",
        "pem_blocks": "PEM private key blocks",
        "bearer_tokens": "Bearer authentication tokens",
        "api_keys": "Keys with prefixes sk_, pk_, rk_, api_, key_",
        "env_vars": "Environment variables with sensitive suffixes",
        "json_patterns": "JSON key-value pairs with sensitive keys"
    }


# Export convenience functions for backwards compatibility
def sanitize_audit_data(data: Any) -> Any:
    """Legacy function for audit data sanitization."""
    if isinstance(data, Mapping):
        return sanitize_dict(data)
    elif isinstance(data, str):
        return sanitize_text(data)
    elif isinstance(data, (list, tuple)):
        return _sanitize_sequence(data)
    else:
        return data

def sanitize_sensitive_data(data: Any) -> Any:
    """Legacy function for general data sanitization."""
    return sanitize_audit_data(data)


def sanitize_sensitive_string(text: str) -> str:
    """Legacy function for string sanitization."""
    return sanitize_text(text)

def sanitize_env(env_dict: Mapping[str, str]) -> Dict[str, str]:
    """Legacy function for environment variable sanitization."""
    return sanitize_dict(env_dict)
