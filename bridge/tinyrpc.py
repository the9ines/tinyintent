"""
TinyIntent Bridge Service

Main entrypoint for the FastAPI application. Initializes all subsystems and
includes the API routes.
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

from tinyintent.config import settings
from tinyintent.bridge.api_routes import router_api
from tinyintent.bridge.gen_client import async_ollama_client
from tinyintent.bridge.logs.audit import initialize_audit_logger


def setup_logging() -> None:
    """Configure structured logging."""
    if settings.logging.structured_logging:
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
        format="%(message)s" if settings.logging.structured_logging else "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.server.log_level.upper())
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    # Startup
    logger = structlog.get_logger()
    
    try:
        # Initialize audit logging
        audit_log_path = Path(__file__).parent / "logs" / "audit.log"
        audit_logger = initialize_audit_logger(
            audit_log_path, 
            max_size_mb=settings.logging.audit_max_size_mb
        )
        
        logger.info("TinyIntent Bridge starting up", version="2.0.0")
        logger.info("Configuration loaded", environment=settings.environment)
        
        # Validate critical settings
        if not settings.security.secret:
            logger.error("TINYINTENT_SECRET not configured")
            raise RuntimeError("TINYINTENT_SECRET environment variable is required")
        
        # Initialize components
        await async_ollama_client.health_check()
        logger.info("Ollama client initialized")
        
        yield
        
    except Exception as e:
        logger.error("Failed to start TinyIntent Bridge", error=str(e))
        raise
    finally:
        # Shutdown
        logger.info("TinyIntent Bridge shutting down")
        await async_ollama_client.close()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    setup_logging()
    
    app = FastAPI(
        title="TinyIntent Bridge",
        version="2.0.0",
        description="Mac-first, local-only AI platform for routing and executing personal assistant tasks",
        lifespan=lifespan,
        debug=settings.debug
    )
    
    # Security middleware
    if settings.is_production():
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    
    # CORS middleware for development
    if settings.is_development():
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    # Include API routes
    app.include_router(router_api)
    
    @app.get("/", include_in_schema=False)
    async def root():
        """Root endpoint with basic service info."""
        return {
            "service": "TinyIntent Bridge",
            "version": "2.0.0",
            "status": "operational",
            "environment": settings.environment
        }
    
    return app


# Create app instance
app = create_app()


def main() -> None:
    """Main entrypoint for CLI execution."""
    try:
        uvicorn.run(
            "tinyintent.bridge.tinyrpc:app",
            host=settings.server.bind,
            port=settings.server.port,
            reload=settings.server.reload and settings.is_development(),
            log_level=settings.server.log_level,
            workers=settings.server.workers,
            access_log=not settings.logging.structured_logging
        )
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        logger = structlog.get_logger()
        logger.error("Failed to start server", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
