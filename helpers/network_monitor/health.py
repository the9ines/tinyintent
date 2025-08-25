#!/usr/bin/env python3
"""
Health Check for Network Monitor Helper

Validates that the network monitoring helper can function properly by checking:
- Required Python dependencies
- Network connectivity 
- SNMP access capabilities
- ML model dependencies
- File system permissions for config backups
"""

import json
import sys
import os
import socket
import tempfile
from pathlib import Path

def check_dependencies():
    """Check if required Python packages are available."""
    dependencies = {
        "pysnmp": "SNMP monitoring support",
        "aiohttp": "Async HTTP client for UniFi API",
        "numpy": "Numerical computing for ML models", 
        "sklearn": "Machine learning for anomaly detection"
    }
    
    results = {
        "status": "success",
        "available": [],
        "missing": [],
        "recommendations": []
    }
    
    for package, description in dependencies.items():
        try:
            if package == "sklearn":
                import sklearn
                results["available"].append(f"{package} ({description})")
            elif package == "pysnmp":
                import pysnmp
                results["available"].append(f"{package} ({description})")
            elif package == "aiohttp":
                import aiohttp
                results["available"].append(f"{package} ({description})")
            elif package == "numpy":
                import numpy
                results["available"].append(f"{package} ({description})")
        except ImportError:
            results["missing"].append(f"{package} ({description})")
            results["recommendations"].append(f"Install {package}: pip install {package}")
    
    if results["missing"]:
        results["status"] = "degraded"
        results["message"] = "Some ML features unavailable - basic monitoring will work"
    else:
        results["message"] = "All dependencies available"
        
    return results

def check_network_access():
    """Test basic network connectivity for SNMP and API access."""
    results = {
        "status": "success", 
        "tests": [],
        "recommendations": []
    }
    
    # Test DNS resolution
    try:
        socket.gethostbyname("google.com")
        results["tests"].append("DNS resolution: PASS")
    except socket.error:
        results["tests"].append("DNS resolution: FAIL")
        results["status"] = "degraded"
        results["recommendations"].append("Check DNS configuration")
    
    # Test outbound connectivity on common ports
    test_ports = [
        (80, "HTTP (UniFi Controller default)"),
        (443, "HTTPS (UniFi Controller SSL)"),
        (161, "SNMP"),
        (8443, "UniFi Controller HTTPS")
    ]
    
    for port, description in test_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(("8.8.8.8", port))
            sock.close()
            
            if result == 0:
                results["tests"].append(f"{description} (port {port}): PASS")
            else:
                results["tests"].append(f"{description} (port {port}): BLOCKED")
                if port == 161:
                    results["status"] = "degraded"
                    results["recommendations"].append("SNMP port 161 may be blocked by firewall")
        except Exception as e:
            results["tests"].append(f"{description} (port {port}): ERROR - {e}")
    
    return results

def check_snmp_capabilities():
    """Test SNMP library functionality."""
    results = {
        "status": "success",
        "capabilities": [],
        "limitations": []
    }
    
    try:
        from pysnmp.hlapi import *
        
        # Test SNMP engine creation
        try:
            engine = SnmpEngine()
            results["capabilities"].append("SNMP engine creation: PASS")
        except Exception as e:
            results["capabilities"].append(f"SNMP engine creation: FAIL - {e}")
            results["status"] = "error"
            
        # Test community data
        try:
            community = CommunityData("public")
            results["capabilities"].append("SNMPv2c community data: PASS")
        except Exception as e:
            results["capabilities"].append(f"SNMPv2c community data: FAIL - {e}")
            
        # Test USM user data (SNMPv3)
        try:
            user = UsmUserData("testuser", "authkey123", "privkey123")
            results["capabilities"].append("SNMPv3 USM data: PASS")
        except Exception as e:
            results["capabilities"].append(f"SNMPv3 USM data: FAIL - {e}")
            
        # Test object identity
        try:
            oid = ObjectIdentity("1.3.6.1.2.1.1.1.0")  # sysDescr
            results["capabilities"].append("SNMP OID handling: PASS")
        except Exception as e:
            results["capabilities"].append(f"SNMP OID handling: FAIL - {e}")
            
    except ImportError:
        results["status"] = "error"
        results["limitations"].append("pysnmp library not available - SNMP monitoring disabled")
        results["capabilities"].append("Install pysnmp: pip install pysnmp")
    
    return results

def check_ml_capabilities():
    """Test machine learning dependencies for anomaly detection."""
    results = {
        "status": "success",
        "models": [],
        "fallback": "rule_based_detection"
    }
    
    try:
        from sklearn.ensemble import IsolationForest
        from sklearn.svm import OneClassSVM
        import numpy as np
        
        # Test Isolation Forest
        try:
            iso_forest = IsolationForest(contamination=0.1, random_state=42)
            test_data = np.array([[1, 2, 3], [2, 3, 4], [3, 4, 5]])
            iso_forest.fit(test_data)
            results["models"].append("Isolation Forest: AVAILABLE")
        except Exception as e:
            results["models"].append(f"Isolation Forest: ERROR - {e}")
            results["status"] = "degraded"
            
        # Test One-Class SVM
        try:
            svm = OneClassSVM(gamma='scale', nu=0.1)
            test_data = np.array([[1, 2, 3], [2, 3, 4], [3, 4, 5]])
            svm.fit(test_data)
            results["models"].append("One-Class SVM: AVAILABLE")
        except Exception as e:
            results["models"].append(f"One-Class SVM: ERROR - {e}")
            results["status"] = "degraded"
            
    except ImportError:
        results["status"] = "degraded"
        results["models"].append("scikit-learn not available - using rule-based anomaly detection only")
    
    return results

def check_backup_permissions():
    """Test file system permissions for configuration backups."""
    results = {
        "status": "success",
        "tests": [],
        "backup_directory": "backups"
    }
    
    backup_dir = Path("backups")
    
    try:
        # Test directory creation
        backup_dir.mkdir(exist_ok=True)
        results["tests"].append("Backup directory creation: PASS")
        
        # Test file write
        test_file = backup_dir / "health_check_test.cfg"
        test_content = "# Test configuration backup file\n"
        
        with open(test_file, 'w') as f:
            f.write(test_content)
        results["tests"].append("Backup file write: PASS")
        
        # Test file read
        with open(test_file, 'r') as f:
            content = f.read()
            if content == test_content:
                results["tests"].append("Backup file read: PASS")
            else:
                results["tests"].append("Backup file read: CONTENT MISMATCH")
                results["status"] = "degraded"
        
        # Test file deletion
        test_file.unlink()
        results["tests"].append("Backup file cleanup: PASS")
        
    except Exception as e:
        results["tests"].append(f"Backup file operations: FAIL - {e}")
        results["status"] = "error"
        results["recommendations"] = ["Check file system permissions for backup directory"]
    
    return results

def main():
    """Run all health checks and return consolidated results."""
    health_results = {
        "helper_name": "network_monitor",
        "version": "1.0.0",
        "timestamp": "2025-08-25T00:00:00Z",
        "overall_status": "success",
        "checks": {}
    }
    
    # Run all health checks
    checks = {
        "dependencies": check_dependencies(),
        "network_access": check_network_access(),
        "snmp_capabilities": check_snmp_capabilities(),
        "ml_capabilities": check_ml_capabilities(),
        "backup_permissions": check_backup_permissions()
    }
    
    health_results["checks"] = checks
    
    # Determine overall status
    statuses = [check["status"] for check in checks.values()]
    
    if "error" in statuses:
        health_results["overall_status"] = "error"
        health_results["message"] = "Critical issues detected - some functionality unavailable"
    elif "degraded" in statuses:
        health_results["overall_status"] = "degraded"
        health_results["message"] = "Some features degraded - basic monitoring available"
    else:
        health_results["overall_status"] = "success"
        health_results["message"] = "All systems operational - full functionality available"
    
    # Collect all recommendations
    all_recommendations = []
    for check in checks.values():
        all_recommendations.extend(check.get("recommendations", []))
    
    if all_recommendations:
        health_results["recommendations"] = all_recommendations
    
    print(json.dumps(health_results, indent=2))
    
    # Exit with appropriate code
    if health_results["overall_status"] == "error":
        sys.exit(1)
    elif health_results["overall_status"] == "degraded":
        sys.exit(2)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()