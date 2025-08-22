"""
TinyIntent Input Validation Module

Provides comprehensive input validation and sanitization for all user inputs
to prevent injection attacks and ensure data integrity.
"""

import re
import html
import json
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import structlog

logger = structlog.get_logger()


class ValidationError(Exception):
    """Raised when input validation fails."""
    def __init__(self, message: str, field: str = None, value: Any = None):
        super().__init__(message)
        self.field = field
        self.value = value


def validate_text_input(text: str, max_length: int = 1000, min_length: int = 1, 
                       field_name: str = "text") -> str:
    """
    Validate and sanitize text input.
    
    Args:
        text: Input text to validate
        max_length: Maximum allowed length
        min_length: Minimum required length  
        field_name: Name of field for error messages
        
    Returns:
        str: Sanitized text
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(text, str):
        raise ValidationError(f"{field_name} must be a string", field_name, text)
    
    # Remove any null bytes
    text = text.replace('\x00', '')
    
    # Trim whitespace
    text = text.strip()
    
    # Check length constraints
    if len(text) < min_length:
        raise ValidationError(f"{field_name} must be at least {min_length} characters", field_name, text)
    
    if len(text) > max_length:
        raise ValidationError(f"{field_name} too long: {len(text)} > {max_length} characters", field_name, text)
    
    # Remove dangerous control characters but preserve basic whitespace
    cleaned_chars = []
    for char in text:
        code = ord(char)
        # Allow: space (32), tab (9), newline (10), carriage return (13), and printable ASCII
        if code >= 32 or code in (9, 10, 13):
            cleaned_chars.append(char)
    
    text = ''.join(cleaned_chars)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    if len(text) < min_length:
        raise ValidationError(f"{field_name} contains insufficient valid content", field_name, text)
    
    # Check for potential script injection
    if _contains_script_injection(text):
        raise ValidationError(f"{field_name} contains potentially dangerous content", field_name, text)
    
    return text


def validate_identifier(identifier: str, max_length: int = 100, field_name: str = "identifier") -> str:
    """
    Validate identifier strings (helper IDs, session IDs, etc).
    
    Args:
        identifier: String to validate as identifier
        max_length: Maximum allowed length
        field_name: Field name for error messages
        
    Returns:
        str: Validated identifier
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(identifier, str):
        raise ValidationError(f"{field_name} must be a string", field_name, identifier)
    
    identifier = identifier.strip()
    
    if not identifier:
        raise ValidationError(f"{field_name} cannot be empty", field_name, identifier)
    
    if len(identifier) > max_length:
        raise ValidationError(f"{field_name} too long: {len(identifier)} > {max_length}", field_name, identifier)
    
    # Only allow alphanumeric, underscore, dash, dot
    if not re.match(r'^[a-zA-Z0-9_.-]+$', identifier):
        raise ValidationError(f"{field_name} contains invalid characters", field_name, identifier)
    
    # Prevent path traversal
    if '..' in identifier or identifier.startswith('.'):
        raise ValidationError(f"{field_name} contains invalid path sequences", field_name, identifier)
    
    return identifier


def validate_json_input(data: Union[str, Dict, List], max_size: int = 10000, 
                       field_name: str = "json_data") -> Dict[str, Any]:
    """
    Validate and parse JSON input.
    
    Args:
        data: JSON string or already parsed data
        max_size: Maximum size in characters for JSON string
        field_name: Field name for error messages
        
    Returns:
        dict: Parsed and validated JSON data
        
    Raises:
        ValidationError: If validation fails
    """
    if isinstance(data, str):
        # Validate JSON string
        if len(data) > max_size:
            raise ValidationError(f"{field_name} too large: {len(data)} > {max_size}", field_name, data)
        
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValidationError(f"{field_name} is not valid JSON: {e}", field_name, data)
    
    if not isinstance(data, dict):
        raise ValidationError(f"{field_name} must be a JSON object", field_name, data)
    
    # Recursively validate nested structures
    _validate_json_structure(data, field_name)
    
    return data


def validate_file_path(path: str, allowed_dirs: List[str] = None, 
                      field_name: str = "file_path") -> Path:
    """
    Validate file path for security.
    
    Args:
        path: File path to validate
        allowed_dirs: List of allowed directory prefixes
        field_name: Field name for error messages
        
    Returns:
        Path: Validated path object
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(path, str):
        raise ValidationError(f"{field_name} must be a string", field_name, path)
    
    path = path.strip()
    
    if not path:
        raise ValidationError(f"{field_name} cannot be empty", field_name, path)
    
    # Convert to Path object for normalization
    try:
        path_obj = Path(path)
    except (ValueError, OSError) as e:
        raise ValidationError(f"{field_name} is not a valid path: {e}", field_name, path)
    
    # Resolve to normalize (but don't require existence)
    try:
        resolved_path = path_obj.resolve()
    except (ValueError, OSError) as e:
        raise ValidationError(f"{field_name} could not be resolved: {e}", field_name, path)
    
    # Check for directory traversal
    if '..' in path or path.startswith('/') and allowed_dirs:
        # If allowed_dirs specified, check against them
        allowed = False
        for allowed_dir in allowed_dirs:
            try:
                resolved_path.relative_to(Path(allowed_dir).resolve())
                allowed = True
                break
            except ValueError:
                continue
        
        if not allowed:
            raise ValidationError(f"{field_name} is outside allowed directories", field_name, path)
    
    return resolved_path


def validate_enum_value(value: str, allowed_values: List[str], 
                       field_name: str = "value") -> str:
    """
    Validate enumerated value.
    
    Args:
        value: Value to validate
        allowed_values: List of allowed values
        field_name: Field name for error messages
        
    Returns:
        str: Validated value
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string", field_name, value)
    
    value = value.strip()
    
    if value not in allowed_values:
        raise ValidationError(
            f"{field_name} must be one of: {', '.join(allowed_values)}", 
            field_name, value
        )
    
    return value


def validate_integer(value: Union[int, str], min_value: int = None, max_value: int = None,
                    field_name: str = "integer") -> int:
    """
    Validate integer input.
    
    Args:
        value: Integer value or string representation
        min_value: Minimum allowed value
        max_value: Maximum allowed value
        field_name: Field name for error messages
        
    Returns:
        int: Validated integer
        
    Raises:
        ValidationError: If validation fails
    """
    if isinstance(value, str):
        try:
            value = int(value.strip())
        except ValueError:
            raise ValidationError(f"{field_name} must be a valid integer", field_name, value)
    
    if not isinstance(value, int):
        raise ValidationError(f"{field_name} must be an integer", field_name, value)
    
    if min_value is not None and value < min_value:
        raise ValidationError(f"{field_name} must be >= {min_value}", field_name, value)
    
    if max_value is not None and value > max_value:
        raise ValidationError(f"{field_name} must be <= {max_value}", field_name, value)
    
    return value


def _contains_script_injection(text: str) -> bool:
    """Check if text contains potential script injection patterns."""
    # Convert to lowercase for case-insensitive detection
    lower_text = text.lower()
    
    # Common script injection patterns
    script_patterns = [
        r'<script[\s>]',
        r'javascript:',
        r'vbscript:',
        r'on\w+\s*=',  # Event handlers like onclick=
        r'eval\s*\(',
        r'expression\s*\(',
        r'import\s+os',
        r'import\s+subprocess',
        r'__import__',
        r'exec\s*\(',
        r'system\s*\(',
        r'popen\s*\(',
        r'shell=true',
    ]
    
    for pattern in script_patterns:
        if re.search(pattern, lower_text, re.IGNORECASE):
            return True
    
    return False


def _validate_json_structure(data: Any, field_name: str, depth: int = 0) -> None:
    """Recursively validate JSON structure."""
    # Prevent excessive nesting
    if depth > 10:
        raise ValidationError(f"{field_name} has excessive nesting depth", field_name, data)
    
    if isinstance(data, dict):
        # Validate keys
        for key in data.keys():
            if not isinstance(key, str):
                raise ValidationError(f"{field_name} keys must be strings", field_name, key)
            
            if len(key) > 100:
                raise ValidationError(f"{field_name} key too long: {key}", field_name, key)
            
            # Check for dangerous key patterns
            if _contains_script_injection(key):
                raise ValidationError(f"{field_name} key contains dangerous content: {key}", field_name, key)
        
        # Validate values recursively
        for key, value in data.items():
            _validate_json_structure(value, f"{field_name}.{key}", depth + 1)
    
    elif isinstance(data, list):
        # Limit list size
        if len(data) > 1000:
            raise ValidationError(f"{field_name} list too large: {len(data)} items", field_name, data)
        
        # Validate items recursively
        for i, item in enumerate(data):
            _validate_json_structure(item, f"{field_name}[{i}]", depth + 1)
    
    elif isinstance(data, str):
        # Validate string values
        if len(data) > 10000:
            raise ValidationError(f"{field_name} string too long: {len(data)}", field_name, data)
        
        if _contains_script_injection(data):
            raise ValidationError(f"{field_name} contains dangerous content", field_name, data)


def validate_helper_input(helper_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate helper input data comprehensively.
    
    Args:
        helper_input: Raw helper input data
        
    Returns:
        dict: Validated helper input
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(helper_input, dict):
        raise ValidationError("Helper input must be a dictionary", "helper_input", helper_input)
    
    # Validate the overall structure
    validated_input = validate_json_input(helper_input, field_name="helper_input")
    
    # Additional helper-specific validations
    for key, value in validated_input.items():
        # Validate key format
        validate_identifier(key, field_name=f"helper_input.{key}")
        
        # Specific validations for known keys
        if key == "operation" and isinstance(value, str):
            validate_enum_value(
                value, 
                ["get_positions", "close_position", "close_all_positions", "get_balance", "cancel_order"],
                f"helper_input.{key}"
            )
        elif key == "symbol" and isinstance(value, str):
            # Validate trading symbol format
            if not re.match(r'^[A-Z]{2,10}[/_][A-Z]{2,10}$', value):
                raise ValidationError(f"Invalid trading symbol format: {value}", f"helper_input.{key}", value)
        elif key in ["amount", "quantity", "price"] and isinstance(value, (int, float, str)):
            # Validate numeric values
            try:
                float_val = float(value)
                if float_val < 0:
                    raise ValidationError(f"{key} must be positive", f"helper_input.{key}", value)
                if float_val > 1e10:  # Reasonable upper limit
                    raise ValidationError(f"{key} value too large", f"helper_input.{key}", value)
            except (ValueError, TypeError):
                raise ValidationError(f"{key} must be a valid number", f"helper_input.{key}", value)
    
    return validated_input


def create_validation_middleware():
    """Create FastAPI middleware for input validation."""
    from fastapi import Request, HTTPException
    from starlette.middleware.base import BaseHTTPMiddleware
    
    class ValidationMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # Validate common request components
            try:
                # Validate headers
                for header_name, header_value in request.headers.items():
                    if len(header_value) > 8192:  # 8KB limit for headers
                        raise HTTPException(status_code=400, detail=f"Header {header_name} too large")
                
                # Validate query parameters
                for param_name, param_value in request.query_params.items():
                    validate_identifier(param_name, field_name=f"query.{param_name}")
                    validate_text_input(param_value, max_length=1000, field_name=f"query.{param_name}")
                
            except ValidationError as e:
                logger.warning("Request validation failed", error=str(e), field=e.field)
                raise HTTPException(status_code=400, detail=f"Validation error: {e}")
            
            return await call_next(request)
    
    return ValidationMiddleware