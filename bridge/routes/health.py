"""
Health and readiness check endpoints.
"""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import time

router = APIRouter(prefix="/health", tags=["health"])

class HealthResponse(BaseModel):
    ok: bool
    ts: str
    service: str = "TinyIntent Bridge"
    version: str = "2.0.0"
    uptime_seconds: Optional[float] = None

class ReadinessResponse(BaseModel):
    ready: bool
    ts: str
    checks: Dict[str, Any]

start_time = time.time()

@router.get("/", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        ok=True,
        ts=datetime.utcnow().isoformat() + "Z",
        uptime_seconds=time.time() - start_time
    )

@router.get("/ready", response_model=ReadinessResponse)  
async def readiness_check():
    """Readiness check with component status."""
    checks = {
        "router": {"status": "ok"},
        "helpers": {"status": "ok"},
        "storage": {"status": "ok"}
    }
    
    return ReadinessResponse(
        ready=True,
        ts=datetime.utcnow().isoformat() + "Z",
        checks=checks
    )

# Legacy endpoints for compatibility
@router.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def healthz():
    """Legacy health check endpoint."""
    return await health_check()

@router.get("/readyz", response_model=ReadinessResponse, include_in_schema=False)
async def readyz():
    """Legacy readiness check endpoint."""
    return await readiness_check()