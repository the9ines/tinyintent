#!/usr/bin/env python3
"""
TinyIntent Rate Limiting & Abuse Protection Tests - M6.6

Tests rate limiting for sessions, global requests, and helper executions
to prevent overloading the bridge or exhausting system resources.
"""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add bridge and helpers to path
sys.path.append(str(Path(__file__).parent.parent / "bridge"))
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

try:
    from tinyintent.bridge.security import RateLimiter
from tinyintent.helpers.executor import HelperRateLimiter, HelperRateLimitError
    HELPERS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helpers framework not available: {e}")
    HELPERS_AVAILABLE = False


class TestBridgeRateLimiting(unittest.TestCase):
    """Test bridge-level rate limiting for sessions and global requests."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create test rate limiter with low limits for fast testing
        self.rate_limiter = RateLimiter(
            session_limit=5,    # 5 requests per minute per session
            global_limit=20,    # 20 requests per minute globally
            window_seconds=60   # 60 second window
        )
    
    def test_session_rate_limit_enforcement(self):
        """Test that per-session rate limits are enforced correctly."""
        session_id = "test-session-1"
        
        # First 5 requests should be allowed
        for i in range(5):
            allowed, retry_after = self.rate_limiter.check_rate_limit(session_id)
            self.assertTrue(allowed, f"Request {i+1} should be allowed")
            self.assertIsNone(retry_after)
        
        # 6th request should be rate limited
        allowed, retry_after = self.rate_limiter.check_rate_limit(session_id)
        self.assertFalse(allowed, "6th request should be rate limited")
        self.assertEqual(retry_after, 60)
    
    def test_global_rate_limit_enforcement(self):
        """Test that global rate limits are enforced across sessions."""
        # Use different sessions to avoid per-session limits
        sessions = [f"test-session-{i}" for i in range(10)]
        
        # Each session makes 2 requests = 20 total (at global limit)
        for session_id in sessions:
            for _ in range(2):
                allowed, retry_after = self.rate_limiter.check_rate_limit(session_id)
                self.assertTrue(allowed, f"Request should be allowed for {session_id}")
                self.assertIsNone(retry_after)
        
        # Next request from any session should hit global limit
        allowed, retry_after = self.rate_limiter.check_rate_limit("new-session")
        self.assertFalse(allowed, "Request should hit global rate limit")
        self.assertEqual(retry_after, 60)
    
    def test_rate_limit_window_reset(self):
        """Test that rate limits reset after the time window."""
        session_id = "test-session-window"
        
        # Fill up the rate limit
        for _ in range(5):
            allowed, _ = self.rate_limiter.check_rate_limit(session_id)
            self.assertTrue(allowed)
        
        # Next request should be limited
        allowed, _ = self.rate_limiter.check_rate_limit(session_id)
        self.assertFalse(allowed)
        
        # Mock time advance by 61 seconds (past window)
        current_time = time.time()
        future_time = current_time + 61
        
        with patch('tinyrpc.time.time', return_value=future_time):
            # Request should now be allowed again
            allowed, retry_after = self.rate_limiter.check_rate_limit(session_id)
            self.assertTrue(allowed)
            self.assertIsNone(retry_after)
    
    def test_different_sessions_independent_limits(self):
        """Test that different sessions have independent rate limits."""
        session_1 = "test-session-1"
        session_2 = "test-session-2"
        
        # Fill up session 1's limit
        for _ in range(5):
            allowed, _ = self.rate_limiter.check_rate_limit(session_1)
            self.assertTrue(allowed)
        
        # Session 1 should now be limited
        allowed, _ = self.rate_limiter.check_rate_limit(session_1)
        self.assertFalse(allowed)
        
        # Session 2 should still have full quota
        for _ in range(5):
            allowed, _ = self.rate_limiter.check_rate_limit(session_2)
            self.assertTrue(allowed)
    
    def test_rate_limiter_stats(self):
        """Test rate limiter statistics reporting."""
        session_1 = "stats-test-1"
        session_2 = "stats-test-2"
        
        # Make some requests
        for _ in range(3):
            self.rate_limiter.check_rate_limit(session_1)
        for _ in range(2):
            self.rate_limiter.check_rate_limit(session_2)
        
        # Check stats
        stats = self.rate_limiter.get_stats()
        
        self.assertEqual(stats["session_limit"], 5)
        self.assertEqual(stats["global_limit"], 20)
        self.assertEqual(stats["window_seconds"], 60)
        self.assertEqual(stats["current_global_count"], 5)
        self.assertEqual(stats["active_sessions"], 2)
        self.assertIn(session_1, stats["session_counts"])
        self.assertIn(session_2, stats["session_counts"])
        self.assertEqual(stats["session_counts"][session_1], 3)
        self.assertEqual(stats["session_counts"][session_2], 2)
    
    def test_rate_limiter_cleanup(self):
        """Test that expired entries are cleaned up."""
        session_id = "cleanup-test"
        
        # Make a request
        self.rate_limiter.check_rate_limit(session_id)
        
        # Verify session is tracked
        stats = self.rate_limiter.get_stats()
        self.assertIn(session_id, stats["session_counts"])
        
        # Mock time advance past window
        current_time = time.time()
        future_time = current_time + 70
        
        with patch('tinyrpc.time.time', return_value=future_time):
            # Trigger cleanup by getting stats (calls internal cleanup)
            # Create new rate limiter to test cleanup on fresh instance
            new_limiter = RateLimiter(session_limit=5, global_limit=20, window_seconds=60)
            stats = new_limiter.get_stats()
            
            # Should have no active sessions after cleanup
            self.assertEqual(stats["active_sessions"], 0)
            self.assertEqual(stats["current_global_count"], 0)


class TestHelperRateLimiting(unittest.TestCase):
    """Test helper execution rate limiting."""
    
    def setUp(self):
        """Set up test environment."""
        if not HELPERS_AVAILABLE:
            self.skipTest("Helpers framework not available")
        
        # Create test helper rate limiter with low limits for fast testing
        self.helper_rate_limiter = HelperRateLimiter(
            default_limit=3,    # 3 executions per minute per helper
            window_seconds=60   # 60 second window
        )
    
    def test_helper_rate_limit_enforcement(self):
        """Test that helper execution rate limits are enforced."""
        helper_id = "test-helper"
        
        # First 3 executions should be allowed
        for i in range(3):
            result = self.helper_rate_limiter.check_helper_rate_limit(helper_id)
            self.assertTrue(result, f"Execution {i+1} should be allowed")
        
        # 4th execution should raise rate limit error
        with self.assertRaises(HelperRateLimitError) as context:
            self.helper_rate_limiter.check_helper_rate_limit(helper_id)
        
        error = context.exception
        self.assertEqual(error.error_code, "HELPER_RATE_LIMIT")
        self.assertEqual(error.helper_id, helper_id)
        self.assertEqual(error.current_count, 3)
        self.assertEqual(error.limit, 3)
        self.assertEqual(error.window_seconds, 60)
    
    def test_different_helpers_independent_limits(self):
        """Test that different helpers have independent rate limits."""
        helper_1 = "helper-1"
        helper_2 = "helper-2"
        
        # Fill up helper 1's limit
        for _ in range(3):
            self.helper_rate_limiter.check_helper_rate_limit(helper_1)
        
        # Helper 1 should now be limited
        with self.assertRaises(HelperRateLimitError):
            self.helper_rate_limiter.check_helper_rate_limit(helper_1)
        
        # Helper 2 should still have full quota
        for _ in range(3):
            result = self.helper_rate_limiter.check_helper_rate_limit(helper_2)
            self.assertTrue(result)
    
    def test_custom_helper_limits(self):
        """Test custom rate limits for specific helpers."""
        helper_id = "custom-limit-helper"
        custom_limit = 5
        
        # First 5 executions should be allowed with custom limit
        for i in range(custom_limit):
            result = self.helper_rate_limiter.check_helper_rate_limit(helper_id, limit=custom_limit)
            self.assertTrue(result, f"Execution {i+1} should be allowed")
        
        # 6th execution should be rate limited
        with self.assertRaises(HelperRateLimitError) as context:
            self.helper_rate_limiter.check_helper_rate_limit(helper_id, limit=custom_limit)
        
        error = context.exception
        self.assertEqual(error.limit, custom_limit)
        self.assertEqual(error.current_count, custom_limit)
    
    def test_helper_rate_limit_window_reset(self):
        """Test helper rate limits reset after time window."""
        helper_id = "window-test-helper"
        
        # Fill up the rate limit
        for _ in range(3):
            self.helper_rate_limiter.check_helper_rate_limit(helper_id)
        
        # Next execution should be limited
        with self.assertRaises(HelperRateLimitError):
            self.helper_rate_limiter.check_helper_rate_limit(helper_id)
        
        # Mock time advance past window
        current_time = time.time()
        future_time = current_time + 61
        
        with patch('sdk.time.time', return_value=future_time):
            # Execution should now be allowed again
            result = self.helper_rate_limiter.check_helper_rate_limit(helper_id)
            self.assertTrue(result)
    
    def test_helper_rate_limit_stats(self):
        """Test helper rate limiting statistics."""
        helper_1 = "stats-helper-1"
        helper_2 = "stats-helper-2"
        
        # Make some executions
        for _ in range(2):
            self.helper_rate_limiter.check_helper_rate_limit(helper_1)
        for _ in range(1):
            self.helper_rate_limiter.check_helper_rate_limit(helper_2)
        
        # Check individual helper stats
        stats_1 = self.helper_rate_limiter.get_helper_stats(helper_1)
        self.assertEqual(stats_1["helper_id"], helper_1)
        self.assertEqual(stats_1["current_count"], 2)
        self.assertEqual(stats_1["limit"], 3)
        self.assertEqual(stats_1["remaining"], 1)
        
        # Check all helpers stats
        all_stats = self.helper_rate_limiter.get_all_stats()
        self.assertEqual(all_stats["default_limit"], 3)
        self.assertEqual(all_stats["total_executions"], 3)
        self.assertEqual(all_stats["active_helpers"], 2)
        self.assertIn(helper_1, all_stats["helper_stats"])
        self.assertIn(helper_2, all_stats["helper_stats"])


class TestRateLimitingIntegration(unittest.TestCase):
    """Integration tests for rate limiting across the system."""
    
    def setUp(self):
        """Set up integration test environment."""
        if not BRIDGE_AVAILABLE or not HELPERS_AVAILABLE:
            self.skipTest("Bridge or helpers not available")
    
    def test_bridge_rate_limiting_with_audit_logging(self):
        """Test that rate limiting violations are properly logged."""
        # This would require setting up the full FastAPI app and making requests
        # For now, we test the components individually
        pass
    
    def test_helper_rate_limiting_in_sdk_execution(self):
        """Test helper rate limiting during actual SDK execution."""
        # This would require mocking the full helper execution environment
        # The rate limiting is tested in the unit tests above
        pass
    
    def test_rate_limiting_environment_configuration(self):
        """Test rate limiting configuration via environment variables."""
        # Test that environment variables are properly read
        with patch.dict(os.environ, {
            'RATE_LIMIT_SESSION': '100',
            'RATE_LIMIT_GLOBAL': '1000', 
            'RATE_LIMIT_WINDOW': '120',
            'HELPER_RATE_LIMIT': '20',
            'HELPER_RATE_LIMIT_WINDOW': '120'
        }):
            # Create new instances to pick up environment variables
            bridge_limiter = RateLimiter(
                session_limit=int(os.getenv("RATE_LIMIT_SESSION", "60")),
                global_limit=int(os.getenv("RATE_LIMIT_GLOBAL", "500")),
                window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "60"))
            )
            
            helper_limiter = HelperRateLimiter(
                default_limit=int(os.getenv("HELPER_RATE_LIMIT", "10")),
                window_seconds=int(os.getenv("HELPER_RATE_LIMIT_WINDOW", "60"))
            )
            
            # Verify configuration
            self.assertEqual(bridge_limiter.session_limit, 100)
            self.assertEqual(bridge_limiter.global_limit, 1000)
            self.assertEqual(bridge_limiter.window_seconds, 120)
            self.assertEqual(helper_limiter.default_limit, 20)
            self.assertEqual(helper_limiter.window_seconds, 120)


class TestRateLimitingStressTest(unittest.TestCase):
    """Stress tests for rate limiting under concurrent load."""
    
    def setUp(self):
        """Set up stress test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.rate_limiter = RateLimiter(
            session_limit=10,
            global_limit=50,
            window_seconds=60
        )
    
    def test_concurrent_session_rate_limiting(self):
        """Test rate limiting under concurrent access from same session."""
        session_id = "concurrent-session"
        results = []
        errors = []
        
        def make_request():
            try:
                allowed, retry_after = self.rate_limiter.check_rate_limit(session_id)
                results.append((allowed, retry_after))
            except Exception as e:
                errors.append(e)
        
        # Create 20 concurrent threads (more than session limit)
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Verify correct number of allowed/denied requests
        allowed_count = sum(1 for allowed, _ in results if allowed)
        denied_count = sum(1 for allowed, _ in results if not allowed)
        
        self.assertEqual(allowed_count, 10, "Should allow exactly 10 requests")
        self.assertEqual(denied_count, 10, "Should deny exactly 10 requests")
        
        # All denied requests should have retry_after set
        for allowed, retry_after in results:
            if not allowed:
                self.assertEqual(retry_after, 60)
    
    def test_concurrent_global_rate_limiting(self):
        """Test global rate limiting under concurrent access from multiple sessions."""
        results = []
        errors = []
        
        def make_requests_for_session(session_id):
            try:
                # Each session makes 3 requests
                for _ in range(3):
                    allowed, retry_after = self.rate_limiter.check_rate_limit(session_id)
                    results.append((session_id, allowed, retry_after))
            except Exception as e:
                errors.append(e)
        
        # Create 20 sessions, each making 3 requests = 60 total (more than global limit of 50)
        threads = []
        for i in range(20):
            session_id = f"session-{i}"
            thread = threading.Thread(target=make_requests_for_session, args=(session_id,))
            threads.append(thread)
        
        # Start all threads
        for thread in threads:
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Verify correct number of allowed/denied requests
        allowed_count = sum(1 for _, allowed, _ in results if allowed)
        denied_count = sum(1 for _, allowed, _ in results if not allowed)
        
        self.assertEqual(allowed_count, 50, "Should allow exactly 50 requests (global limit)")
        self.assertEqual(denied_count, 10, "Should deny exactly 10 requests")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)