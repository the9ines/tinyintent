"""
Agent lifecycle management routes (M10.x features).
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime
from ..security import verify_csrf_token
from ..validation import validate_identifier, validate_text_input, validate_enum_value, ValidationError
import re

router = APIRouter(prefix="/agents", tags=["agents"])

class AgentCreateRequest(BaseModel):
    name: str
    description: str
    category: str
    capabilities: List[str]
    manifest: Dict[str, Any]

class AgentCreateResponse(BaseModel):
    agent_id: str
    status: str
    message: str

class LifecycleState(BaseModel):
    state: str  # draft, trusted, deprecated, retired
    since: str
    notes: Optional[str] = None

class LifecycleResponse(BaseModel):
    helper_id: str
    lifecycle: LifecycleState
    metrics: Dict[str, Any]

@router.post("/create", response_model=AgentCreateResponse)
async def create_agent(request: AgentCreateRequest, csrf_valid: bool = Depends(verify_csrf_token)):
    """Create a new helper agent from specification."""
    try:
        # Validate inputs
        name = validate_text_input(request.name, max_length=100, field_name="name")
        description = validate_text_input(request.description, max_length=500, field_name="description")
        category = validate_identifier(request.category, field_name="category")
        
        # Validate capabilities
        if not isinstance(request.capabilities, list):
            raise ValidationError("capabilities must be a list", "capabilities", request.capabilities)
        
        validated_capabilities = []
        for i, cap in enumerate(request.capabilities):
            validated_cap = validate_identifier(cap, field_name=f"capabilities[{i}]")
            validated_capabilities.append(validated_cap)
        
        # Generate safe agent ID
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())
        agent_id = f"generated_{safe_name}"
        
        # TODO: Implement actual agent creation
        return AgentCreateResponse(
            agent_id=agent_id,
            status="created",
            message=f"Agent '{name}' created successfully"
        )
        
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/lifecycle/{helper_id}", response_model=LifecycleResponse)
async def get_agent_lifecycle(helper_id: str):
    """Get agent lifecycle status and metrics."""
    try:
        # Validate helper_id
        validated_helper_id = validate_identifier(helper_id, field_name="helper_id")
        
        # TODO: Implement actual lifecycle management
        if validated_helper_id not in ["log_tailer", "bot_guard", "ssh_ops"]:
            raise HTTPException(status_code=404, detail="Agent not found")
            
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    
    return LifecycleResponse(
        helper_id=helper_id,
        lifecycle=LifecycleState(
            state="trusted",
            since="2024-12-15T00:00:00Z",
            notes="Core helper - production ready"
        ),
        metrics={
            "executions_total": 0,
            "success_rate": 0.0,
            "avg_latency_ms": 0,
            "last_execution": None
        }
    )

@router.post("/lifecycle/set")
async def set_agent_lifecycle(helper_id: str, state: str, notes: Optional[str] = None, csrf_valid: bool = Depends(verify_csrf_token)):
    """Set agent lifecycle state."""
    try:
        # Validate inputs
        validated_helper_id = validate_identifier(helper_id, field_name="helper_id")
        validated_state = validate_enum_value(
            state, 
            ["draft", "trusted", "deprecated", "retired"], 
            field_name="state"
        )
        
        validated_notes = None
        if notes:
            validated_notes = validate_text_input(notes, max_length=500, field_name="notes")
        
        # TODO: Implement actual lifecycle state management
        return {
            "helper_id": validated_helper_id,
            "old_state": "trusted",
            "new_state": validated_state,
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "notes": validated_notes
        }
        
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")

@router.post("/promote")
async def promote_agent(helper_id: str, from_stage: str = "draft", csrf_valid: bool = Depends(verify_csrf_token)):
    """Promote staged agent to trusted status."""
    # TODO: Implement actual agent promotion
    return {
        "helper_id": helper_id,
        "from_stage": from_stage,
        "to_stage": "trusted",
        "promoted_at": datetime.utcnow().isoformat() + "Z"
    }

@router.get("/provenance/{helper_id}")
async def get_agent_provenance(helper_id: str):
    """Get agent provenance and verification status."""
    # TODO: Implement actual provenance checking
    return {
        "helper_id": helper_id,
        "verified": True,
        "signature": "mock_signature_hash",
        "created_at": "2024-12-15T00:00:00Z",
        "created_by": "system",
        "file_hash": "mock_file_hash"
    }