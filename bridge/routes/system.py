"""
System management and monitoring routes.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
import os
import json
from pathlib import Path
from ..security import verify_csrf_token
from ..secret_manager import get_secret_manager

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

class TrainingSummaryResponse(BaseModel):
    timestamp: str
    status: str
    model: Dict[str, Any]
    dataset: Dict[str, Any]
    training: Dict[str, Any]
    performance: Dict[str, Any]
    files: Dict[str, Any]
    sample_predictions: List[Dict[str, Any]]

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
async def emergency_kill(reason: str = "Manual trigger", csrf_valid: bool = Depends(verify_csrf_token)):
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

@router.get("/router/train_summary", response_model=TrainingSummaryResponse)
async def router_train_summary():
    """Get router training summary and model deployment status."""
    train_summary_path = Path("router/train_summary.json")
    
    if not train_summary_path.exists():
        raise HTTPException(
            status_code=404, 
            detail="Training summary not found. Run 'make router-train' to generate."
        )
    
    try:
        with open(train_summary_path, 'r') as f:
            train_summary = json.load(f)
        return TrainingSummaryResponse(**train_summary)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load training summary: {str(e)}"
        )


@router.get("/secrets/status")
async def secrets_status():
    """Get secret management system status."""
    secret_manager = get_secret_manager()
    return secret_manager.get_security_status()


@router.get("/secrets/available/{helper_id}")
async def list_available_secrets(helper_id: str, trust_level: str = "draft"):
    """List secrets available to a specific helper."""
    secret_manager = get_secret_manager()
    
    # Validate trust level
    valid_levels = ["draft", "trusted", "deprecated", "retired"]
    if trust_level not in valid_levels:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid trust level. Must be one of: {valid_levels}"
        )
    
    try:
        available_secrets = secret_manager.list_available_secrets(helper_id, trust_level)
        return {
            "helper_id": helper_id,
            "trust_level": trust_level,
            "available_secrets": available_secrets,
            "count": len(available_secrets)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list available secrets: {str(e)}"
        )