"""
TinyIntent Shortcut Formatting Utilities

Provides text formatting functions for Apple Shortcuts integration,
converting structured TinyIntent responses into speakable text format.
"""

import re
import html
from typing import Dict, Any, Optional


def to_speakable_text(payload: Dict[str, Any]) -> str:
    """
    Convert TinyIntent payload to speakable text for iOS Shortcuts.
    
    Prefers assistant_text/gen_text if present; otherwise synthesizes
    a 1-2 sentence summary from structured fields.
    
    Args:
        payload: TinyIntent response payload
        
    Returns:
        str: Speakable text, stripped of markdown and capped at ~280 chars
    """
    # Try to extract preferred text fields
    speakable_candidates = [
        payload.get("assistant_text"),
        payload.get("gen_text"),
        payload.get("text"),
        payload.get("message"),
        payload.get("content")
    ]
    
    # Find first non-empty text field
    for candidate in speakable_candidates:
        if candidate and isinstance(candidate, str) and candidate.strip():
            text = candidate.strip()
            break
    else:
        # Synthesize from structured fields
        text = _synthesize_from_structure(payload)
    
    # Clean and format for speech
    return _format_for_speech(text)


def _synthesize_from_structure(payload: Dict[str, Any]) -> str:
    """Synthesize speakable text from structured payload fields."""
    # Handle different response types
    status = payload.get("status", "")
    action = payload.get("action", "")
    helper_id = payload.get("helper_id", "")
    
    # Handle success cases
    if status == "success":
        if action == "preview":
            # Preview responses
            preview_data = payload.get("preview_json", {})
            if isinstance(preview_data, dict):
                preview_message = preview_data.get("message", "")
                if preview_message:
                    return f"Preview: {preview_message}"
                
                # Handle specific helper types
                if helper_id == "bot_guard":
                    positions = preview_data.get("positions", [])
                    if positions:
                        return f"Found {len(positions)} trading positions to review."
                    else:
                        return "No active trading positions found."
                
                # Generic preview response
                return f"Action preview ready for {helper_id or 'helper'}."
            else:
                return "Action preview completed successfully."
        
        elif action == "execute":
            # Execution responses
            if helper_id:
                return f"Executed {helper_id} successfully."
            else:
                return "Action executed successfully."
        
        elif action in ["gen", "generation"]:
            # Generation responses - should have been caught in candidates
            return "Response generated successfully."
        
        else:
            return "Request completed successfully."
    
    # Handle error cases
    elif status == "error":
        error_msg = payload.get("error", "")
        if error_msg:
            return f"Error: {error_msg}"
        else:
            return "An error occurred while processing the request."
    
    # Handle routing responses
    elif payload.get("route_used"):
        route = payload.get("route_used")
        if route == "gen":
            return "Routing to text generation."
        elif route == "act":
            return "Routing to action execution."
        else:
            return f"Routed to {route}."
    
    # Handle approval-required cases
    elif payload.get("approval_token"):
        return "Action requires approval. Please confirm to execute."
    
    # Default fallback
    return "Request processed."


def _format_for_speech(text: str) -> str:
    """
    Format text for iOS speech synthesis.
    
    - Strip markdown, code fences, URLs
    - Collapse whitespace
    - Limit to ~280 characters
    - Ensure speakable punctuation
    """
    if not text:
        return "No response available."
    
    # HTML decode first
    text = html.unescape(text)
    
    # Remove markdown formatting
    text = _strip_markdown(text)
    
    # Remove code fences and blocks
    text = re.sub(r'```[\s\S]*?```', '', text)  # Triple backticks
    text = re.sub(r'`[^`]+`', '', text)  # Inline code
    
    # Remove URLs
    text = re.sub(r'https?://[^\s]+', '', text)
    text = re.sub(r'www\.[^\s]+', '', text)
    
    # Remove excessive punctuation
    text = re.sub(r'[!]{2,}', '!', text)
    text = re.sub(r'[?]{2,}', '?', text)
    text = re.sub(r'[.]{3,}', '...', text)
    
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Ensure proper sentence ending
    if text and not text[-1] in '.!?':
        text += '.'
    
    # Limit length for speakability
    if len(text) > 280:
        # Try to break at sentence boundary
        sentences = re.split(r'[.!?]+', text)
        truncated = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            
            if len(truncated + sentence) + 1 <= 280:
                if truncated:
                    truncated += ". " + sentence
                else:
                    truncated = sentence
            else:
                break
        
        if truncated:
            text = truncated
            if not text.endswith(('.', '!', '?')):
                text += '.'
        else:
            # Hard truncate if no sentence boundaries
            text = text[:277] + "..."
    
    return text


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting."""
    # Bold and italic
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'\*([^*]+)\*', r'\1', text)  # *italic*
    text = re.sub(r'__([^_]+)__', r'\1', text)  # __bold__
    text = re.sub(r'_([^_]+)_', r'\1', text)  # _italic_
    
    # Headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    
    # Links
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # [text](url)
    
    # Lists
    text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    # Blockquotes
    text = re.sub(r'^\s*>\s+', '', text, flags=re.MULTILINE)
    
    return text


def sanitize_short_input(text: str, max_length: int = 800) -> str:
    """
    Sanitize input text from iOS Shortcuts.
    
    Args:
        text: Raw input text from Shortcut
        max_length: Maximum allowed length (default 800)
        
    Returns:
        str: Sanitized text
        
    Raises:
        ValueError: If text is too long or contains invalid characters
    """
    if not isinstance(text, str):
        raise ValueError("Input must be a string")
    
    # Trim whitespace
    text = text.strip()
    
    if not text:
        raise ValueError("Input text cannot be empty")
    
    # Check length
    if len(text) > max_length:
        raise ValueError(f"Input text too long: {len(text)} > {max_length} characters")
    
    # Remove control characters (but keep common whitespace)
    # Allow: space (32), tab (9), newline (10), carriage return (13)
    cleaned_chars = []
    for char in text:
        code = ord(char)
        if code >= 32 or code in (9, 10, 13):
            cleaned_chars.append(char)
        # Skip other control characters
    
    text = ''.join(cleaned_chars)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    if not text:
        raise ValueError("Input text contains only invalid characters")
    
    return text


def format_shortcut_response(payload: Dict[str, Any], return_format: str = "text") -> Dict[str, Any]:
    """
    Format a complete shortcut response.
    
    Args:
        payload: Original TinyIntent response
        return_format: "text" or "json"
        
    Returns:
        dict: Formatted response for iOS Shortcut
    """
    if return_format == "text":
        speak_text = to_speakable_text(payload)
        
        # Check if truncation occurred
        truncated = len(speak_text) < len(str(payload))
        
        return {
            "speak": speak_text,
            "truncated": truncated,
            "data": payload
        }
    
    elif return_format == "json":
        # Return full JSON payload for advanced Shortcuts
        return payload
    
    else:
        raise ValueError(f"Invalid return format: {return_format}. Must be 'text' or 'json'")


def get_shortcut_error_response(error_code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create a shortcut-friendly error response.
    
    Args:
        error_code: Error code (e.g., "EXECUTION_DISABLED", "APPROVAL_REQUIRED")
        message: Human-readable error message
        details: Optional additional error details
        
    Returns:
        dict: Shortcut error response
    """
    speak_text = f"Error: {message}"
    
    # Make common errors more user-friendly for speech
    if error_code == "EXECUTION_DISABLED":
        speak_text = "Execution is currently disabled. Only previews are available."
    elif error_code == "APPROVAL_REQUIRED":
        speak_text = "This action requires approval. Please use the full interface to approve and execute."
    elif error_code == "SANDBOX_LIMIT":
        speak_text = "Action exceeded safety limits and was blocked."
    elif error_code == "CAPABILITY_VIOLATION":
        speak_text = "Action requires capabilities that are not available."
    elif error_code == "RATE_LIMIT":
        speak_text = "Too many requests. Please wait before trying again."
    elif error_code == "QUOTA_EXCEEDED":
        speak_text = "Daily usage quota exceeded. Please try again tomorrow."
    
    return {
        "speak": speak_text,
        "truncated": False,
        "error": error_code,
        "message": message,
        "details": details or {}
    }