"""
TinyIntent Bridge Service - Streamlined Version

Clean, modular FastAPI application with proper structure.
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# Import route modules
from .routes import (
    health_router,
    helpers_router,
    agents_router, 
    shortcut_router,
    system_router
)

def setup_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure root logger
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
    )

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan management."""
    # Startup
    setup_logging()
    logger = structlog.get_logger()
    logger.info("TinyIntent Bridge starting up")
    
    # TODO: Initialize subsystems
    # - Helper registry
    # - Router client
    # - Generation client
    # - Storage systems
    
    yield
    
    # Shutdown
    logger.info("TinyIntent Bridge shutting down")

def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="TinyIntent Bridge",
        version="2.0.0",
        description="Voice-Activated AI Assistant Platform",
        lifespan=lifespan
    )
    
    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*"]  # Configure appropriately for production
    )
    
    # Include routers
    app.include_router(health_router)
    app.include_router(helpers_router)
    app.include_router(agents_router)
    app.include_router(shortcut_router)
    app.include_router(system_router)
    
    # Root endpoint
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "service": "TinyIntent Bridge",
            "version": "2.0.0",
            "status": "operational",
            "features": [
                "🧠 SmallIntent.mlmodel routing",
                "📱 iPhone Shortcut voice interface", 
                "🤖 Secure helper execution framework",
                "🔒 Comprehensive security & audit logging",
                "📊 System monitoring & health checks"
            ],
            "endpoints": {
                "health": "/health",
                "shortcut": "/shortcut/ping, /shortcut/route",
                "helpers": "/helpers",
                "agents": "/agents/lifecycle",
                "system": "/system/doctor",
                "docs": "/docs"
            }
        }
    
    return app

# Create the app instance
app = create_app()

def main():
    """CLI entry point for running the server directly."""
    uvicorn.run(
        "tinyintent.bridge.tinyrpc_streamlined:app",
        host="0.0.0.0",
        port=8787,
        reload=True
    )

if __name__ == "__main__":
    main()