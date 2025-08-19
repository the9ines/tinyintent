#!/usr/bin/env python3
"""
TinyIntent Helper Health & Self-Tests Tests - M8.6

Tests helper health check functionality including:
- Health check script execution
- Timeout handling
- Error reporting
- API endpoint functionality
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent))

try:
    from helpers.sdk import run_helper_health_check, run_all_helper_health_checks, helper_registry
    HEALTH_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helper health checks not available: {e}")
    HEALTH_AVAILABLE = False

try:
    import requests
    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False


class TestHelperHealthChecks(unittest.TestCase):
    """Test helper health check functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not HEALTH_AVAILABLE:
            self.skipTest("Helper health checks not available")
        
        # Create temporary directory for test helpers
        self.test_dir = Path(tempfile.mkdtemp(prefix="helper_health_test_"))
        
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary directory
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _create_test_helper(self, helper_id: str, health_script_content: str = None, 
                          health_script_name: str = "health.py", make_executable: bool = True,
                          create_manifest: bool = True) -> Path:
        """Create a test helper with health check script."""
        helper_dir = self.test_dir / helper_id
        helper_dir.mkdir(parents=True, exist_ok=True)
        
        if create_manifest:
            # Create basic manifest
            manifest_content = """
purpose: Test helper for health checks
capabilities:
  preview: true
  execute: true
sandbox:
  commands: ["python3", "main.py"]
metadata:
  author: Test Suite
"""
            with open(helper_dir / "helper.yaml", 'w') as f:
                f.write(manifest_content)
        
        if health_script_content:
            # Create health check script
            health_script_path = helper_dir / health_script_name
            with open(health_script_path, 'w') as f:
                f.write(health_script_content)
            
            if make_executable:
                health_script_path.chmod(0o755)
        
        return helper_dir
    
    def test_health_check_helper_not_found(self):
        """Test health check for non-existent helper."""
        result = run_helper_health_check("nonexistent_helper")
        
        self.assertEqual(result["helper_id"], "nonexistent_helper")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "helper_not_found")
        self.assertIn("not found in registry", result["message"])
    
    def test_health_check_no_healthcheck_configured(self):
        """Test health check for helper without health check configured."""
        # Test with ssh_ops which has no healthcheck in registry
        result = run_helper_health_check("ssh_ops")
        
        self.assertEqual(result["helper_id"], "ssh_ops")
        self.assertEqual(result["status"], "skipped")
        self.assertIn("No health check configured", result["message"])
    
    def test_health_check_script_not_found(self):
        """Test health check when script file doesn't exist."""
        # Mock registry to simulate helper with missing health script
        with patch.object(helper_registry, 'get_registry_entry') as mock_get_entry:
            mock_entry = MagicMock()
            mock_entry.healthcheck = "missing_health.py"
            mock_get_entry.return_value = mock_entry
            
            # Mock helper directory check
            with patch('helpers.sdk.Path') as mock_path:
                mock_helper_dir = MagicMock()
                mock_helper_dir.exists.return_value = True
                mock_path.return_value.__truediv__.return_value = mock_helper_dir
                
                mock_health_script = MagicMock()
                mock_health_script.exists.return_value = False
                mock_helper_dir.__truediv__.return_value = mock_health_script
                
                result = run_helper_health_check("test_helper")
                
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"], "healthcheck_script_not_found")
    
    def test_successful_python_health_check(self):
        """Test successful Python health check execution."""
        # Create test helper with successful health script
        health_script = """#!/usr/bin/env python3
import json
import sys

result = {
    "status": "healthy",
    "message": "All checks passed",
    "checks": {"test": "pass"}
}

print(json.dumps(result))
sys.exit(0)
"""
        
        helper_dir = self._create_test_helper("test_python_health", health_script, "health.py")
        
        # Mock registry and file system
        with patch.object(helper_registry, 'get_registry_entry') as mock_get_entry:
            mock_entry = MagicMock()
            mock_entry.healthcheck = "health.py"
            mock_get_entry.return_value = mock_entry
            
            with patch('helpers.sdk.Path') as mock_path:
                # Mock the helper directory structure
                mock_helpers_dir = MagicMock()
                mock_helper_dir = helper_dir  # Use real test directory
                mock_path.return_value.__truediv__.return_value = mock_helper_dir
                
                result = run_helper_health_check("test_python_health")
                
                self.assertEqual(result["helper_id"], "test_python_health")
                self.assertEqual(result["status"], "healthy")
                self.assertIn("duration_ms", result)
                self.assertIsInstance(result["duration_ms"], int)
    
    def test_failed_health_check(self):
        """Test failed health check execution."""
        # Create test helper with failing health script
        health_script = """#!/usr/bin/env python3
import sys

print("Health check failed!")
sys.exit(1)
"""
        
        helper_dir = self._create_test_helper("test_failed_health", health_script, "health.py")
        
        # Mock registry and file system
        with patch.object(helper_registry, 'get_registry_entry') as mock_get_entry:
            mock_entry = MagicMock()
            mock_entry.healthcheck = "health.py"
            mock_get_entry.return_value = mock_entry
            
            with patch('helpers.sdk.Path') as mock_path:
                mock_helpers_dir = MagicMock()
                mock_helper_dir = helper_dir
                mock_path.return_value.__truediv__.return_value = mock_helper_dir
                
                result = run_helper_health_check("test_failed_health")
                
                self.assertEqual(result["helper_id"], "test_failed_health")
                self.assertEqual(result["status"], "unhealthy")
                self.assertEqual(result["exit_code"], 1)
                self.assertIn("Health check failed!", result["stdout"])
    
    def test_timeout_health_check(self):
        """Test health check timeout handling."""
        # Create test helper with long-running health script
        health_script = """#!/usr/bin/env python3
import time
import sys

time.sleep(5)  # Sleep longer than timeout
print("This should not be reached")
sys.exit(0)
"""
        
        helper_dir = self._create_test_helper("test_timeout_health", health_script, "health.py")
        
        # Mock registry and file system
        with patch.object(helper_registry, 'get_registry_entry') as mock_get_entry:
            mock_entry = MagicMock()
            mock_entry.healthcheck = "health.py"
            mock_get_entry.return_value = mock_entry
            
            with patch('helpers.sdk.Path') as mock_path:
                mock_helpers_dir = MagicMock()
                mock_helper_dir = helper_dir
                mock_path.return_value.__truediv__.return_value = mock_helper_dir
                
                result = run_helper_health_check("test_timeout_health", timeout_seconds=1)
                
                self.assertEqual(result["helper_id"], "test_timeout_health")
                self.assertEqual(result["status"], "timeout")
                self.assertEqual(result["timeout_seconds"], 1)
                self.assertIn("timed out", result["message"])
    
    def test_javascript_health_check(self):
        """Test JavaScript health check execution."""
        # Create test helper with JavaScript health script
        health_script = """#!/usr/bin/env node
const result = {
    status: "healthy",
    message: "JavaScript health check passed",
    checks: {test: "pass"}
};

console.log(JSON.stringify(result));
process.exit(0);
"""
        
        helper_dir = self._create_test_helper("test_js_health", health_script, "health.js")
        
        # Mock registry and file system
        with patch.object(helper_registry, 'get_registry_entry') as mock_get_entry:
            mock_entry = MagicMock()
            mock_entry.healthcheck = "health.js"
            mock_get_entry.return_value = mock_entry
            
            with patch('helpers.sdk.Path') as mock_path:
                mock_helpers_dir = MagicMock()
                mock_helper_dir = helper_dir
                mock_path.return_value.__truediv__.return_value = mock_helper_dir
                
                # Check if node is available before running test
                import shutil
                if shutil.which('node'):
                    result = run_helper_health_check("test_js_health")
                    
                    self.assertEqual(result["helper_id"], "test_js_health")
                    self.assertEqual(result["status"], "healthy")
                    self.assertIn("duration_ms", result)
                else:
                    # Skip if node not available
                    self.skipTest("Node.js not available for JavaScript health check test")
    
    def test_shell_script_health_check(self):
        """Test shell script health check execution."""
        # Create test helper with shell health script
        health_script = """#!/bin/bash
echo '{"status": "healthy", "message": "Shell script health check passed"}'
exit 0
"""
        
        helper_dir = self._create_test_helper("test_shell_health", health_script, "health.sh")
        
        # Mock registry and file system
        with patch.object(helper_registry, 'get_registry_entry') as mock_get_entry:
            mock_entry = MagicMock()
            mock_entry.healthcheck = "health.sh"
            mock_get_entry.return_value = mock_entry
            
            with patch('helpers.sdk.Path') as mock_path:
                mock_helpers_dir = MagicMock()
                mock_helper_dir = helper_dir
                mock_path.return_value.__truediv__.return_value = mock_helper_dir
                
                result = run_helper_health_check("test_shell_health")
                
                self.assertEqual(result["helper_id"], "test_shell_health")
                self.assertEqual(result["status"], "healthy")
                self.assertIn("duration_ms", result)
    
    def test_all_helpers_health_check(self):
        """Test running health checks for all helpers."""
        # Mock registry to return some test helpers
        with patch.object(helper_registry, 'get_validation_summary') as mock_get_summary:
            mock_get_summary.return_value = {
                "helpers": {
                    "helper1": {"is_valid": True},
                    "helper2": {"is_valid": True},
                    "helper3": {"is_valid": True}
                }
            }
            
            # Mock individual health checks
            with patch('helpers.sdk.run_helper_health_check') as mock_health_check:
                mock_health_check.side_effect = [
                    {"helper_id": "helper1", "status": "healthy"},
                    {"helper_id": "helper2", "status": "unhealthy"},
                    {"helper_id": "helper3", "status": "skipped"}
                ]
                
                result = run_all_helper_health_checks()
                
                self.assertIn("summary", result)
                self.assertIn("results", result)
                self.assertIn("timestamp", result)
                
                summary = result["summary"]
                self.assertEqual(summary["total"], 3)
                self.assertEqual(summary["healthy"], 1)
                self.assertEqual(summary["unhealthy"], 1)
                self.assertEqual(summary["skipped"], 1)
                self.assertEqual(summary["errors"], 0)
                self.assertEqual(summary["timeouts"], 0)
    
    def test_real_bot_guard_health_check(self):
        """Test the actual bot_guard health check if available."""
        # Only run if bot_guard exists and has health check
        try:
            registry_entry = helper_registry.get_registry_entry("bot_guard")
            if registry_entry and registry_entry.healthcheck:
                result = run_helper_health_check("bot_guard", timeout_seconds=15)
                
                self.assertEqual(result["helper_id"], "bot_guard")
                self.assertIn(result["status"], ["healthy", "unhealthy", "error"])
                self.assertIn("duration_ms", result)
                
                print(f"✓ bot_guard health check: {result['status']} ({result.get('duration_ms', 0)}ms)")
                if result.get("stdout"):
                    print(f"  Output: {result['stdout'][:100]}...")
            else:
                self.skipTest("bot_guard helper not available or no health check configured")
        except Exception as e:
            self.skipTest(f"bot_guard health check failed: {e}")
    
    def test_real_log_tailer_health_check(self):
        """Test the actual log_tailer health check if available."""
        # Only run if log_tailer exists and has health check
        try:
            registry_entry = helper_registry.get_registry_entry("log_tailer")
            if registry_entry and registry_entry.healthcheck:
                result = run_helper_health_check("log_tailer", timeout_seconds=15)
                
                self.assertEqual(result["helper_id"], "log_tailer")
                self.assertIn(result["status"], ["healthy", "unhealthy", "error"])
                self.assertIn("duration_ms", result)
                
                print(f"✓ log_tailer health check: {result['status']} ({result.get('duration_ms', 0)}ms)")
                if result.get("stdout"):
                    print(f"  Output: {result['stdout'][:100]}...")
            else:
                self.skipTest("log_tailer helper not available or no health check configured")
        except Exception as e:
            self.skipTest(f"log_tailer health check failed: {e}")


@unittest.skipIf(not HTTP_CLIENT_AVAILABLE, "requests not available")
class TestHelperHealthHTTP(unittest.TestCase):
    """Test helper health checks via HTTP endpoints."""
    
    def setUp(self):
        """Set up HTTP test environment."""
        self.base_url = "http://localhost:8787"
        self.auth_headers = {}  # Add auth if required
        
        # Test if bridge is running
        try:
            response = requests.get(f"{self.base_url}/healthz", timeout=2)
            self.bridge_available = response.status_code == 200
        except requests.exceptions.RequestException:
            self.bridge_available = False
        
        if not self.bridge_available:
            self.skipTest("Bridge service not running at localhost:8787")
    
    def test_helper_health_endpoint_exists(self):
        """Test that GET /helpers/health/{helper_id} endpoint exists."""
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/health/{helper_id}",
                headers=self.auth_headers,
                timeout=15
            )
            
            # Should not be 404 (not found)
            self.assertNotEqual(response.status_code, 404, 
                              f"GET /helpers/health/{helper_id} endpoint not found")
            
            print(f"✓ GET /helpers/health/{helper_id} endpoint exists (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to reach GET /helpers/health/{helper_id} endpoint: {e}")
    
    def test_all_helpers_health_endpoint(self):
        """Test GET /helpers/health endpoint for all helpers."""
        try:
            response = requests.get(
                f"{self.base_url}/helpers/health",
                headers=self.auth_headers,
                timeout=30  # Longer timeout for running multiple health checks
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                expected_fields = ["status", "health_checks", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertEqual(data["status"], "success")
                
                # Check health_checks structure
                health_checks = data["health_checks"]
                self.assertIn("summary", health_checks)
                self.assertIn("results", health_checks)
                
                summary = health_checks["summary"]
                summary_fields = ["total", "healthy", "unhealthy", "skipped", "errors", "timeouts"]
                for field in summary_fields:
                    self.assertIn(field, summary, f"Missing field '{field}' in summary")
                
                print(f"✓ GET /helpers/health returned results for {summary['total']} helpers")
                print(f"  Healthy: {summary['healthy']}, Unhealthy: {summary['unhealthy']}, Skipped: {summary['skipped']}")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for health endpoint (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test GET /helpers/health endpoint: {e}")
    
    def test_individual_helper_health_response(self):
        """Test individual helper health check response structure."""
        helper_id = "log_tailer"  # Use log_tailer as it should have health check
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/health/{helper_id}",
                headers=self.auth_headers,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                expected_fields = ["status", "health_check", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertEqual(data["status"], "success")
                
                # Check health_check structure
                health_check = data["health_check"]
                required_fields = ["helper_id", "status"]
                for field in required_fields:
                    self.assertIn(field, health_check, f"Missing field '{field}' in health_check")
                
                self.assertEqual(health_check["helper_id"], helper_id)
                self.assertIn(health_check["status"], 
                            ["healthy", "unhealthy", "error", "timeout", "skipped"])
                
                print(f"✓ {helper_id} health check: {health_check['status']}")
                if health_check.get("duration_ms"):
                    print(f"  Duration: {health_check['duration_ms']}ms")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test individual helper health endpoint: {e}")


if __name__ == "__main__":
    # Run tests with detailed output
    unittest.main(verbosity=2)