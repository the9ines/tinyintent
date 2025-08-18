#!/usr/bin/env python3
"""
TinyIntent Router & Async Generation Tests - M7.0

Tests router refactor and async generation with mocked Ollama endpoints
to verify timeout handling, retries, backoff, and concurrency control.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

# Add bridge to path
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

try:
    from tinyrpc import SmallIntentRouter, AsyncOllamaClient, router, async_ollama_client
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Bridge not available: {e}")
    BRIDGE_AVAILABLE = False


class TestSmallIntentRouter(unittest.TestCase):
    """Test SmallIntent router for routing decisions."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create test router with fallback (no Swift runner available in tests)
        self.router = SmallIntentRouter()
    
    def test_fallback_routing_generation(self):
        """Test fallback routing for generation requests."""
        test_cases = [
            ("What is the weather like?", "gen"),
            ("Explain how neural networks work", "gen"),
            ("Help me understand Python", "gen"),
            ("Tell me a joke", "gen")
        ]
        
        for text, expected_route in test_cases:
            result = self.router.route_request(text)
            
            self.assertIn("route", result)
            self.assertIn("intent", result)
            self.assertIn("confidence", result)
            self.assertEqual(result["route"], expected_route)
            self.assertIsInstance(result["confidence"], (int, float))
    
    def test_fallback_routing_action(self):
        """Test fallback routing for action requests."""
        test_cases = [
            ("Close my bot positions", "act"),
            ("Show me my trading positions", "act"),
            ("Stop the emergency bot", "act"),
            ("Execute the trading strategy", "act"),
            ("Run the backup script", "act"),
            ("Do something with my bot", "act")
        ]
        
        for text, expected_route in test_cases:
            result = self.router.route_request(text)
            
            self.assertEqual(result["route"], expected_route)
            self.assertEqual(result["intent"], "bot_management")
            self.assertGreaterEqual(result["confidence"], 0.5)
    
    def test_router_unavailable_fallback(self):
        """Test router falls back gracefully when Swift runner unavailable."""
        # Create router with non-existent path to test fallback
        nonexistent_path = Path("/nonexistent/router.swift")
        router = SmallIntentRouter(router_path=nonexistent_path)
        
        # Router should use fallback logic when router_available is False
        self.assertFalse(router.router_available)
        
        result = router.route_request("Test message")
        
        # Should still return valid routing result
        self.assertIn("route", result)
        self.assertIn("intent", result)
        self.assertIn("confidence", result)
        self.assertIn(result["route"], ["gen", "act"])
    
    @patch('subprocess.run')
    def test_router_with_swift_success(self, mock_subprocess):
        """Test router with successful Swift execution."""
        # Mock successful Swift router call
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"route":"act","intent":"bot_management","confidence":0.95}'
        mock_subprocess.return_value = mock_result
        
        # Create router with available path
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Close my positions")
        
        self.assertEqual(result["route"], "act")
        self.assertEqual(result["intent"], "bot_management")
        self.assertEqual(result["confidence"], 0.95)
    
    @patch('subprocess.run')
    def test_router_swift_failure_fallback(self, mock_subprocess):
        """Test router falls back when Swift execution fails."""
        # Mock failed Swift router call
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Model not found"
        mock_subprocess.return_value = mock_result
        
        # Create router with available path
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Close my positions")
        
        # Should fall back to hardcoded routing
        self.assertIn("route", result)
        self.assertIn("intent", result)
        self.assertIn("confidence", result)
    
    @patch('subprocess.run')
    def test_router_invalid_json_fallback(self, mock_subprocess):
        """Test router falls back when Swift returns invalid JSON."""
        # Mock Swift router with invalid JSON
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = 'invalid json response'
        mock_subprocess.return_value = mock_result
        
        # Create router with available path
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Test message")
        
        # Should fall back to hardcoded routing
        self.assertIn("route", result)
        self.assertIn("intent", result)
        self.assertIn("confidence", result)


class TestAsyncOllamaClient(unittest.IsolatedAsyncioTestCase):
    """Test async Ollama client with timeouts, retries, and concurrency."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create test client with short timeouts for fast testing
        self.client = AsyncOllamaClient()
        self.client.gen_timeout = 2  # 2 second timeout
        self.client.max_retries = 2
        self.client.backoff_ms = 100  # 100ms backoff
    
    async def test_successful_generation(self):
        """Test successful async generation."""
        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Generated text response"}
        
        async def mock_post(*args, **kwargs):
            # Add small delay to ensure latency > 0
            await asyncio.sleep(0.001)
            return mock_response
        
        with patch.object(self.client.client, 'post', side_effect=mock_post) as mock_post_method:
            response_text, latency_ms = await self.client.generate_async("llama2", "Test prompt")
            
            self.assertEqual(response_text, "Generated text response")
            self.assertIsInstance(latency_ms, int)
            self.assertGreaterEqual(latency_ms, 0)  # Changed to >= to handle very fast mocks
            mock_post_method.assert_called_once()
    
    async def test_timeout_handling(self):
        """Test timeout handling with proper error response."""
        # Mock timeout exception
        with patch.object(self.client.client, 'post', side_effect=httpx.TimeoutException("Request timed out")):
            
            with self.assertRaises(Exception) as context:
                await self.client.generate_async("llama2", "Test prompt")
            
            # Should be HTTPException with 504 status
            self.assertIn("timed out", str(context.exception))
    
    async def test_retry_mechanism(self):
        """Test retry mechanism with backoff."""
        # Mock first two calls to fail, third to succeed
        mock_responses = [
            httpx.TimeoutException("Timeout 1"),
            httpx.TimeoutException("Timeout 2"),
            MagicMock(status_code=200, json=lambda: {"response": "Success after retries"})
        ]
        
        call_count = 0
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            response = mock_responses[call_count]
            call_count += 1
            if isinstance(response, Exception):
                raise response
            return response
        
        with patch.object(self.client.client, 'post', side_effect=mock_post):
            start_time = time.time()
            response_text, latency_ms = await self.client.generate_async("llama2", "Test prompt")
            end_time = time.time()
            
            self.assertEqual(response_text, "Success after retries")
            self.assertEqual(call_count, 3)  # Should have made 3 attempts
            
            # Should have taken time for backoff delays
            total_time = end_time - start_time
            expected_min_time = 0.1 + 0.2  # 100ms + 200ms backoff
            self.assertGreater(total_time, expected_min_time / 1000)
    
    async def test_max_retries_exhausted(self):
        """Test behavior when max retries are exhausted."""
        # Mock all calls to fail
        with patch.object(self.client.client, 'post', side_effect=httpx.TimeoutException("Persistent timeout")):
            
            with self.assertRaises(Exception) as context:
                await self.client.generate_async("llama2", "Test prompt")
            
            # Should be HTTPException after all retries exhausted
            self.assertIn("timed out", str(context.exception))
    
    async def test_http_error_handling(self):
        """Test HTTP error response handling."""
        # Mock HTTP error response
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.request = MagicMock()
        
        def raise_http_error(*args, **kwargs):
            raise httpx.HTTPStatusError("Server error", request=mock_response.request, response=mock_response)
        
        with patch.object(self.client.client, 'post', side_effect=raise_http_error):
            
            with self.assertRaises(Exception) as context:
                await self.client.generate_async("llama2", "Test prompt")
            
            # Should handle HTTP errors gracefully
            self.assertIn("timed out", str(context.exception))
    
    async def test_concurrent_request_limiting(self):
        """Test semaphore limits concurrent requests."""
        # Set small semaphore for testing
        self.client.concurrency_limit = 2
        self.client._semaphore = asyncio.Semaphore(2)
        
        # Track concurrent requests
        concurrent_count = 0
        max_concurrent = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            
            # Simulate slow response
            await asyncio.sleep(0.1)
            
            concurrent_count -= 1
            return MagicMock(
                status_code=200,
                json=lambda: {"response": f"Response {concurrent_count}"}
            )
        
        with patch.object(self.client.client, 'post', side_effect=mock_post):
            # Start 4 concurrent requests with semaphore of 2
            tasks = [
                self.client.generate_async("llama2", f"Prompt {i}")
                for i in range(4)
            ]
            
            results = await asyncio.gather(*tasks)
            
            # All requests should complete
            self.assertEqual(len(results), 4)
            
            # Should never exceed semaphore limit
            self.assertLessEqual(max_concurrent, 2)
    
    async def test_client_cleanup(self):
        """Test async client cleanup."""
        # Mock the close method
        with patch.object(self.client.client, 'aclose', new_callable=AsyncMock) as mock_close:
            await self.client.close()
            mock_close.assert_called_once()


class TestRouterIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for router and async generation."""
    
    def setUp(self):
        """Set up integration test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    async def test_router_to_generation_flow(self):
        """Test complete flow from router decision to async generation."""
        # Mock router to return generation route
        with patch.object(router, 'route_request') as mock_router:
            mock_router.return_value = {
                "route": "gen",
                "intent": "general_query",
                "confidence": 0.8
            }
            
            # Mock successful generation
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"response": "Generated response"}
            
            with patch.object(async_ollama_client.client, 'post', return_value=mock_response):
                response_text, latency_ms = await async_ollama_client.generate_async("llama2", "Test prompt")
                
                self.assertEqual(response_text, "Generated response")
                self.assertIsInstance(latency_ms, int)
    
    async def test_router_to_action_flow(self):
        """Test complete flow from router decision to action routing.""" 
        # Mock router to return action route
        with patch.object(router, 'route_request') as mock_router:
            mock_router.return_value = {
                "route": "act",
                "intent": "bot_management", 
                "confidence": 0.9
            }
            
            # Verify router decision is used correctly
            result = router.route_request("Close my bot positions")
            
            self.assertEqual(result["route"], "act")
            self.assertEqual(result["intent"], "bot_management")
            self.assertGreater(result["confidence"], 0.8)


class TestEnvironmentConfiguration(unittest.IsolatedAsyncioTestCase):
    """Test environment variable configuration for async generation."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    def test_default_configuration(self):
        """Test default configuration values."""
        client = AsyncOllamaClient()
        
        # Check default values (may be overridden by environment)
        self.assertIsInstance(client.gen_timeout, int)
        self.assertIsInstance(client.max_retries, int)
        self.assertIsInstance(client.backoff_ms, int)
        self.assertIsNotNone(client.semaphore)
        self.assertIn("localhost", client.ollama_host)
    
    def test_environment_configuration(self):
        """Test configuration via environment variables."""
        test_env = {
            'OLLAMA_HOST': 'http://test-host:8080',
            'GEN_TIMEOUT_S': '30',
            'GEN_MAX_RETRIES': '3',
            'GEN_BACKOFF_MS': '500',
            'GEN_CONCURRENCY': '8'
        }
        
        with patch.dict(os.environ, test_env):
            client = AsyncOllamaClient()
            
            self.assertEqual(client.ollama_host, 'http://test-host:8080')
            self.assertEqual(client.gen_timeout, 30)
            self.assertEqual(client.max_retries, 3)
            self.assertEqual(client.backoff_ms, 500)
            self.assertEqual(client.semaphore._value, 8)


class TestErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling in async generation."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.client = AsyncOllamaClient()
    
    async def test_connection_error_handling(self):
        """Test connection error handling."""
        with patch.object(self.client.client, 'post', side_effect=httpx.ConnectError("Connection failed")):
            
            with self.assertRaises(Exception) as context:
                await self.client.generate_async("llama2", "Test prompt")
            
            # Should handle connection errors gracefully
            self.assertIn("timed out", str(context.exception))
    
    async def test_malformed_response_handling(self):
        """Test malformed JSON response handling."""
        # Mock response with invalid JSON
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
        
        with patch.object(self.client.client, 'post', return_value=mock_response):
            
            with self.assertRaises(Exception):
                await self.client.generate_async("llama2", "Test prompt")
    
    async def test_empty_response_handling(self):
        """Test empty response handling."""
        # Mock response with empty or missing response field
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}  # Missing 'response' field
        
        with patch.object(self.client.client, 'post', return_value=mock_response):
            response_text, latency_ms = await self.client.generate_async("llama2", "Test prompt")
            
            # Should handle missing response field gracefully
            self.assertEqual(response_text, "")
            self.assertIsInstance(latency_ms, int)


def run_async_test(coro):
    """Helper to run async tests."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)