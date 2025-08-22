#!/usr/bin/env python3
"""
TinyIntent Router Reliability Monitoring Tests - M7.2

Tests continuous health monitoring of router decisions, confidence distributions,
histogram calculations, abstain percentages, and database persistence.
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

# Add bridge to path
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

try:
    from tinyintent.bridge.router_client import RouterMetrics
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Bridge not available: {e}")
    BRIDGE_AVAILABLE = False


class TestRouterMetricsCollection(unittest.TestCase):
    """Test router metrics buffer and collection functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create test metrics collector with small buffer
        self.metrics = RouterMetrics(buffer_size=10)
    
    def test_record_routing_decision(self):
        """Test recording router decisions in buffer."""
        # Record a generation decision
        self.metrics.record_routing_decision(
            route="gen",
            intent="general_query", 
            confidence=0.85,
            latency_ms=150.5,
            outcome="preview",
            text_length=25,
            session_id="test-session-1"
        )
        
        # Check buffer has entry
        self.assertEqual(len(self.metrics.metrics_buffer), 1)
        
        entry = self.metrics.metrics_buffer[0]
        self.assertEqual(entry["route"], "gen")
        self.assertEqual(entry["intent"], "general_query")
        self.assertEqual(entry["confidence"], 0.85)
        self.assertEqual(entry["latency_ms"], 150.5)
        self.assertEqual(entry["outcome"], "preview")
        self.assertEqual(entry["text_length"], 25)
        self.assertEqual(entry["session_id"], "test-session-1")
        self.assertIsInstance(entry["timestamp"], float)
        self.assertIsNone(entry["abstain_reason"])
    
    def test_record_abstain_decision(self):
        """Test recording abstain decisions with reasons."""
        self.metrics.record_routing_decision(
            route="abstain",
            intent="unclear_intent",
            confidence=0.45,
            latency_ms=75.2,
            outcome="abstain", 
            text_length=15,
            session_id="test-session-2",
            abstain_reason="Confidence 0.45 below threshold 0.55"
        )
        
        entry = self.metrics.metrics_buffer[0]
        self.assertEqual(entry["route"], "abstain")
        self.assertEqual(entry["confidence"], 0.45)
        self.assertIsNotNone(entry["abstain_reason"])
        self.assertIn("threshold", entry["abstain_reason"])
    
    def test_record_error(self):
        """Test recording router errors."""
        self.metrics.record_error(
            error_type="router_execution_error",
            error_message="Swift runner failed with timeout",
            session_id="test-session-error"
        )
        
        # Check error buffer has entry
        self.assertEqual(len(self.metrics.error_buffer), 1)
        
        error = self.metrics.error_buffer[0]
        self.assertEqual(error["error_type"], "router_execution_error")
        self.assertEqual(error["error_message"], "Swift runner failed with timeout")
        self.assertEqual(error["session_id"], "test-session-error")
        self.assertIsInstance(error["timestamp"], float)
    
    def test_buffer_size_limit(self):
        """Test that buffer respects size limit."""
        # Fill buffer beyond limit
        for i in range(15):
            self.metrics.record_routing_decision(
                route="gen",
                intent=f"intent_{i}",
                confidence=0.7 + (i * 0.01),
                latency_ms=100.0,
                outcome="preview"
            )
        
        # Should only keep last 10 entries (buffer size)
        self.assertEqual(len(self.metrics.metrics_buffer), 10)
        
        # First entry should be intent_5 (entries 0-4 were evicted)
        first_entry = list(self.metrics.metrics_buffer)[0]
        self.assertEqual(first_entry["intent"], "intent_5")
        
        # Last entry should be intent_14
        last_entry = list(self.metrics.metrics_buffer)[-1]
        self.assertEqual(last_entry["intent"], "intent_14")
    
    def test_error_buffer_size_limit(self):
        """Test that error buffer respects size limit."""
        # Fill error buffer beyond default limit (50)
        for i in range(55):
            self.metrics.record_error(
                error_type="test_error",
                error_message=f"Error message {i}",
                session_id=f"session_{i}"
            )
        
        # Should only keep last 50 entries
        self.assertEqual(len(self.metrics.error_buffer), 50)
        
        # First error should be from i=5 (entries 0-4 were evicted)
        first_error = list(self.metrics.error_buffer)[0]
        self.assertEqual(first_error["error_message"], "Error message 5")


class TestRouterMetricsAnalysis(unittest.TestCase):
    """Test router metrics analysis and histogram generation."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.metrics = RouterMetrics(buffer_size=100)
        self._populate_test_data()
    
    def _populate_test_data(self):
        """Populate metrics with test data."""
        # Add variety of routing decisions
        test_data = [
            # High confidence generation
            {"route": "gen", "intent": "explanation", "confidence": 0.9, "outcome": "preview"},
            {"route": "gen", "intent": "general_query", "confidence": 0.85, "outcome": "preview"},
            {"route": "gen", "intent": "assistance", "confidence": 0.8, "outcome": "preview"},
            
            # High confidence actions
            {"route": "act", "intent": "bot_management", "confidence": 0.95, "outcome": "execute"},
            {"route": "act", "intent": "bot_management", "confidence": 0.88, "outcome": "preview"},
            
            # Abstain decisions
            {"route": "abstain", "intent": "unclear", "confidence": 0.45, "outcome": "abstain", "abstain_reason": "Low confidence"},
            {"route": "abstain", "intent": "unclear", "confidence": 0.35, "outcome": "abstain", "abstain_reason": "Very low confidence"},
            
            # Medium confidence
            {"route": "gen", "intent": "general_query", "confidence": 0.65, "outcome": "preview"},
            {"route": "act", "intent": "system_monitoring", "confidence": 0.7, "outcome": "preview"},
        ]
        
        for i, data in enumerate(test_data):
            self.metrics.record_routing_decision(
                route=data["route"],
                intent=data["intent"], 
                confidence=data["confidence"],
                latency_ms=100 + i * 10,  # Varying latencies
                outcome=data["outcome"],
                text_length=20 + i * 5,
                session_id=f"test-session-{i}",
                abstain_reason=data.get("abstain_reason")
            )
    
    def test_confidence_histogram(self):
        """Test confidence histogram generation."""
        summary = self.metrics.get_metrics_summary()
        
        histogram = summary["confidence_histogram"]
        self.assertIsInstance(histogram, dict)
        self.assertIn("bins", histogram)
        self.assertIn("counts", histogram)
        self.assertIn("total", histogram)
        self.assertIn("min", histogram)
        self.assertIn("max", histogram)
        
        # Check histogram structure
        bins = histogram["bins"]
        counts = histogram["counts"]
        
        self.assertEqual(len(bins), 10)  # 10 bins by default
        self.assertEqual(len(counts), 10)
        self.assertEqual(histogram["total"], 9)  # 9 test entries
        
        # Check bins have correct structure
        for bin_info in bins:
            self.assertIn("lower", bin_info)
            self.assertIn("upper", bin_info)
            self.assertIn("count", bin_info)
            self.assertIsInstance(bin_info["lower"], (int, float))
            self.assertIsInstance(bin_info["upper"], (int, float))
            self.assertIsInstance(bin_info["count"], int)
        
        # Check min/max values
        self.assertAlmostEqual(histogram["min"], 0.35, places=2)
        self.assertAlmostEqual(histogram["max"], 0.95, places=2)
    
    def test_route_distribution(self):
        """Test route distribution calculation."""
        summary = self.metrics.get_metrics_summary()
        
        route_dist = summary["route_distribution"]
        self.assertEqual(route_dist["gen"], 4)  # 4 generation requests
        self.assertEqual(route_dist["act"], 3)  # 3 action requests 
        self.assertEqual(route_dist["abstain"], 2)  # 2 abstain decisions
    
    def test_intent_distribution(self):
        """Test intent distribution calculation."""
        summary = self.metrics.get_metrics_summary()
        
        intent_dist = summary["intent_distribution"]
        self.assertEqual(intent_dist["bot_management"], 2)
        self.assertEqual(intent_dist["general_query"], 2)
        self.assertEqual(intent_dist["unclear"], 2)
        self.assertEqual(intent_dist["explanation"], 1)
        self.assertEqual(intent_dist["assistance"], 1)
        self.assertEqual(intent_dist["system_monitoring"], 1)
    
    def test_abstain_metrics(self):
        """Test abstain percentage calculation."""
        summary = self.metrics.get_metrics_summary()
        
        abstain_metrics = summary["abstain_metrics"]
        self.assertEqual(abstain_metrics["total_abstains"], 2)
        self.assertAlmostEqual(abstain_metrics["abstain_percentage"], 22.22, places=1)  # 2/9 * 100
        
        # Test recent abstain rate (should be same since all data is recent)
        self.assertAlmostEqual(abstain_metrics["recent_abstain_rate_1h"], 22.22, places=1)
    
    def test_latency_metrics(self):
        """Test latency statistics calculation.""" 
        summary = self.metrics.get_metrics_summary()
        
        latency_metrics = summary["latency_metrics"]
        self.assertIsInstance(latency_metrics["average_ms"], (int, float))
        self.assertIsInstance(latency_metrics["p95_ms"], (int, float))
        self.assertEqual(latency_metrics["sample_count"], 9)
        
        # Average should be around 140ms (100 + 4*10 average offset)
        self.assertGreater(latency_metrics["average_ms"], 120)
        self.assertLess(latency_metrics["average_ms"], 160)
    
    def test_outcome_distribution(self):
        """Test outcome distribution calculation."""
        summary = self.metrics.get_metrics_summary()
        
        outcome_dist = summary["outcome_distribution"]
        self.assertEqual(outcome_dist["preview"], 6)  # 6 preview outcomes
        self.assertEqual(outcome_dist["execute"], 1)  # 1 execute outcome
        self.assertEqual(outcome_dist["abstain"], 2)  # 2 abstain outcomes
    
    def test_empty_metrics_summary(self):
        """Test metrics summary when no data is available."""
        empty_metrics = RouterMetrics(buffer_size=10)
        summary = empty_metrics.get_metrics_summary()
        
        self.assertEqual(summary["summary"]["total_requests"], 0)
        self.assertEqual(summary["confidence_histogram"]["total"], 0)
        self.assertEqual(summary["route_distribution"], {})
        self.assertEqual(summary["intent_distribution"], {})
        self.assertEqual(summary["abstain_metrics"]["total_abstains"], 0)
        self.assertEqual(summary["abstain_metrics"]["abstain_percentage"], 0)


class TestHistogramGeneration(unittest.TestCase):
    """Test histogram generation edge cases and accuracy."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.metrics = RouterMetrics(buffer_size=50)
    
    def test_histogram_empty_values(self):
        """Test histogram with empty values list."""
        histogram = self.metrics._create_histogram([])
        
        self.assertEqual(histogram["bins"], [])
        self.assertEqual(histogram["counts"], [])
        self.assertEqual(histogram["total"], 0)
    
    def test_histogram_single_value(self):
        """Test histogram with single repeated value."""
        values = [0.75] * 10
        histogram = self.metrics._create_histogram(values)
        
        self.assertEqual(len(histogram["bins"]), 1)
        self.assertEqual(histogram["bins"][0]["count"], 10)
        self.assertEqual(histogram["total"], 10)
        self.assertAlmostEqual(histogram["bins"][0]["lower"], 0.75, places=2)
    
    def test_histogram_uniform_distribution(self):
        """Test histogram with uniform distribution."""
        # Values evenly distributed from 0.1 to 1.0
        values = [0.1 + i * 0.1 for i in range(10)]
        histogram = self.metrics._create_histogram(values, bins=5)
        
        self.assertEqual(len(histogram["bins"]), 5)
        self.assertEqual(histogram["total"], 10)
        
        # With uniform distribution, each bin should have 2 values
        for bin_info in histogram["bins"]:
            self.assertEqual(bin_info["count"], 2)
    
    def test_histogram_edge_values(self):
        """Test histogram with edge values (0.0 and 1.0)."""
        values = [0.0, 0.25, 0.5, 0.75, 1.0]
        histogram = self.metrics._create_histogram(values, bins=4)
        
        self.assertEqual(histogram["total"], 5)
        self.assertEqual(histogram["min"], 0.0)
        self.assertEqual(histogram["max"], 1.0)
        
        # Check that edge values are properly binned
        total_counts = sum(bin_info["count"] for bin_info in histogram["bins"])
        self.assertEqual(total_counts, 5)


class TestRouterMetricsIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for router metrics with HTTP endpoints."""
    
    def setUp(self):
        """Set up integration test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Mock FastAPI dependencies for testing
        self.mock_auth = True
    
    @patch('tinyrpc.verify_auth')
    async def test_router_metrics_endpoint(self, mock_auth):
        """Test GET /router/metrics endpoint."""
        mock_auth.return_value = True
        
        # Import router metrics endpoints
        from tinyrpc import get_router_metrics
        
        # Add some test data
        router_metrics.record_routing_decision(
            route="gen", intent="test", confidence=0.8, latency_ms=100, outcome="preview"
        )
        
        # Call endpoint
        result = await get_router_metrics(auth=True)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("router_metrics", result)
        self.assertIn("message", result)
        
        metrics = result["router_metrics"]
        self.assertIn("summary", metrics)
        self.assertIn("confidence_histogram", metrics)
        self.assertIn("route_distribution", metrics)
        self.assertIn("abstain_metrics", metrics)
    
    @patch('tinyrpc.verify_auth')
    async def test_router_metrics_debug_endpoint(self, mock_auth):
        """Test GET /router/metrics/debug endpoint."""
        mock_auth.return_value = True
        
        from tinyrpc import get_router_metrics_debug
        
        # Add test data
        router_metrics.record_routing_decision(
            route="act", intent="test_debug", confidence=0.9, latency_ms=150, outcome="execute"
        )
        
        # Call debug endpoint
        result = await get_router_metrics_debug(limit=10, auth=True)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("recent_entries", result)
        self.assertIn("count", result)
        
        entries = result["recent_entries"]
        self.assertGreater(len(entries), 0)
        
        # Check entry structure
        entry = entries[-1]  # Most recent entry
        self.assertIn("timestamp", entry)
        self.assertIn("timestamp_iso", entry)
        self.assertIn("route", entry)
        self.assertIn("intent", entry)
        self.assertIn("confidence", entry)
    
    @patch('tinyrpc.verify_auth')
    async def test_router_metrics_flush_endpoint(self, mock_auth):
        """Test POST /router/metrics/flush endpoint."""
        mock_auth.return_value = True
        
        from tinyrpc import flush_router_metrics as flush_endpoint
        
        # Add test data to buffer
        router_metrics.record_routing_decision(
            route="gen", intent="flush_test", confidence=0.75, latency_ms=200, outcome="preview"
        )
        
        # Mock the flush to database method
        with patch.object(router_metrics, 'flush_to_database') as mock_flush:
            mock_flush.return_value = {
                "status": "success",
                "flushed_count": 1,
                "message": "Test flush completed"
            }
            
            result = await flush_endpoint(auth=True)
            
            self.assertEqual(result["status"], "success")
            self.assertIn("flush_result", result)
            
            mock_flush.assert_called_once()


class TestDatabaseIntegration(unittest.TestCase):
    """Test database integration for router metrics persistence."""
    
    def setUp(self):
        """Set up database test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create temporary database for testing
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = Path(self.temp_dir) / "test_episodes.db"
    
    def tearDown(self):
        """Clean up test database."""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_flush_to_database(self):
        """Test flushing metrics buffer to database."""
        # Create test episode logger with temp database
        sys.path.append(str(Path(__file__).parent.parent / "bridge"))
        from episodes import EpisodeLogger
        
        test_logger = EpisodeLogger(data_dir=Path(self.temp_dir))
        
        # Create test metrics buffer
        test_buffer = [
            {
                "timestamp": time.time(),
                "session_id": "db-test-1",
                "route": "gen", 
                "intent": "test_intent",
                "confidence": 0.8,
                "latency_ms": 125.5,
                "outcome": "preview",
                "text_length": 30,
                "abstain_reason": None
            },
            {
                "timestamp": time.time() - 10,
                "session_id": "db-test-2", 
                "route": "abstain",
                "intent": "unclear",
                "confidence": 0.4,
                "latency_ms": 75.0,
                "outcome": "abstain",
                "text_length": 15,
                "abstain_reason": "Low confidence"
            }
        ]
        
        # Flush to database
        result = test_logger.flush_router_metrics(test_buffer)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["flushed_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        
        # Verify data was stored
        stats = test_logger.get_router_metrics_stats()
        self.assertEqual(stats["total_requests"], 2)
        self.assertEqual(stats["route_distribution"]["gen"], 1)
        self.assertEqual(stats["route_distribution"]["abstain"], 1)
        self.assertAlmostEqual(stats["avg_confidence"], 0.6, places=1)
    
    def test_router_metrics_stats(self):
        """Test router metrics statistics calculation."""
        sys.path.append(str(Path(__file__).parent.parent / "bridge"))
        from episodes import EpisodeLogger
        
        test_logger = EpisodeLogger(data_dir=Path(self.temp_dir))
        
        # Add varied test data
        test_data = []
        current_time = time.time()
        
        # Add some recent data (last hour)
        for i in range(5):
            test_data.append({
                "timestamp": current_time - (i * 300),  # Every 5 minutes
                "session_id": f"recent-{i}",
                "route": "gen" if i % 2 == 0 else "act",
                "intent": "test_intent",
                "confidence": 0.7 + (i * 0.05),
                "latency_ms": 100 + (i * 20),
                "outcome": "preview",
                "text_length": 25,
                "abstain_reason": None
            })
        
        # Add some older data (2 hours ago)
        for i in range(3):
            test_data.append({
                "timestamp": current_time - 7200 - (i * 300),
                "session_id": f"old-{i}",
                "route": "abstain",
                "intent": "unclear",
                "confidence": 0.3 + (i * 0.1),
                "latency_ms": 50,
                "outcome": "abstain", 
                "text_length": 10,
                "abstain_reason": "Low confidence"
            })
        
        # Flush all data
        flush_result = test_logger.flush_router_metrics(test_data)
        self.assertEqual(flush_result["flushed_count"], 8)
        
        # Get stats
        stats = test_logger.get_router_metrics_stats()
        
        self.assertEqual(stats["total_requests"], 8)
        self.assertEqual(stats["route_distribution"]["gen"], 3)
        self.assertEqual(stats["route_distribution"]["act"], 2)
        self.assertEqual(stats["route_distribution"]["abstain"], 3)
        
        # Check abstain rates
        self.assertAlmostEqual(stats["abstain_rate_percent"], 37.5, places=1)  # 3/8 * 100
        self.assertEqual(stats["recent_abstain_rate_1h_percent"], 0.0)  # No recent abstains
        
        # Check outcome distribution
        self.assertEqual(stats["outcome_distribution"]["preview"], 5)
        self.assertEqual(stats["outcome_distribution"]["abstain"], 3)


class TestConcurrentAccess(unittest.TestCase):
    """Test thread safety of router metrics collection."""
    
    def setUp(self):
        """Set up concurrent test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.metrics = RouterMetrics(buffer_size=1000)
    
    def test_concurrent_recording(self):
        """Test concurrent recording of router decisions."""
        results = []
        errors = []
        
        def record_metrics(thread_id):
            """Record metrics from a thread.""" 
            try:
                for i in range(50):
                    self.metrics.record_routing_decision(
                        route="gen",
                        intent=f"thread_{thread_id}_intent_{i}",
                        confidence=0.5 + (i * 0.01),
                        latency_ms=100 + i,
                        outcome="preview",
                        session_id=f"thread_{thread_id}_session_{i}"
                    )
                results.append(thread_id)
            except Exception as e:
                errors.append((thread_id, e))
        
        # Create and start threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=record_metrics, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(results), 5)
        
        # Verify metrics were recorded (should be 5 * 50 = 250 entries)
        self.assertEqual(len(self.metrics.metrics_buffer), 250)
    
    def test_concurrent_summary_generation(self):
        """Test concurrent access to metrics summary."""
        # Add some initial data
        for i in range(100):
            self.metrics.record_routing_decision(
                route="gen" if i % 2 == 0 else "act",
                intent=f"intent_{i}",
                confidence=0.6 + (i % 4) * 0.1,
                latency_ms=50 + i,
                outcome="preview"
            )
        
        summaries = []
        errors = []
        
        def get_summary(thread_id):
            """Get metrics summary from a thread."""
            try:
                for _ in range(10):
                    summary = self.metrics.get_metrics_summary()
                    summaries.append((thread_id, summary))
            except Exception as e:
                errors.append((thread_id, e))
        
        # Create and start threads
        threads = []
        for i in range(3):
            thread = threading.Thread(target=get_summary, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        self.assertEqual(len(summaries), 30)  # 3 threads * 10 summaries
        
        # Verify all summaries are consistent
        first_summary = summaries[0][1]
        for thread_id, summary in summaries:
            self.assertEqual(summary["summary"]["total_requests"], 100)
            self.assertEqual(len(summary["route_distribution"]), len(first_summary["route_distribution"]))


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)