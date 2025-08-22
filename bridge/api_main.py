"""
TinyIntent Bridge API - Streamlined Main Routes

Modular, clean API structure replacing the monolithic api_routes.py.
"""

from fastapi import APIRouter, Request, HTTPException, Response
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
async def main_route(request: RouteRequest, fastapi_request: Request, response: Response):
    """
    Main TinyIntent routing endpoint.
    
    Routes text input through SmallIntent model and executes appropriate actions.
    This is the core endpoint that powers the entire TinyIntent system.
    """
    try:
        # TODO: Integrate with actual router and helper execution
        mock_response = {
            "status": "success",
            "route_used": request.route or ("act" if request.helper_id else "gen"),
            "text": f"Processed: {request.text}",
            "data": {
                "router_confidence": 0.85,
                "helper_used": request.helper_id,
                "execution_mode": "execute" if request.execute else "preview"
            },
            "session_id": request.session_id or "main-session",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        return RouteResponse(**mock_response)
        
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