"""
TinyIntent API Routes

Defines all FastAPI endpoints for the bridge service.
This module uses an APIRouter to keep the main application file clean.

M9.1: API Documentation for Operators

Major Endpoints:
- GET  /healthz                    - Basic health check
- GET  /readyz                     - Readiness check  
- POST /route                      - Main routing endpoint (gen/act)
- GET  /helpers                    - List available helpers
- POST /helpers/reload             - Reload helper registry
- GET  /helpers/health             - Check all helper health
- GET  /helpers/health/{helper_id} - Check specific helper health
- POST /agents/create              - Create new helper from specification
- POST /agents/suggest             - Suggest agents from abstain patterns
- POST /agents/create_from_suggestion - Create agent from suggestion
- POST /agents/lifecycle/set       - Set helper lifecycle state
- GET  /agents/lifecycle/{helper_id} - Get helper lifecycle status and metrics
- GET  /agents/prune_suggestions   - Get suggestions for helpers to deprecate/retire
- POST /agents/promote             - Promote staged agent to trusted status (M10.4)
- GET  /agents/provenance/{helper_id} - Get agent provenance and verification status (M10.5)
- GET  /doctor                     - System health & readiness report
- GET  /router/metrics             - Router performance metrics
- POST /gen/cancel                 - Cancel generation request
- POST /emergency/kill             - Emergency kill switch
- GET  /emergency/status           - Emergency status check

Authentication: Bearer token via Authorization header
Rate Limits: Configurable per-session and global limits
Security: All helpers require approval for execution by default
"""

from fastapi import APIRouter, Depends, Request, HTTPException, Response
from pydantic import BaseModel, validator
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import json
import time
import random
import asyncio

from tinyintent.bridge.security import verify_auth
from tinyintent.bridge.gen_client import async_ollama_client, generation_task_manager
from tinyintent.bridge.router_client import router
from tinyintent.bridge.resolve import helper_resolver, model_resolver
from tinyintent.helpers.sdk import helper_executor, helper_registry
from tinyintent.data.episodes.logger import episode_logger
from tinyintent.bridge.security import rate_limiter, emergency_kill
from tinyintent.bridge.logs.audit import get_audit_logger
from tinyintent.bridge.agent_generator import agent_generator
from tinyintent.data.episodes.episodes import episode_miner, agent_staging_storage
from tinyintent.helpers.manifest import validate_agent_spec, infer_min_capabilities

# M10.7: Import agent quota manager
from tinyintent.bridge.quota import agent_quota_manager

# M11.0: Import shortcut formatting utilities
from tinyintent.bridge.shortcut_format import (
    sanitize_short_input, 
    format_shortcut_response, 
    get_shortcut_error_response
)

router_api = APIRouter()

# Pydantic Models for API
class RouteRequest(BaseModel):
    text: str
    route: Optional[str] = "auto"
    llm_pref: Optional[str] = None
    llm_model: Optional[str] = None
    session_id: Optional[str] = None
    helper_id: Optional[str] = None
    helper_input: Optional[Dict[str, Any]] = None
    execute: Optional[bool] = False
    approval_token: Optional[str] = None
    idempotency_key: Optional[str] = None
    override_route: Optional[str] = None

    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('text field cannot be empty')
        return v

class RouteResponse(BaseModel):
    status: str
    route_used: str
    text_response: Optional[str] = None
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None
    session_id: str
    action: Optional[str] = None
    helper_id: Optional[str] = None
    preview_json: Optional[Dict[str, Any]] = None
    approval_token: Optional[str] = None
    execution_enabled: Optional[bool] = None  # M7.5: Execution control visibility
    reflection: Optional[Dict[str, Any]] = None
    veto_reason: Optional[str] = None
    reflection_error: Optional[str] = None
    idempotent: Optional[bool] = None

class FeedbackRequest(BaseModel):
    session_id: str
    feedback: str

class FeedbackResponse(BaseModel):
    status: str
    message: str

class GenerationCancelRequest(BaseModel):
    request_id: str
    reason: Optional[str] = "Manual cancellation requested"

class EmergencyKillRequest(BaseModel):
    reason: Optional[str] = "Manual emergency kill triggered"

# M10.3: Agent Staging Models
class AgentStageRequest(BaseModel):
    helper_id: str
    mode: str = "shadow"  # "shadow" only for staging
    match_intent: Optional[str] = None

    @validator('mode')
    def validate_mode(cls, v):
        if v not in ["shadow"]:
            raise ValueError('mode must be "shadow"')
        return v

class AgentCanaryRequest(BaseModel):
    helper_id: str
    pct: float
    match_intent: Optional[str] = None

    @validator('pct')
    def validate_pct(cls, v):
        if not 0 <= v <= 20:
            raise ValueError('pct must be between 0 and 20')
        return v

class AgentUnstageRequest(BaseModel):
    helper_id: str

class AgentStagingResponse(BaseModel):
    status: str
    helper_id: str
    message: str
    config: Optional[Dict[str, Any]] = None

class AgentReportResponse(BaseModel):
    helper_id: str
    report: Dict[str, Any]
    generated_at: str

# M10.4: Agent Promotion Models
class AgentPromoteRequest(BaseModel):
    helper_id: str
    window_hours: Optional[int] = 24

class AgentPromoteResponse(BaseModel):
    status: str
    helper_id: str
    promoted: bool
    message: str
    evaluation: Optional[Dict[str, Any]] = None
    previous_state: Optional[str] = None
    new_state: Optional[str] = None

# M10.5: Agent Provenance Models
class AgentProvenanceResponse(BaseModel):
    helper_id: str
    provenance_ok: bool
    reason: str
    provenance_data: Optional[Dict[str, Any]] = None
    verification_details: Optional[Dict[str, Any]] = None
    generated_at: str

# M11.0: Shortcut Models
class ShortcutRouteRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    mode: str = "preview"  # "preview" or "execute"
    return_format: str = "text"  # "text" or "json" (using return_format to avoid keyword conflict)
    
    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('text field cannot be empty')
        return v
    
    @validator('mode')
    def mode_must_be_valid(cls, v):
        if v not in ["preview", "execute"]:
            raise ValueError('mode must be "preview" or "execute"')
        return v
    
    @validator('return_format')
    def return_format_must_be_valid(cls, v):
        if v not in ["text", "json"]:
            raise ValueError('return_format must be "text" or "json"')
        return v

class ShortcutRouteResponse(BaseModel):
    speak: str
    truncated: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    message: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

class ShortcutPingResponse(BaseModel):
    ok: bool
    ts: str
    service: str = "TinyIntent Bridge"
    version: str = "2.0.0"

# API Endpoints
@router_api.post("/route", response_model=RouteResponse)
async def route_request_endpoint(request: RouteRequest, fastapi_request: Request, response: Response, auth: bool = Depends(verify_auth)):
    # Get idempotency key from header or request body (prefer body)
    idempotency_key_header = fastapi_request.headers.get("X-Idempotency-Key")
    idempotency_key = request.idempotency_key or idempotency_key_header
    
    # Get or create session ID
    session_id = request.session_id
    if not session_id:
        session_id = experience_store.create_session()
    elif not experience_store.session_exists(session_id):
        experience_store.create_session(session_id)
    
    # Update session activity
    experience_store.update_session_activity(session_id)
    
    # Rate limiting check (M6.6)
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        # Log rate limit violation
        audit_logger = get_audit_logger()
        if audit_logger:
            audit_logger.log_entry({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                "action": "rate_limit",
                "session_id": session_id,
                "success": False,
                "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown",
                "user_agent": fastapi_request.headers.get("User-Agent", "unknown"),
                "route": request.route,
                "text_length": len(request.text) if request.text else 0,
                "retry_after": retry_after
            })
        
        # Log failed episode for rate limiting
        episode_logger.log_episode(
            session_id=session_id,
            action="rate_limited",
            helper_id="N/A",
            input_data={"route": request.route, "text_length": len(request.text) if request.text else 0},
            status_code=429,
            success=False,
            error_code="RATE_LIMIT_EXCEEDED"
        )
        
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit-Session": str(rate_limiter.session_limit),
                "X-RateLimit-Limit-Global": str(rate_limiter.global_limit),
                "X-RateLimit-Window": str(rate_limiter.window_seconds)
            }
        )
    
    # Determine which model to use
    model_to_use = None
    if request.llm_model:
        model_to_use = request.llm_model
    elif request.llm_pref:
        model_to_use = model_resolver.get_model(request.llm_pref)
        if not model_to_use:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model preference: {request.llm_pref}"
            )
    else:
        # Default to small model
        model_to_use = model_resolver.get_model("small")
    
    if not model_to_use:
        raise HTTPException(
            status_code=500,
            detail="No suitable model configured"
        )
    
    # M7.0: Use SmallIntent router for automatic routing when route is "auto"
    if request.route == "auto":
        try:
            routing_result = router.route_request(request.text)
            determined_route = routing_result["route"]
            intent = routing_result["intent"]
            confidence = routing_result["confidence"]
            
            # M7.1: Handle abstain decisions
            if determined_route == "abstain":
                abstain_reason = routing_result.get("abstain_reason", "low_confidence")
                abstain_reason_detail = routing_result.get("abstain_reason_detail", "Low confidence routing decision")
                suggested_route = routing_result.get("suggested_route", "gen")
                
                # M7.4: Check for operator override
                if request.override_route:
                    determined_route = request.override_route
                    confidence = 0.9
                    intent = f"{intent}_override"
                else:
                    return RouteResponse(
                        status="abstain",
                        route_used="abstain",
                        text_response=f"Router abstained: {abstain_reason_detail}. Consider being more specific or try manual routing with route=\"{suggested_route}\".",
                        session_id=session_id,
                        execution_enabled=emergency_kill.is_execution_enabled(),
                        reflection={
                            "abstain_reason": abstain_reason,
                            "abstain_reason_detail": abstain_reason_detail,
                            "suggested_route": suggested_route,
                            "confidence": confidence,
                            "intent": intent
                        }
                    )
            
            actual_route = determined_route
            
        except Exception as e:
            actual_route = "gen"
            intent = "general_query"
            confidence = 0.5
    else:
        actual_route = request.route
        intent = None
        confidence = None
    
    if actual_route == "gen":
        try:
            response_text, latency_ms = await async_ollama_client.generate_async(
                model_to_use, 
                request.text,
                session_id=session_id
            )
            
            return RouteResponse(
                status="success",
                route_used="gen",
                text_response=response_text,
                model_used=model_to_use,
                latency_ms=latency_ms,
                session_id=session_id,
                execution_enabled=emergency_kill.is_execution_enabled()
            )
            
        except HTTPException as e:
            raise e
            
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during generation: {str(e)}"
            )
    
    elif actual_route == "act":
        try:
            if not helper_executor:
                raise HTTPException(status_code=503, detail="Helpers framework not available")

            if request.execute and not emergency_kill.is_execution_enabled():
                raise HTTPException(status_code=503, detail="Execution disabled")

            helper_id = request.helper_id or "bot_guard"
            helper_input = request.helper_input or {}

            # M10.2: Lifecycle enforcement - check if helper can be routed
            is_deprecated = False
            if helper_registry and helper_id in helper_registry.registry_entries:
                helper_entry = helper_registry.registry_entries[helper_id]
                
                # Block retired helpers with 410 Gone
                if helper_entry.is_retired():
                    # Audit log the attempted use of retired helper
                    audit_logger = get_audit_logger()
                    if audit_logger:
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "helper_lifecycle_violation",
                            "session_id": session_id,
                            "helper_id": helper_id,
                            "lifecycle_state": "retired",
                            "violation_type": "retired_helper_access",
                            "success": False,
                            "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown"
                        })
                    
                    raise HTTPException(
                        status_code=410,
                        detail=f"Helper '{helper_id}' has been retired and is no longer available",
                        headers={"X-Helper-Status": "retired"}
                    )
                
                # Warn about deprecated helpers but allow execution
                if helper_entry.is_deprecated():
                    is_deprecated = True
                    # Audit log the use of deprecated helper
                    audit_logger = get_audit_logger()
                    if audit_logger:
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "helper_lifecycle_warning",
                            "session_id": session_id,
                            "helper_id": helper_id,
                            "lifecycle_state": "deprecated",
                            "warning_type": "deprecated_helper_usage",
                            "success": True,
                            "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown"
                        })

            # M10.3: Shadow/Canary execution - run staged helpers in parallel
            await _execute_staging_helpers(request, session_id, actual_route, intent)
            
            # M10.7: Agent Quota & Cost Guardrails - Check quotas before execution
            if request.execute:
                # Check execute quota (both per-minute and daily budget)
                quota_allowed, retry_after, quota_reason = agent_quota_manager.check_execute_quota(helper_id)
                if not quota_allowed:
                    # Log quota violation
                    audit_logger = get_audit_logger()
                    if audit_logger:
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "agent_quota_violation",
                            "session_id": session_id,
                            "helper_id": helper_id,
                            "violation_type": quota_reason,
                            "quota_type": "execute",
                            "retry_after": retry_after,
                            "success": False,
                            "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown"
                        })
                    
                    # Log episode for quota violation
                    episode_logger.log_episode(
                        session_id=session_id,
                        action="agent_quota_violation",
                        helper_id=helper_id,
                        input_data={
                            "quota_type": "execute",
                            "violation_type": quota_reason,
                            "retry_after": retry_after
                        },
                        status_code=429 if quota_reason == "exec_per_min_exceeded" else 403,
                        success=False,
                        error_code="AGENT_QUOTA_EXCEEDED"
                    )
                    
                    # Return appropriate HTTP error
                    if quota_reason == "exec_per_min_exceeded":
                        raise HTTPException(
                            status_code=429,
                            detail=f"Agent execution quota exceeded for {helper_id}. Try again later.",
                            headers={
                                "Retry-After": str(retry_after),
                                "X-Quota-Type": "exec_per_min",
                                "X-Helper-ID": helper_id
                            }
                        )
                    else:  # daily_exec_budget_exceeded
                        raise HTTPException(
                            status_code=403,
                            detail=f"Daily execution budget exceeded for {helper_id}. Resets at midnight.",
                            headers={
                                "Retry-After": str(retry_after),
                                "X-Quota-Type": "daily_exec_budget",
                                "X-Helper-ID": helper_id
                            }
                        )
                
                # Record the execute request for quota tracking
                agent_quota_manager.record_execute_request(helper_id)
            else:
                # Check preview quota
                quota_allowed, retry_after = agent_quota_manager.check_preview_quota(helper_id)
                if not quota_allowed:
                    # Log quota violation
                    audit_logger = get_audit_logger()
                    if audit_logger:
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "agent_quota_violation",
                            "session_id": session_id,
                            "helper_id": helper_id,
                            "violation_type": "preview_per_min_exceeded",
                            "quota_type": "preview",
                            "retry_after": retry_after,
                            "success": False,
                            "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown"
                        })
                    
                    # Log episode for quota violation
                    episode_logger.log_episode(
                        session_id=session_id,
                        action="agent_quota_violation",
                        helper_id=helper_id,
                        input_data={
                            "quota_type": "preview",
                            "violation_type": "preview_per_min_exceeded",
                            "retry_after": retry_after
                        },
                        status_code=429,
                        success=False,
                        error_code="AGENT_QUOTA_EXCEEDED"
                    )
                    
                    raise HTTPException(
                        status_code=429,
                        detail=f"Agent preview quota exceeded for {helper_id}. Try again later.",
                        headers={
                            "Retry-After": str(retry_after),
                            "X-Quota-Type": "preview_per_min",
                            "X-Helper-ID": helper_id
                        }
                    )
                
                # Record the preview request for quota tracking
                agent_quota_manager.record_preview_request(helper_id)

            try:
                if request.execute:
                    helper_result = helper_executor.execute(
                        helper_id=helper_id,
                        input_data=helper_input,
                        session_id=session_id,
                        token_id=request.approval_token,
                        idempotency_key=idempotency_key
                    )
                else:
                    helper_result = helper_executor.preview(
                        helper_id=helper_id,
                        input_data=helper_input,
                        session_id=session_id
                    )
            except ValueError as e:
                # M10.5: Handle provenance verification failures
                if hasattr(e, 'error_code') and e.error_code == "PROVENANCE_INVALID":
                    audit_logger.log_entry({
                        "action": "helper_execution_blocked",
                        "helper_id": helper_id,
                        "reason": "PROVENANCE_INVALID",
                        "session_id": session_id,
                        "success": False
                    })
                    
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "PROVENANCE_INVALID",
                            "message": "Helper execution blocked due to provenance verification failure",
                            "helper_id": helper_id,
                            "reason": str(e)
                        }
                    )
                else:
                    # Re-raise other ValueError exceptions
                    raise HTTPException(status_code=400, detail=str(e))
            
            # M10.7: Handle sandbox and capability violations with structured error response
            except Exception as e:
                # Import violation errors here to avoid circular imports
                from tinyintent.helpers.sandbox import SandboxViolationError, CapabilityViolationError
                
                if isinstance(e, SandboxViolationError):
                    # Log sandbox violation to audit and episodes
                    audit_logger.log_entry({
                        "action": "sandbox_violation",
                        "helper_id": helper_id,
                        "session_id": session_id,
                        "violation_type": e.error_code,
                        "details": e.details,
                        "success": False
                    })
                    
                    # M10.7: Log to episodes for violation tracking
                    try:
                        episode_logger.log_helper_violation(
                            session_id=session_id,
                            helper_id=helper_id,
                            violation_type="sandbox",
                            error_code=e.error_code,
                            details=e.details
                        )
                    except Exception:
                        pass  # Don't fail if episode logging fails
                    
                    # M10.7: Return 403 for sandbox violations (security violation)
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "SANDBOX_LIMIT",
                            "detail": f"Exceeded {e.details.get('limit_type', 'resource')} limit",
                            "helper_id": helper_id,
                            "violation": e.error_code,
                            "limits": {
                                k: v for k, v in e.details.items() 
                                if k.endswith('_limit') or k.endswith('_limit_seconds') or k.endswith('_limit_mb')
                            }
                        }
                    )
                
                elif isinstance(e, CapabilityViolationError):
                    # Log capability violation to audit and episodes
                    audit_logger.log_entry({
                        "action": "capability_violation",
                        "helper_id": helper_id,
                        "session_id": session_id,
                        "capability": e.capability,
                        "operation": e.operation,
                        "details": e.details,
                        "success": False
                    })
                    
                    # Log to episodes for violation tracking
                    try:
                        episode_logger.log_helper_violation(
                            session_id=session_id,
                            helper_id=helper_id,
                            violation_type="capability",
                            error_code=e.error_code,
                            details={
                                "capability": e.capability,
                                "operation": e.operation,
                                **e.details
                            }
                        )
                    except Exception:
                        pass  # Don't fail if episode logging fails
                    
                    # Return 403 for capability violations (permission denied)
                    raise HTTPException(
                        status_code=403,
                        detail={
                            "error": "CAPABILITY_VIOLATION",
                            "detail": f"Helper lacks required capability: {e.capability}",
                            "helper_id": helper_id,
                            "capability": e.capability,
                            "operation": e.operation
                        }
                    )
                
                else:
                    # Re-raise other exceptions
                    raise e
            
            # M10.2: Set deprecation header if helper is deprecated
            if is_deprecated:
                response.headers["X-Helper-Deprecated"] = "true"
                response.headers["X-Helper-Status"] = "deprecated"
            
            return RouteResponse(
                status=helper_result.get("status", "success"),
                route_used="act",
                session_id=session_id,
                action=helper_result.get("action"),
                helper_id=helper_id,
                preview_json=helper_result.get("preview_json") or helper_result.get("result"),
                approval_token=helper_result.get("approval_token"),
                execution_enabled=emergency_kill.is_execution_enabled()
            )
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown route: {actual_route}")

@router_api.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest, auth: bool = Depends(verify_auth)):
    return {"status": "success", "message": "Feedback received."}

@router_api.post("/admin/reload-models")
async def reload_models(auth: bool = Depends(verify_auth)):
    model_resolver.reload()
    return {"status": "success", "message": "Models reloaded"}

@router_api.post("/admin/reload-helpers")
async def reload_helpers(auth: bool = Depends(verify_auth)):
    helper_registry.reload()
    return {"status": "success", "message": "Helpers reloaded"}

@router_api.post("/helpers/reload")
async def reload_helpers_dynamic(auth: bool = Depends(verify_auth)):
    reload_result = helper_resolver.load_helpers()
    return {"status": "success", "message": "Helpers reloaded dynamically", "result": reload_result}

@router_api.get("/helpers/health/{helper_id}")
async def get_helper_health(helper_id: str, timeout: int = 10, auth: bool = Depends(verify_auth)):
    """
    M8.6: Run health check for a specific helper.
    Returns health status, timing, and output from the helper's health check script.
    """
    from tinyintent.helpers.sdk import run_helper_health_check
    from datetime import datetime
    
    audit_logger = get_audit_logger()
    
    try:
        # Run health check
        health_result = run_helper_health_check(helper_id, timeout_seconds=timeout)
        
        # Add timestamp and wrap in standard response
        result = {
            "status": "success",
            "health_check": health_result,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
        # Log health check attempt
        audit_logger.log_entry({
            "action": "helper_health_check",
            "helper_id": helper_id,
            "health_status": health_result.get("status"),
            "duration_ms": health_result.get("duration_ms"),
            "success": True
        })
        
        return result
        
    except Exception as e:
        # Log health check failure
        audit_logger.log_entry({
            "action": "helper_health_check",
            "helper_id": helper_id,
            "success": False,
            "error": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run health check for helper {helper_id}: {str(e)}"
        )

@router_api.get("/helpers/health")
async def get_all_helpers_health(timeout: int = 10, auth: bool = Depends(verify_auth)):
    """
    M8.6: Run health checks for all helpers.
    Returns health status summary and individual results for each helper.
    """
    from tinyintent.helpers.sdk import run_all_helper_health_checks
    from datetime import datetime
    
    audit_logger = get_audit_logger()
    
    try:
        # Run health checks for all helpers
        health_results = run_all_helper_health_checks(timeout_seconds=timeout)
        
        # Wrap in standard response
        result = {
            "status": "success",
            "health_checks": health_results,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
        # Log bulk health check
        audit_logger.log_entry({
            "action": "all_helpers_health_check",
            "total_helpers": health_results["summary"]["total"],
            "healthy_count": health_results["summary"]["healthy"],
            "unhealthy_count": health_results["summary"]["unhealthy"],
            "success": True
        })
        
        return result
        
    except Exception as e:
        # Log health check failure
        audit_logger.log_entry({
            "action": "all_helpers_health_check",
            "success": False,
            "error": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to run health checks: {str(e)}"
        )

@router_api.get("/healthz")
async def health_check():
    """Enhanced health check with execution control and model status."""
    from pathlib import Path
    
    # Basic health
    health_status = {"status": "ok"}
    
    # Add execution control visibility
    health_status["execution"] = {
        "enabled": emergency_kill.is_execution_enabled(),
        "flag_file_exists": emergency_kill.emergency_flag_file.exists() if hasattr(emergency_kill, 'emergency_flag_file') else False
    }
    
    # Add model status
    project_root = Path(__file__).parent.parent
    small_model_path = project_root / "router" / "SmallIntent.mlmodel"
    tiny_model_path = project_root / "router" / "TinyIntent.mlmodel"
    
    health_status["models"] = {
        "SmallIntent": {"available": small_model_path.exists()},
        "TinyIntent": {"available": tiny_model_path.exists()}
    }
    
    return health_status

@router_api.get("/readyz")
async def readiness_check():
    """Enhanced readiness check with detailed system state."""
    from pathlib import Path
    import os
    
    ready = True
    issues = []
    
    # Check execution state
    execution_enabled = emergency_kill.is_execution_enabled()
    
    # Check models
    project_root = Path(__file__).parent.parent
    small_model_exists = (project_root / "router" / "SmallIntent.mlmodel").exists()
    tiny_model_exists = (project_root / "router" / "TinyIntent.mlmodel").exists()
    
    if not (small_model_exists or tiny_model_exists):
        ready = False
        issues.append("No CoreML models available")
    
    # Check critical environment variables
    if not os.getenv("TINYINTENT_SECRET"):
        ready = False
        issues.append("TINYINTENT_SECRET not configured")
    
    return {
        "ready": ready,
        "issues": issues,
        "execution": {
            "enabled": execution_enabled,
            "helpers_can_execute": execution_enabled
        },
        "models": {
            "SmallIntent": {"available": small_model_exists},
            "TinyIntent": {"available": tiny_model_exists},
            "any_available": small_model_exists or tiny_model_exists
        },
        "environment": {
            "secret_configured": bool(os.getenv("TINYINTENT_SECRET"))
        }
    }

@router_api.post("/gen/cancel")
async def cancel_generation(request: GenerationCancelRequest, auth: bool = Depends(verify_auth)):
    result = generation_task_manager.cancel_task(request.request_id)
    return result

@router_api.post("/emergency/kill")
async def emergency_kill_switch(request: EmergencyKillRequest, fastapi_request: Request, auth: bool = Depends(verify_auth)):
    triggered_by = f"{fastapi_request.client.host}"
    success = emergency_kill.trigger_emergency_kill(request.reason, triggered_by)
    return {"status": "success", "activated": success}

@router_api.get("/emergency/status")
async def emergency_status(auth: bool = Depends(verify_auth)):
    return emergency_kill.get_status()

@router_api.get("/doctor")
async def system_doctor(auth: bool = Depends(verify_auth)):
    """M9.0: System health and readiness endpoint."""
    import json
    from pathlib import Path
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Check for recent doctor results (updated path)
        project_root = Path(__file__).parent.parent
        doctor_results_file = project_root / "bridge" / "logs" / "doctor.json"
        
        # Fallback to old location for backward compatibility
        if not doctor_results_file.exists():
            doctor_results_file = project_root / "data" / "doctor_results.json"
        
        if doctor_results_file.exists():
            # Load recent results
            with open(doctor_results_file, 'r') as f:
                doctor_data = json.load(f)
            
            # Check if results are recent (within last hour)
            result_timestamp = doctor_data.get("timestamp", "")
            age_minutes = 999
            if result_timestamp:
                try:
                    from datetime import datetime
                    result_time = datetime.fromisoformat(result_timestamp.replace('Z', '+00:00'))
                    now = datetime.now().astimezone()
                    age_minutes = (now - result_time).total_seconds() / 60
                except:
                    pass
            
            # Add metadata about result freshness
            doctor_data["result_age_minutes"] = age_minutes
            doctor_data["results_fresh"] = age_minutes < 60
            
            # Add current execution control status
            from datetime import datetime
            doctor_data["current_execution_status"] = {
                "enabled": emergency_kill.is_execution_enabled(),
                "checked_at": datetime.now().isoformat() + 'Z'
            }
            
            # Add current model status
            small_model_path = project_root / "router" / "SmallIntent.mlmodel"
            tiny_model_path = project_root / "router" / "TinyIntent.mlmodel"
            
            doctor_data["current_model_status"] = {
                "SmallIntent": {"available": small_model_path.exists()},
                "TinyIntent": {"available": tiny_model_path.exists()},
                "checked_at": datetime.now().isoformat() + 'Z'
            }
            
            # Log doctor access
            audit_logger.log_entry({
                "action": "doctor_check_accessed",
                "result_age_minutes": age_minutes,
                "overall_status": doctor_data.get("overall_status", "unknown"),
                "execution_enabled": emergency_kill.is_execution_enabled(),
                "models_available": small_model_path.exists() or tiny_model_path.exists(),
                "success": True
            })
            
            return doctor_data
        else:
            # No results available - recommend running doctor
            audit_logger.log_entry({
                "action": "doctor_check_accessed", 
                "error": "No doctor results available",
                "success": False
            })
            
            return {
                "timestamp": None,
                "overall_status": "unknown",
                "checks": {},
                "recommendations": ["Run 'make doctor' to generate system health report"],
                "summary": {
                    "total_checks": 0,
                    "passed_checks": 0,
                    "failed_checks": 0,
                    "warning_checks": 0,
                    "error_checks": 0,
                    "recommendation_count": 1
                },
                "result_age_minutes": None,
                "results_fresh": False,
                "message": "No system health results available. Run 'make doctor' to generate report."
            }
    
    except Exception as e:
        # Log error
        audit_logger.log_entry({
            "action": "doctor_check_error",
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve system health status: {str(e)}"
        )

# M10.0: Agent Generator Models
class AgentCreateRequest(BaseModel):
    id: str
    description: str
    language: str
    capabilities: Optional[List[str]] = []
    can_execute: Optional[bool] = False
    risk_level: Optional[str] = "high"
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    
    @validator('id')
    def validate_id(cls, v):
        if not v or not v.strip():
            raise ValueError('Agent ID cannot be empty')
        return v.strip()
    
    @validator('description')
    def validate_description(cls, v):
        if not v or not v.strip():
            raise ValueError('Description cannot be empty')
        return v.strip()
    
    @validator('language')
    def validate_language(cls, v):
        valid_languages = {"python", "node"}
        if v not in valid_languages:
            raise ValueError(f'Language must be one of: {", ".join(valid_languages)}')
        return v
    
    @validator('can_execute')
    def validate_can_execute(cls, v):
        if v is True:
            raise ValueError('can_execute must be false for generated agents (safety requirement)')
        return False  # Always force to false

class AgentCreateResponse(BaseModel):
    created: bool
    helper_id: str
    enabled: Optional[bool] = None
    validation: Dict[str, Any]
    files_created: Optional[List[str]] = None
    errors: Optional[List[str]] = None
    provenance: Optional[Dict[str, Any]] = None  # M10.5: Provenance generation result

@router_api.post("/agents/create", response_model=AgentCreateResponse)
async def create_agent(request: AgentCreateRequest, auth: bool = Depends(verify_auth)):
    """M10.0: Create a new helper agent from specification."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    # Check rate limits
    session_id = "agent_create"  # Use fixed session for agent creation
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        audit_logger.log_entry({
            "action": "agent_create_rate_limited",
            "helper_id": request.id,
            "retry_after": retry_after,
            "success": False
        })
        
        raise HTTPException(
            status_code=429,
            detail="Agent creation rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )
    
    try:
        # Convert request to dict for agent generator
        spec = {
            "id": request.id,
            "description": request.description,
            "language": request.language,
            "capabilities": request.capabilities or [],
            "can_execute": False,  # Always false for safety
            "risk_level": request.risk_level or "high",
            "inputs": request.inputs,
            "outputs": request.outputs
        }
        
        # Create the agent
        result = agent_generator.create_agent(spec)
        
        # If successful, trigger helper reload
        if result["created"]:
            try:
                helper_registry.reload()
                
                # Log episode event
                episode_logger.log_event({
                    "action": "agent_create",
                    "helper_id": request.id,
                    "language": request.language,
                    "capabilities": request.capabilities,
                    "success": True,
                    "files_created": result.get("files_created", [])
                })
                
                # Return success response
                return AgentCreateResponse(
                    created=True,
                    helper_id=request.id,
                    enabled=True,
                    validation=result["validation"],
                    files_created=result.get("files_created", []),
                    provenance=result.get("provenance")  # M10.5: Include provenance
                )
                
            except Exception as reload_error:
                # Agent created but reload failed
                audit_logger.log_entry({
                    "action": "agent_create_reload_failed",
                    "helper_id": request.id,
                    "error": str(reload_error),
                    "success": False
                })
                
                result["errors"] = result.get("errors", []) + [f"Helper reload failed: {str(reload_error)}"]
                result["validation"]["warnings"] = result["validation"].get("warnings", []) + ["Helper reload failed"]
                
                return AgentCreateResponse(
                    created=True,
                    helper_id=request.id,
                    enabled=False,  # Not enabled due to reload failure
                    validation=result["validation"],
                    files_created=result.get("files_created", []),
                    errors=result.get("errors", []),
                    provenance=result.get("provenance")  # M10.5: Include provenance
                )
        else:
            # Creation failed
            episode_logger.log_event({
                "action": "agent_create",
                "helper_id": request.id,
                "language": request.language,
                "success": False,
                "errors": result.get("errors", [])
            })
            
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Agent creation failed",
                    "errors": result.get("errors", []),
                    "validation": result.get("validation", {})
                }
            )
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_create_error",
            "helper_id": request.id,
            "error": str(e),
            "success": False
        })
        
        episode_logger.log_event({
            "action": "agent_create",
            "helper_id": request.id,
            "success": False,
            "errors": [str(e)]
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Agent creation failed: {str(e)}"
        )

# M10.1: Agent Evolution Models
class AgentSuggestRequest(BaseModel):
    window_hours: Optional[int] = 24
    min_count: Optional[int] = 8
    max_suggestions: Optional[int] = 5

class AgentSuggestion(BaseModel):
    spec: Dict[str, Any]
    valid: bool
    errors: Optional[List[str]] = None
    cluster_info: Optional[Dict[str, Any]] = None

class AgentSuggestResponse(BaseModel):
    suggestions: List[AgentSuggestion]
    clusters_analyzed: int
    total_abstain_events: int
    window_hours: int

class AgentCreateFromSuggestionRequest(BaseModel):
    spec: Dict[str, Any]
    
    @validator('spec')
    def validate_spec_structure(cls, v):
        if not isinstance(v, dict):
            raise ValueError('Spec must be a dictionary')
        required_fields = ['id', 'description', 'language', 'inputs', 'outputs']
        for field in required_fields:
            if field not in v:
                raise ValueError(f'Missing required field: {field}')
        return v

@router_api.post("/agents/suggest", response_model=AgentSuggestResponse)
async def suggest_agents(request: AgentSuggestRequest, auth: bool = Depends(verify_auth)):
    """M10.1: Suggest new agents based on abstain/fallback patterns."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    # Check rate limits
    session_id = "agent_suggest"
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        audit_logger.log_entry({
            "action": "agent_suggest_rate_limited",
            "retry_after": retry_after,
            "success": False
        })
        
        raise HTTPException(
            status_code=429,
            detail="Agent suggestion rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )
    
    try:
        # Mine abstain clusters
        clusters = episode_miner.mine_abstain_clusters(
            window_hours=request.window_hours,
            min_count=request.min_count,
            max_clusters=request.max_suggestions
        )
        
        if not clusters:
            # No clusters found
            audit_logger.log_entry({
                "action": "agent_suggest",
                "window_hours": request.window_hours,
                "clusters_found": 0,
                "success": True
            })
            
            return AgentSuggestResponse(
                suggestions=[],
                clusters_analyzed=0,
                total_abstain_events=0,
                window_hours=request.window_hours
            )
        
        # Generate suggestions for each cluster
        suggestions = []
        total_events = sum(cluster["sample_count"] for cluster in clusters)
        
        for cluster in clusters:
            try:
                # Generate agent spec using Ollama
                spec = await _generate_agent_spec_from_cluster(cluster)
                
                if spec:
                    # Validate the generated spec
                    is_valid, errors = validate_agent_spec(spec)
                    
                    suggestion = AgentSuggestion(
                        spec=spec,
                        valid=is_valid,
                        errors=errors if not is_valid else None,
                        cluster_info={
                            "sample_count": cluster["sample_count"],
                            "representative_text": cluster["representative_text"],
                            "themes": cluster.get("themes", []),
                            "confidence_score": cluster.get("confidence_score", 0.0)
                        }
                    )
                    
                    suggestions.append(suggestion)
                    
            except Exception as e:
                # Log error but continue with other clusters
                audit_logger.log_entry({
                    "action": "agent_suggest_cluster_error",
                    "cluster_id": cluster.get("cluster_id", "unknown"),
                    "error": str(e),
                    "success": False
                })
                
                # Add failed suggestion
                suggestions.append(AgentSuggestion(
                    spec={},
                    valid=False,
                    errors=[f"Failed to generate spec: {str(e)}"],
                    cluster_info={
                        "sample_count": cluster["sample_count"],
                        "representative_text": cluster["representative_text"]
                    }
                ))
        
        # Log successful suggestion generation
        audit_logger.log_entry({
            "action": "agent_suggest",
            "window_hours": request.window_hours,
            "clusters_found": len(clusters),
            "suggestions_generated": len(suggestions),
            "valid_suggestions": len([s for s in suggestions if s.valid]),
            "total_abstain_events": total_events,
            "success": True
        })
        
        # Log episode event
        episode_logger.log_event({
            "action": "agent_suggest",
            "clusters_analyzed": len(clusters),
            "suggestions_generated": len(suggestions),
            "window_hours": request.window_hours,
            "success": True
        })
        
        return AgentSuggestResponse(
            suggestions=suggestions,
            clusters_analyzed=len(clusters),
            total_abstain_events=total_events,
            window_hours=request.window_hours
        )
        
    except Exception as e:
        # Log error
        audit_logger.log_entry({
            "action": "agent_suggest_error",
            "error": str(e),
            "success": False
        })
        
        episode_logger.log_event({
            "action": "agent_suggest",
            "success": False,
            "errors": [str(e)]
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Agent suggestion failed: {str(e)}"
        )

@router_api.post("/agents/create_from_suggestion", response_model=AgentCreateResponse)
async def create_agent_from_suggestion(request: AgentCreateFromSuggestionRequest, auth: bool = Depends(verify_auth)):
    """M10.1: Create agent from previously suggested specification."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    # Check rate limits
    session_id = "agent_create_from_suggestion"
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        audit_logger.log_entry({
            "action": "agent_create_from_suggestion_rate_limited",
            "helper_id": request.spec.get("id", "unknown"),
            "retry_after": retry_after,
            "success": False
        })
        
        raise HTTPException(
            status_code=429,
            detail="Agent creation rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )
    
    try:
        # Re-validate the spec (security requirement)
        is_valid, errors = validate_agent_spec(request.spec)
        if not is_valid:
            audit_logger.log_entry({
                "action": "agent_create_from_suggestion_validation_failed",
                "helper_id": request.spec.get("id", "unknown"),
                "errors": errors,
                "success": False
            })
            
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Suggestion spec validation failed",
                    "errors": errors
                }
            )
        
        # Apply safe defaults and create agent
        spec = request.spec.copy()
        spec["can_execute"] = False  # Always force to false
        spec["risk_level"] = spec.get("risk_level", "high")
        
        # Create the agent using existing flow
        result = agent_generator.create_agent(spec)
        
        # If successful, trigger helper reload
        if result["created"]:
            try:
                helper_registry.reload()
                
                # Log episode event with suggestion source
                episode_logger.log_event({
                    "action": "agent_create_from_suggestion",
                    "helper_id": spec["id"],
                    "language": spec["language"],
                    "capabilities": spec.get("capabilities", []),
                    "success": True,
                    "files_created": result.get("files_created", []),
                    "label_source": "suggestion"  # Mark as suggestion-derived
                })
                
                # Return success response
                return AgentCreateResponse(
                    created=True,
                    helper_id=spec["id"],
                    enabled=True,
                    validation=result["validation"],
                    files_created=result.get("files_created", []),
                    provenance=result.get("provenance")  # M10.5: Include provenance
                )
                
            except Exception as reload_error:
                # Agent created but reload failed
                audit_logger.log_entry({
                    "action": "agent_create_from_suggestion_reload_failed",
                    "helper_id": spec["id"],
                    "error": str(reload_error),
                    "success": False
                })
                
                result["errors"] = result.get("errors", []) + [f"Helper reload failed: {str(reload_error)}"]
                
                return AgentCreateResponse(
                    created=True,
                    helper_id=spec["id"],
                    enabled=False,
                    validation=result["validation"],
                    files_created=result.get("files_created", []),
                    errors=result.get("errors", []),
                    provenance=result.get("provenance")  # M10.5: Include provenance
                )
        else:
            # Creation failed
            episode_logger.log_event({
                "action": "agent_create_from_suggestion",
                "helper_id": spec["id"],
                "success": False,
                "errors": result.get("errors", [])
            })
            
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Agent creation from suggestion failed",
                    "errors": result.get("errors", []),
                    "validation": result.get("validation", {})
                }
            )
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_create_from_suggestion_error",
            "helper_id": request.spec.get("id", "unknown"),
            "error": str(e),
            "success": False
        })
        
        episode_logger.log_event({
            "action": "agent_create_from_suggestion",
            "helper_id": request.spec.get("id", "unknown"),
            "success": False,
            "errors": [str(e)]
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Agent creation from suggestion failed: {str(e)}"
        )

async def _generate_agent_spec_from_cluster(cluster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Generate agent specification from cluster using Ollama."""
    try:
        # Build prompt from cluster information
        representative_text = cluster["representative_text"]
        examples = cluster.get("examples", [])[:3]  # Use top 3 examples
        themes = cluster.get("themes", [])
        
        # Create prompt for Ollama
        prompt = f"""Based on the following user requests that the system couldn't handle, generate a JSON specification for a new helper agent.

Representative request: "{representative_text}"

Additional examples:
"""
        
        for i, example in enumerate(examples, 1):
            prompt += f"{i}. \"{example.get('text', '')}\"\n"
        
        if themes:
            prompt += f"\nIdentified themes: {', '.join(themes)}\n"
        
        prompt += """
Generate a JSON object with this exact structure:
{
  "id": "helper_name_in_snake_case",
  "description": "Brief description of what this helper does",
  "language": "python",
  "capabilities": ["network"],
  "inputs": {
    "type": "object",
    "properties": {
      "input_field": {"type": "string", "description": "Description"}
    },
    "required": ["input_field"]
  },
  "outputs": {
    "type": "object", 
    "properties": {
      "result": {"type": "string", "description": "Description"}
    },
    "required": ["result"]
  }
}

Requirements:
- ID must be lowercase with underscores, 3-40 characters
- Language should be "python" or "node"
- Capabilities should be minimal (only "network", "filesystem", "database" if clearly needed)
- Input/output schemas must be valid JSON Schema
- Make the helper specific to the request patterns shown

Return only the JSON object, no other text."""

        # Call Ollama for generation
        response = await async_ollama_client.generate(
            model="llama2",  # Use configured model
            prompt=prompt,
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=1000
        )
        
        if not response or "text" not in response:
            return None
        
        # Parse JSON response
        response_text = response["text"].strip()
        
        # Try to extract JSON from response
        try:
            # Look for JSON object in response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx]
                spec = json.loads(json_str)
                
                # Apply safety defaults
                spec["can_execute"] = False
                spec["risk_level"] = "high"
                
                # Infer minimal capabilities if not provided or too broad
                if not spec.get("capabilities"):
                    spec["capabilities"] = infer_min_capabilities(spec)
                else:
                    # Validate and filter capabilities
                    valid_caps = {"network", "filesystem", "database", "compute"}
                    spec["capabilities"] = [cap for cap in spec.get("capabilities", []) if cap in valid_caps]
                
                return spec
                
        except json.JSONDecodeError:
            # Failed to parse JSON
            return None
        
        return None
        
    except Exception as e:
        print(f"Error generating agent spec: {e}")
        return None


# M10.2: Agent Lifecycle Governance Models
class LifecycleSetRequest(BaseModel):
    helper_id: str
    state: str
    notes: Optional[str] = None
    
    @validator('state')
    def validate_state(cls, v):
        valid_states = {"draft", "trusted", "deprecated", "retired"}
        if v not in valid_states:
            raise ValueError(f'State must be one of: {", ".join(valid_states)}')
        return v
    
    @validator('helper_id')
    def validate_helper_id(cls, v):
        if not v or len(v) < 1:
            raise ValueError('Helper ID is required')
        return v

class LifecycleResponse(BaseModel):
    helper_id: str
    lifecycle: Dict[str, Any]
    metrics: Optional[Dict[str, Any]] = None

class PruneSuggestionsResponse(BaseModel):
    suggestions: List[Dict[str, Any]]
    criteria: Dict[str, Any]
    total_helpers: int
    candidates_found: int


@router_api.post("/agents/lifecycle/set")
async def set_agent_lifecycle(request: LifecycleSetRequest, auth: bool = Depends(verify_auth)):
    """M10.2: Set helper lifecycle state."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    # Check rate limits
    session_id = "lifecycle_management"
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        audit_logger.log_entry({
            "action": "lifecycle_set_rate_limited",
            "helper_id": request.helper_id,
            "retry_after": retry_after,
            "success": False
        })
        
        raise HTTPException(
            status_code=429,
            detail="Lifecycle management rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )
    
    try:
        # Check if helper exists
        if not helper_registry.get_registry_entry(request.helper_id):
            audit_logger.log_entry({
                "action": "lifecycle_set_helper_not_found",
                "helper_id": request.helper_id,
                "success": False
            })
            
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{request.helper_id}' not found"
            )
        
        # Update lifecycle state
        success = helper_registry.update_helper_lifecycle(
            request.helper_id,
            request.state,
            request.notes
        )
        
        if not success:
            audit_logger.log_entry({
                "action": "lifecycle_set_update_failed",
                "helper_id": request.helper_id,
                "state": request.state,
                "success": False
            })
            
            raise HTTPException(
                status_code=500,
                detail="Failed to update helper lifecycle state"
            )
        
        # Trigger helper reload to reflect changes
        try:
            helper_registry.reload()
        except Exception as reload_error:
            audit_logger.log_entry({
                "action": "lifecycle_set_reload_failed",
                "helper_id": request.helper_id,
                "error": str(reload_error),
                "success": False
            })
            # Continue despite reload failure
        
        # Log successful lifecycle change
        audit_logger.log_entry({
            "action": "agent_lifecycle_change",
            "helper_id": request.helper_id,
            "old_state": None,  # Could track previous state
            "new_state": request.state,
            "notes": request.notes,
            "success": True
        })
        
        # Log episode event
        episode_logger.log_event({
            "action": "agent_lifecycle_change",
            "helper_id": request.helper_id,
            "state": request.state,
            "notes": request.notes,
            "success": True
        })
        
        return {
            "success": True,
            "helper_id": request.helper_id,
            "state": request.state,
            "message": f"Helper '{request.helper_id}' lifecycle updated to '{request.state}'"
        }
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "lifecycle_set_error",
            "helper_id": request.helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Lifecycle update failed: {str(e)}"
        )


@router_api.get("/agents/lifecycle/{helper_id}", response_model=LifecycleResponse)
async def get_agent_lifecycle(helper_id: str, auth: bool = Depends(verify_auth)):
    """M10.2: Get helper lifecycle status and metrics."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Check if helper exists
        entry = helper_registry.get_registry_entry(helper_id)
        if not entry:
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{helper_id}' not found"
            )
        
        # Get lifecycle information
        lifecycle = helper_registry.get_helper_lifecycle(helper_id)
        
        # Get basic metrics (placeholder for M10.2 metrics implementation)
        metrics = {
            "calls_30_days": 0,  # TODO: Implement from metrics system
            "success_rate": 0.0,  # TODO: Implement from metrics system
            "last_used": None,  # TODO: Implement from metrics system
            "error_rate": 0.0  # TODO: Implement from metrics system
        }
        
        # Log access
        audit_logger.log_entry({
            "action": "lifecycle_get",
            "helper_id": helper_id,
            "success": True
        })
        
        return LifecycleResponse(
            helper_id=helper_id,
            lifecycle=lifecycle,
            metrics=metrics
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "lifecycle_get_error",
            "helper_id": helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get lifecycle information: {str(e)}"
        )


@router_api.get("/agents/prune_suggestions", response_model=PruneSuggestionsResponse)
async def get_prune_suggestions(
    min_days: int = 30,
    min_calls: int = 3,
    max_error_rate: float = 0.4,
    auth: bool = Depends(verify_auth)
):
    """M10.2: Get suggestions for helpers to deprecate or retire."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        suggestions = []
        total_helpers = len(helper_registry.list_all_helpers())
        
        # Analyze each helper for pruning candidates
        for helper_id in helper_registry.list_all_helpers():
            entry = helper_registry.get_registry_entry(helper_id)
            if not entry:
                continue
            
            # Skip already retired helpers
            if entry.is_retired():
                continue
            
            # Get basic metrics (placeholder implementation)
            # TODO: Implement real metrics from helper usage tracking
            metrics = {
                "calls_30_days": 0,  # Would come from real metrics
                "success_rate": 1.0,  # Would come from real metrics
                "error_rate": 0.0,  # Would come from real metrics
                "last_used_days": 999,  # Would come from real metrics
                "is_generated": entry.is_draft()  # AI-generated helpers are candidates
            }
            
            # Determine if helper is a candidate for pruning
            reasons = []
            recommendation = None
            
            # Check usage criteria
            if metrics["calls_30_days"] < min_calls:
                reasons.append(f"Low usage: {metrics['calls_30_days']} calls in {min_days} days")
            
            if metrics["error_rate"] > max_error_rate:
                reasons.append(f"High error rate: {metrics['error_rate']:.1%}")
            
            if metrics["last_used_days"] > min_days:
                reasons.append(f"Unused for {metrics['last_used_days']} days")
            
            # Determine recommendation
            if len(reasons) >= 2:
                if entry.is_deprecated():
                    recommendation = "retire"
                elif metrics["error_rate"] > max_error_rate:
                    recommendation = "retire"
                else:
                    recommendation = "deprecate"
            elif len(reasons) == 1 and not entry.is_deprecated():
                recommendation = "deprecate"
            
            # Add to suggestions if there's a recommendation
            if recommendation and reasons:
                suggestions.append({
                    "helper_id": helper_id,
                    "current_state": entry.lifecycle.get("state", "unknown"),
                    "recommendation": recommendation,
                    "reasons": reasons,
                    "metrics": metrics,
                    "priority": "high" if len(reasons) >= 2 else "medium"
                })
        
        # Sort by priority and number of reasons
        suggestions.sort(key=lambda x: (
            x["priority"] == "high",  # High priority first
            len(x["reasons"]),  # More reasons first
            x["helper_id"]  # Alphabetical for consistency
        ), reverse=True)
        
        # Log prune suggestions request
        audit_logger.log_entry({
            "action": "prune_suggestions",
            "criteria": {
                "min_days": min_days,
                "min_calls": min_calls,
                "max_error_rate": max_error_rate
            },
            "suggestions_count": len(suggestions),
            "success": True
        })
        
        return PruneSuggestionsResponse(
            suggestions=suggestions,
            criteria={
                "min_days": min_days,
                "min_calls": min_calls,
                "max_error_rate": max_error_rate
            },
            total_helpers=total_helpers,
            candidates_found=len(suggestions)
        )
        
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "prune_suggestions_error",
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate prune suggestions: {str(e)}"
        )


@router_api.post("/agents/promote", response_model=AgentPromoteResponse)
async def promote_agent(request: AgentPromoteRequest, auth: bool = Depends(verify_auth)):
    """M10.4: Promote staged agent to trusted status based on objective criteria."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    # Check rate limits
    session_id = "agent_promotion"
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        audit_logger.log_entry({
            "action": "agent_promote_rate_limited",
            "helper_id": request.helper_id,
            "retry_after": retry_after,
            "success": False
        })
        
        raise HTTPException(
            status_code=429,
            detail="Agent promotion rate limit exceeded",
            headers={"Retry-After": str(retry_after)}
        )
    
    try:
        # Import the evaluator
        from scripts.eval_agents import AgentEvaluator
        
        # Check if helper exists
        registry_entry = helper_registry.get_registry_entry(request.helper_id)
        if not registry_entry:
            audit_logger.log_entry({
                "action": "agent_promote_helper_not_found",
                "helper_id": request.helper_id,
                "success": False
            })
            
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{request.helper_id}' not found"
            )
        
        # Check current lifecycle state
        current_lifecycle = helper_registry.get_helper_lifecycle(request.helper_id)
        current_state = current_lifecycle.get("state", "unknown")
        
        # Only allow promotion from draft or deprecated state
        if current_state not in ["draft", "deprecated"]:
            audit_logger.log_entry({
                "action": "agent_promote_invalid_state",
                "helper_id": request.helper_id,
                "current_state": current_state,
                "success": False
            })
            
            raise HTTPException(
                status_code=400,
                detail=f"Cannot promote helper in state '{current_state}'. Only 'draft' or 'deprecated' helpers can be promoted."
            )
        
        # Evaluate for promotion
        evaluator = AgentEvaluator()
        evaluation = evaluator.evaluate_for_promotion(request.helper_id, request.window_hours)
        
        if evaluation["promote"]:
            # Update lifecycle to trusted
            success = helper_registry.update_helper_lifecycle(
                request.helper_id,
                "trusted",
                f"Automatically promoted based on objective criteria. Previous state: {current_state}"
            )
            
            if not success:
                audit_logger.log_entry({
                    "action": "agent_promote_update_failed",
                    "helper_id": request.helper_id,
                    "evaluation": evaluation,
                    "success": False
                })
                
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update helper lifecycle state"
                )
            
            # Trigger helper reload to reflect changes
            try:
                helper_registry.reload()
            except Exception as reload_error:
                audit_logger.log_entry({
                    "action": "agent_promote_reload_failed",
                    "helper_id": request.helper_id,
                    "error": str(reload_error),
                    "success": False
                })
                # Continue despite reload failure
            
            # Log successful promotion
            audit_logger.log_entry({
                "action": "agent_promote",
                "helper_id": request.helper_id,
                "previous_state": current_state,
                "new_state": "trusted",
                "evaluation": evaluation,
                "success": True
            })
            
            # Log episode event
            episode_logger.log_event({
                "action": "agent_promote",
                "helper_id": request.helper_id,
                "previous_state": current_state,
                "new_state": "trusted",
                "promotion_metrics": evaluation["metrics"],
                "success": True
            })
            
            return AgentPromoteResponse(
                status="success",
                helper_id=request.helper_id,
                promoted=True,
                message=f"Helper '{request.helper_id}' promoted to trusted status",
                evaluation=evaluation,
                previous_state=current_state,
                new_state="trusted"
            )
        else:
            # Promotion criteria not met
            audit_logger.log_entry({
                "action": "agent_promote_criteria_not_met",
                "helper_id": request.helper_id,
                "evaluation": evaluation,
                "success": False
            })
            
            # Return 412 Precondition Failed with structured reasons
            raise HTTPException(
                status_code=412,
                detail={
                    "message": "Promotion criteria not met",
                    "helper_id": request.helper_id,
                    "reasons": evaluation["reasons"],
                    "evaluation": evaluation
                }
            )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_promote_error",
            "helper_id": request.helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Promotion failed: {str(e)}"
        )


@router_api.get("/agents/provenance/{helper_id}", response_model=AgentProvenanceResponse)
async def get_agent_provenance(helper_id: str, auth: bool = Depends(verify_auth)):
    """M10.5: Get agent provenance information and verification status."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Check if helper exists
        registry_entry = helper_registry.get_registry_entry(helper_id)
        if not registry_entry:
            audit_logger.log_entry({
                "action": "agent_provenance_helper_not_found",
                "helper_id": helper_id,
                "success": False
            })
            
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{helper_id}' not found"
            )
        
        # Get provenance information from registry entry
        provenance_ok = registry_entry.provenance_ok
        provenance_reason = registry_entry.provenance_reason
        verification_details = registry_entry.provenance_details
        
        # Try to read the actual provenance.json file
        provenance_data = None
        try:
            from pathlib import Path
            from tinyintent.bridge.provenance import verify_provenance
            import json
            
            # Determine helper directory
            if hasattr(registry_entry, 'manifest_path') and registry_entry.manifest_path:
                helper_dir = Path(registry_entry.manifest_path).parent
            else:
                project_root = Path(__file__).parent.parent
                helper_dir = project_root / "helpers" / helper_id
            
            provenance_file = helper_dir / "provenance.json"
            if provenance_file.exists():
                with open(provenance_file, 'r') as f:
                    provenance_data = json.load(f)
                
                # Sanitize signature for API response (show only first/last 8 chars)
                if "sig" in provenance_data:
                    sig = provenance_data["sig"]
                    if len(sig) > 16:
                        provenance_data["sig"] = f"{sig[:8]}...{sig[-8:]}"
        
        except Exception as e:
            # Don't fail the endpoint if we can't read the file
            audit_logger.log_entry({
                "action": "agent_provenance_file_read_error",
                "helper_id": helper_id,
                "error": str(e),
                "success": False
            })
        
        # Log provenance access
        audit_logger.log_entry({
            "action": "agent_provenance_accessed",
            "helper_id": helper_id,
            "provenance_ok": provenance_ok,
            "success": True
        })
        
        return AgentProvenanceResponse(
            helper_id=helper_id,
            provenance_ok=provenance_ok,
            reason=provenance_reason,
            provenance_data=provenance_data,
            verification_details=verification_details,
            generated_at=datetime.utcnow().isoformat() + 'Z'
        )
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_provenance_error",
            "helper_id": helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get provenance information: {str(e)}"
        )


@router_api.get("/endpoints")
async def get_endpoints():
    """Get all available API endpoints for discovery."""
    from fastapi import FastAPI
    from fastapi.routing import APIRoute
    
    # Get the FastAPI app instance
    app = router_api.app
    if app is None:
        # Fallback if app not available
        return {"error": "App instance not available"}
    
    endpoints = []
    
    for route in app.routes:
        if isinstance(route, APIRoute):
            # Sanitize route information - remove any sensitive defaults
            endpoint_info = {
                "path": route.path,
                "methods": sorted(list(route.methods - {"HEAD", "OPTIONS"})),  # Exclude HEAD/OPTIONS
            }
            
            # Add name if available and not internal
            if route.name and not route.name.startswith("_"):
                endpoint_info["name"] = route.name
            
            # Add summary if available (from OpenAPI)
            if hasattr(route, "summary") and route.summary:
                endpoint_info["summary"] = route.summary
            
            endpoints.append(endpoint_info)
    
    # Sort by path for consistent ordering
    endpoints.sort(key=lambda x: x["path"])
    
    return {
        "endpoints": endpoints,
        "total_count": len(endpoints),
        "service": "TinyIntent Bridge",
        "version": "2.0.0"
    }


@router_api.get("/router/train_summary")
async def get_train_summary(auth: bool = Depends(verify_auth)):
    """Get training summary with metrics from last training run."""
    from pathlib import Path
    import json
    
    # Look for training summary file
    project_root = Path(__file__).parent.parent
    train_summary_path = project_root / "router" / "train_summary.json"
    
    if not train_summary_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No training summary found. Run training with 'make router-train' first."
        )
    
    try:
        with open(train_summary_path, 'r') as f:
            train_summary = json.load(f)
        
        # Add current model status
        small_model_path = project_root / "router" / "SmallIntent.mlmodel"
        tiny_model_path = project_root / "router" / "TinyIntent.mlmodel"
        
        train_summary['current_models'] = {
            'SmallIntent': {
                'exists': small_model_path.exists(),
                'path': str(small_model_path) if small_model_path.exists() else None,
                'size_mb': None
            },
            'TinyIntent': {
                'exists': tiny_model_path.exists(),
                'path': str(tiny_model_path) if tiny_model_path.exists() else None,
                'size_mb': None
            }
        }
        
        # Calculate model sizes if they exist
        if small_model_path.exists():
            try:
                size_mb = sum(f.stat().st_size for f in small_model_path.rglob('*') if f.is_file()) / (1024 * 1024)
                train_summary['current_models']['SmallIntent']['size_mb'] = round(size_mb, 2)
                # Check if model meets size constraint
                train_summary['current_models']['SmallIntent']['meets_size_constraint'] = size_mb <= 16
            except Exception:
                pass
        
        if tiny_model_path.exists():
            try:
                size_mb = sum(f.stat().st_size for f in tiny_model_path.rglob('*') if f.is_file()) / (1024 * 1024)
                train_summary['current_models']['TinyIntent']['size_mb'] = round(size_mb, 2)
                # Check if model meets size constraint  
                train_summary['current_models']['TinyIntent']['meets_size_constraint'] = size_mb <= 5
            except Exception:
                pass
        
        # Add evaluation results if available
        eval_results_path = project_root / "router" / "data" / "eval_results.json"
        if eval_results_path.exists():
            try:
                with open(eval_results_path, 'r') as f:
                    eval_results = json.load(f)
                    train_summary['evaluation_results'] = {
                        'timestamp': eval_results.get('timestamp'),
                        'accuracy': eval_results.get('performance', {}).get('accuracy'),
                        'precision_macro': eval_results.get('performance', {}).get('precision_macro'),
                        'recall_macro': eval_results.get('performance', {}).get('recall_macro'),
                        'f1_macro': eval_results.get('performance', {}).get('f1_macro'),
                        'latency_p95_ms': eval_results.get('performance', {}).get('latency', {}).get('p95_ms'),
                        'promotion_eligible': eval_results.get('promotion', {}).get('promotion_eligible', False)
                    }
            except Exception:
                pass
        
        # Add deployment status
        train_summary['deployment_status'] = {
            'models_ready': small_model_path.exists() and tiny_model_path.exists(),
            'training_complete': train_summary.get('status') == 'completed',
            'evaluation_complete': eval_results_path.exists(),
            'api_version': '2.0'
        }
        
        return train_summary
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to read training summary: {str(e)}"
        )


# M10.3: Agent Staging Helper Functions

async def _execute_staging_helpers(request: RouteRequest, session_id: str, route: str, intent: Optional[str] = None):
    """
    Execute shadow and canary helpers in parallel without affecting the main response.
    This is the core staging execution logic for M10.3.
    """
    try:
        # Get all staged helpers from configuration
        staged_helpers = _get_staged_helpers_for_request(request, route, intent)
        
        if not staged_helpers:
            return  # No staged helpers to execute
        
        # Execute staged helpers in background (fire and forget)
        tasks = []
        for staging_config in staged_helpers:
            if staging_config["mode"] == "shadow":
                task = _execute_shadow_helper(staging_config, request, session_id, intent)
            elif staging_config["mode"] == "canary":
                task = _execute_canary_helper(staging_config, request, session_id, intent)
            
            if task:
                tasks.append(task)
        
        # Execute all staging tasks in parallel without waiting for completion
        if tasks:
            # Create background tasks that don't block the main response
            asyncio.create_task(_run_staging_tasks(tasks))
    
    except Exception as e:
        # Log staging errors but don't let them affect the main response
        audit_logger = get_audit_logger()
        if audit_logger:
            audit_logger.log_entry({
                "action": "staging_execution_error",
                "session_id": session_id,
                "route": route,
                "error": str(e),
                "success": False
            })

async def _run_staging_tasks(tasks: List):
    """Run staging tasks in parallel and handle errors gracefully."""
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        # Silently handle errors - staging should never affect main response
        pass

def _get_staged_helpers_for_request(request: RouteRequest, route: str, intent: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get list of staged helpers that should be executed for this request."""
    staged_helpers = []
    
    try:
        # Get all helpers with staging configurations
        # In a full implementation, this would query the staging storage
        # For now, we'll return an empty list as the storage doesn't have a direct query method
        # This would be: agent_staging_storage.get_all_staging_configs()
        return staged_helpers
        
    except Exception:
        return []

async def _execute_shadow_helper(staging_config: Dict[str, Any], request: RouteRequest, session_id: str, intent: Optional[str] = None):
    """Execute a helper in shadow mode (dry-run only)."""
    helper_id = staging_config["helper_id"]
    match_intent = staging_config.get("match_intent")
    
    # Skip if intent doesn't match (if specified)
    if match_intent and intent and intent != match_intent:
        return
    
    start_time = time.time()
    
    try:
        # Execute helper in shadow mode (always dry_run=True)
        helper_input = request.helper_input or {}
        
        shadow_result = helper_executor.preview(
            helper_id=helper_id,
            input_data=helper_input,
            session_id=session_id,
            execution_mode="shadow"
        )
        
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        # Log shadow execution to staging storage
        await agent_staging_storage.log_shadow_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent=intent,
            latency_ms=latency_ms,
            success=shadow_result.get("status") == "success",
            error_code=None,
            output_data=shadow_result.get("preview_json")
        )
        
        # Audit log the shadow execution
        audit_logger = get_audit_logger()
        if audit_logger:
            audit_logger.log_entry({
                "action": "agent_shadow_run",
                "helper_id": helper_id,
                "session_id": session_id,
                "intent": intent,
                "latency_ms": latency_ms,
                "success": shadow_result.get("status") == "success",
                "execution_mode": "shadow"
            })
    
    except Exception as e:
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        # Log failed shadow execution
        await agent_staging_storage.log_shadow_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=request.helper_input or {},
            intent=intent,
            latency_ms=latency_ms,
            success=False,
            error_code=type(e).__name__,
            output_data=None
        )
        
        # Audit log the shadow execution error
        audit_logger = get_audit_logger()
        if audit_logger:
            audit_logger.log_entry({
                "action": "agent_shadow_run_error",
                "helper_id": helper_id,
                "session_id": session_id,
                "intent": intent,
                "latency_ms": latency_ms,
                "error": str(e),
                "success": False,
                "execution_mode": "shadow"
            })

async def _execute_canary_helper(staging_config: Dict[str, Any], request: RouteRequest, session_id: str, intent: Optional[str] = None):
    """Execute a helper in canary mode with percentage-based traffic splitting."""
    helper_id = staging_config["helper_id"]
    canary_pct = staging_config.get("canary_pct", 0)
    match_intent = staging_config.get("match_intent")
    
    # Skip if intent doesn't match (if specified)
    if match_intent and intent and intent != match_intent:
        return
    
    # Determine if this request should be part of canary (percentage-based)
    is_canary = random.randint(1, 100) <= canary_pct
    treatment = "canary" if is_canary else "control"
    
    # Log control group (no execution)
    if not is_canary:
        await agent_staging_storage.log_canary_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=request.helper_input or {},
            intent=intent,
            latency_ms=0,
            success=True,
            treatment="control",
            error_code=None,
            output_data=None
        )
        return
    
    # Execute canary treatment
    start_time = time.time()
    
    try:
        # Execute helper in canary mode (always dry_run=True for staging)
        helper_input = request.helper_input or {}
        
        canary_result = helper_executor.preview(
            helper_id=helper_id,
            input_data=helper_input,
            session_id=session_id,
            execution_mode="canary"
        )
        
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        # Log canary execution to staging storage
        await agent_staging_storage.log_canary_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent=intent,
            latency_ms=latency_ms,
            success=canary_result.get("status") == "success",
            treatment="canary",
            error_code=None,
            output_data=canary_result.get("preview_json")
        )
        
        # Audit log the canary execution
        audit_logger = get_audit_logger()
        if audit_logger:
            audit_logger.log_entry({
                "action": "agent_canary_run",
                "helper_id": helper_id,
                "session_id": session_id,
                "intent": intent,
                "treatment": "canary",
                "canary_pct": canary_pct,
                "latency_ms": latency_ms,
                "success": canary_result.get("status") == "success",
                "execution_mode": "canary"
            })
    
    except Exception as e:
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        # Log failed canary execution
        await agent_staging_storage.log_canary_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=request.helper_input or {},
            intent=intent,
            latency_ms=latency_ms,
            success=False,
            treatment="canary",
            error_code=type(e).__name__,
            output_data=None
        )
        
        # Audit log the canary execution error
        audit_logger = get_audit_logger()
        if audit_logger:
            audit_logger.log_entry({
                "action": "agent_canary_run_error",
                "helper_id": helper_id,
                "session_id": session_id,
                "intent": intent,
                "treatment": "canary",
                "canary_pct": canary_pct,
                "latency_ms": latency_ms,
                "error": str(e),
                "success": False,
                "execution_mode": "canary"
            })


# M10.3: Agent Staging Endpoints

@router_api.post("/agents/stage", response_model=AgentStagingResponse)
async def stage_agent(request: AgentStageRequest, auth: bool = Depends(verify_auth)):
    """Enable shadow execution for an agent."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Validate helper exists
        if not helper_registry.has_helper(request.helper_id):
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{request.helper_id}' not found"
            )
        
        # M10.3: Lifecycle gate - only draft or deprecated agents can be staged
        helper_entry = helper_registry.get_registry_entry(request.helper_id)
        if helper_entry:
            lifecycle_state = helper_entry.lifecycle.get("state", "draft")
            if lifecycle_state not in ["draft", "deprecated"]:
                # Log lifecycle violation
                audit_logger.log_entry({
                    "action": "agent_stage_blocked",
                    "helper_id": request.helper_id,
                    "lifecycle_state": lifecycle_state,
                    "reason": "Only draft or deprecated agents can be staged",
                    "success": False
                })
                
                raise HTTPException(
                    status_code=403,
                    detail=f"Cannot stage {lifecycle_state} agent. Only draft or deprecated agents can be staged."
                )
        
        # Set staging configuration
        agent_staging_storage.set_staging_config(
            helper_id=request.helper_id,
            mode=request.mode,
            match_intent=request.match_intent
        )
        
        # Log staging action
        audit_logger.log_entry({
            "action": "agent_stage",
            "helper_id": request.helper_id,
            "mode": request.mode,
            "match_intent": request.match_intent,
            "success": True
        })
        
        # Get current config for response
        config = agent_staging_storage.get_staging_config(request.helper_id)
        
        return AgentStagingResponse(
            status="success",
            helper_id=request.helper_id,
            message=f"Agent staged in {request.mode} mode",
            config=config
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_stage_error",
            "helper_id": request.helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to stage agent: {str(e)}"
        )


@router_api.post("/agents/canary", response_model=AgentStagingResponse)
async def canary_agent(request: AgentCanaryRequest, auth: bool = Depends(verify_auth)):
    """Enable canary rollout for an agent."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Validate helper exists
        if not helper_registry.has_helper(request.helper_id):
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{request.helper_id}' not found"
            )
        
        # M10.3: Lifecycle gate - trusted agents can be canaried for regression checks
        helper_entry = helper_registry.get_registry_entry(request.helper_id)
        if helper_entry:
            lifecycle_state = helper_entry.lifecycle.get("state", "draft")
            if lifecycle_state == "retired":
                # Log lifecycle violation
                audit_logger.log_entry({
                    "action": "agent_canary_blocked",
                    "helper_id": request.helper_id,
                    "lifecycle_state": lifecycle_state,
                    "reason": "Retired agents cannot be canaried",
                    "success": False
                })
                
                raise HTTPException(
                    status_code=410,
                    detail="Cannot canary retired agent"
                )
        
        # Set canary configuration
        agent_staging_storage.set_staging_config(
            helper_id=request.helper_id,
            mode="canary",
            canary_pct=request.pct,
            match_intent=request.match_intent
        )
        
        # Log canary action
        audit_logger.log_entry({
            "action": "agent_canary",
            "helper_id": request.helper_id,
            "canary_pct": request.pct,
            "match_intent": request.match_intent,
            "success": True
        })
        
        # Get current config for response
        config = agent_staging_storage.get_staging_config(request.helper_id)
        
        return AgentStagingResponse(
            status="success",
            helper_id=request.helper_id,
            message=f"Agent canaried at {request.pct}% traffic",
            config=config
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_canary_error",
            "helper_id": request.helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to canary agent: {str(e)}"
        )


@router_api.post("/agents/unstage", response_model=AgentStagingResponse)
async def unstage_agent(request: AgentUnstageRequest, auth: bool = Depends(verify_auth)):
    """Remove staging configuration for an agent."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Validate helper exists
        if not helper_registry.has_helper(request.helper_id):
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{request.helper_id}' not found"
            )
        
        # Remove staging configuration
        agent_staging_storage.remove_staging_config(request.helper_id)
        
        # Log unstaging action
        audit_logger.log_entry({
            "action": "agent_unstage",
            "helper_id": request.helper_id,
            "success": True
        })
        
        return AgentStagingResponse(
            status="success",
            helper_id=request.helper_id,
            message="Agent unstaged successfully",
            config=None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_unstage_error",
            "helper_id": request.helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unstage agent: {str(e)}"
        )


@router_api.get("/agents/report/{helper_id}", response_model=AgentReportResponse)
async def get_agent_report(helper_id: str, window_hours: int = 24, auth: bool = Depends(verify_auth)):
    """Get safety and quality report for an agent."""
    
    # Get audit logger
    audit_logger = get_audit_logger()
    
    try:
        # Validate helper exists
        if not helper_registry.has_helper(helper_id):
            raise HTTPException(
                status_code=404,
                detail=f"Helper '{helper_id}' not found"
            )
        
        # Check if report exists on disk
        helpers_dir = Path(__file__).parent.parent / "helpers"
        report_path = helpers_dir / helper_id / "report.json"
        
        if report_path.exists():
            # Load existing report
            try:
                with open(report_path, 'r') as f:
                    report = json.load(f)
                
                # Check if report is recent enough (within last 4 hours)
                report_time = datetime.fromisoformat(report.get("evaluation_timestamp", "1970-01-01"))
                if datetime.now() - report_time < timedelta(hours=4):
                    # Log report access
                    audit_logger.log_entry({
                        "action": "agent_report_access",
                        "helper_id": helper_id,
                        "source": "cache",
                        "success": True
                    })
                    
                    return AgentReportResponse(
                        helper_id=helper_id,
                        report=report,
                        generated_at=report.get("evaluation_timestamp", "unknown")
                    )
            except Exception as e:
                # If we can't load the cached report, generate a new one
                pass
        
        # Generate report on demand
        try:
            # Import the evaluator
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
            from eval_agents import AgentEvaluator
            
            evaluator = AgentEvaluator()
            report = evaluator.evaluate_agent(helper_id, window_hours)
            
            # Save the report
            evaluator.save_report(helper_id, report)
            
            # Log report generation
            audit_logger.log_entry({
                "action": "agent_report_generate",
                "helper_id": helper_id,
                "window_hours": window_hours,
                "success": True
            })
            
            return AgentReportResponse(
                helper_id=helper_id,
                report=report,
                generated_at=report.get("evaluation_timestamp", "unknown")
            )
            
        except Exception as e:
            # Log report generation error
            audit_logger.log_entry({
                "action": "agent_report_error",
                "helper_id": helper_id,
                "error": str(e),
                "success": False
            })
            
            raise HTTPException(
                status_code=500,
                detail=f"Failed to generate report: {str(e)}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        # Log unexpected errors
        audit_logger.log_entry({
            "action": "agent_report_error",
            "helper_id": helper_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get agent report: {str(e)}"
        )


# M11.0: iPhone Shortcut Voice Interface

def verify_shortcut_token(request: Request) -> bool:
    """
    Verify X-Shortcut-Token header for iOS Shortcuts authentication.
    
    Args:
        request: FastAPI request object
        
    Returns:
        bool: True if token is valid
        
    Raises:
        HTTPException: 401 if token is missing or invalid
    """
    import os
    
    # Get required token from environment
    required_token = os.getenv("SHORTCUT_TOKEN")
    if not required_token:
        raise HTTPException(
            status_code=500,
            detail="SHORTCUT_TOKEN not configured on server"
        )
    
    # Get token from request header
    provided_token = request.headers.get("X-Shortcut-Token")
    if not provided_token:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Shortcut-Token header"
        )
    
    # Verify token match
    if provided_token != required_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid X-Shortcut-Token"
        )
    
    return True


@router_api.get("/shortcut/ping", response_model=ShortcutPingResponse)
async def shortcut_ping(request: Request, auth: bool = Depends(verify_shortcut_token)):
    """
    Health check endpoint for iOS Shortcuts.
    
    Designed for Apple Shortcuts → Get Contents of URL to verify connectivity
    and authentication before sending voice commands.
    """
    return ShortcutPingResponse(
        ok=True,
        ts=datetime.utcnow().isoformat() + 'Z'
    )


@router_api.post("/shortcut/route", response_model=ShortcutRouteResponse)
async def shortcut_route(
    request: ShortcutRouteRequest, 
    fastapi_request: Request, 
    response: Response,
    auth: bool = Depends(verify_shortcut_token)
):
    """
    Main routing endpoint for iOS Shortcuts voice interface.
    
    Designed for Apple Shortcuts → Dictate Text → Get Contents of URL → Speak Text.
    
    Accepts dictated speech as text, routes through existing TinyIntent flow
    (respects router thresholds, approval gates, EXECUTION_ENABLED, provenance,
    quotas, sandboxing), and returns speakable response.
    
    Headers:
        X-Shortcut-Token: Required authentication token
    
    Body:
        {
            "text": "close ETH position",
            "session_id": "optional-session-id", 
            "mode": "preview|execute",
            "return_format": "text|json"
        }
    
    Response:
        {
            "speak": "Position closed on ETH at market.",
            "truncated": false,
            "data": { ...full normal payload... }
        }
    """
    import os
    
    # Get configuration
    max_length = int(os.getenv("SHORTCUT_MAX_LEN", "800"))
    execution_enabled = os.getenv("TINYINTENT_EXECUTION_ENABLED", "0") == "1"
    
    # Generate session ID if not provided
    session_id = request.session_id or f"shortcut_{int(time.time())}"
    
    audit_logger = get_audit_logger()
    
    try:
        # Sanitize input text
        try:
            sanitized_text = sanitize_short_input(request.text, max_length)
        except ValueError as e:
            # Log the validation error
            audit_logger.log_entry({
                "action": "shortcut_route",
                "session_id": session_id,
                "mode": request.mode,
                "validation_error": str(e),
                "success": False
            })
            
            error_response = get_shortcut_error_response(
                "VALIDATION_ERROR", 
                str(e),
                {"text_length": len(request.text), "max_length": max_length}
            )
            
            raise HTTPException(status_code=400, detail=error_response)
        
        # Check execution permissions for execute mode
        if request.mode == "execute":
            if not execution_enabled:
                # Log execution disabled attempt
                audit_logger.log_entry({
                    "action": "shortcut_route",
                    "session_id": session_id,
                    "mode": request.mode,
                    "blocked_reason": "execution_disabled",
                    "success": False
                })
                
                error_response = get_shortcut_error_response(
                    "EXECUTION_DISABLED",
                    "Execution is currently disabled on this server"
                )
                
                raise HTTPException(status_code=403, detail=error_response)
        
        # Create RouteRequest for existing flow
        route_request = RouteRequest(
            text=sanitized_text,
            route="auto",  # Let router decide
            session_id=session_id,
            execute=(request.mode == "execute")
        )
        
        # Log shortcut request
        audit_logger.log_entry({
            "action": "shortcut_route",
            "session_id": session_id,
            "mode": request.mode,
            "return_format": request.return_format,
            "text_length": len(sanitized_text),
            "success": None  # Will be updated below
        })
        
        # Route through existing flow
        try:
            # Use the existing route_request_endpoint logic
            # This ensures all gates (quotas, sandboxing, provenance, etc.) are respected
            route_response = await route_request_endpoint(
                route_request, 
                fastapi_request, 
                response, 
                auth=True  # Already authenticated via shortcut token
            )
            
            # Convert to shortcut format
            response_data = route_response.dict()
            shortcut_response = format_shortcut_response(response_data, request.return_format)
            
            # Update audit log with success
            audit_logger.log_entry({
                "action": "shortcut_route_success",
                "session_id": session_id,
                "mode": request.mode,
                "route_used": response_data.get("route_used"),
                "helper_id": response_data.get("helper_id"),
                "success": True
            })
            
            return ShortcutRouteResponse(**shortcut_response)
            
        except HTTPException as e:
            # Handle structured errors from existing flow
            status_code = e.status_code
            detail = e.detail
            
            # Map common errors to shortcut-friendly responses
            if status_code == 403:
                if isinstance(detail, dict):
                    error_code = detail.get("error", "FORBIDDEN")
                    message = detail.get("detail", "Action not allowed")
                else:
                    error_code = "FORBIDDEN"
                    message = str(detail)
                
                error_response = get_shortcut_error_response(error_code, message, detail if isinstance(detail, dict) else None)
            elif status_code == 429:
                error_response = get_shortcut_error_response(
                    "RATE_LIMIT", 
                    "Too many requests. Please wait before trying again.",
                    detail if isinstance(detail, dict) else None
                )
            elif status_code == 400:
                error_response = get_shortcut_error_response(
                    "VALIDATION_ERROR",
                    "Invalid request",
                    detail if isinstance(detail, dict) else None
                )
            else:
                error_response = get_shortcut_error_response(
                    "SERVER_ERROR",
                    "An error occurred processing your request"
                )
            
            # Log the error
            audit_logger.log_entry({
                "action": "shortcut_route_error",
                "session_id": session_id,
                "mode": request.mode,
                "error_code": error_response.get("error"),
                "status_code": status_code,
                "success": False
            })
            
            # Return appropriate HTTP status with shortcut-friendly response
            raise HTTPException(status_code=status_code, detail=error_response)
            
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Handle unexpected errors
        audit_logger.log_entry({
            "action": "shortcut_route_error",
            "session_id": session_id,
            "mode": request.mode,
            "error": str(e),
            "success": False
        })
        
        error_response = get_shortcut_error_response(
            "SERVER_ERROR",
            "An unexpected error occurred"
        )
        
        raise HTTPException(status_code=500, detail=error_response)
