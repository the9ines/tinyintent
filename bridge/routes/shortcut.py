"""
M11.0: iPhone Shortcut Voice Interface Routes

Endpoints optimized for iOS Shortcuts integration with voice commands.
"""

from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import os
import logging

from ..shortcut_format import (
    sanitize_short_input, 
    format_shortcut_response,
    get_shortcut_error_response
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shortcut", tags=["shortcut"])

class ShortcutRouteRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    mode: str = "preview"  # preview or execute
    return_format: str = "text"  # text or json

class ShortcutRouteResponse(BaseModel):
    speak: Optional[str] = None
    truncated: bool = False
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

class ShortcutPingResponse(BaseModel):
    ok: bool
    ts: str
    service: str
    version: str

def verify_shortcut_token(request: Request) -> bool:
    """Verify X-Shortcut-Token header for iOS Shortcuts authentication."""
    expected_token = os.environ.get('SHORTCUT_TOKEN', 'iphone-shortcut-secure-token-123')
    provided_token = request.headers.get("X-Shortcut-Token")
    
    if not provided_token:
        raise HTTPException(
            status_code=401, 
            detail="Missing X-Shortcut-Token header"
        )
    
    if provided_token != expected_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid X-Shortcut-Token"
        )
    
    return True

@router.get("/ping", response_model=ShortcutPingResponse)
async def shortcut_ping(request: Request, auth: bool = Depends(verify_shortcut_token)):
    """
    Health check endpoint for iOS Shortcuts.
    
    Designed for Apple Shortcuts → Dictate Text → Get Contents of URL → Speak Text.
    """
    return ShortcutPingResponse(
        ok=True,
        ts=datetime.utcnow().isoformat() + "Z",
        service="TinyIntent Bridge",
        version="2.0.0"
    )

@router.post("/route", response_model=ShortcutRouteResponse)
async def shortcut_route(
    request: ShortcutRouteRequest, 
    fastapi_request: Request, 
    response: Response,
    auth: bool = Depends(verify_shortcut_token)
):
    """
    Main routing endpoint for iPhone Shortcuts.
    
    Designed for Apple Shortcuts → Dictate Text → Get Contents of URL → Speak Text.
    Accepts voice input, routes through TinyIntent, returns speech-optimized responses.
    """
    
    try:
        # Validate and sanitize input
        max_len = int(os.environ.get('SHORTCUT_MAX_LEN', '800'))
        clean_text = sanitize_short_input(request.text, max_len)
        
        # Mock response for current implementation
        # TODO: Replace with actual TinyIntent routing
        mock_payload = {
            "status": "success",
            "route_used": "gen" if "what" in clean_text.lower() or "how" in clean_text.lower() else "act",
            "text": f"I received your command: '{clean_text}'. This is a test response for iPhone Shortcut integration.",
            "session_id": request.session_id or "shortcut-session",
            "mode": request.mode,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Check execution mode
        execution_enabled = os.environ.get('TINYINTENT_EXECUTION_ENABLED', '0') == '1'
        if request.mode == "execute" and not execution_enabled:
            return get_shortcut_error_response(
                "EXECUTION_DISABLED",
                "Execution is currently disabled. Only previews are available."
            )
        
        # Format response based on return format
        if request.return_format == "text":
            formatted = format_shortcut_response(mock_payload, "text")
            return ShortcutRouteResponse(**formatted)
        elif request.return_format == "json":
            return ShortcutRouteResponse(data=mock_payload)
        else:
            # Fallback formatting
            speak_text = mock_payload.get("text", "Request processed successfully.")
            if len(speak_text) > 280:
                speak_text = speak_text[:277] + "..."
            
            return ShortcutRouteResponse(
                speak=speak_text,
                truncated=len(speak_text) > 280,
                data=mock_payload
            )
            
    except ValueError as e:
        error_msg = str(e)
        return get_shortcut_error_response("VALIDATION_ERROR", error_msg)
    
    except Exception as e:
        logger.exception("Error processing shortcut request")
        return get_shortcut_error_response("INTERNAL_ERROR", "An internal error occurred")