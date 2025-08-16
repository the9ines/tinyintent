"""
TinyIntent Bridge MVP - FastAPI service for routing and orchestrating AI tasks.
"""

import os
import shutil
import subprocess
import time
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator
import uvicorn

from resolve import ModelResolver
from events import event_logger, session_manager


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
        "missing_models": missing_models
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
    auth: bool = Depends(verify_auth)
) -> RouteResponse:
    """Route a request to generation or action."""
    
    # Get or create session ID
    session_id = request.session_id
    if not session_id:
        session_id = session_manager.create_session()
    elif not session_manager.session_exists(session_id):
        session_manager.create_session(session_id)
    
    # Update session activity
    session_manager.update_session_activity(session_id)
    
    # Determine which model to use
    model_to_use = None
    if request.llm_model:
        model_to_use = request.llm_model
    elif request.llm_pref:
        model_to_use = model_resolver.get_model(request.llm_pref)
        if not model_to_use:
            # Log error event
            event_logger.log_request(
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
        event_logger.log_request(
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
            event_logger.log_request(
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
            event_logger.log_request(
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
            event_logger.log_request(
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
        # Log not implemented event
        event_logger.log_request(
            session_id=session_id,
            text=request.text,
            route_final="act",
            success=False,
            error_code="NOT_IMPLEMENTED"
        )
        # Action route - return 501 Not Implemented
        raise HTTPException(
            status_code=501,
            detail="Action routing not yet implemented (coming in M4)"
        )
    
    elif request.route == "auto":
        # Log not implemented event
        event_logger.log_request(
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
        event_logger.log_request(
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
    """Submit feedback for a session/episode."""
    
    # Validate session exists
    if not session_manager.session_exists(request.session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session {request.session_id} not found"
        )
    
    # Log feedback event
    try:
        event_logger.log_feedback(request.session_id, request.feedback)
        
        # Update session activity
        session_manager.update_session_activity(request.session_id)
        
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