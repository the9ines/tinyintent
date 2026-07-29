"""
TinyIntent Bridge API - Streamlined Main Routes

Modular, clean API structure replacing the monolithic api_routes.py.
"""

import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import APIRouter, Request, HTTPException, Response, Depends
from pydantic import BaseModel

# Import modular route handlers
from .routes.health import router as health_router
from .routes.helpers import router as helpers_router
from .routes.agents import router as agents_router
from .routes.shortcut import router as shortcut_router
from .routes.system import router as system_router
from .routes.router import router as router_router
from .security import get_csrf_token, verify_csrf_token
from .validation import validate_text_input, validate_identifier, ValidationError

# Import router and executor
try:
    from .router_client import router as small_intent_router
    ROUTER_AVAILABLE = True
except Exception:
    ROUTER_AVAILABLE = False
    small_intent_router = None

try:
    from helpers.sdk import helper_registry
    from helpers.executor import HelperExecutor
    helper_executor = HelperExecutor(helper_registry)
    EXECUTOR_AVAILABLE = True
except Exception:
    EXECUTOR_AVAILABLE = False
    helper_executor = None

logger = logging.getLogger(__name__)

# Main API router
router_api = APIRouter()

# Include all modular routers
router_api.include_router(health_router)
router_api.include_router(helpers_router)
router_api.include_router(agents_router)
router_api.include_router(shortcut_router)
router_api.include_router(system_router)
router_api.include_router(router_router)

# Legacy route models for compatibility
class RouteRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    route: Optional[str] = None  # gen, act, or auto-detect
    helper_id: Optional[str] = None
    execute: bool = False

class RouteResponse(BaseModel):
    status: str
    route_used: str
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    session_id: str
    timestamp: str

# Main routing endpoint for backward compatibility
@router_api.post("/route", response_model=RouteResponse)
async def main_route(
    request: RouteRequest,
    fastapi_request: Request,
    response: Response,
    csrf_valid: bool = Depends(verify_csrf_token)
):
    """
    Main TinyIntent routing endpoint.

    Routes text input through SmallIntent model and executes appropriate actions.
    This is the core endpoint that powers the entire TinyIntent system.

    Flow:
    1. Validate inputs
    2. Route through SmallIntent model (or use provided route)
    3. If act route: execute helper (preview or execute mode)
    4. If gen route: return routing info for generation
    """
    start_time = time.time()

    try:
        # Validate inputs
        validated_text = validate_text_input(request.text, max_length=2000, field_name="text")

        validated_session_id = "main-session"
        if request.session_id:
            validated_session_id = validate_identifier(request.session_id, field_name="session_id")

        validated_route = None
        if request.route:
            if request.route not in ["gen", "act", "auto"]:
                raise ValidationError("route must be 'gen', 'act', or 'auto'", "route", request.route)
            validated_route = request.route

        validated_helper_id = None
        if request.helper_id:
            validated_helper_id = validate_identifier(request.helper_id, field_name="helper_id")

        # Step 1: Route through SmallIntent model (unless route is explicitly specified)
        router_confidence = 0.0
        router_intent = None

        if validated_route is None or validated_route == "auto":
            if ROUTER_AVAILABLE and small_intent_router:
                routing_result = small_intent_router.route_request(
                    validated_text,
                    session_id=validated_session_id
                )
                validated_route = routing_result.get("route", "gen")
                router_confidence = routing_result.get("confidence", 0.0)
                router_intent = routing_result.get("intent")

                # Handle abstain case - fallback to gen
                if validated_route == "abstain":
                    validated_route = "gen"
            else:
                # Router unavailable - default to gen
                validated_route = "gen"
                router_confidence = 0.5

        # Step 2: Execute based on route
        result_data: Dict[str, Any] = {
            "router_confidence": router_confidence,
            "router_intent": router_intent,
            "execution_mode": "execute" if request.execute else "preview"
        }

        if validated_route == "act":
            # Action route - execute helper
            if not EXECUTOR_AVAILABLE or not helper_executor:
                raise HTTPException(
                    status_code=503,
                    detail="Helper executor not available"
                )

            # Determine which helper to use
            helper_id = validated_helper_id or router_intent
            if not helper_id:
                # Try to infer helper from intent
                helper_id = _infer_helper_from_text(validated_text)

            if helper_id:
                try:
                    helper_input = {"text": validated_text}

                    if request.execute:
                        # Execute mode
                        execution_result = helper_executor.execute(
                            helper_id=helper_id,
                            input_data=helper_input,
                            session_id=validated_session_id
                        )
                    else:
                        # Preview mode
                        execution_result = helper_executor.preview(
                            helper_id=helper_id,
                            input_data=helper_input,
                            session_id=validated_session_id
                        )

                    result_data["helper_used"] = helper_id
                    result_data["helper_result"] = execution_result

                except ValueError as e:
                    # Helper validation error
                    result_data["helper_error"] = str(e)
                    result_data["helper_used"] = helper_id

            else:
                result_data["helper_error"] = "No matching helper found for intent"

        # Calculate latency
        latency_ms = (time.time() - start_time) * 1000
        result_data["latency_ms"] = round(latency_ms, 2)

        return RouteResponse(
            status="success",
            route_used=validated_route,
            text=f"Routed: {validated_text[:50]}..." if len(validated_text) > 50 else f"Routed: {validated_text}",
            data=result_data,
            session_id=validated_session_id,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )

    except ValidationError as e:
        logger.warning("Input validation failed", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in main route")
        raise HTTPException(status_code=500, detail="Internal server error")


def _infer_helper_from_text(text: str) -> Optional[str]:
    """Infer helper ID from text using keyword matching."""
    text_lower = text.lower()

    # Map keywords to helpers
    helper_mappings = {
        "weather": ["weather", "temperature", "forecast", "rain", "sunny", "cold", "hot"],
        "system_monitor": ["cpu", "memory", "disk", "system", "performance", "load"],
        "network_monitor": ["network", "bandwidth", "ping", "latency", "connection"],
        "bot_guard": ["bot", "trading", "position", "trade", "crypto", "bitcoin"],
        "log_tailer": ["log", "logs", "error", "tail", "debug"],
        "traffic": ["traffic", "commute", "route", "driving"],
    }

    for helper_id, keywords in helper_mappings.items():
        if any(keyword in text_lower for keyword in keywords):
            return helper_id

    return None

# Root endpoint
@router_api.get("/")
async def root():
    """Root endpoint showing API information."""
    return {
        "service": "TinyIntent Bridge API",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": {
            "health": "/health, /health/ready",
            "helpers": "/helpers, /helpers/health",
            "agents": "/agents/lifecycle, /agents/create",
            "shortcut": "/shortcut/ping, /shortcut/route",
            "system": "/system/doctor, /system/emergency/kill",
            "router": "/router/train_summary, /router/metrics",
            "main": "/route"
        },
        "documentation": "/docs"
    }


# CSRF token endpoint
@router_api.get("/csrf-token")
async def get_csrf_token_endpoint(request: Request):
    """Get a CSRF token for state-changing operations."""
    session_id = request.headers.get("X-Session-ID", "default")
    csrf_token = get_csrf_token(session_id)
    
    return {
        "csrf_token": csrf_token,
        "session_id": session_id,
        "expires_in": 3600,  # 1 hour
        "usage": "Include as X-CSRF-Token header in POST/PUT/DELETE requests"
    }