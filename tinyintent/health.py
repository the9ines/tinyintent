"""
TinyIntent Health Check System

Comprehensive health monitoring for all system components.
"""

import asyncio
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog
from pydantic import BaseModel

from tinyintent.config import settings
from tinyintent.utils import measure_time, retry_with_backoff

logger = structlog.get_logger()


class HealthStatus(BaseModel):
    """Health status for a component."""
    component: str
    status: str  # healthy, unhealthy, warning, unknown
    message: str
    details: Dict[str, Any] = {}
    timestamp: str
    response_time_ms: Optional[float] = None


class SystemHealth(BaseModel):
    """Overall system health."""
    overall_status: str
    components: List[HealthStatus]
    timestamp: str
    healthy_count: int
    unhealthy_count: int
    warning_count: int


class HealthChecker:
    """Performs health checks on system components."""
    
    def __init__(self):
        self.timeout = 10.0
    
    @measure_time
    def check_disk_space(self) -> HealthStatus:
        """Check available disk space."""
        try:
            project_root = settings.project_root
            stat = os.statvfs(project_root)
            
            # Calculate space in GB
            free_space_gb = (stat.f_frsize * stat.f_bavail) / (1024**3)
            total_space_gb = (stat.f_frsize * stat.f_blocks) / (1024**3)
            used_percent = ((total_space_gb - free_space_gb) / total_space_gb) * 100
            
            if free_space_gb < 1.0:  # Less than 1GB free
                status = "unhealthy"
                message = f"Low disk space: {free_space_gb:.1f}GB free"
            elif free_space_gb < 5.0:  # Less than 5GB free
                status = "warning"
                message = f"Disk space getting low: {free_space_gb:.1f}GB free"
            else:
                status = "healthy"
                message = f"Sufficient disk space: {free_space_gb:.1f}GB free"
            
            return HealthStatus(
                component="disk_space",
                status=status,
                message=message,
                details={
                    "free_space_gb": round(free_space_gb, 2),
                    "total_space_gb": round(total_space_gb, 2),
                    "used_percent": round(used_percent, 1)
                },
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
            
        except Exception as e:
            return HealthStatus(
                component="disk_space",
                status="unknown",
                message=f"Failed to check disk space: {str(e)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
    
    @measure_time
    def check_sqlite_database(self) -> HealthStatus:
        """Check SQLite database connectivity."""
        try:
            db_path = settings.database.episodes_dir / "events.db"
            
            if not db_path.exists():
                return HealthStatus(
                    component="sqlite_database",
                    status="warning",
                    message="Database file does not exist yet",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
                )
            
            # Test database connection
            with sqlite3.connect(db_path, timeout=5.0) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                table_count = cursor.fetchone()[0]
            
            return HealthStatus(
                component="sqlite_database",
                status="healthy",
                message=f"Database accessible with {table_count} tables",
                details={"table_count": table_count, "db_path": str(db_path)},
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
            
        except Exception as e:
            return HealthStatus(
                component="sqlite_database",
                status="unhealthy",
                message=f"Database check failed: {str(e)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
    
    @measure_time
    async def check_ollama_connection(self) -> HealthStatus:
        """Check Ollama server connectivity."""
        try:
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{settings.models.ollama_url}/api/version")
                response.raise_for_status()
                
                response_time_ms = (time.time() - start_time) * 1000
                version_data = response.json()
                
                return HealthStatus(
                    component="ollama_server",
                    status="healthy",
                    message="Ollama server is accessible",
                    details={
                        "url": settings.models.ollama_url,
                        "version": version_data.get("version", "unknown")
                    },
                    response_time_ms=response_time_ms,
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
                )
                
        except httpx.TimeoutException:
            return HealthStatus(
                component="ollama_server",
                status="unhealthy",
                message="Ollama server connection timeout",
                details={"url": settings.models.ollama_url},
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
        except httpx.RequestError as e:
            return HealthStatus(
                component="ollama_server",
                status="unhealthy",
                message=f"Ollama server connection failed: {str(e)}",
                details={"url": settings.models.ollama_url},
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
        except Exception as e:
            return HealthStatus(
                component="ollama_server",
                status="unknown",
                message=f"Ollama server check error: {str(e)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
    
    @measure_time
    def check_router_model(self) -> HealthStatus:
        """Check router model availability."""
        try:
            router_model_paths = [
                settings.project_root / "router" / "SmallIntent.mlmodel",
                settings.project_root / "router" / "weights" / "model.mlmodel"
            ]
            
            # Check if any router model exists
            available_models = [path for path in router_model_paths if path.exists()]
            
            if not available_models:
                return HealthStatus(
                    component="router_model",
                    status="warning",
                    message="No router model found",
                    details={"searched_paths": [str(p) for p in router_model_paths]},
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
                )
            
            # Get info about the first available model
            model_path = available_models[0]
            model_size_mb = model_path.stat().st_size / (1024 * 1024)
            
            return HealthStatus(
                component="router_model",
                status="healthy",
                message=f"Router model available: {model_path.name}",
                details={
                    "model_path": str(model_path),
                    "size_mb": round(model_size_mb, 2),
                    "available_models": len(available_models)
                },
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
            
        except Exception as e:
            return HealthStatus(
                component="router_model",
                status="unknown",
                message=f"Router model check failed: {str(e)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
    
    @measure_time
    def check_system_dependencies(self) -> HealthStatus:
        """Check required system dependencies."""
        try:
            dependencies = {
                "python3": ["python3", "--version"],
                "swift": ["swift", "--version"],
                "node": ["node", "--version"]
            }
            
            available = {}
            missing = []
            
            for dep_name, cmd in dependencies.items():
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        version_line = result.stdout.strip().split('\n')[0]
                        available[dep_name] = version_line
                    else:
                        missing.append(dep_name)
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    missing.append(dep_name)
            
            if missing:
                status = "warning" if len(missing) < len(dependencies) else "unhealthy"
                message = f"Missing dependencies: {', '.join(missing)}"
            else:
                status = "healthy"
                message = "All system dependencies available"
            
            return HealthStatus(
                component="system_dependencies",
                status=status,
                message=message,
                details={
                    "available": available,
                    "missing": missing,
                    "total_checked": len(dependencies)
                },
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
            
        except Exception as e:
            return HealthStatus(
                component="system_dependencies",
                status="unknown",
                message=f"Dependency check failed: {str(e)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
    
    @measure_time
    def check_audit_log(self) -> HealthStatus:
        """Check audit log system."""
        try:
            audit_log_path = settings.project_root / "bridge" / "logs" / "audit.log"
            
            if not audit_log_path.exists():
                return HealthStatus(
                    component="audit_log",
                    status="warning",
                    message="Audit log file does not exist yet",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
                )
            
            # Check if log is writable
            audit_log_path.touch()
            
            # Get log size
            log_size_mb = audit_log_path.stat().st_size / (1024 * 1024)
            max_size_mb = settings.logging.audit_max_size_mb
            
            if log_size_mb > max_size_mb * 0.9:  # 90% of max size
                status = "warning"
                message = f"Audit log approaching size limit: {log_size_mb:.1f}MB"
            else:
                status = "healthy"
                message = f"Audit log operational: {log_size_mb:.1f}MB"
            
            return HealthStatus(
                component="audit_log",
                status=status,
                message=message,
                details={
                    "log_path": str(audit_log_path),
                    "size_mb": round(log_size_mb, 2),
                    "max_size_mb": max_size_mb
                },
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
            
        except Exception as e:
            return HealthStatus(
                component="audit_log",
                status="unhealthy",
                message=f"Audit log check failed: {str(e)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
    
    async def run_all_checks(self) -> SystemHealth:
        """Run all health checks and return system health."""
        logger.info("Starting system health checks")
        
        # Run async checks
        async_checks = [
            self.check_ollama_connection()
        ]
        
        # Run sync checks
        sync_checks = [
            self.check_disk_space(),
            self.check_sqlite_database(),
            self.check_router_model(),
            self.check_system_dependencies(),
            self.check_audit_log()
        ]
        
        # Combine all results
        async_results = await asyncio.gather(*async_checks, return_exceptions=True)
        all_results = sync_checks + [
            result if isinstance(result, HealthStatus) else HealthStatus(
                component="unknown",
                status="unknown",
                message=f"Check failed: {str(result)}",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime())
            )
            for result in async_results
        ]
        
        # Calculate overall status
        healthy_count = sum(1 for r in all_results if r.status == "healthy")
        unhealthy_count = sum(1 for r in all_results if r.status == "unhealthy")
        warning_count = sum(1 for r in all_results if r.status == "warning")
        
        if unhealthy_count > 0:
            overall_status = "unhealthy"
        elif warning_count > 0:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        logger.info(
            "Health checks completed",
            overall_status=overall_status,
            healthy=healthy_count,
            unhealthy=unhealthy_count,
            warnings=warning_count
        )
        
        return SystemHealth(
            overall_status=overall_status,
            components=all_results,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            healthy_count=healthy_count,
            unhealthy_count=unhealthy_count,
            warning_count=warning_count
        )


# Global health checker instance
health_checker = HealthChecker()