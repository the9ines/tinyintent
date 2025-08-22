"""
Simple TinyIntent Server

Fallback server implementation when full app is not available.
"""

import os
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

def create_simple_app() -> FastAPI:
    """Create a simple TinyIntent server."""
    app = FastAPI(
        title="TinyIntent Bridge - Simple Mode",
        version="2.0.0",
        description="Simplified TinyIntent server for basic functionality"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Models
    class HealthResponse(BaseModel):
        ok: bool
        ts: str
        service: str
        version: str
        mode: str = "simple"
    
    class ShortcutPingResponse(BaseModel):
        ok: bool
        ts: str
        service: str
        version: str
    
    class ShortcutRouteRequest(BaseModel):
        text: str
        session_id: Optional[str] = None
        mode: str = "preview"
        return_format: str = "text"
    
    class ShortcutRouteResponse(BaseModel):
        speak: Optional[str] = None
        truncated: bool = False
        data: Optional[Dict[str, Any]] = None
        error: Optional[str] = None
    
    # Authentication
    def verify_shortcut_token(request: Request) -> bool:
        """Verify X-Shortcut-Token header."""
        expected_token = os.environ.get('SHORTCUT_TOKEN', 'tinyintent-shortcut-token-123')
        provided_token = request.headers.get("X-Shortcut-Token")
        
        if not provided_token:
            raise HTTPException(status_code=401, detail="Missing X-Shortcut-Token header")
        
        if provided_token != expected_token:
            raise HTTPException(status_code=401, detail="Invalid X-Shortcut-Token")
        
        return True
    
    # Routes
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "TinyIntent Bridge - Simple Mode",
            "version": "2.0.0",
            "status": "running",
            "endpoints": [
                "GET /health - Health check",
                "GET /shortcut/ping - Shortcut health check", 
                "POST /shortcut/route - Shortcut routing"
            ]
        }
    
    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Health check."""
        return HealthResponse(
            ok=True,
            ts=datetime.utcnow().isoformat() + "Z",
            service="TinyIntent Bridge",
            version="2.0.0"
        )
    
    @app.get("/shortcut/ping", response_model=ShortcutPingResponse)
    async def shortcut_ping(request: Request, auth: bool = Depends(verify_shortcut_token)):
        """Shortcut health check."""
        return ShortcutPingResponse(
            ok=True,
            ts=datetime.utcnow().isoformat() + "Z",
            service="TinyIntent Bridge",
            version="2.0.0"
        )
    
    @app.post("/shortcut/route", response_model=ShortcutRouteResponse)
    async def shortcut_route(
        request: ShortcutRouteRequest,
        fastapi_request: Request,
        auth: bool = Depends(verify_shortcut_token)
    ):
        """Simple shortcut routing."""
        try:
            # Basic input validation
            if not request.text or len(request.text.strip()) == 0:
                return ShortcutRouteResponse(
                    speak="Error: Input text cannot be empty",
                    error="VALIDATION_ERROR"
                )
            
            max_len = int(os.environ.get('SHORTCUT_MAX_LEN', '800'))
            if len(request.text) > max_len:
                return ShortcutRouteResponse(
                    speak=f"Error: Input text too long. Maximum {max_len} characters.",
                    error="VALIDATION_ERROR"
                )
            
            # Simple mock response
            speak_text = f"I received your command: '{request.text}'. TinyIntent simple mode is active."
            
            response_data = {
                "status": "success",
                "mode": "simple",
                "text": speak_text,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            if request.return_format == "text":
                return ShortcutRouteResponse(
                    speak=speak_text,
                    truncated=False,
                    data=response_data
                )
            else:
                return ShortcutRouteResponse(data=response_data)
                
        except Exception as e:
            return ShortcutRouteResponse(
                speak="An error occurred while processing your request.",
                error="INTERNAL_ERROR"
            )
    
    return app