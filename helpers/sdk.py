"""
TinyIntent Helpers SDK

This module serves as the primary entrypoint for the Helpers Framework.
It re-exports the core components from the modularized sub-packages.
"""

import os
from pathlib import Path
from typing import Dict, Any

# Environment loading utility
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

# Re-export core components from the new modular structure
from .manifest import HelperManifest, validate_helper_manifest
from .registry import HelperRegistry, HelperRegistryEntry
from .sandbox import HelperSandbox, SandboxViolationError, CapabilityViolationError
from .executor import HelperExecutor, HelperRateLimiter, HelperRateLimitError

# Global instances, maintaining the original pattern
helper_registry = HelperRegistry()
helper_executor = HelperExecutor(helper_registry)


def run_helper_health_check(helper_id: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    M8.6: Run health check for a specific helper.
    
    Args:
        helper_id: ID of the helper to check
        timeout_seconds: Maximum time to wait for health check
        
    Returns:
        dict: Health check result with status, output, and timing
    """
    import subprocess
    import time
    from pathlib import Path
    from typing import Dict, Any
    
    # Check if helper exists in registry
    registry_entry = helper_registry.get_registry_entry(helper_id)
    if not registry_entry:
        return {
            "helper_id": helper_id,
            "status": "error",
            "error": "helper_not_found",
            "message": f"Helper '{helper_id}' not found in registry"
        }
    
    # Check if helper has health check configured
    if not registry_entry.healthcheck:
        return {
            "helper_id": helper_id,
            "status": "skipped",
            "message": "No health check configured for this helper"
        }
    
    # Get helper directory
    helpers_dir = Path(__file__).parent
    helper_dir = helpers_dir / helper_id
    
    if not helper_dir.exists():
        return {
            "helper_id": helper_id,
            "status": "error", 
            "error": "helper_directory_not_found",
            "message": f"Helper directory not found: {helper_dir}"
        }
    
    # Get health check script path
    health_script = helper_dir / registry_entry.healthcheck
    
    if not health_script.exists():
        return {
            "helper_id": helper_id,
            "status": "error",
            "error": "healthcheck_script_not_found", 
            "message": f"Health check script not found: {health_script}"
        }
    
    # Determine command to run based on file extension
    script_extension = health_script.suffix.lower()
    if script_extension == '.py':
        cmd = ['python3', str(health_script)]
    elif script_extension == '.js':
        cmd = ['node', str(health_script)]
    elif script_extension == '.sh':
        cmd = ['bash', str(health_script)]
    else:
        # Try to run directly (assume executable)
        cmd = [str(health_script)]
    
    start_time = time.time()
    
    try:
        # Run health check with timeout
        result = subprocess.run(
            cmd,
            cwd=helper_dir,
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        if result.returncode == 0:
            return {
                "helper_id": helper_id,
                "status": "healthy",
                "message": "Health check passed",
                "duration_ms": duration_ms,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip() if result.stderr.strip() else None
            }
        else:
            return {
                "helper_id": helper_id,
                "status": "unhealthy",
                "message": f"Health check failed with exit code {result.returncode}",
                "duration_ms": duration_ms,
                "exit_code": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip()
            }
            
    except subprocess.TimeoutExpired:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "helper_id": helper_id,
            "status": "timeout",
            "message": f"Health check timed out after {timeout_seconds} seconds",
            "duration_ms": duration_ms,
            "timeout_seconds": timeout_seconds
        }
        
    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        return {
            "helper_id": helper_id,
            "status": "error",
            "error": "execution_failed",
            "message": f"Failed to execute health check: {str(e)}",
            "duration_ms": duration_ms
        }


def run_all_helper_health_checks(timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    M8.6: Run health checks for all helpers.
    
    Args:
        timeout_seconds: Maximum time to wait for each health check
        
    Returns:
        dict: Health check results for all helpers
    """
    from datetime import datetime
    
    results = {}
    summary = {
        "total": 0,
        "healthy": 0,
        "unhealthy": 0,
        "skipped": 0,
        "errors": 0,
        "timeouts": 0
    }
    
    # Get all helpers from registry
    validation_summary = helper_registry.get_validation_summary()
    helpers = validation_summary.get("helpers", {})
    
    for helper_id in helpers.keys():
        result = run_helper_health_check(helper_id, timeout_seconds)
        results[helper_id] = result
        
        # Update summary
        summary["total"] += 1
        status = result.get("status", "error")
        if status == "healthy":
            summary["healthy"] += 1
        elif status == "unhealthy":
            summary["unhealthy"] += 1
        elif status == "skipped":
            summary["skipped"] += 1
        elif status == "timeout":
            summary["timeouts"] += 1
        else:
            summary["errors"] += 1
    
    return {
        "summary": summary,
        "results": results,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
