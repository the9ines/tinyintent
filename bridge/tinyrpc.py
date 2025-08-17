"""
TinyIntent Bridge MVP - FastAPI service for routing and orchestrating AI tasks.
Implements M2: Experience Store with NDJSON and SQLite logging.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator
import uvicorn

# Load environment variables from .env file if it exists
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value.strip('"').strip("'")

# Load .env file on module import
load_env_file()

from resolve import ModelResolver
from store import experience_store
from approval import approval_manager
from episodes import episode_logger

# Import helpers framework (with fallback for missing dependencies)
import sys
sys.path.append(str(Path(__file__).parent.parent / "helpers"))
try:
    from sdk import helper_registry, helper_executor
    from reflector import reflector
    HELPERS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helpers framework not available: {e}")
    HELPERS_AVAILABLE = False
    helper_registry = None
    helper_executor = None
    reflector = None


# Initialize FastAPI app
app = FastAPI(title="TinyIntent Bridge", version="1.0.0")

# Initialize model resolver
model_resolver = ModelResolver()

# Security
security = HTTPBearer(auto_error=False)


class RouteRequest(BaseModel):
    """Request model for POST /route endpoint."""
    text: str
    route: Optional[str] = "auto"  # auto|gen|act
    llm_pref: Optional[str] = None  # small|medium|large
    llm_model: Optional[str] = None  # specific ollama tag
    session_id: Optional[str] = None  # Session ID for episode tracking
    helper_id: Optional[str] = None  # Specific helper for act route
    helper_input: Optional[Dict[str, Any]] = None  # Direct helper input
    # Guarded execution fields
    execute: Optional[bool] = False  # True to execute, False for preview (default)
    approval_token: Optional[str] = None  # Required for execute=True
    # Idempotency field
    idempotency_key: Optional[str] = None  # Optional idempotency key
    
    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('text field cannot be empty')
        return v


class RouteResponse(BaseModel):
    """Response model for POST /route endpoint."""
    status: str
    route_used: str
    text_response: Optional[str] = None
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None
    session_id: str
    _router_fallback: Optional[bool] = None
    # Helper-specific fields for act route
    action: Optional[str] = None  # preview|execute
    helper_id: Optional[str] = None
    preview_json: Optional[Dict[str, Any]] = None
    approval_token: Optional[str] = None
    # Reflection layer fields
    reflection: Optional[Dict[str, Any]] = None
    veto_reason: Optional[str] = None
    reflection_error: Optional[str] = None
    # Idempotency field
    idempotent: Optional[bool] = None


class FeedbackRequest(BaseModel):
    """Request model for POST /feedback endpoint."""
    session_id: str
    feedback: str
    
    @validator('feedback')
    def feedback_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('feedback field cannot be empty')
        return v


class FeedbackResponse(BaseModel):
    """Response model for POST /feedback endpoint."""
    status: str
    message: str


def get_tinyintent_secret() -> str:
    """Get the required TINYINTENT_SECRET from environment."""
    secret = os.getenv("TINYINTENT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="TINYINTENT_SECRET environment variable is required"
        )
    return secret


def verify_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """Verify X-TinyIntent-Secret header authentication."""
    # Check if dev bypass is enabled for localhost
    allow_dev_local = os.getenv("ALLOW_DEV_LOCAL", "0") == "1"
    if allow_dev_local:
        # Check if request is from localhost without X-Forwarded-For
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if not x_forwarded_for and request.client and request.client.host in ["127.0.0.1", "localhost"]:
            return True
    
    # Check for X-TinyIntent-Secret header
    secret_header = request.headers.get("X-TinyIntent-Secret")
    if not secret_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-TinyIntent-Secret header is required"
        )
    
    expected_secret = get_tinyintent_secret()
    if secret_header != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-TinyIntent-Secret"
        )
    
    return True


def call_ollama_generate(model_tag: str, prompt: str) -> tuple[str, int]:
    """Call ollama to generate text and return the response with latency."""
    start_time = time.time()
    
    try:
        # Call ollama run command
        result = subprocess.run(
            ["ollama", "run", model_tag, prompt],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown ollama error"
            raise HTTPException(
                status_code=500,
                detail=f"Ollama execution failed: {error_msg}"
            )
        
        response_text = result.stdout.strip()
        return response_text, latency_ms
        
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="Ollama request timed out"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Ollama binary not found. Please ensure ollama is installed and in PATH."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error calling ollama: {str(e)}"
        )


def check_ollama_present() -> bool:
    """Check if ollama binary is available."""
    return shutil.which("ollama") is not None


def check_env_valid() -> bool:
    """Check if required environment variables are set."""
    return os.getenv("TINYINTENT_SECRET") is not None


def check_router_binary() -> bool:
    """Check if router binary is available (placeholder for M3)."""
    # TODO: Implement router binary check in M3
    return False


def check_helpers_present() -> bool:
    """Check if helpers are available and loaded."""
    if not HELPERS_AVAILABLE or not helper_registry:
        return False
    return len(helper_registry.list_helpers()) > 0


def get_missing_helpers() -> List[str]:
    """Get list of helpers that failed to load."""
    if not HELPERS_AVAILABLE:
        return ["helpers framework not available"]
    # TODO: Implement missing helpers detection
    return []


def route_to_helper(text: str, model_tag: str) -> str:
    """Use LLM to determine which helper to use for action routing."""
    # Simple heuristic for M4 - in M5 this would use the trained router
    text_lower = text.lower()
    
    if any(term in text_lower for term in ['bot', 'position', 'trade', 'close', 'stop', 'emergency']):
        return 'bot_guard'
    
    # Default fallback
    return 'bot_guard'


def extract_helper_input(text: str, helper_id: str, model_tag: str) -> Dict[str, Any]:
    """Use LLM to extract structured input for helper from natural language."""
    # Simple extraction logic for M4 - in M5 this would use LLM
    text_lower = text.lower()
    
    if helper_id == 'bot_guard':
        # Extract trading operations from text
        if 'close all' in text_lower or 'emergency' in text_lower:
            return {
                "operation": "close_all_positions",
                "dry_run": True
            }
        elif 'close' in text_lower:
            # Try to extract symbol
            symbols = ['btc', 'eth', 'sol', 'ada', 'dot']
            symbol = None
            for s in symbols:
                if s in text_lower:
                    symbol = f"{s.upper()}/USDT"
                    break
            
            return {
                "operation": "close_position",
                "symbol": symbol or "BTC/USDT",
                "dry_run": True
            }
        elif 'position' in text_lower:
            return {
                "operation": "get_positions",
                "dry_run": True
            }
        elif 'balance' in text_lower:
            return {
                "operation": "get_balance",
                "dry_run": True
            }
    
    # Default fallback
    return {
        "operation": "get_positions",
        "dry_run": True
    }


@app.get("/healthz")
async def health_check() -> Dict[str, str]:
    """Health check endpoint - no authentication required."""
    return {"status": "ok"}


@app.get("/readyz")
async def readiness_check() -> Dict[str, Any]:
    """Readiness check endpoint - no authentication required."""
    models = model_resolver.get_all_models()
    missing_models = model_resolver.get_missing_models()
    
    checks = {
        "env_valid": check_env_valid(),
        "ollama_present": check_ollama_present(),
        "router_binary": check_router_binary(),
        "models_present": len(missing_models) == 0,
        "missing_models": missing_models,
        "helpers_present": check_helpers_present(),
        "missing_helpers": get_missing_helpers()
    }
    
    # Return 503 if any critical checks fail
    all_ready = checks["env_valid"] and checks["ollama_present"]
    status_code = 200 if all_ready else 503
    
    return {
        "ready": all_ready,
        "checks": checks,
        "models": models
    }


@app.post("/route")
async def route_request(
    request: RouteRequest, 
    fastapi_request: Request,
    auth: bool = Depends(verify_auth)
) -> RouteResponse:
    """
    Route a request to generation or action with full event logging.
    
    Example usage:
    
    # Preview request
    curl -X POST "http://localhost:8787/route" \
      -H "Content-Type: application/json" \
      -H "X-TinyIntent-Secret: your_secret" \
      -d '{"text": "Show my positions", "route": "act", "helper_id": "bot_guard"}'
    
    # Execute with approval token and idempotency
    curl -X POST "http://localhost:8787/route" \
      -H "Content-Type: application/json" \
      -H "X-TinyIntent-Secret: your_secret" \
      -H "X-Idempotency-Key: unique-key-123" \
      -d '{"text": "Show my positions", "route": "act", "helper_id": "bot_guard", 
           "execute": true, "approval_token": "abc123..."}'
    """
    
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
    
    # Determine which model to use
    model_to_use = None
    if request.llm_model:
        model_to_use = request.llm_model
    elif request.llm_pref:
        model_to_use = model_resolver.get_model(request.llm_pref)
        if not model_to_use:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final=request.route,
                success=False,
                error_code="INVALID_MODEL_PREF"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model preference: {request.llm_pref}"
            )
    else:
        # Default to small model
        model_to_use = model_resolver.get_model("small")
    
    if not model_to_use:
        # Log error event
        experience_store.log_request(
            session_id=session_id,
            text=request.text,
            route_final=request.route,
            success=False,
            error_code="NO_MODEL_CONFIGURED"
        )
        raise HTTPException(
            status_code=500,
            detail="No suitable model configured"
        )
    
    # Handle different route types
    if request.route == "gen":
        # Generation route - call ollama
        try:
            response_text, latency_ms = call_ollama_generate(model_to_use, request.text)
            
            # Log successful event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="gen",
                model_used=model_to_use,
                latency_ms=latency_ms,
                success=True
            )
            
            return RouteResponse(
                status="success",
                route_used="gen",
                text_response=response_text,
                model_used=model_to_use,
                latency_ms=latency_ms,
                session_id=session_id
            )
            
        except HTTPException as e:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="gen",
                model_used=model_to_use,
                success=False,
                error_code="OLLAMA_ERROR"
            )
            raise  # Re-raise HTTP exceptions from call_ollama_generate
            
        except Exception as e:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="gen",
                model_used=model_to_use,
                success=False,
                error_code="UNEXPECTED_ERROR"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during generation: {str(e)}"
            )
    
    elif request.route == "act":
        # Action route - delegate to Helpers Orchestrator
        try:
            start_time = time.time()
            
            # Check if helpers are available and enabled
            if not HELPERS_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="Helpers framework not available (missing dependencies)"
                )
                
            helpers_enabled = os.getenv("HELPERS_ENABLED", "1") == "1"
            if not helpers_enabled:
                raise HTTPException(
                    status_code=503,
                    detail="Helpers framework is disabled"
                )
            
            # Check execution gate for execute mode
            if request.execute:
                execution_enabled = os.getenv("EXECUTION_ENABLED", "0") == "1"
                if not execution_enabled:
                    raise HTTPException(
                        status_code=503,
                        detail="Execution disabled"
                    )
            
            # Determine helper to use
            if request.helper_id:
                helper_id = request.helper_id
            else:
                # Use LLM to route to appropriate helper
                helper_id = route_to_helper(request.text, model_to_use)
            
            # Prepare helper input
            if request.helper_input:
                helper_input = request.helper_input
            else:
                # Use LLM to extract structured input from natural language
                helper_input = extract_helper_input(request.text, helper_id, model_to_use)
            
            # Check for idempotency in execute mode
            if request.execute and idempotency_key:
                cached_result = approval_manager.get_idempotency_result(
                    idempotency_key, helper_id, helper_input
                )
                if cached_result:
                    # Return cached result with idempotent flag
                    cached_result["idempotent"] = True
                    return RouteResponse(**cached_result)
            
            # Determine execution mode
            execution_mode = "execute" if request.execute else "preview"
            
            # Handle guarded execution flow
            if request.execute:
                # Get helper manifest for risk level
                helper_manifest = helper_registry.get_helper(helper_id)
                if not helper_manifest:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Helper not found: {helper_id}"
                    )
                
                # Check if helper can execute
                if not helper_manifest.can_execute():
                    raise HTTPException(
                        status_code=501,
                        detail=f"Helper {helper_id} does not support execution"
                    )
                
                # Get risk level from registry or manifest
                registry_entry = helper_registry.registry_data.get("helpers", {}).get(helper_id, {})
                risk_level = registry_entry.get("risk_level", "medium")
                
                # Validate approval token for execution
                is_valid, error_msg, token_id = approval_manager.validate_approval_token(
                    request.approval_token, helper_id, helper_input, request.text, risk_level
                )
                
                if not is_valid:
                    # Log failed approval attempt
                    experience_store.log_request(
                        session_id=session_id,
                        text=request.text,
                        route_final="act",
                        helper_id=helper_id,
                        success=False,
                        error_code="APPROVAL_FAILED"
                    )
                    
                    # Determine reason code for better error reporting
                    reason_code = "TOKEN_INVALID"
                    if "already used" in error_msg:
                        reason_code = "TOKEN_USED"
                    elif "expired" in error_msg:
                        reason_code = "TOKEN_EXPIRED"
                    elif "too old" in error_msg:
                        reason_code = "TOKEN_TOO_OLD"
                    elif "does not match" in error_msg:
                        reason_code = "TOKEN_MISMATCH"
                    
                    raise HTTPException(
                        status_code=403,
                        detail=error_msg,
                        headers={"reason_code": reason_code}
                    )
                
                # Execute helper
                try:
                    helper_result = helper_executor.execute(
                        helper_id=helper_id,
                        input_data=helper_input,
                        session_id=session_id,
                        token_id=token_id,
                        idempotency_key=idempotency_key
                    )
                except ValueError as e:
                    if hasattr(e, 'missing_vars'):
                        # Missing environment variables - return 409
                        raise HTTPException(
                            status_code=409,
                            detail=f"Required environment variables missing for {helper_id}",
                            headers={"missing_vars": json.dumps(e.missing_vars)}
                        )
                    elif "Output schema validation failed" in str(e):
                        # Schema validation failed - return 500
                        raise HTTPException(
                            status_code=500,
                            detail="Helper output schema validation failed",
                            headers={"error_code": "SCHEMA_VALIDATION_FAILED"}
                        )
                    else:
                        raise
                
                except RuntimeError as e:
                    # Check for sandbox violations
                    if "Sandbox violation:" in str(e):
                        # Extract error code from sandbox violation
                        error_msg = str(e)
                        if "SANDBOX_TIMEOUT" in error_msg:
                            error_code = "SANDBOX_TIMEOUT"
                        elif "SANDBOX_CPU_LIMIT" in error_msg:
                            error_code = "SANDBOX_CPU_LIMIT"
                        elif "SANDBOX_MEMORY_LIMIT" in error_msg:
                            error_code = "SANDBOX_MEMORY_LIMIT"
                        elif "SANDBOX_OUTPUT_SIZE" in error_msg:
                            error_code = "SANDBOX_OUTPUT_SIZE"
                        else:
                            error_code = "SANDBOX_VIOLATION"
                        
                        raise HTTPException(
                            status_code=500,
                            detail="Helper execution failed due to sandbox limits",
                            headers={"error_code": error_code}
                        )
                    else:
                        # Regular runtime error
                        raise HTTPException(
                            status_code=500,
                            detail=f"Helper execution failed: {str(e)}",
                            headers={"error_code": "EXECUTION_FAILED"}
                        )
                
                # Cache result for idempotency if key provided
                if idempotency_key:
                    cache_result = {
                        "status": helper_result.get("status", "success"),
                        "route_used": "act",
                        "session_id": session_id,
                        "action": "execute",
                        "helper_id": helper_id,
                        "result": helper_result.get("result")
                    }
                    approval_manager.set_idempotency_result(
                        idempotency_key, helper_id, helper_input, cache_result
                    )
                
            else:
                # Execute helper in preview mode
                try:
                    helper_result = helper_executor.preview(
                        helper_id=helper_id,
                        input_data=helper_input,
                        session_id=session_id
                    )
                except RuntimeError as e:
                    # Check for sandbox violations in preview mode
                    if "Sandbox violation:" in str(e):
                        # Extract error code from sandbox violation
                        error_msg = str(e)
                        if "SANDBOX_TIMEOUT" in error_msg:
                            error_code = "SANDBOX_TIMEOUT"
                        elif "SANDBOX_CPU_LIMIT" in error_msg:
                            error_code = "SANDBOX_CPU_LIMIT"
                        elif "SANDBOX_MEMORY_LIMIT" in error_msg:
                            error_code = "SANDBOX_MEMORY_LIMIT"
                        elif "SANDBOX_OUTPUT_SIZE" in error_msg:
                            error_code = "SANDBOX_OUTPUT_SIZE"
                        else:
                            error_code = "SANDBOX_VIOLATION"
                        
                        raise HTTPException(
                            status_code=500,
                            detail="Helper preview failed due to sandbox limits",
                            headers={"error_code": error_code}
                        )
                    else:
                        # Regular runtime error
                        raise HTTPException(
                            status_code=500,
                            detail=f"Helper preview failed: {str(e)}",
                            headers={"error_code": "PREVIEW_FAILED"}
                        )
            
            # Apply reflection layer validation
            reflection_enabled = os.getenv("REFLECTION_ENABLED", "1") == "1"
            reflection_result = None
            
            if reflection_enabled and reflector and helper_result.get("status") == "success":
                try:
                    reflection_result = reflector.reflect(
                        helper_id=helper_id,
                        user_text=request.text,
                        helper_input=helper_input,
                        helper_output=helper_result.get("preview_json", {}),
                        session_id=session_id
                    )
                    
                    # Add reflection data to helper result
                    helper_result["reflection"] = reflection_result
                    
                    # Override approval if reflection vetoes
                    if not reflection_result.get("approved", False):
                        helper_result["status"] = "vetoed"
                        helper_result["veto_reason"] = reflection_result.get("veto_reason")
                        
                except Exception as e:
                    # Don't fail the request if reflection fails, but log it
                    helper_result["reflection_error"] = str(e)
            
            # Generate approval token for preview mode if helper supports execution
            approval_token = None
            if not request.execute and helper_result.get("status") == "success":
                # Check if helper requires approval for execution
                helper_manifest = helper_registry.get_helper(helper_id)
                if helper_manifest and helper_manifest.can_execute():
                    approval_token = approval_manager.generate_approval_token(
                        helper_id=helper_id,
                        helper_input=helper_input,
                        session_id=session_id,
                        user_text=request.text
                    )
                    helper_result["approval_token"] = approval_token
            
            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)
            
            # Log successful event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="act",
                helper_id=helper_id,
                helper_input=helper_input,
                preview_json=helper_result.get("preview_json"),
                latency_ms=latency_ms,
                success=True
            )
            
            # Log episode for router retraining
            final_status = helper_result.get("status", "success")
            episode_success = final_status == "success"
            episode_error_code = None
            
            if not episode_success:
                if helper_result.get("veto_reason"):
                    episode_error_code = "REFLECTION_VETO"
                elif helper_result.get("reflection_error"):
                    episode_error_code = "REFLECTION_ERROR"
            
            episode_logger.log_episode(
                session_id=session_id,
                action=execution_mode,
                helper_id=helper_id,
                input_data=helper_input,
                status_code=200,  # HTTP status for successful response
                success=episode_success,
                approval_token_id=token_id if request.execute else None,
                idempotency_key=idempotency_key,
                error_code=episode_error_code
            )
            
            # Build response based on execution mode
            if request.execute:
                return RouteResponse(
                    status=helper_result.get("status", "success"),
                    route_used="act",
                    session_id=session_id,
                    latency_ms=latency_ms,
                    action="execute",
                    helper_id=helper_id,
                    preview_json=helper_result.get("result"),
                    reflection=helper_result.get("reflection"),
                    veto_reason=helper_result.get("veto_reason"),
                    reflection_error=helper_result.get("reflection_error")
                )
            else:
                return RouteResponse(
                    status=helper_result.get("status", "success"),
                    route_used="act",
                    session_id=session_id,
                    latency_ms=latency_ms,
                    action="preview",
                    helper_id=helper_result.get("helper_id", helper_id),
                    preview_json=helper_result.get("preview_json"),
                    approval_token=helper_result.get("approval_token"),
                    reflection=helper_result.get("reflection"),
                    veto_reason=helper_result.get("veto_reason"),
                    reflection_error=helper_result.get("reflection_error")
                )
            
        except HTTPException as e:
            # Log failed episode for HTTP exceptions
            error_code = None
            if e.status_code == 403:
                error_code = "APPROVAL_FAILED"
            elif e.status_code == 409:
                error_code = "MISSING_ENVIRONMENT"
            elif e.status_code == 500:
                error_code = "SCHEMA_VALIDATION_FAILED"
            elif e.status_code == 503:
                error_code = "EXECUTION_DISABLED"
            
            episode_logger.log_episode(
                session_id=session_id,
                action=execution_mode,
                helper_id=helper_id if 'helper_id' in locals() else "unknown",
                input_data=helper_input if 'helper_input' in locals() else {},
                status_code=e.status_code,
                success=False,
                approval_token_id=token_id if 'token_id' in locals() else None,
                idempotency_key=idempotency_key,
                error_code=error_code
            )
            
            raise  # Re-raise HTTP exceptions
            
        except Exception as e:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="act",
                success=False,
                error_code="HELPER_ERROR"
            )
            
            # Log failed episode for unexpected errors
            episode_logger.log_episode(
                session_id=session_id,
                action=execution_mode if 'execution_mode' in locals() else "unknown",
                helper_id=helper_id if 'helper_id' in locals() else "unknown",
                input_data=helper_input if 'helper_input' in locals() else {},
                status_code=500,
                success=False,
                approval_token_id=None,
                idempotency_key=idempotency_key,
                error_code="HELPER_ERROR"
            )
            
            raise HTTPException(
                status_code=500,
                detail=f"Helper execution failed: {str(e)}"
            )
    
    elif request.route == "auto":
        # Log not implemented event
        experience_store.log_request(
            session_id=session_id,
            text=request.text,
            route_final="auto",
            success=False,
            error_code="NOT_IMPLEMENTED"
        )
        # Auto routing - return 501 Not Implemented
        raise HTTPException(
            status_code=501,
            detail="Auto routing not yet implemented - router support coming in M3"
        )
    
    else:
        # Log error event
        experience_store.log_request(
            session_id=session_id,
            text=request.text,
            route_final=request.route,
            success=False,
            error_code="UNKNOWN_ROUTE"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unknown route: {request.route}"
        )


@app.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    auth: bool = Depends(verify_auth)
) -> FeedbackResponse:
    """Submit feedback for a session/episode. Implements M2 requirement."""
    
    # Validate session exists
    if not experience_store.session_exists(request.session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session {request.session_id} not found"
        )
    
    # Log feedback event
    try:
        experience_store.log_feedback(request.session_id, request.feedback)
        
        # Update session activity
        experience_store.update_session_activity(request.session_id)
        
        return FeedbackResponse(
            status="success",
            message="Feedback logged successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to log feedback: {str(e)}"
        )


@app.post("/admin/reload-models")
async def reload_models(auth: bool = Depends(verify_auth)) -> Dict[str, str]:
    """Reload models.yaml configuration."""
    try:
        model_resolver.reload()
        return {"status": "success", "message": "Models reloaded"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload models: {str(e)}"
        )


@app.post("/admin/reload-helpers")
async def reload_helpers(auth: bool = Depends(verify_auth)) -> Dict[str, str]:
    """Reload helper manifests. M4: Helpers Framework v1"""
    if not HELPERS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Helpers framework not available (missing dependencies)"
        )
        
    try:
        helper_registry.reload()
        helpers_count = len(helper_registry.list_helpers())
        return {
            "status": "success", 
            "message": f"Helpers reloaded - {helpers_count} helpers available",
            "helpers": helper_registry.list_helpers()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload helpers: {str(e)}"
        )


if __name__ == "__main__":
    # Get configuration from environment
    bind_addr = os.getenv("TINYINTENT_BIND", "0.0.0.0")
    port = int(os.getenv("TINYINTENT_PORT", "8787"))
    
    # Ensure TINYINTENT_SECRET is set
    if not os.getenv("TINYINTENT_SECRET"):
        print("ERROR: TINYINTENT_SECRET environment variable is required")
        exit(1)
    
    # Start the server
    uvicorn.run(
        "tinyrpc:app",
        host=bind_addr,
        port=port,
        reload=False,
        log_level="info"
    )