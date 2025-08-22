#!/usr/bin/env python3
"""
TinyIntent Generation Reliability Tests - M7.3

Tests circuit breaker functionality, health checks, generation cancellation,
and integration with router metrics for the generation resilience system.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import threading
from collections import deque
import httpx

# Add bridge to path
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

try:
    from tinyintent.bridge.gen_client import (
    GenerationCircuitBreaker, 
    GenerationTaskManager, 
    AsyncOllamaClient,
    CircuitBreakerState
)
from tinyintent.bridge.router_client import router_metrics
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Bridge not available: {e}")
    BRIDGE_AVAILABLE = False


class TestCircuitBreakerCore(unittest.TestCase):
    """Test core circuit breaker functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create circuit breaker with test configuration
        with patch.dict(os.environ, {
            'GEN_CB_FAIL_WINDOW': '60',
            'GEN_CB_THRESHOLD': '3', 
            'GEN_CB_COOLDOWN': '10'
        }):
            self.circuit_breaker = GenerationCircuitBreaker()
    
    def test_initial_state_closed(self):
        """Test circuit breaker starts in CLOSED state."""
        can_execute, reason, info = self.circuit_breaker.can_execute("test-model")
        
        self.assertTrue(can_execute)
        self.assertEqual(reason, "closed")
        self.assertEqual(info["state"], "closed")
        self.assertEqual(info["failure_count"], 0)
    
    def test_failure_accumulation(self):
        """Test failure accumulation before threshold."""
        model = "test-model"
        
        # Record 2 failures (below threshold of 3)
        self.circuit_breaker.record_failure(model, "timeout")
        self.circuit_breaker.record_failure(model, "connection")
        
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        
        self.assertTrue(can_execute)
        self.assertEqual(reason, "closed")
        self.assertEqual(info["failure_count"], 2)
        
        stats = self.circuit_breaker.get_stats()
        self.assertEqual(stats["model_states"][model]["total_failures"], 2)
    
    def test_circuit_opens_on_threshold(self):
        """Test circuit breaker opens when failure threshold is reached."""
        model = "test-model"
        
        # Record 3 failures (meets threshold)
        for i in range(3):
            self.circuit_breaker.record_failure(model, "timeout")
        
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        
        self.assertFalse(can_execute)
        self.assertEqual(reason, "open")
        self.assertEqual(info["state"], "open")
        self.assertEqual(info["failure_count"], 3)
        self.assertGreater(info["cooldown_remaining"], 0)
    
    def test_circuit_stays_open_during_cooldown(self):
        """Test circuit breaker stays open during cooldown period."""
        model = "test-model"
        
        # Trigger circuit to open
        for i in range(3):
            self.circuit_breaker.record_failure(model, "timeout")
        
        # Verify it's open
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        self.assertFalse(can_execute)
        
        # Should still be open immediately after
        can_execute2, reason2, info2 = self.circuit_breaker.can_execute(model)
        self.assertFalse(can_execute2)
        self.assertEqual(reason2, "open")
    
    def test_circuit_transitions_to_half_open(self):
        """Test circuit breaker transitions to HALF_OPEN after cooldown."""
        model = "test-model"
        
        # Trigger circuit to open
        for i in range(3):
            self.circuit_breaker.record_failure(model, "timeout")
        
        # Manually set cooldown to be expired (simulate time passage)
        breaker_state = self.circuit_breaker._get_breaker_state(model)
        breaker_state["state_changed_at"] = time.time() - 20  # 20 seconds ago
        
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        
        self.assertTrue(can_execute)
        self.assertEqual(reason, "half_open")
        self.assertEqual(info["state"], "half_open")
    
    def test_half_open_success_closes_circuit(self):
        """Test successful request in HALF_OPEN closes the circuit."""
        model = "test-model"
        
        # Open circuit
        for i in range(3):
            self.circuit_breaker.record_failure(model, "timeout")
        
        # Transition to half-open (simulate cooldown expiry)
        breaker_state = self.circuit_breaker._get_breaker_state(model)
        breaker_state["state_changed_at"] = time.time() - 20
        breaker_state["state"] = CircuitBreakerState.HALF_OPEN
        
        # Record success in half-open state
        self.circuit_breaker.record_success(model)
        
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        
        self.assertTrue(can_execute)
        self.assertEqual(reason, "closed")
        self.assertEqual(info["failure_count"], 0)  # Failures cleared
    
    def test_half_open_failure_reopens_circuit(self):
        """Test failed request in HALF_OPEN reopens the circuit."""
        model = "test-model"
        
        # Open circuit then transition to half-open
        for i in range(3):
            self.circuit_breaker.record_failure(model, "timeout")
        
        breaker_state = self.circuit_breaker._get_breaker_state(model)
        breaker_state["state"] = CircuitBreakerState.HALF_OPEN
        
        # Record failure in half-open state
        self.circuit_breaker.record_failure(model, "timeout")
        
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        
        self.assertFalse(can_execute)
        self.assertEqual(reason, "open")
    
    def test_per_model_isolation(self):
        """Test circuit breakers are isolated per model."""
        model1 = "model-1"
        model2 = "model-2"
        
        # Fail model1 to open its circuit
        for i in range(3):
            self.circuit_breaker.record_failure(model1, "timeout")
        
        # Record success for model2
        self.circuit_breaker.record_success(model2)
        
        # Model1 should be open, model2 should be closed
        can_exec1, reason1, _ = self.circuit_breaker.can_execute(model1)
        can_exec2, reason2, _ = self.circuit_breaker.can_execute(model2)
        
        self.assertFalse(can_exec1)
        self.assertEqual(reason1, "open")
        
        self.assertTrue(can_exec2)
        self.assertEqual(reason2, "closed")
    
    def test_rolling_window_cleanup(self):
        """Test failure window cleanup removes old failures."""
        model = "test-model"
        
        # Manually add old failure (beyond window)
        breaker_state = self.circuit_breaker._get_breaker_state(model)
        old_time = time.time() - 120  # 120 seconds ago (beyond 60s window)
        breaker_state["failures"].append(old_time)
        
        # Add recent failure
        self.circuit_breaker.record_failure(model, "timeout")
        
        # Check count - old failure should be cleaned up
        can_execute, reason, info = self.circuit_breaker.can_execute(model)
        self.assertEqual(info["failure_count"], 1)  # Only recent failure
    
    def test_circuit_breaker_stats(self):
        """Test circuit breaker statistics collection."""
        model1 = "model-1"
        model2 = "model-2"
        
        # Add some requests and failures
        self.circuit_breaker.record_success(model1)
        self.circuit_breaker.record_failure(model1, "timeout")
        self.circuit_breaker.record_failure(model2, "connection")
        
        stats = self.circuit_breaker.get_stats()
        
        self.assertIn("config", stats)
        self.assertIn("model_states", stats)
        self.assertIn("failure_threshold", stats)
        self.assertIn("fail_window_seconds", stats)
        self.assertIn("cooldown_seconds", stats)
        
        # Check model-specific stats
        self.assertIn(model1, stats["model_states"])
        self.assertIn(model2, stats["model_states"])
        
        model1_stats = stats["model_states"][model1]
        self.assertEqual(model1_stats["total_requests"], 2)
        self.assertEqual(model1_stats["total_failures"], 1)
        self.assertEqual(model1_stats["state"], "closed")


class TestGenerationTaskManager(unittest.TestCase):
    """Test generation task manager for cancellation."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.task_manager = GenerationTaskManager()
    
    def test_task_registration(self):
        """Test task registration and tracking."""
        # Create mock task
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        
        request_id = "test-request-123"
        model = "test-model"
        session_id = "test-session"
        
        # Register task
        self.task_manager.register_task(request_id, mock_task, model, session_id)
        
        # Verify registration
        stats = self.task_manager.get_stats()
        self.assertEqual(stats["active_tasks"], 1)
        self.assertEqual(stats["total_registered"], 1)
        
        # Task should be in active tasks
        self.assertIn(request_id, self.task_manager.active_tasks)
    
    def test_task_unregistration(self):
        """Test task unregistration."""
        mock_task = MagicMock()
        request_id = "test-request-123"
        
        # Register then unregister
        self.task_manager.register_task(request_id, mock_task, "model", "session")
        self.task_manager.unregister_task(request_id)
        
        # Should be removed from active tasks
        self.assertNotIn(request_id, self.task_manager.active_tasks)
        
        stats = self.task_manager.get_stats()
        self.assertEqual(stats["active_tasks"], 0)
        self.assertEqual(stats["total_registered"], 1)
    
    def test_task_cancellation(self):
        """Test task cancellation."""
        mock_task = MagicMock()
        mock_task.cancel.return_value = True
        mock_task.cancelled.return_value = False
        
        request_id = "test-request-123"
        model = "test-model"
        session_id = "test-session"
        
        # Register task
        self.task_manager.register_task(request_id, mock_task, model, session_id)
        
        # Cancel task
        result = self.task_manager.cancel_task(request_id, "test cancellation")
        
        self.assertTrue(result["success"])
        self.assertEqual(result["model"], model)
        self.assertEqual(result["session_id"], session_id)
        self.assertIn("cancelled_at", result)
        
        # Task should be cancelled
        mock_task.cancel.assert_called_once()
        
        stats = self.task_manager.get_stats()
        self.assertEqual(stats["total_cancelled"], 1)
    
    def test_cancel_nonexistent_task(self):
        """Test cancelling non-existent task."""
        result = self.task_manager.cancel_task("nonexistent-id", "test")
        
        self.assertFalse(result["success"])
        self.assertIn("not found", result["reason"])
    
    def test_cancel_already_completed_task(self):
        """Test cancelling already completed/cancelled task."""
        mock_task = MagicMock()
        mock_task.cancelled.return_value = True  # Already cancelled
        mock_task.cancel.return_value = False
        
        request_id = "test-request-123"
        
        self.task_manager.register_task(request_id, mock_task, "model", "session")
        
        result = self.task_manager.cancel_task(request_id, "test")
        
        self.assertFalse(result["success"])
        self.assertIn("already", result["reason"])
    
    def test_concurrent_task_operations(self):
        """Test thread-safe task operations."""
        results = []
        errors = []
        
        def register_tasks(thread_id):
            """Register tasks from multiple threads."""
            try:
                for i in range(10):
                    mock_task = MagicMock()
                    request_id = f"thread-{thread_id}-task-{i}"
                    self.task_manager.register_task(request_id, mock_task, "model", "session")
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, e))
        
        # Create multiple threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=register_tasks, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify no errors and correct counts
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), 3)
        
        stats = self.task_manager.get_stats()
        self.assertEqual(stats["active_tasks"], 30)  # 3 threads * 10 tasks
        self.assertEqual(stats["total_registered"], 30)


class TestAsyncOllamaIntegration(unittest.IsolatedAsyncioTestCase):
    """Test AsyncOllamaClient integration with circuit breaker."""
    
    def setUp(self):
        """Set up async test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create client with test configuration
        with patch.dict(os.environ, {
            'OLLAMA_HOST': 'http://localhost:11434',
            'GEN_TIMEOUT_S': '5',
            'GEN_MAX_RETRIES': '1',
            'GEN_CONCURRENCY': '2'
        }):
            self.client = AsyncOllamaClient()
    
    async def asyncTearDown(self):
        """Clean up async resources."""
        if hasattr(self, 'client'):
            await self.client.close()
    
    @patch('httpx.AsyncClient.post')
    async def test_successful_generation(self, mock_post):
        """Test successful generation request."""
        # Mock successful Ollama response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "Generated text response"}
        mock_post.return_value = mock_response
        
        # Mock circuit breaker to allow execution
        with patch('tinyrpc.generation_circuit_breaker') as mock_cb:
            mock_cb.can_execute.return_value = (True, "closed", {"state": "closed"})
            
            result = await self.client.generate_async(
                model="test-model",
                prompt="Test prompt",
                request_id="test-req-123",
                session_id="test-session"
            )
        
        text, latency_ms = result
        self.assertEqual(text, "Generated text response")
        self.assertIsInstance(latency_ms, int)
        self.assertGreater(latency_ms, 0)
        
        # Verify circuit breaker interactions
        mock_cb.can_execute.assert_called_once_with("test-model")
        mock_cb.record_success.assert_called_once_with("test-model", "test-session")
    
    @patch('httpx.AsyncClient.post')
    async def test_circuit_breaker_blocks_request(self, mock_post):
        """Test circuit breaker blocking requests."""
        # Mock circuit breaker in open state
        with patch('tinyrpc.generation_circuit_breaker') as mock_cb:
            mock_cb.can_execute.return_value = (
                False, 
                "open", 
                {"state": "open", "cooldown_remaining": 15}
            )
            
            # Should raise HTTPException without making request
            with self.assertRaises(Exception) as context:
                await self.client.generate_async(
                    model="failing-model",
                    prompt="Test prompt",
                    session_id="test-session"
                )
            
            # Should not have made HTTP request
            mock_post.assert_not_called()
            
            # Verify circuit breaker was checked
            mock_cb.can_execute.assert_called_once_with("failing-model")
    
    @patch('httpx.AsyncClient.post')
    async def test_generation_failure_recorded(self, mock_post):
        """Test generation failures are recorded in circuit breaker."""
        # Mock timeout exception
        mock_post.side_effect = httpx.TimeoutException("Request timeout")
        
        with patch('tinyrpc.generation_circuit_breaker') as mock_cb:
            mock_cb.can_execute.return_value = (True, "closed", {"state": "closed"})
            
            with self.assertRaises(Exception):
                await self.client.generate_async(
                    model="test-model",
                    prompt="Test prompt",
                    session_id="test-session"
                )
            
            # Verify failure was recorded
            mock_cb.record_failure.assert_called_once_with(
                "test-model", "timeout", "test-session"
            )
    
    async def test_generation_cancellation(self):
        """Test generation task cancellation."""
        with patch('tinyrpc.generation_circuit_breaker') as mock_cb, \
             patch('tinyrpc.generation_task_manager') as mock_tm:
            
            mock_cb.can_execute.return_value = (True, "closed", {"state": "closed"})
            
            # Create a task that will be cancelled
            async def cancelled_generation():
                # This will be cancelled before making the request
                await asyncio.sleep(10)  # Long sleep
            
            # Simulate task cancellation
            task = asyncio.create_task(cancelled_generation())
            task.cancel()
            
            # Mock current_task to return cancelled task
            with patch('asyncio.current_task', return_value=task):
                with self.assertRaises(Exception) as context:
                    await self.client.generate_async(
                        model="test-model",
                        prompt="Test prompt",
                        session_id="test-session"
                    )
            
            # Verify task manager interactions
            mock_tm.register_task.assert_called_once()
            mock_tm.unregister_task.assert_called_once()
    
    @patch('httpx.AsyncClient.post')
    async def test_retry_mechanism(self, mock_post):
        """Test retry mechanism with backoff."""
        # Mock first request fails, second succeeds
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500
        
        mock_response_success = MagicMock()
        mock_response_success.status_code = 200
        mock_response_success.json.return_value = {"response": "Success after retry"}
        
        mock_post.side_effect = [
            httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_response_fail),
            mock_response_success
        ]
        
        with patch('tinyrpc.generation_circuit_breaker') as mock_cb:
            mock_cb.can_execute.return_value = (True, "closed", {"state": "closed"})
            
            result = await self.client.generate_async(
                model="test-model",
                prompt="Test prompt",
                session_id="test-session"
            )
        
        text, latency_ms = result
        self.assertEqual(text, "Success after retry")
        
        # Verify 2 requests were made (original + 1 retry)
        self.assertEqual(mock_post.call_count, 2)
        
        # Should record success after retry
        mock_cb.record_success.assert_called_once()


class TestHealthEndpointIntegration(unittest.IsolatedAsyncioTestCase):
    """Test health endpoint functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    @patch('tinyrpc.async_ollama_client')
    @patch('tinyrpc.router') 
    @patch('tinyrpc.generation_circuit_breaker')
    @patch('tinyrpc.generation_task_manager')
    async def test_healthy_status(self, mock_tm, mock_cb, mock_router, mock_client):
        """Test health endpoint with all components healthy."""
        # Mock healthy Ollama response
        mock_ollama_response = MagicMock()
        mock_ollama_response.status_code = 200
        mock_ollama_response.json.return_value = {
            "models": [
                {"name": "llama3.2:3b"}, 
                {"name": "codestral:7b"}
            ]
        }
        mock_client.client.get.return_value = mock_ollama_response
        mock_client.ollama_host = "http://localhost:11434"
        
        # Mock healthy router
        mock_router.router_available = True
        mock_router.route_request.return_value = {
            "route": "gen", 
            "confidence": 0.85
        }
        mock_router.router_path = Path("/path/to/router")
        
        # Mock healthy circuit breaker
        mock_cb.get_stats.return_value = {
            "model_states": {
                "llama3.2:3b": {"state": "closed"},
                "codestral:7b": {"state": "closed"}
            },
            "failure_threshold": 5,
            "fail_window_seconds": 120,
            "cooldown_seconds": 30
        }
        
        # Mock task manager
        mock_tm.get_stats.return_value = {
            "active_tasks": 2,
            "total_registered": 10,
            "total_cancelled": 1
        }
        
        # Import and call health endpoint
        from tinyrpc import health_check
        
        result = await health_check()
        
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["service"], "tinyintent-bridge")
        self.assertIn("components", result)
        
        # Verify component statuses
        components = result["components"]
        self.assertEqual(components["bridge"]["status"], "healthy")
        self.assertEqual(components["ollama"]["status"], "healthy")
        self.assertEqual(components["router"]["status"], "healthy")
        self.assertEqual(components["circuit_breaker"]["status"], "healthy")
        self.assertEqual(components["task_manager"]["status"], "healthy")
    
    @patch('tinyrpc.async_ollama_client')
    async def test_unhealthy_ollama(self, mock_client):
        """Test health endpoint with unhealthy Ollama."""
        # Mock Ollama connection failure
        mock_client.client.get.side_effect = httpx.ConnectError("Connection refused")
        mock_client.ollama_host = "http://localhost:11434"
        
        from tinyrpc import health_check
        
        with self.assertRaises(Exception) as context:
            await health_check()
        
        # Should return 503 status
        self.assertEqual(context.exception.status_code, 503)
        
        # Check error details
        error_detail = context.exception.detail
        self.assertEqual(error_detail["status"], "unhealthy")
        self.assertEqual(error_detail["components"]["ollama"]["status"], "unhealthy")


class TestRouterMetricsIntegration(unittest.TestCase):
    """Test circuit breaker integration with router metrics."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Clear router metrics for clean test
        router_metrics.metrics_buffer.clear()
        router_metrics.error_buffer.clear()
    
    def test_circuit_breaker_event_recording(self):
        """Test circuit breaker events are recorded in router metrics."""
        # Record circuit breaker events
        router_metrics.record_circuit_breaker_event(
            model="test-model",
            event_type="failure",
            state="closed",
            session_id="test-session",
            additional_info={"error_type": "timeout", "failure_count": 1}
        )
        
        router_metrics.record_circuit_breaker_event(
            model="test-model",
            event_type="state_change",
            state="open",
            session_id="test-session",
            additional_info={"old_state": "closed", "failure_count": 3}
        )
        
        # Verify events are in error buffer
        error_entries = list(router_metrics.error_buffer)
        self.assertEqual(len(error_entries), 2)
        
        failure_event = error_entries[0]
        self.assertEqual(failure_event["event_type"], "circuit_breaker_failure")
        self.assertEqual(failure_event["model"], "test-model")
        self.assertEqual(failure_event["state"], "closed")
        self.assertEqual(failure_event["session_id"], "test-session")
        self.assertEqual(failure_event["additional_info"]["error_type"], "timeout")
        
        state_change_event = error_entries[1]
        self.assertEqual(state_change_event["event_type"], "circuit_breaker_state_change")
        self.assertEqual(state_change_event["state"], "open")
        self.assertEqual(state_change_event["additional_info"]["old_state"], "closed")
    
    def test_circuit_breaker_metrics_integration(self):
        """Test circuit breaker generates metrics during operation."""
        with patch.dict(os.environ, {
            'GEN_CB_THRESHOLD': '2',
            'GEN_CB_FAIL_WINDOW': '60'
        }):
            cb = GenerationCircuitBreaker()
        
        model = "test-model"
        session_id = "test-session"
        
        # Clear previous events
        router_metrics.error_buffer.clear()
        
        # Record failure that should trigger metrics
        cb.record_failure(model, "timeout", session_id)
        
        # Verify failure event was recorded
        error_entries = list(router_metrics.error_buffer)
        failure_events = [e for e in error_entries if e["event_type"] == "circuit_breaker_failure"]
        self.assertGreater(len(failure_events), 0)
        
        failure_event = failure_events[0]
        self.assertEqual(failure_event["model"], model)
        self.assertEqual(failure_event["session_id"], session_id)
        self.assertEqual(failure_event["additional_info"]["error_type"], "timeout")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)