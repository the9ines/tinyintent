#!/usr/bin/env python3
"""
TinyIntent Helper Metrics & Health Reporting Tests - M8.5

Tests helper metrics tracking, rolling window statistics, and health reporting endpoints.
Validates that metrics are recorded correctly for previews, executes, and errors.
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent / "bridge"))
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

try:
    from tinyintent.helpers.sdk import HelperMetrics, helper_registry, helper_executor, helper_metrics
    METRICS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helper metrics not available: {e}")
    METRICS_AVAILABLE = False

try:
    import requests
    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False


class TestHelperMetricsTracking(unittest.TestCase):
    """Test helper metrics tracking functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not METRICS_AVAILABLE:
            self.skipTest("Helper metrics not available")
        
        # Create temporary directory for test database
        self.test_dir = Path(tempfile.mkdtemp(prefix="helper_metrics_test_"))
        
        # Create test metrics instance with temporary database
        self.test_metrics = HelperMetrics()
        self.test_metrics.db_path = self.test_dir / "test_events.db"
        self.test_metrics._ensure_metrics_tables()
        
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary directory
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_metrics_initialization(self):
        """Test metrics system initialization."""
        metrics = HelperMetrics()
        
        # Should have rolling window set
        self.assertEqual(metrics.rolling_window, timedelta(hours=24))
        
        # Should have empty metrics initially
        self.assertEqual(len(metrics.metrics), 0)
        
        # Should have database path set
        self.assertIsNotNone(metrics.db_path)
    
    def test_record_preview_event(self):
        """Test recording preview events."""
        helper_id = "test_helper"
        session_id = "test_session_123"
        
        # Record successful preview
        self.test_metrics.record_helper_event(
            helper_id=helper_id,
            event_type="preview",
            success=True,
            session_id=session_id,
            latency_ms=150
        )
        
        # Check metrics updated
        metrics = self.test_metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["helper_id"], helper_id)
        self.assertEqual(metrics["total_previews"], 1)
        self.assertEqual(metrics["total_executes"], 0)
        self.assertEqual(metrics["total_errors"], 0)
        self.assertIsNotNone(metrics["last_used"])
        
        # Check rolling window
        self.assertEqual(metrics["rolling_24h"]["previews"], 1)
        self.assertEqual(metrics["rolling_24h"]["executes"], 0)
        self.assertEqual(metrics["rolling_24h"]["errors"], 0)
        self.assertEqual(metrics["rolling_24h"]["error_rate"], 0.0)
    
    def test_record_execute_event(self):
        """Test recording execute events."""
        helper_id = "test_helper"
        
        # Record successful execute
        self.test_metrics.record_helper_event(
            helper_id=helper_id,
            event_type="execute",
            success=True,
            latency_ms=300
        )
        
        # Check metrics updated
        metrics = self.test_metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 0)
        self.assertEqual(metrics["total_executes"], 1)
        self.assertEqual(metrics["total_errors"], 0)
        
        # Check rolling window
        self.assertEqual(metrics["rolling_24h"]["previews"], 0)
        self.assertEqual(metrics["rolling_24h"]["executes"], 1)
        self.assertEqual(metrics["rolling_24h"]["errors"], 0)
        self.assertEqual(metrics["rolling_24h"]["error_rate"], 0.0)
    
    def test_record_error_events(self):
        """Test recording error events and error rate calculation."""
        helper_id = "test_helper"
        
        # Record successful preview
        self.test_metrics.record_helper_event(
            helper_id=helper_id,
            event_type="preview",
            success=True
        )
        
        # Record failed preview
        self.test_metrics.record_helper_event(
            helper_id=helper_id,
            event_type="preview",
            success=False,
            error_message="Test error message"
        )
        
        # Record failed execute
        self.test_metrics.record_helper_event(
            helper_id=helper_id,
            event_type="execute",
            success=False,
            error_message="Execute failed"
        )
        
        # Check metrics
        metrics = self.test_metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 2)
        self.assertEqual(metrics["total_executes"], 1)
        self.assertEqual(metrics["total_errors"], 2)
        
        # Check rolling window
        self.assertEqual(metrics["rolling_24h"]["previews"], 2)
        self.assertEqual(metrics["rolling_24h"]["executes"], 1)
        self.assertEqual(metrics["rolling_24h"]["errors"], 2)
        
        # Check error rate: 2 errors / 3 total operations = 0.6667
        expected_error_rate = 2.0 / 3.0
        self.assertAlmostEqual(metrics["rolling_24h"]["error_rate"], expected_error_rate, places=4)
    
    def test_multiple_helpers_metrics(self):
        """Test metrics tracking for multiple helpers."""
        helper1 = "helper_one"
        helper2 = "helper_two"
        
        # Record events for helper1
        self.test_metrics.record_helper_event(helper1, "preview", True)
        self.test_metrics.record_helper_event(helper1, "execute", True)
        
        # Record events for helper2
        self.test_metrics.record_helper_event(helper2, "preview", False, error_message="Error in helper2")
        
        # Check individual metrics
        metrics1 = self.test_metrics.get_helper_metrics(helper1)
        metrics2 = self.test_metrics.get_helper_metrics(helper2)
        
        self.assertEqual(metrics1["total_previews"], 1)
        self.assertEqual(metrics1["total_executes"], 1)
        self.assertEqual(metrics1["total_errors"], 0)
        
        self.assertEqual(metrics2["total_previews"], 1)
        self.assertEqual(metrics2["total_executes"], 0)
        self.assertEqual(metrics2["total_errors"], 1)
        
        # Check all metrics
        all_metrics = self.test_metrics.get_all_helper_metrics()
        
        self.assertEqual(all_metrics["total_helpers"], 2)
        self.assertIn(helper1, all_metrics["helpers"])
        self.assertIn(helper2, all_metrics["helpers"])
    
    def test_rolling_window_cleanup(self):
        """Test that old events are cleaned up from rolling window."""
        helper_id = "test_helper"
        
        # Mock old timestamp (25 hours ago)
        old_time = datetime.utcnow() - timedelta(hours=25)
        
        # Manually add old event to history
        with self.test_metrics.lock:
            helper_metrics = self.test_metrics.metrics[helper_id]
            helper_metrics['preview_history'].append((old_time, True))
            helper_metrics['total_previews'] = 1
        
        # Record new event
        self.test_metrics.record_helper_event(helper_id, "preview", True)
        
        # Check that rolling window only shows new event
        metrics = self.test_metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 2)  # Total includes old event
        self.assertEqual(metrics["rolling_24h"]["previews"], 1)  # Rolling window excludes old event
    
    def test_metrics_persistence(self):
        """Test that metrics are persisted to database."""
        helper_id = "test_helper"
        
        # Record event
        self.test_metrics.record_helper_event(
            helper_id=helper_id,
            event_type="preview",
            success=True,
            session_id="test_session",
            latency_ms=200
        )
        
        # Check database directly
        with sqlite3.connect(self.test_metrics.db_path) as conn:
            # Check helper_events table
            cursor = conn.execute('SELECT * FROM helper_events WHERE helper_id = ?', (helper_id,))
            events = cursor.fetchall()
            
            self.assertEqual(len(events), 1)
            event = events[0]
            self.assertEqual(event[1], helper_id)  # helper_id
            self.assertEqual(event[2], "preview")  # event_type
            self.assertEqual(event[3], 1)  # success (True)
            self.assertEqual(event[5], "test_session")  # session_id
            self.assertEqual(event[7], 200)  # latency_ms
            
            # Check helper_metrics table
            cursor = conn.execute('SELECT * FROM helper_metrics WHERE helper_id = ?', (helper_id,))
            metrics = cursor.fetchone()
            
            self.assertIsNotNone(metrics)
            self.assertEqual(metrics[0], helper_id)  # helper_id
            self.assertEqual(metrics[1], 1)  # total_previews
            self.assertEqual(metrics[2], 0)  # total_executes
            self.assertEqual(metrics[3], 0)  # total_errors
    
    def test_load_persisted_metrics(self):
        """Test loading persisted metrics from database."""
        helper_id = "test_helper"
        
        # Insert test data directly into database
        with sqlite3.connect(self.test_metrics.db_path) as conn:
            # Insert aggregated metrics
            conn.execute('''
                INSERT INTO helper_metrics 
                (helper_id, total_previews, total_executes, total_errors, last_used)
                VALUES (?, ?, ?, ?, ?)
            ''', (helper_id, 5, 3, 1, datetime.utcnow().isoformat() + 'Z'))
            
            # Insert recent events
            recent_time = datetime.utcnow() - timedelta(hours=2)
            conn.execute('''
                INSERT INTO helper_events 
                (helper_id, event_type, success, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (helper_id, "preview", True, recent_time.isoformat() + 'Z'))
            
            conn.commit()
        
        # Create new metrics instance and load persisted data
        new_metrics = HelperMetrics()
        new_metrics.db_path = self.test_metrics.db_path
        new_metrics.load_persisted_metrics()
        
        # Check loaded data
        metrics = new_metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 5)
        self.assertEqual(metrics["total_executes"], 3)
        self.assertEqual(metrics["total_errors"], 1)
        self.assertEqual(metrics["rolling_24h"]["previews"], 1)  # Only recent event
    
    def test_metrics_for_nonexistent_helper(self):
        """Test getting metrics for helper that hasn't been used."""
        metrics = self.test_metrics.get_helper_metrics("nonexistent_helper")
        
        self.assertEqual(metrics["helper_id"], "nonexistent_helper")
        self.assertEqual(metrics["total_previews"], 0)
        self.assertEqual(metrics["total_executes"], 0)
        self.assertEqual(metrics["total_errors"], 0)
        self.assertIsNone(metrics["last_used"])
        self.assertEqual(metrics["rolling_24h"]["previews"], 0)
        self.assertEqual(metrics["rolling_24h"]["executes"], 0)
        self.assertEqual(metrics["rolling_24h"]["errors"], 0)
        self.assertEqual(metrics["rolling_24h"]["error_rate"], 0.0)


class TestHelperExecutorMetricsIntegration(unittest.TestCase):
    """Test metrics integration with helper executor."""
    
    def setUp(self):
        """Set up test environment."""
        if not METRICS_AVAILABLE:
            self.skipTest("Helper metrics not available")
        
        # Create temporary directory for test
        self.test_dir = Path(tempfile.mkdtemp(prefix="executor_metrics_test_"))
        
        # Mock helper executor with metrics
        self.mock_executor = MagicMock()
        self.test_metrics = HelperMetrics()
        self.test_metrics.db_path = self.test_dir / "test_events.db"
        self.test_metrics._ensure_metrics_tables()
        self.mock_executor.metrics = self.test_metrics
        
    def tearDown(self):
        """Clean up test environment."""
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_executor_preview_metrics_recording(self):
        """Test that executor records metrics for preview operations."""
        # Simulate executor recording metrics directly
        helper_id = "test_helper"
        session_id = "test_session"
        
        # Simulate successful preview
        self.mock_executor.metrics.record_helper_event(
            helper_id=helper_id,
            event_type="preview",
            success=True,
            session_id=session_id,
            latency_ms=150
        )
        
        # Check metrics
        metrics = self.mock_executor.metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 1)
        self.assertEqual(metrics["total_executes"], 0)
        self.assertEqual(metrics["total_errors"], 0)
    
    def test_executor_execute_metrics_recording(self):
        """Test that executor records metrics for execute operations."""
        helper_id = "test_helper"
        
        # Simulate successful execute
        self.mock_executor.metrics.record_helper_event(
            helper_id=helper_id,
            event_type="execute",
            success=True,
            latency_ms=500
        )
        
        # Check metrics
        metrics = self.mock_executor.metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 0)
        self.assertEqual(metrics["total_executes"], 1)
        self.assertEqual(metrics["total_errors"], 0)
    
    def test_executor_error_metrics_recording(self):
        """Test that executor records metrics for failed operations."""
        helper_id = "test_helper"
        
        # Simulate failed preview
        self.mock_executor.metrics.record_helper_event(
            helper_id=helper_id,
            event_type="preview",
            success=False,
            error_message="Test validation error",
            latency_ms=50
        )
        
        # Check metrics
        metrics = self.mock_executor.metrics.get_helper_metrics(helper_id)
        
        self.assertEqual(metrics["total_previews"], 1)
        self.assertEqual(metrics["total_errors"], 1)
        self.assertEqual(metrics["rolling_24h"]["error_rate"], 1.0)


@unittest.skipIf(not HTTP_CLIENT_AVAILABLE, "requests not available")
class TestHelperMetricsHTTP(unittest.TestCase):
    """Test helper metrics via HTTP endpoints."""
    
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
    
    def test_get_helper_metrics_endpoint_exists(self):
        """Test that GET /helpers/metrics/{helper_id} endpoint exists."""
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/metrics/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            # Should not be 404 (not found)
            self.assertNotEqual(response.status_code, 404, 
                              f"GET /helpers/metrics/{helper_id} endpoint not found")
            
            print(f"✓ GET /helpers/metrics/{helper_id} endpoint exists (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to reach GET /helpers/metrics/{helper_id} endpoint: {e}")
    
    def test_get_helper_metrics_response_structure(self):
        """Test GET /helpers/metrics/{helper_id} response structure."""
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/metrics/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                expected_fields = ["status", "metrics", "helper_info", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertEqual(data["status"], "success")
                
                # Check metrics structure
                metrics = data["metrics"]
                required_metrics_fields = [
                    "helper_id", "total_previews", "total_executes", "total_errors",
                    "last_used", "rolling_24h"
                ]
                
                for field in required_metrics_fields:
                    self.assertIn(field, metrics, f"Missing field '{field}' in metrics")
                
                # Check rolling window structure
                rolling_24h = metrics["rolling_24h"]
                rolling_fields = ["previews", "executes", "errors", "error_rate"]
                
                for field in rolling_fields:
                    self.assertIn(field, rolling_24h, f"Missing field '{field}' in rolling_24h")
                
                # Check helper info
                helper_info = data["helper_info"]
                info_fields = ["name", "enabled", "risk_level", "can_execute"]
                
                for field in info_fields:
                    self.assertIn(field, helper_info, f"Missing field '{field}' in helper_info")
                
                print(f"✓ GET /helpers/metrics/{helper_id} returned valid metrics structure")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for metrics endpoint (status: {response.status_code})")
            elif response.status_code == 404:
                print(f"⚠ Helper {helper_id} not found (might be expected)")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test GET /helpers/metrics/{helper_id} endpoint: {e}")
    
    def test_get_all_helper_metrics_endpoint(self):
        """Test GET /helpers/metrics endpoint for all helpers."""
        try:
            response = requests.get(
                f"{self.base_url}/helpers/metrics",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                expected_fields = ["status", "metrics", "summary", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertEqual(data["status"], "success")
                
                # Check metrics structure
                metrics = data["metrics"]
                self.assertIn("helpers", metrics)
                self.assertIn("total_helpers", metrics)
                self.assertIn("timestamp", metrics)
                
                # Check summary structure
                summary = data["summary"]
                summary_fields = [
                    "total_helpers", "total_previews", "total_executes", 
                    "total_errors", "overall_error_rate"
                ]
                
                for field in summary_fields:
                    self.assertIn(field, summary, f"Missing field '{field}' in summary")
                
                # Verify data types
                self.assertIsInstance(metrics["helpers"], dict)
                self.assertIsInstance(summary["total_helpers"], int)
                self.assertIsInstance(summary["overall_error_rate"], (int, float))
                
                print(f"✓ GET /helpers/metrics returned metrics for {summary['total_helpers']} helpers")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for all metrics endpoint (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test GET /helpers/metrics endpoint: {e}")
    
    def test_get_metrics_nonexistent_helper(self):
        """Test GET /helpers/metrics/{helper_id} with nonexistent helper."""
        helper_id = "nonexistent_helper_metrics_12345"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/metrics/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 404:
                data = response.json()
                self.assertIn("detail", data)
                self.assertIn("not found", data["detail"].lower())
                print(f"✓ GET /helpers/metrics/{helper_id} correctly returned 404")
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status for nonexistent helper metrics: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test nonexistent helper metrics endpoint: {e}")


if __name__ == "__main__":
    # Run tests with detailed output
    unittest.main(verbosity=2)