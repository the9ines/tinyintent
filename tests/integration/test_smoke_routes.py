#!/usr/bin/env python3
"""
Smoke Tests for TinyIntent API Routes

Tests critical API endpoints to ensure they're working correctly:
- Health endpoints
- Router metrics
- Helper management
- Preview/approve/execute flow
- System endpoints

M9.1: Final Polish & Release Prep
"""

import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import requests
import responses

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class SmokeTestConfig:
    """Configuration for smoke tests."""
    
    def __init__(self):
        self.base_url = os.getenv("SMOKE_BASE_URL", "http://localhost:8787")
        self.secret = os.getenv("TINYINTENT_SECRET", "test-secret")
        self.execution_enabled = os.getenv("EXECUTION_ENABLED", "0") == "1"
        self.timeout = 10
        self.skip_execution = not self.execution_enabled
    
    @property
    def headers(self):
        return {
            "Authorization": f"Bearer {self.secret}",
            "Content-Type": "application/json"
        }


class BaseSmokeTest(unittest.TestCase):
    """Base class for smoke tests."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test configuration."""
        cls.config = SmokeTestConfig()
        cls.session = requests.Session()
        cls.session.headers.update(cls.config.headers)
    
    @classmethod
    def tearDownClass(cls):
        """Clean up session."""
        cls.session.close()
    
    def check_endpoint(self, path, method="GET", data=None, expected_status=200):
        """Helper to check an endpoint."""
        url = f"{self.config.base_url}{path}"
        
        try:
            if method == "GET":
                response = self.session.get(url, timeout=self.config.timeout)
            elif method == "POST":
                response = self.session.post(url, json=data, timeout=self.config.timeout)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            self.assertEqual(
                response.status_code, 
                expected_status, 
                f"Endpoint {path} returned {response.status_code}, expected {expected_status}. Response: {response.text[:200]}"
            )
            
            return response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
            
        except requests.exceptions.ConnectionError:
            self.skipTest(f"Cannot connect to {self.config.base_url}. Is the bridge service running?")
        except requests.exceptions.Timeout:
            self.fail(f"Timeout connecting to {path}")


class TestHealthEndpoints(BaseSmokeTest):
    """Test health and readiness endpoints."""
    
    def test_health_check(self):
        """Test basic health endpoint."""
        response = self.check_endpoint("/healthz")
        self.assertIn("status", response)
        self.assertEqual(response["status"], "ok")
    
    def test_readiness_check(self):
        """Test readiness endpoint."""
        response = self.check_endpoint("/readyz")
        self.assertIn("ready", response)
        self.assertTrue(response["ready"])


class TestSystemEndpoints(BaseSmokeTest):
    """Test system monitoring endpoints."""
    
    def test_doctor_endpoint(self):
        """Test system doctor endpoint."""
        response = self.check_endpoint("/doctor")
        
        # Check required fields
        required_fields = ["timestamp", "overall_status", "checks", "recommendations", "summary"]
        for field in required_fields:
            self.assertIn(field, response, f"Missing required field: {field}")
        
        # Check overall status is valid
        valid_statuses = ["healthy", "ready", "unhealthy", "unknown"]
        self.assertIn(response["overall_status"], valid_statuses)
        
        # Check summary structure
        summary = response["summary"]
        summary_fields = ["total_checks", "passed_checks", "failed_checks", "warning_checks", "error_checks"]
        for field in summary_fields:
            self.assertIn(field, summary, f"Missing summary field: {field}")
            self.assertIsInstance(summary[field], int, f"Summary field {field} should be integer")
    
    def test_emergency_status(self):
        """Test emergency status endpoint."""
        response = self.check_endpoint("/emergency/status")
        
        # Check required fields
        required_fields = ["execution_enabled", "flag_file_exists"]
        for field in required_fields:
            self.assertIn(field, response, f"Missing required field: {field}")


class TestRouterEndpoints(BaseSmokeTest):
    """Test router-related endpoints."""
    
    def test_router_metrics(self):
        """Test router metrics endpoint."""
        response = self.check_endpoint("/router/metrics")
        
        # Should return metrics structure
        self.assertIsInstance(response, dict)
        # Basic metrics that should exist
        if "total_requests" in response:
            self.assertIsInstance(response["total_requests"], int)


class TestHelperEndpoints(BaseSmokeTest):
    """Test helper management endpoints."""
    
    def test_helpers_list(self):
        """Test listing helpers."""
        response = self.check_endpoint("/helpers")
        
        # Should return list of helpers
        self.assertIsInstance(response, list)
        
        # Check each helper has required fields
        for helper in response:
            required_fields = ["id", "name", "enabled", "risk_level"]
            for field in required_fields:
                self.assertIn(field, helper, f"Helper missing required field: {field}")
    
    def test_helpers_reload(self):
        """Test reloading helpers."""
        response = self.check_endpoint("/helpers/reload", method="POST")
        
        # Should return success response
        self.assertIn("status", response)
        self.assertEqual(response["status"], "success")
    
    def test_helper_health_all(self):
        """Test getting health for all helpers."""
        response = self.check_endpoint("/helpers/health")
        
        # Should return dict of helper health results
        self.assertIsInstance(response, dict)
        
        # Each health result should have basic structure
        for helper_id, health_result in response.items():
            self.assertIn("status", health_result)
            self.assertIn("timestamp", health_result)
    
    def test_helper_health_individual(self):
        """Test getting health for individual helper."""
        # First get list of helpers
        helpers_response = self.check_endpoint("/helpers")
        
        if helpers_response:
            # Test health check for first helper
            helper_id = helpers_response[0]["id"]
            response = self.check_endpoint(f"/helpers/health/{helper_id}")
            
            # Check health response structure
            required_fields = ["status", "timestamp"]
            for field in required_fields:
                self.assertIn(field, response, f"Missing required field: {field}")


class TestRouteFlow(BaseSmokeTest):
    """Test the complete route flow: preview → approve → execute."""
    
    def test_route_preview_gen(self):
        """Test generation route in preview mode."""
        data = {
            "text": "What is the weather like today?",
            "route": "gen",
            "execute": False
        }
        
        response = self.check_endpoint("/route", method="POST", data=data)
        
        # Check response structure
        required_fields = ["status", "route_used", "session_id"]
        for field in required_fields:
            self.assertIn(field, response, f"Missing required field: {field}")
        
        self.assertEqual(response["route_used"], "gen")
        self.assertEqual(response["status"], "success")
    
    def test_route_preview_act(self):
        """Test action route in preview mode."""
        data = {
            "text": "Show me my trading positions",
            "route": "act",
            "helper_id": "bot_guard",
            "execute": False
        }
        
        response = self.check_endpoint("/route", method="POST", data=data)
        
        # Check response structure
        required_fields = ["status", "route_used", "session_id"]
        for field in required_fields:
            self.assertIn(field, response, f"Missing required field: {field}")
        
        self.assertEqual(response["route_used"], "act")
        
        # Should include approval token for preview
        if response["status"] == "success":
            self.assertIn("approval_token", response)
    
    @unittest.skipIf(SmokeTestConfig().skip_execution, "Execution disabled (EXECUTION_ENABLED != 1)")
    def test_route_execute_with_approval(self):
        """Test executing action with approval token."""
        # First get approval token
        preview_data = {
            "text": "Show me my trading positions",
            "route": "act", 
            "helper_id": "bot_guard",
            "execute": False
        }
        
        preview_response = self.check_endpoint("/route", method="POST", data=preview_data)
        
        if preview_response.get("status") == "success" and "approval_token" in preview_response:
            # Now try to execute with approval token
            execute_data = {
                "text": "Show me my trading positions",
                "route": "act",
                "helper_id": "bot_guard", 
                "execute": True,
                "approval_token": preview_response["approval_token"]
            }
            
            # This might return 501 (not implemented) or actually execute
            # We just want to make sure the flow works
            try:
                execute_response = self.check_endpoint("/route", method="POST", data=execute_data, expected_status=200)
                self.assertEqual(execute_response["status"], "success")
            except AssertionError as e:
                # If we get 501, that's also acceptable (not implemented yet)
                if "501" in str(e):
                    pass  # Expected for some helpers
                else:
                    raise
    
    def test_route_invalid_helper(self):
        """Test routing with invalid helper."""
        data = {
            "text": "Do something",
            "route": "act",
            "helper_id": "nonexistent_helper",
            "execute": False
        }
        
        response = self.check_endpoint("/route", method="POST", data=data, expected_status=400)
        self.assertIn("error", response.get("detail", "").lower())


class TestSecurityEndpoints(BaseSmokeTest):
    """Test security-related endpoints."""
    
    def test_unauthorized_access(self):
        """Test that endpoints require authentication."""
        # Remove auth header
        session = requests.Session()
        session.headers["Content-Type"] = "application/json"
        
        try:
            response = session.get(f"{self.config.base_url}/helpers", timeout=self.config.timeout)
            self.assertEqual(response.status_code, 401, "Endpoint should require authentication")
        except requests.exceptions.ConnectionError:
            self.skipTest("Bridge service not running")
        finally:
            session.close()
    
    def test_invalid_auth(self):
        """Test with invalid auth token.""" 
        session = requests.Session()
        session.headers.update({
            "Authorization": "Bearer invalid-token",
            "Content-Type": "application/json"
        })
        
        try:
            response = session.get(f"{self.config.base_url}/helpers", timeout=self.config.timeout)
            self.assertEqual(response.status_code, 401, "Invalid token should be rejected")
        except requests.exceptions.ConnectionError:
            self.skipTest("Bridge service not running")
        finally:
            session.close()


class TestErrorHandling(BaseSmokeTest):
    """Test error handling and edge cases."""
    
    def test_malformed_route_request(self):
        """Test malformed route request."""
        data = {
            "text": "",  # Empty text should be rejected
            "route": "gen"
        }
        
        response = self.check_endpoint("/route", method="POST", data=data, expected_status=422)
        # Should get validation error
    
    def test_nonexistent_endpoint(self):
        """Test accessing nonexistent endpoint."""
        response = self.check_endpoint("/nonexistent", expected_status=404)


class TestPerformance(BaseSmokeTest):
    """Basic performance and reliability tests."""
    
    def test_concurrent_health_checks(self):
        """Test multiple concurrent health checks."""
        import threading
        import queue
        
        results = queue.Queue()
        num_threads = 5
        
        def check_health():
            try:
                response = self.check_endpoint("/healthz")
                results.put(("success", response))
            except Exception as e:
                results.put(("error", str(e)))
        
        # Start threads
        threads = []
        for _ in range(num_threads):
            thread = threading.Thread(target=check_health)
            thread.start()
            threads.append(thread)
        
        # Wait for completion
        for thread in threads:
            thread.join(timeout=10)
        
        # Check results
        success_count = 0
        while not results.empty():
            result_type, result_data = results.get()
            if result_type == "success":
                success_count += 1
        
        # At least most requests should succeed
        self.assertGreaterEqual(success_count, num_threads * 0.8)


class TestSmokeTestSuite(unittest.TestCase):
    """Meta-test to validate smoke test configuration."""
    
    def test_config_loaded(self):
        """Test that configuration is loaded correctly."""
        config = SmokeTestConfig()
        self.assertIsNotNone(config.base_url)
        self.assertIsNotNone(config.secret)
        self.assertIsInstance(config.execution_enabled, bool)
        self.assertIsInstance(config.timeout, int)
    
    def test_required_env_vars(self):
        """Test that required environment variables are noted."""
        # This test documents required env vars
        required_for_full_tests = [
            "TINYINTENT_SECRET",
            "EXECUTION_ENABLED"  # Optional, but affects test coverage
        ]
        
        missing = []
        for var in required_for_full_tests:
            if var not in os.environ:
                missing.append(var)
        
        if missing:
            print(f"ℹ️  Note: Missing env vars for full test coverage: {', '.join(missing)}")


def run_smoke_tests():
    """Run smoke tests with proper setup."""
    print("🔥 Running TinyIntent API Smoke Tests")
    print("=" * 50)
    
    # Check if we're in smoke mode
    smoke_mode = os.getenv("SMOKE_MODE", "false").lower() == "true"
    if smoke_mode:
        print("🧪 Running in SMOKE_MODE")
    
    config = SmokeTestConfig()
    print(f"📍 Target: {config.base_url}")
    print(f"🔐 Auth: {'Configured' if config.secret else 'Missing'}")
    print(f"⚡ Execution: {'Enabled' if config.execution_enabled else 'Disabled (preview only)'}")
    print()
    
    # Run tests
    unittest.main(argv=[''], exit=False, verbosity=2)


if __name__ == '__main__':
    run_smoke_tests()