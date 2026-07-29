"""
Agent lifecycle management routes (M10.x features).
"""

import json
import re
from datetime import datetime
from pathlib import Path

import structlog
import yaml
from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from ..security import verify_csrf_token
from ..validation import validate_identifier, validate_text_input, validate_enum_value, ValidationError

# Import helper registry and provenance
try:
    from helpers.sdk import helper_registry
    from ..provenance import generate_and_save_provenance
    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False
    helper_registry = None
    generate_and_save_provenance = None

logger = structlog.get_logger()

router = APIRouter(prefix="/agents", tags=["agents"])

# Path to helpers directory
HELPERS_DIR = Path(__file__).parent.parent.parent / "helpers"

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
    """
    Create a new helper agent from specification.

    Creates the helper directory structure with:
    - helper.yaml: Main manifest file
    - input.schema.json: Input validation schema
    - output.schema.json: Output validation schema
    - main.py: Stub implementation
    - provenance.json: Cryptographic provenance record

    New helpers start in 'draft' lifecycle state.
    """
    try:
        # Validate inputs
        name = validate_text_input(request.name, max_length=100, field_name="name")
        description = validate_text_input(request.description, max_length=500, field_name="description")
        category = validate_identifier(request.category, field_name="category")

        # Validate capabilities
        if not isinstance(request.capabilities, list):
            raise ValidationError("capabilities must be a list", "capabilities", request.capabilities)

        # Allowed capability types
        allowed_capabilities = {"network", "filesystem", "database", "shell", "preview", "execute"}
        validated_capabilities = []
        for i, cap in enumerate(request.capabilities):
            validated_cap = validate_identifier(cap, field_name=f"capabilities[{i}]")
            if validated_cap not in allowed_capabilities:
                raise ValidationError(
                    f"Invalid capability '{validated_cap}'. Allowed: {', '.join(sorted(allowed_capabilities))}",
                    f"capabilities[{i}]",
                    validated_cap
                )
            validated_capabilities.append(validated_cap)

        # Generate safe agent ID
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())
        agent_id = f"generated_{safe_name}"

        # Check if helper already exists
        helper_dir = HELPERS_DIR / agent_id
        if helper_dir.exists():
            raise HTTPException(
                status_code=409,
                detail=f"Helper '{agent_id}' already exists. Use a different name or delete the existing helper."
            )

        # Create helper directory
        helper_dir.mkdir(parents=True, mode=0o755)

        try:
            # Generate helper.yaml manifest
            helper_manifest = {
                "purpose": description,
                "schema": {
                    "input": "./input.schema.json",
                    "output": "./output.schema.json"
                },
                "capabilities": {
                    "preview": "preview" in validated_capabilities or True,
                    "execute": "execute" in validated_capabilities or True,
                    "emergency_close": False
                },
                "sandbox": {
                    "commands": ["/usr/bin/python3", "./main.py"],
                    "network": "enabled" if "network" in validated_capabilities else "disabled",
                    "timeouts": [
                        {"name": "default", "seconds": 5},
                        {"name": "execute", "seconds": 10}
                    ],
                    "cpu": {"max_ms": 2000},
                    "mem": {"max_mb": 64}
                },
                "environment": {
                    "required": [],
                    "optional": []
                },
                "metadata": {
                    "version": request.manifest.get("version", "1.0.0"),
                    "author": request.manifest.get("author", "API"),
                    "risk_level": request.manifest.get("risk_level", "medium"),
                    "audit_required": True
                }
            }

            # Write helper.yaml
            with open(helper_dir / "helper.yaml", 'w') as f:
                yaml.dump(helper_manifest, f, default_flow_style=False, sort_keys=False)

            # Generate input schema
            input_schema = request.manifest.get("input_schema", {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Input text"}
                },
                "required": ["text"]
            })
            with open(helper_dir / "input.schema.json", 'w') as f:
                json.dump(input_schema, f, indent=2)

            # Generate output schema
            output_schema = request.manifest.get("output_schema", {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "result": {"type": "string", "description": "Output result"},
                    "success": {"type": "boolean"}
                },
                "required": ["result", "success"]
            })
            with open(helper_dir / "output.schema.json", 'w') as f:
                json.dump(output_schema, f, indent=2)

            # Generate stub main.py
            main_py_content = f'''#!/usr/bin/env python3
"""
{name} - Generated Helper

{description}

Category: {category}
Capabilities: {', '.join(validated_capabilities) if validated_capabilities else 'none'}

This is a generated stub. Implement your logic in the execute() function.
"""

import json
import sys
from typing import Dict, Any


def preview(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Preview the action without executing."""
    return {{
        "preview": True,
        "description": f"Would process: {{input_data.get('text', '')}}",
        "estimated_time_ms": 100
    }}


def execute(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """Execute the helper action."""
    # TODO: Implement your helper logic here
    text = input_data.get("text", "")

    return {{
        "result": f"Processed: {{text}}",
        "success": True
    }}


def main():
    """Main entry point for sandbox execution."""
    if len(sys.argv) < 2:
        print(json.dumps({{"error": "No input provided"}}))
        sys.exit(1)

    try:
        input_data = json.loads(sys.argv[1])
        mode = input_data.get("_mode", "execute")

        if mode == "preview":
            result = preview(input_data)
        else:
            result = execute(input_data)

        print(json.dumps(result))

    except json.JSONDecodeError as e:
        print(json.dumps({{"error": f"Invalid JSON input: {{e}}"}}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({{"error": str(e), "success": False}}))
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
            with open(helper_dir / "main.py", 'w') as f:
                f.write(main_py_content)

            # Generate provenance
            if REGISTRY_AVAILABLE and generate_and_save_provenance:
                ok, reason, provenance_data = generate_and_save_provenance(
                    agent_id, helper_dir, "api_create"
                )
                if not ok:
                    logger.warning("Failed to generate provenance", helper_id=agent_id, reason=reason)
            else:
                logger.warning("Provenance generation unavailable", helper_id=agent_id)

            # Reload registry to pick up new helper
            if REGISTRY_AVAILABLE and helper_registry:
                try:
                    helper_registry.reload()
                except Exception as reload_error:
                    logger.warning("Failed to reload registry", error=str(reload_error))

            logger.info("Helper created successfully",
                       helper_id=agent_id,
                       category=category,
                       capabilities=validated_capabilities)

            return AgentCreateResponse(
                agent_id=agent_id,
                status="created",
                message=f"Agent '{name}' created successfully in draft state. "
                        f"Implement logic in helpers/{agent_id}/main.py"
            )

        except Exception as e:
            # Clean up on failure
            if helper_dir.exists():
                import shutil
                shutil.rmtree(helper_dir, ignore_errors=True)
            raise

    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Validation error: {e}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create agent", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to create agent: {str(e)}")

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