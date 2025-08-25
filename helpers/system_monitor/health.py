#!/usr/bin/env python3
"""
Health check for system_monitor helper.
Verifies that psutil is available and system monitoring can be performed.
"""

import sys
import json
from typing import Dict, Any

def check_psutil_availability() -> Dict[str, Any]:
    """Check if psutil is available and working."""
    try:
        import psutil
        
        # Test basic functionality
        cpu_count = psutil.cpu_count()
        memory = psutil.virtual_memory()
        
        return {
            "available": True,
            "version": getattr(psutil, '__version__', 'unknown'),
            "cpu_cores": cpu_count,
            "total_memory_gb": round(memory.total / (1024**3), 2)
        }
    except ImportError:
        return {
            "available": False,
            "error": "psutil not installed",
            "fix": "Install with: pip install psutil"
        }
    except Exception as e:
        return {
            "available": False,
            "error": f"psutil error: {str(e)}"
        }

def check_system_access() -> Dict[str, Any]:
    """Check if system monitoring functions work."""
    try:
        import psutil
        
        checks = {}
        
        # Test CPU access
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            checks["cpu"] = {"available": True, "current_usage": cpu_percent}
        except Exception as e:
            checks["cpu"] = {"available": False, "error": str(e)}
        
        # Test memory access
        try:
            memory = psutil.virtual_memory()
            checks["memory"] = {
                "available": True, 
                "usage_percent": memory.percent
            }
        except Exception as e:
            checks["memory"] = {"available": False, "error": str(e)}
        
        # Test disk access
        try:
            disk_usage = psutil.disk_usage('/')
            checks["disk"] = {
                "available": True,
                "usage_percent": round((disk_usage.used / disk_usage.total) * 100, 1)
            }
        except Exception as e:
            checks["disk"] = {"available": False, "error": str(e)}
        
        # Test network access
        try:
            net_io = psutil.net_io_counters()
            checks["network"] = {
                "available": True,
                "has_stats": net_io is not None
            }
        except Exception as e:
            checks["network"] = {"available": False, "error": str(e)}
        
        return checks
        
    except ImportError:
        return {"error": "psutil not available for system checks"}

def main():
    """Main health check entry point."""
    try:
        health_data = {
            "helper_id": "system_monitor",
            "version": "1.0.0",
            "status": "healthy",
            "checks": {}
        }
        
        # Check psutil availability
        psutil_check = check_psutil_availability()
        health_data["checks"]["psutil"] = psutil_check
        
        if not psutil_check["available"]:
            health_data["status"] = "unhealthy"
            health_data["issues"] = [psutil_check.get("error", "psutil unavailable")]
        else:
            # Check system access
            system_checks = check_system_access()
            health_data["checks"]["system_access"] = system_checks
            
            # Check if any system access failed
            failed_checks = []
            for check_name, check_result in system_checks.items():
                if isinstance(check_result, dict) and not check_result.get("available", True):
                    failed_checks.append(f"{check_name}: {check_result.get('error', 'failed')}")
            
            if failed_checks:
                health_data["status"] = "degraded"
                health_data["issues"] = failed_checks
        
        print(json.dumps(health_data, indent=2))
        
        # Return appropriate exit code
        if health_data["status"] == "healthy":
            sys.exit(0)
        elif health_data["status"] == "degraded":
            sys.exit(1)  # Warning
        else:
            sys.exit(2)  # Error
            
    except Exception as e:
        error_response = {
            "helper_id": "system_monitor",
            "version": "1.0.0", 
            "status": "error",
            "error": str(e)
        }
        print(json.dumps(error_response, indent=2))
        sys.exit(2)

if __name__ == "__main__":
    main()