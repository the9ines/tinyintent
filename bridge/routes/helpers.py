"""
Helper management and execution routes.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime

router = APIRouter(prefix="/helpers", tags=["helpers"])

class HelperInfo(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    category: str
    risk_level: str

class HelperListResponse(BaseModel):
    helpers: List[HelperInfo]
    count: int

class HelperHealthResponse(BaseModel):
    helper_id: str
    status: str
    last_check: str
    details: Optional[Dict[str, Any]] = None

@router.get("/", response_model=HelperListResponse)
async def list_helpers():
    """List all available helpers."""
    # TODO: Integrate with actual helper registry
    mock_helpers = [
        HelperInfo(
            id="log_tailer",
            name="Log Tailer", 
            description="Retrieve and filter log entries",
            enabled=True,
            category="monitoring",
            risk_level="low"
        ),
        HelperInfo(
            id="bot_guard",
            name="Bot Guard",
            description="Crypto trading bot management", 
            enabled=True,
            category="trading",
            risk_level="high"
        ),
        HelperInfo(
            id="ssh_ops", 
            name="SSH Operations",
            description="Remote server management",
            enabled=True,
            category="infrastructure", 
            risk_level="high"
        )
    ]
    
    return HelperListResponse(
        helpers=mock_helpers,
        count=len(mock_helpers)
    )

@router.post("/reload")
async def reload_helpers():
    """Reload helper registry."""
    # TODO: Implement actual helper reload
    return {"status": "success", "message": "Helper registry reloaded"}

@router.get("/health", response_model=List[HelperHealthResponse])
async def check_all_helper_health():
    """Check health of all helpers."""
    # TODO: Implement actual health checks
    mock_health = [
        HelperHealthResponse(
            helper_id="log_tailer",
            status="healthy",
            last_check=datetime.utcnow().isoformat() + "Z"
        ),
        HelperHealthResponse(
            helper_id="bot_guard", 
            status="configuration_required",
            last_check=datetime.utcnow().isoformat() + "Z",
            details={"missing_env": ["EXCHANGE_API_KEY"]}
        ),
        HelperHealthResponse(
            helper_id="ssh_ops",
            status="configuration_required", 
            last_check=datetime.utcnow().isoformat() + "Z",
            details={"missing_env": ["SSH_HOST"]}
        )
    ]
    
    return mock_health

@router.get("/health/{helper_id}", response_model=HelperHealthResponse)
async def check_helper_health(helper_id: str):
    """Check health of a specific helper."""
    # TODO: Implement actual health check for specific helper
    if helper_id not in ["log_tailer", "bot_guard", "ssh_ops"]:
        raise HTTPException(status_code=404, detail="Helper not found")
    
    return HelperHealthResponse(
        helper_id=helper_id,
        status="healthy" if helper_id == "log_tailer" else "configuration_required",
        last_check=datetime.utcnow().isoformat() + "Z"
    )