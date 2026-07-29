"""
TinyIntent Bridge Service

Main entrypoint for the FastAPI application. Initializes all subsystems and
includes the API routes.
"""

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

# Add project root to path for imports
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tinyintent.config import settings
from .api_main import router_api
# LLM generation capabilities removed - focusing on automation only
from .logs.audit import initialize_audit_logger, get_audit_logger
from helpers.sdk import helper_registry
from data.episodes.episodes import agent_staging_storage



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


def get_trusted_helpers() -> list:
    """Get list of trusted helper IDs from registry."""
    try:
        validation_summary = helper_registry.get_validation_summary()
        helpers = validation_summary.get("helpers", {})
        return [
            helper_id for helper_id, info in helpers.items()
            if info.get("lifecycle", {}).get("state") == "trusted"
        ]
    except Exception:
        return []


async def network_anomaly_watcher() -> None:
    """
    Background watcher for network anomaly detection and trusted helper rollback.

    Monitors trusted helpers for high error rates and automatically deprecates
    helpers that exceed the error threshold within the monitoring window.

    Configuration via environment variables:
    - NETWORK_CHECK_INTERVAL_S: Check interval in seconds (default: 300)
    - TINYINTENT_ROLLBACK_ENABLED: Enable rollback feature (default: false)
    - TINYINTENT_ROLLBACK_WINDOW_HOURS: Metrics window in hours (default: 24)
    - TINYINTENT_ERROR_RATE_THRESHOLD: Error rate threshold (default: 0.15)
    """
    import asyncio
    import os

    logger = structlog.get_logger()

    # Get network monitoring configuration
    check_interval_seconds = int(os.getenv("NETWORK_CHECK_INTERVAL_S", "300"))  # 5 minutes

    # Rollback configuration - M10.4 feature
    rollback_enabled = os.getenv("TINYINTENT_ROLLBACK_ENABLED", "false").lower() == "true"
    window_hours = int(os.getenv("TINYINTENT_ROLLBACK_WINDOW_HOURS", "24"))
    error_rate_threshold = float(os.getenv("TINYINTENT_ERROR_RATE_THRESHOLD", "0.15"))

    # Get audit logger instance
    audit_logger = get_audit_logger()

    if os.getenv("TINYINTENT_LOG_LEVEL", "warning").lower() in ["debug", "info"]:
        logger.info("Network anomaly watcher started",
                   check_interval=check_interval_seconds,
                   rollback_enabled=rollback_enabled)

    while True:
        try:
            # Wait for check interval
            await asyncio.sleep(check_interval_seconds)

            # Skip rollback checks if feature is disabled
            if not rollback_enabled:
                continue

            # Get current trusted helpers
            trusted_helpers = get_trusted_helpers()

            for helper_id in trusted_helpers:
                try:
                    # Get metrics for the rollback window
                    metrics = agent_staging_storage.get_staging_metrics(helper_id, window_hours)
                    
                    # Calculate error rate (both shadow and canary runs)
                    total_runs = metrics.get("shadow_runs", 0) + metrics.get("canary_runs", 0)
                    
                    if total_runs == 0:
                        # No data in rollback window, skip
                        continue
                    
                    # Calculate combined error rate
                    shadow_errors = (1.0 - metrics.get("shadow_success_rate", 1.0)) * metrics.get("shadow_runs", 0)
                    canary_errors = (1.0 - metrics.get("canary_success_rate", 1.0)) * metrics.get("canary_runs", 0)
                    total_errors = shadow_errors + canary_errors
                    error_rate = total_errors / total_runs if total_runs > 0 else 0.0
                    
                    logger.debug("Checked helper metrics", 
                               helper_id=helper_id, 
                               total_runs=total_runs, 
                               error_rate=error_rate,
                               threshold=error_rate_threshold)
                    
                    # Check if error rate exceeds threshold
                    if error_rate > error_rate_threshold and total_runs >= 5:  # Minimum runs for reliable data
                        # Trigger automatic rollback
                        logger.warning("Auto-rollback triggered", 
                                     helper_id=helper_id, 
                                     error_rate=error_rate, 
                                     threshold=error_rate_threshold,
                                     runs_analyzed=total_runs)
                        
                        # Update lifecycle to deprecated
                        success = helper_registry.update_helper_lifecycle(
                            helper_id,
                            "deprecated",
                            f"Automatically deprecated due to high error rate ({error_rate:.1%}) in {window_hours}h window. "
                            f"Analyzed {total_runs} runs."
                        )
                        
                        if success:
                            # Trigger helper reload to reflect changes
                            try:
                                helper_registry.reload()
                            except Exception as reload_error:
                                logger.error("Failed to reload registry after rollback", 
                                           helper_id=helper_id, error=str(reload_error))
                            
                            # Log successful rollback
                            if audit_logger:
                                audit_logger.log_entry({
                                    "action": "agent_auto_rollback",
                                    "helper_id": helper_id,
                                    "previous_state": "trusted",
                                    "new_state": "deprecated",
                                    "error_rate": error_rate,
                                    "threshold": error_rate_threshold,
                                    "window_hours": window_hours,
                                    "total_runs": total_runs,
                                    "success": True
                                })
                            
                            logger.info("Helper auto-rollback completed", 
                                      helper_id=helper_id, 
                                      error_rate=error_rate)
                        else:
                            # Log rollback failure
                            if audit_logger:
                                audit_logger.log_entry({
                                    "action": "agent_auto_rollback_failed",
                                    "helper_id": helper_id,
                                    "error_rate": error_rate,
                                    "success": False
                                })
                            
                            logger.error("Failed to rollback helper", helper_id=helper_id)

                except Exception as helper_error:
                    logger.error("Error checking helper for rollback",
                               helper_id=helper_id, error=str(helper_error))

                    if audit_logger:
                        audit_logger.log_entry({
                            "action": "rollback_check_error",
                            "helper_id": helper_id,
                            "error": str(helper_error),
                            "success": False
                        })

        except asyncio.CancelledError:
            if os.getenv("TINYINTENT_LOG_LEVEL", "warning").lower() in ["debug", "info"]:
                logger.info("Rollback watcher cancelled")
            break
        except Exception as e:
            logger.error("Rollback watcher error", error=str(e))
            # Continue running despite errors
            await asyncio.sleep(60)  # Wait 1 minute before retrying


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    # Startup
    logger = structlog.get_logger()
    rollback_task = None
    
    try:
        # Initialize audit logging
        audit_log_path = Path(__file__).parent / "logs" / "audit.log"
        audit_logger = initialize_audit_logger(
            audit_log_path, 
            max_size_mb=settings.logging.audit_max_size_mb
        )
        
        # Only log startup details in debug mode
        log_level = os.getenv("TINYINTENT_LOG_LEVEL", "warning").lower()
        if log_level in ["debug", "info"]:
            logger.info("TinyIntent Bridge starting up", version="2.0.0")
            logger.info("Configuration loaded", environment=settings.environment)
        
        # SECURITY: Enhanced secret validation on startup
        if not settings.security.secret:
            logger.error("TINYINTENT_SECRET not configured")
            raise RuntimeError("TINYINTENT_SECRET environment variable is required")
        
        # Perform comprehensive secret strength validation
        try:
            from .secret_validator import validate_production_secret
            
            validation_result = validate_production_secret(settings.security.secret)
            
            if not validation_result.is_valid:
                error_msg = f"TinyIntent API secret validation failed (score: {validation_result.score}/100):\n"
                for issue in validation_result.issues:
                    error_msg += f"  - {issue}\n"
                
                if validation_result.suggestions:
                    error_msg += "\nRecommendations:\n"
                    for suggestion in validation_result.suggestions:
                        error_msg += f"  - {suggestion}\n"
                
                # Log comprehensive validation failure  
                logger.error("Secret validation failed during startup", 
                           score=validation_result.score,
                           entropy=validation_result.entropy,
                           issues=validation_result.issues[:3])  # Limit log verbosity
                
                raise RuntimeError(error_msg)
            else:
                logger.info("Secret validation passed", 
                          score=validation_result.score,
                          entropy=round(validation_result.entropy, 1))
        
        except ImportError:
            # Fallback validation if secret_validator not available
            logger.warning("Advanced secret validation unavailable, using basic validation")

        # M10.4: Start background rollback watcher for trusted agents
        import asyncio
        rollback_task = asyncio.create_task(network_anomaly_watcher())
        if log_level in ["debug", "info"]:
            logger.info("Agent rollback watcher started")
        
        yield
        
    except Exception as e:
        logger.error("Failed to start TinyIntent Bridge", error=str(e))
        raise
    finally:
        # Shutdown
        log_level = os.getenv("TINYINTENT_LOG_LEVEL", "warning").lower()
        if log_level in ["debug", "info"]:
            logger.info("TinyIntent Bridge shutting down")
        
        # Cancel rollback watcher
        if rollback_task:
            rollback_task.cancel()
            try:
                await rollback_task
            except asyncio.CancelledError:
                pass
            if log_level in ["debug", "info"]:
                logger.info("Agent rollback watcher stopped")


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
