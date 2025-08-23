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
from ..security import constant_time_compare
from ..router_client import SmallIntentRouter
from ..gen_client import async_ollama_client
from ..edge_case_logger import log_router_decision, log_user_correction
from helpers.executor import HelperExecutor
from helpers.registry import HelperRegistry

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
    
    if not constant_time_compare(provided_token, expected_token):
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
        
        # Route through TinyIntent system
        session_id = request.session_id or f"shortcut-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        
        # Initialize router with fallback capability
        try:
            router_client = SmallIntentRouter(require_models=False)
        except Exception:
            router_client = None
        
        # Determine route using router or fallback logic
        if router_client and router_client.router_available and router_client.models_available:
            try:
                # Pass session_id for edge case logging
                route_result = router_client.route_request(clean_text, session_id=session_id)
                route_used = route_result["route"]
                router_confidence = route_result.get("confidence", 0.0)
                intent = route_result.get("intent", "unknown")
            except Exception as e:
                logger.warning(f"Router failed, using fallback: {e}")
                route_used = "gen" if any(word in clean_text.lower() for word in ["what", "how", "why", "when", "where", "explain", "tell me"]) else "act"
                router_confidence = 0.0
                intent = "fallback"
                
                # Log fallback scenario as edge case
                log_router_decision(
                    text=clean_text,
                    session_id=session_id,
                    predicted_route="unknown",
                    predicted_confidence=0.0,
                    actual_route=route_used,
                    actual_confidence=router_confidence,
                    fallback_reason=f"router_exception: {str(e)}",
                    context_source="iPhone_shortcut",
                    voice_command=True,
                    shortcut_session=True
                )
        else:
            # Fallback routing logic
            route_used = "gen" if any(word in clean_text.lower() for word in ["what", "how", "why", "when", "where", "explain", "tell me"]) else "act"
            router_confidence = 0.0
            intent = "fallback"
            
            # Log fallback scenario as edge case
            log_router_decision(
                text=clean_text,
                session_id=session_id,
                predicted_route="unknown",
                predicted_confidence=0.0,
                actual_route=route_used,
                actual_confidence=router_confidence,
                fallback_reason="router_unavailable",
                context_source="iPhone_shortcut",
                voice_command=True,
                shortcut_session=True
            )
        
        response_text = ""
        execution_result = None
        
        # Handle generation requests
        if route_used == "gen":
            try:
                # Generate response using Ollama
                model = os.environ.get('OLLAMA_MODEL', 'llama3.2:3b')
                prompt = f"Answer this question concisely for voice response (max 2 sentences): {clean_text}"
                
                response_text_raw, latency_ms = await async_ollama_client.generate_async(
                    model=model,
                    prompt=prompt,
                    session_id=session_id
                )
                
                generation_result = {
                    "text": response_text_raw,
                    "model": model,
                    "latency_ms": latency_ms,
                    "tokens": len(response_text_raw.split()) if response_text_raw else 0
                }
                response_text = generation_result.get("text", "").strip()
                
                # Optimize for voice output
                if len(response_text) > 280:
                    # Find last sentence that fits
                    sentences = response_text.split('. ')
                    truncated = ""
                    for sentence in sentences:
                        if len(truncated + sentence) <= 277:
                            truncated += sentence + ". "
                        else:
                            break
                    response_text = truncated.strip() or response_text[:277] + "..."
                
                execution_result = {
                    "generation_used": True,
                    "model": generation_result.get("model", "unknown"),
                    "tokens": generation_result.get("tokens", 0),
                    "latency_ms": generation_result.get("latency_ms", 0)
                }
                
            except Exception as e:
                logger.error(f"Generation failed: {e}")
                response_text = f"I understand you asked: '{clean_text}'. However, I'm having trouble generating a response right now. Please try again in a moment."
                execution_result = {"generation_used": False, "error": str(e)}
        
        # Handle action requests
        elif route_used == "act":
            try:
                # Initialize helper execution
                registry = HelperRegistry()
                executor = HelperExecutor(registry)
                
                # For voice interface, we'll try to match common helpers
                helper_candidates = []
                text_lower = clean_text.lower()
                
                if any(word in text_lower for word in ["log", "error", "tail", "check"]):
                    helper_candidates.append("log_tailer")
                elif any(word in text_lower for word in ["trade", "position", "crypto", "bot", "close", "buy", "sell"]):
                    helper_candidates.append("bot_guard")
                
                if helper_candidates:
                    # Try the first matching helper
                    helper_id = helper_candidates[0]
                    
                    # Simple input mapping for voice commands
                    helper_input = {"operation": "status", "text": clean_text}
                    if "close" in text_lower:
                        helper_input["operation"] = "close_position"
                    elif "position" in text_lower or "status" in text_lower:
                        helper_input["operation"] = "get_positions"
                    
                    # Execute in preview mode for safety
                    result = executor.preview(helper_id, helper_input)
                    
                    if result.get("status") == "success":
                        response_text = result.get("message", f"Action executed successfully: {clean_text}")
                        execution_result = {
                            "helper_used": helper_id,
                            "helper_input": helper_input,
                            "preview_mode": True,
                            "execution_time_ms": result.get("execution_time_ms", 0)
                        }
                    else:
                        response_text = f"I couldn't complete that action: {result.get('message', 'Unknown error')}"
                        execution_result = {"helper_used": helper_id, "error": result.get("message")}
                else:
                    response_text = f"I understand you want to take an action: '{clean_text}'. However, I'm not sure which specific action to perform. Try being more specific."
                    execution_result = {"action_recognized": False, "reason": "no_matching_helper"}
                    
            except Exception as e:
                logger.error(f"Helper execution failed: {e}")
                response_text = f"I understand you want to take an action: '{clean_text}'. However, I'm having trouble processing actions right now."
                execution_result = {"action_recognized": True, "error": str(e)}
        
        # Create response payload
        response_payload = {
            "status": "success",
            "route_used": route_used,
            "text": response_text,
            "session_id": session_id,
            "mode": request.mode,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "router_confidence": router_confidence,
            "intent": intent,
            "execution_result": execution_result
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
            formatted = format_shortcut_response(response_payload, "text")
            return ShortcutRouteResponse(**formatted)
        elif request.return_format == "json":
            return ShortcutRouteResponse(data=response_payload)
        else:
            # Default voice-optimized formatting
            speak_text = response_payload.get("text", "Request processed successfully.")
            is_truncated = len(speak_text) > 280
            
            if is_truncated:
                speak_text = speak_text[:277] + "..."
            
            return ShortcutRouteResponse(
                speak=speak_text,
                truncated=is_truncated,
                data=response_payload
            )
            
    except ValueError as e:
        error_msg = str(e)
        return get_shortcut_error_response("VALIDATION_ERROR", error_msg)
    
    except Exception as e:
        logger.exception("Error processing shortcut request")
        return get_shortcut_error_response("INTERNAL_ERROR", "An internal error occurred")