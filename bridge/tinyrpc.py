"""
TinyIntent Bridge MVP - FastAPI service for routing and orchestrating AI tasks.
"""

import os
import shutil
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uvicorn

from resolve import ModelResolver


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


class RouteResponse(BaseModel):
    """Response model for POST /route endpoint."""
    status: str
    route_used: str
    text_response: Optional[str] = None
    model_used: Optional[str] = None
    _router_fallback: Optional[bool] = None


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
    
    # Handle different route types
    if request.route == "gen":
        # Generation route - placeholder implementation
        return RouteResponse(
            status="success",
            route_used="gen",
            text_response=f"Generated response for: {request.text}",
            model_used=model_to_use
        )
    
    elif request.route == "act":
        # Action route - placeholder implementation for M4
        return RouteResponse(
            status="success",
            route_used="act",
            text_response="Action routing not yet implemented (coming in M4)",
            model_used=model_to_use
        )
    
    elif request.route == "auto":
        # Auto routing - placeholder implementation for M3
        # For now, use simple heuristic fallback
        if "generate" in request.text.lower() or "write" in request.text.lower():
            route_used = "gen"
        else:
            route_used = "act"
        
        return RouteResponse(
            status="success",
            route_used=route_used,
            text_response=f"Auto-routed to {route_used}: {request.text}",
            model_used=model_to_use,
            _router_fallback=True
        )
    
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown route: {request.route}"
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