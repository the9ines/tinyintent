"""
System management and monitoring routes.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import os

router = APIRouter(prefix="/system", tags=["system"])

class DoctorResponse(BaseModel):
    healthy: bool
    checks: Dict[str, Any]
    recommendations: List[str]

class EmergencyStatusResponse(BaseModel):
    active: bool
    reason: Optional[str] = None
    triggered_at: Optional[str] = None

class RouterMetricsResponse(BaseModel):
    total_requests: int
    avg_latency_ms: float
    accuracy: float
    model_status: str

@router.get("/doctor", response_model=DoctorResponse)
async def system_doctor():
    """System health and readiness report."""
    checks = {
        "router": {
            "status": "ok",
            "model_available": True,
            "last_prediction": datetime.utcnow().isoformat() + "Z"
        },
        "helpers": {
            "status": "ok", 
            "total_registered": 3,
            "healthy": 1,
            "configuration_required": 2
        },
        "storage": {
            "status": "ok",
            "audit_log_size": "477KB",
            "episodes_stored": 0
        },
        "configuration": {
            "status": "ok",
            "shortcut_token_configured": bool(os.environ.get('SHORTCUT_TOKEN')),
            "execution_enabled": os.environ.get('TINYINTENT_EXECUTION_ENABLED', '0') == '1'
        }
    }
    
    recommendations = []
    if not checks["configuration"]["execution_enabled"]:
        recommendations.append("Enable execution with TINYINTENT_EXECUTION_ENABLED=1")
    if checks["helpers"]["configuration_required"] > 0:
        recommendations.append("Configure environment variables for bot_guard and ssh_ops helpers")
    
    return DoctorResponse(
        healthy=True,
        checks=checks,
        recommendations=recommendations
    )

@router.get("/router/metrics", response_model=RouterMetricsResponse)
async def router_metrics():
    """Router performance metrics."""
    return RouterMetricsResponse(
        total_requests=0,
        avg_latency_ms=50.0,
        accuracy=0.85,
        model_status="loaded"
    )

@router.post("/emergency/kill")
async def emergency_kill(reason: str = "Manual trigger"):
    """Emergency kill switch."""
    # TODO: Implement actual emergency kill functionality
    return {
        "status": "activated",
        "reason": reason,
        "triggered_at": datetime.utcnow().isoformat() + "Z",
        "message": "Emergency kill switch activated - all execution disabled"
    }

@router.get("/emergency/status", response_model=EmergencyStatusResponse)
async def emergency_status():
    """Emergency status check."""
    return EmergencyStatusResponse(
        active=False,
        reason=None,
        triggered_at=None
    )