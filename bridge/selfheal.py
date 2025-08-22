#!/usr/bin/env python3
"""
TinyIntent Self-Heal Monitor
Checks system readiness and logs warnings for missing components
"""

import json
import logging
from datetime import datetime
from pathlib import Path
import argparse
import sys

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    import urllib.error
    HAS_REQUESTS = False

def setup_logging():
    """Setup JSON logging to selfheal.log"""
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / "selfheal.log"
    
    # Simple file logging without formatters for JSON output
    return log_file

def log_json(log_file, level, message, **extra):
    """Write JSON log entry to file"""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "component": "selfheal",
        "message": message,
        **extra
    }
    
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')

def check_readiness_requests(url, timeout=5):
    """Query /readyz using requests library"""
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        return {"error": str(e), "status": "unreachable"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}", "status": "invalid_response"}

def check_readiness_urllib(url, timeout=5):
    """Query /readyz using urllib"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = response.read().decode('utf-8')
            return json.loads(data)
    except urllib.error.URLError as e:
        return {"error": str(e), "status": "unreachable"}
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}", "status": "invalid_response"}
    except Exception as e:
        return {"error": str(e), "status": "unknown_error"}

def check_readiness(base_url="http://localhost:8787", timeout=5):
    """Query /readyz endpoint and return parsed response"""
    url = f"{base_url}/readyz"
    
    if HAS_REQUESTS:
        return check_readiness_requests(url, timeout)
    else:
        return check_readiness_urllib(url, timeout)

def analyze_readiness(readiness_data, log_file):
    """Analyze readiness data and log warnings for missing components"""
    issues = []
    
    # Required checks
    required_checks = ["models_present", "router_binary"]
    
    # Optional checks
    optional_checks = ["helpers_valid"]
    
    for check in required_checks:
        if check not in readiness_data:
            issues.append(f"Missing required check: {check}")
        elif not readiness_data.get(check, False):
            issues.append(f"Required component not ready: {check}")
    
    for check in optional_checks:
        if check in readiness_data and not readiness_data.get(check, False):
            issues.append(f"Optional component not ready: {check}")
    
    # Log any issues found
    if issues:
        for issue in issues:
            log_json(log_file, "WARNING", issue, readiness_data=readiness_data)
    
    # Log error if service unreachable
    if "error" in readiness_data:
        log_json(log_file, "ERROR", f"Readiness check failed: {readiness_data['error']}", 
                readiness_data=readiness_data)
    
    return len(issues) == 0 and "error" not in readiness_data

def main():
    """Main self-heal monitoring function"""
    parser = argparse.ArgumentParser(
        description="TinyIntent Self-Heal Monitor",
        epilog="Usage: python bridge/selfheal.py --dry-run"
    )
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Only log issues, do not attempt fixes (default: True)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                       help="Disable dry-run mode")
    parser.add_argument("--url", default="http://localhost:8787",
                       help="Base URL for TinyIntent bridge (default: localhost:8787)")
    
    args = parser.parse_args()
    
    log_file = setup_logging()
    
    # Log startup
    log_json(log_file, "INFO", "Self-heal monitor started", 
             dry_run=args.dry_run, base_url=args.url)
    
    # Check system readiness
    readiness_data = check_readiness(args.url)
    
    # Analyze and log issues
    is_healthy = analyze_readiness(readiness_data, log_file)
    
    if is_healthy:
        log_json(log_file, "INFO", "System readiness check passed", 
                readiness=readiness_data)
    else:
        log_json(log_file, "WARNING", "System readiness issues detected", 
                readiness=readiness_data)
    
    # Placeholder for future healing actions
    if not args.dry_run and not is_healthy:
        log_json(log_file, "INFO", "Healing actions would be performed here (not implemented)")
        # TODO: Implement actual healing logic
    
    return 0 if is_healthy else 1

if __name__ == "__main__":
    sys.exit(main())