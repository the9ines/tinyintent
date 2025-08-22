"""
TinyIntent Bridge API - Streamlined Main Routes

Modular, clean API structure replacing the monolithic api_routes.py.
"""

from fastapi import APIRouter, Request, HTTPException, Response, Depends
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import logging

# Import modular route handlers
from .routes.health import router as health_router
from .routes.helpers import router as helpers_router  
from .routes.agents import router as agents_router
from .routes.shortcut import router as shortcut_router
from .routes.system import router as system_router
from .routes.router import router as router_router
from .security import get_csrf_token, verify_csrf_token
from .validation import validate_text_input, validate_identifier, ValidationError

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
    """
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
        
        # TODO: Integrate with actual router and helper execution
        mock_response = {
            "status": "success",
            "route_used": validated_route or ("act" if validated_helper_id else "gen"),
            "text": f"Processed: {validated_text}",
            "data": {
                "router_confidence": 0.85,
                "helper_used": validated_helper_id,
                "execution_mode": "execute" if request.execute else "preview"
            },
            "session_id": validated_session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        return RouteResponse(**mock_response)
        
    except ValidationError as e:
        logger.warning("Input validation failed", error=str(e), field=e.field)
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    except Exception as e:
        logger.exception("Error in main route")
        raise HTTPException(status_code=500, detail="Internal server error")

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