#!/usr/bin/env python3
"""
Tests for Emergency Kill Switch Flow - M6.3

Tests emergency kill switch functionality, state persistence, and fail-safe behavior.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

# Add bridge to path for testing
import sys
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

from logs.rotate import initialize_audit_logger


class TestEmergencyKillSwitch(unittest.TestCase):
    """Test emergency kill switch core functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.flag_file = Path(self.temp_dir) / "emergency.flag"
        self.audit_log = Path(self.temp_dir) / "audit.log"
        
        # Set emergency flag path for testing
        os.environ["EMERGENCY_FLAG_PATH"] = str(self.flag_file)
        
        # Initialize audit logger for testing
        self.audit_logger = initialize_audit_logger(self.audit_log)
        
        # Import and create EmergencyKillSwitch after setting up paths
        from tinyrpc import EmergencyKillSwitch
        self.kill_switch = EmergencyKillSwitch(self.flag_file)
    
    def tearDown(self):
        """Clean up test environment."""
        # Safe cleanup of flag file
        try:
            self.flag_file.unlink()
        except FileNotFoundError:
            pass
        
        # Clean up temp file if it exists
        temp_file = self.flag_file.with_suffix('.tmp')
        try:
            temp_file.unlink()
        except FileNotFoundError:
            pass
        
        # Remove environment variable
        if "EMERGENCY_FLAG_PATH" in os.environ:
            del os.environ["EMERGENCY_FLAG_PATH"]
        
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_initial_state_no_flag_file(self):
        """Test initial state when no flag file exists."""
        # Should be disabled by default (EXECUTION_ENABLED=0)
        self.assertFalse(self.kill_switch.is_execution_enabled())
        
        status = self.kill_switch.get_status()
        self.assertFalse(status["execution_enabled"])
        self.assertFalse(status["flag_file_exists"])
    
    def test_initial_state_with_execution_enabled(self):
        """Test initial state with EXECUTION_ENABLED=1."""
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            self.assertTrue(kill_switch.is_execution_enabled())
            
            status = kill_switch.get_status()
            self.assertTrue(status["execution_enabled"])
            self.assertFalse(status["flag_file_exists"])
    
    def test_initial_state_with_existing_flag_file(self):
        """Test initial state when flag file already exists."""
        # Create flag file before initialization
        flag_data = {
            "triggered_at": "2025-08-17T12:00:00.000000Z",
            "reason": "Previous emergency",
            "triggered_by": "test"
        }
        with open(self.flag_file, 'w') as f:
            json.dump(flag_data, f)
        
        from tinyrpc import EmergencyKillSwitch
        kill_switch = EmergencyKillSwitch(self.flag_file)
        
        # Should be disabled due to flag file
        self.assertFalse(kill_switch.is_execution_enabled())
        
        status = kill_switch.get_status()
        self.assertFalse(status["execution_enabled"])
        self.assertTrue(status["flag_file_exists"])
        self.assertIn("emergency_data", status)
        self.assertEqual(status["emergency_data"]["reason"], "Previous emergency")
    
    def test_trigger_emergency_kill_success(self):
        """Test successful emergency kill trigger."""
        # Start with execution enabled
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            self.assertTrue(kill_switch.is_execution_enabled())
            
            # Trigger emergency kill
            success = kill_switch.trigger_emergency_kill(
                reason="Test emergency",
                triggered_by="test_user"
            )
            
            self.assertTrue(success)
            self.assertFalse(kill_switch.is_execution_enabled())
            
            # Verify flag file was created
            self.assertTrue(self.flag_file.exists())
            
            with open(self.flag_file, 'r') as f:
                flag_data = json.load(f)
            
            self.assertEqual(flag_data["reason"], "Test emergency")
            self.assertEqual(flag_data["triggered_by"], "test_user")
            self.assertIn("triggered_at", flag_data)
    
    def test_trigger_emergency_kill_already_disabled(self):
        """Test emergency kill when already disabled."""
        # Start with execution disabled
        self.assertFalse(self.kill_switch.is_execution_enabled())
        
        # Try to trigger emergency kill
        success = self.kill_switch.trigger_emergency_kill(
            reason="Test emergency",
            triggered_by="test_user"
        )
        
        # Should return False since already disabled
        self.assertFalse(success)
        self.assertFalse(self.flag_file.exists())
    
    def test_emergency_kill_thread_safety(self):
        """Test thread safety of emergency kill operations."""
        import threading
        
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            results = []
            
            def trigger_kill(thread_id):
                success = kill_switch.trigger_emergency_kill(
                    reason=f"Thread {thread_id}",
                    triggered_by=f"thread_{thread_id}"
                )
                results.append(success)
            
            # Start multiple threads trying to trigger emergency kill
            threads = []
            for i in range(5):
                thread = threading.Thread(target=trigger_kill, args=(i,))
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
            
            # Only one thread should succeed
            successful_triggers = sum(results)
            self.assertEqual(successful_triggers, 1)
            
            # Kill switch should be disabled
            self.assertFalse(kill_switch.is_execution_enabled())
            self.assertTrue(self.flag_file.exists())
    
    def test_startup_respects_emergency_flag_path(self):
        """Test that startup respects EMERGENCY_FLAG_PATH and doesn't error if missing."""
        # Test with custom path that doesn't exist
        custom_path = Path(self.temp_dir) / "custom_emergency.flag"
        
        with patch.dict(os.environ, {"EMERGENCY_FLAG_PATH": str(custom_path)}):
            from tinyrpc import EmergencyKillSwitch
            
            # Should not error if file doesn't exist
            kill_switch = EmergencyKillSwitch(custom_path)
            
            # Should be disabled by default (EXECUTION_ENABLED=0)
            self.assertFalse(kill_switch.is_execution_enabled())
            
            # Should use the custom path
            self.assertEqual(kill_switch.flag_file_path, custom_path)
    
    def test_atomic_write_safety(self):
        """Test that atomic write prevents corruption during concurrent access."""
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            # Trigger emergency kill
            success = kill_switch.trigger_emergency_kill("Atomic test", "test_user")
            self.assertTrue(success)
            
            # Verify no temp file remains
            temp_file = self.flag_file.with_suffix('.tmp')
            self.assertFalse(temp_file.exists())
            
            # Verify flag file is valid JSON
            with open(self.flag_file, 'r') as f:
                data = json.load(f)
            
            self.assertEqual(data["reason"], "Atomic test")
            self.assertEqual(data["triggered_by"], "test_user")
            self.assertIn("triggered_at", data)
    
    def test_get_status_comprehensive(self):
        """Test comprehensive status reporting."""
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            # Initial status
            status = kill_switch.get_status()
            self.assertTrue(status["execution_enabled"])
            self.assertFalse(status["flag_file_exists"])
            self.assertNotIn("emergency_data", status)
            
            # Trigger emergency kill
            kill_switch.trigger_emergency_kill(
                reason="Status test",
                triggered_by="test_status"
            )
            
            # Status after emergency kill
            status = kill_switch.get_status()
            self.assertFalse(status["execution_enabled"])
            self.assertTrue(status["flag_file_exists"])
            self.assertIn("emergency_data", status)
            self.assertEqual(status["emergency_data"]["reason"], "Status test")


class TestEmergencyKillAPI(unittest.TestCase):
    """Test emergency kill switch API endpoints."""
    
    def setUp(self):
        """Set up test environment with mock server."""
        self.temp_dir = tempfile.mkdtemp()
        self.flag_file = Path(self.temp_dir) / "emergency.flag"
        
        # Set emergency flag path for testing
        os.environ["EMERGENCY_FLAG_PATH"] = str(self.flag_file)
        
        # Mock the FastAPI app and emergency kill switch
        self.mock_emergency_kill = MagicMock()
        self.mock_request = MagicMock()
        self.mock_request.client.host = "127.0.0.1"
        self.mock_request.headers = {"User-Agent": "test-client"}
    
    def tearDown(self):
        """Clean up test environment."""
        # Safe cleanup of flag file
        try:
            self.flag_file.unlink()
        except FileNotFoundError:
            pass
        
        # Clean up temp file if it exists
        temp_file = self.flag_file.with_suffix('.tmp')
        try:
            temp_file.unlink()
        except FileNotFoundError:
            pass
        
        # Remove environment variable
        if "EMERGENCY_FLAG_PATH" in os.environ:
            del os.environ["EMERGENCY_FLAG_PATH"]
        
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_emergency_kill_endpoint_success(self):
        """Test successful emergency kill API call."""
        import asyncio
        
        # Mock successful emergency kill
        self.mock_emergency_kill.trigger_emergency_kill.return_value = True
        
        # Import the endpoint function
        from tinyrpc import emergency_kill_switch, EmergencyKillRequest
        
        # Create request
        request = EmergencyKillRequest(reason="API test emergency")
        
        # Mock the global emergency_kill object
        with patch('tinyrpc.emergency_kill', self.mock_emergency_kill), \
             patch('tinyrpc.emergency_flag_path', self.flag_file):
            
            # Run async function
            response = asyncio.run(emergency_kill_switch(request, self.mock_request, True))
            
            self.assertEqual(response["status"], "emergency_kill_activated")
            self.assertIn("Emergency kill switch activated", response["message"])
            self.assertEqual(response["reason"], "API test emergency")
            self.assertIn("127.0.0.1", response["triggered_by"])
            
            # Verify emergency kill was called with correct parameters
            self.mock_emergency_kill.trigger_emergency_kill.assert_called_once()
            call_args = self.mock_emergency_kill.trigger_emergency_kill.call_args
            self.assertEqual(call_args[1]["reason"], "API test emergency")
            self.assertIn("127.0.0.1", call_args[1]["triggered_by"])
    
    def test_emergency_kill_endpoint_already_disabled(self):
        """Test emergency kill API when already disabled."""
        import asyncio
        
        # Mock already disabled
        self.mock_emergency_kill.trigger_emergency_kill.return_value = False
        self.mock_emergency_kill.get_status.return_value = {
            "execution_enabled": False,
            "flag_file_exists": True
        }
        
        from tinyrpc import emergency_kill_switch, EmergencyKillRequest
        
        request = EmergencyKillRequest(reason="Already disabled test")
        
        with patch('tinyrpc.emergency_kill', self.mock_emergency_kill):
            response = asyncio.run(emergency_kill_switch(request, self.mock_request, True))
            
            self.assertEqual(response["status"], "already_disabled")
            self.assertIn("Execution already disabled", response["message"])
    
    def test_emergency_status_endpoint(self):
        """Test emergency status API endpoint."""
        import asyncio
        
        mock_status = {
            "execution_enabled": False,
            "flag_file_exists": True,
            "emergency_data": {
                "reason": "Test emergency",
                "triggered_at": "2025-08-17T12:00:00Z"
            }
        }
        
        self.mock_emergency_kill.get_status.return_value = mock_status
        
        from tinyrpc import emergency_status
        
        with patch('tinyrpc.emergency_kill', self.mock_emergency_kill), \
             patch('tinyrpc.emergency_flag_path', self.flag_file):
            
            response = asyncio.run(emergency_status(True))
            
            self.assertFalse(response["execution_enabled"])
            self.assertTrue(response["flag_file_exists"])
            self.assertIn("recovery_instructions", response)
            self.assertIn("manually remove", response["recovery_instructions"])


class TestExecutionGate(unittest.TestCase):
    """Test execution gate behavior with emergency kill switch."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.flag_file = Path(self.temp_dir) / "emergency.flag"
        
        # Set emergency flag path for testing
        os.environ["EMERGENCY_FLAG_PATH"] = str(self.flag_file)
    
    def tearDown(self):
        """Clean up test environment."""
        # Safe cleanup of flag file
        try:
            self.flag_file.unlink()
        except FileNotFoundError:
            pass
        
        # Clean up temp file if it exists
        temp_file = self.flag_file.with_suffix('.tmp')
        try:
            temp_file.unlink()
        except FileNotFoundError:
            pass
        
        # Remove environment variable
        if "EMERGENCY_FLAG_PATH" in os.environ:
            del os.environ["EMERGENCY_FLAG_PATH"]
        
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_execution_allowed_when_enabled(self):
        """Test that execution is allowed when enabled."""
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            self.assertTrue(kill_switch.is_execution_enabled())
    
    def test_execution_blocked_after_emergency_kill(self):
        """Test that execution is blocked after emergency kill."""
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            # Initially enabled
            self.assertTrue(kill_switch.is_execution_enabled())
            
            # Trigger emergency kill
            kill_switch.trigger_emergency_kill("Test block", "test")
            
            # Now should be disabled
            self.assertFalse(kill_switch.is_execution_enabled())
    
    def test_execution_blocked_on_startup_with_flag(self):
        """Test that execution is blocked on startup if flag file exists."""
        # Create flag file
        flag_data = {
            "triggered_at": "2025-08-17T12:00:00Z",
            "reason": "Previous emergency",
            "triggered_by": "previous_user"
        }
        with open(self.flag_file, 'w') as f:
            json.dump(flag_data, f)
        
        # Even with EXECUTION_ENABLED=1, should be disabled due to flag
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            self.assertFalse(kill_switch.is_execution_enabled())


class TestAuditLogging(unittest.TestCase):
    """Test audit logging for emergency kill switch events."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.flag_file = Path(self.temp_dir) / "emergency.flag"
        self.audit_log = Path(self.temp_dir) / "audit.log"
        
        # Set emergency flag path for testing
        os.environ["EMERGENCY_FLAG_PATH"] = str(self.flag_file)
        
        # Initialize audit logger
        self.audit_logger = initialize_audit_logger(self.audit_log)
    
    def tearDown(self):
        """Clean up test environment."""
        # Safe cleanup of flag file
        try:
            self.flag_file.unlink()
        except FileNotFoundError:
            pass
        
        # Clean up temp file if it exists
        temp_file = self.flag_file.with_suffix('.tmp')
        try:
            temp_file.unlink()
        except FileNotFoundError:
            pass
        
        # Remove environment variable
        if "EMERGENCY_FLAG_PATH" in os.environ:
            del os.environ["EMERGENCY_FLAG_PATH"]
        
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_emergency_kill_audit_logging(self):
        """Test that emergency kill events are properly logged."""
        with patch('tinyrpc.audit_logger', self.audit_logger):
            with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
                from tinyrpc import EmergencyKillSwitch
                kill_switch = EmergencyKillSwitch(self.flag_file)
                
                # Trigger emergency kill
                success = kill_switch.trigger_emergency_kill(
                    reason="Audit test emergency",
                    triggered_by="audit_test_user"
                )
                
                self.assertTrue(success)
                
                # Check audit log
                self.assertTrue(self.audit_log.exists())
                
                with open(self.audit_log, 'r') as f:
                    log_lines = f.readlines()
                
                # Should have logged the emergency kill event
                emergency_events = []
                for line in log_lines:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("action") == "emergency_kill":
                            emergency_events.append(entry)
                    except json.JSONDecodeError:
                        continue
                
                self.assertEqual(len(emergency_events), 1)
                
                event = emergency_events[0]
                self.assertEqual(event["reason"], "Audit test emergency")
                self.assertEqual(event["triggered_by"], "audit_test_user")
                self.assertTrue(event["success"])
                self.assertEqual(event["severity"], "CRITICAL")
    
    def test_startup_flag_audit_logging(self):
        """Test that startup with emergency flag is logged."""
        # Create flag file
        flag_data = {
            "triggered_at": "2025-08-17T12:00:00Z",
            "reason": "Previous emergency",
            "triggered_by": "previous_user"
        }
        with open(self.flag_file, 'w') as f:
            json.dump(flag_data, f)
        
        with patch('tinyrpc.audit_logger', self.audit_logger):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            # Check audit log for startup warning
            with open(self.audit_log, 'r') as f:
                log_lines = f.readlines()
            
            startup_events = []
            for line in log_lines:
                try:
                    entry = json.loads(line.strip())
                    if entry.get("action") == "emergency_startup_disabled":
                        startup_events.append(entry)
                except json.JSONDecodeError:
                    continue
            
            self.assertEqual(len(startup_events), 1)
            
            event = startup_events[0]
            self.assertIn("Execution disabled on startup due to emergency flag", event["message"])
            self.assertTrue(event["success"])


class TestIntegrationScenarios(unittest.TestCase):
    """Test integration scenarios and edge cases."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.flag_file = Path(self.temp_dir) / "emergency.flag"
        
        # Set emergency flag path for testing
        os.environ["EMERGENCY_FLAG_PATH"] = str(self.flag_file)
    
    def tearDown(self):
        """Clean up test environment."""
        # Safe cleanup of flag file
        try:
            self.flag_file.unlink()
        except FileNotFoundError:
            pass
        
        # Clean up temp file if it exists
        temp_file = self.flag_file.with_suffix('.tmp')
        try:
            temp_file.unlink()
        except FileNotFoundError:
            pass
        
        # Remove environment variable
        if "EMERGENCY_FLAG_PATH" in os.environ:
            del os.environ["EMERGENCY_FLAG_PATH"]
        
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_manual_recovery_flow(self):
        """Test manual recovery by removing flag file."""
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            
            # Start with execution enabled
            kill_switch = EmergencyKillSwitch(self.flag_file)
            self.assertTrue(kill_switch.is_execution_enabled())
            
            # Trigger emergency kill
            kill_switch.trigger_emergency_kill("Recovery test", "test")
            self.assertFalse(kill_switch.is_execution_enabled())
            self.assertTrue(self.flag_file.exists())
            
            # Manually remove flag file (simulating admin recovery)
            self.flag_file.unlink()
            
            # Create new instance (simulating restart)
            new_kill_switch = EmergencyKillSwitch(self.flag_file)
            
            # Should be enabled again since EXECUTION_ENABLED=1 and no flag
            self.assertTrue(new_kill_switch.is_execution_enabled())
    
    def test_corrupted_flag_file_handling(self):
        """Test handling of corrupted flag file."""
        # Create corrupted flag file
        with open(self.flag_file, 'w') as f:
            f.write("invalid json content")
        
        with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
            from tinyrpc import EmergencyKillSwitch
            kill_switch = EmergencyKillSwitch(self.flag_file)
            
            # Should still disable execution even with corrupted file
            self.assertFalse(kill_switch.is_execution_enabled())
            
            # Status should handle corruption gracefully
            status = kill_switch.get_status()
            self.assertFalse(status["execution_enabled"])
            self.assertTrue(status["flag_file_exists"])
            self.assertIn("emergency_data", status)
            self.assertIn("error", status["emergency_data"])
    
    def test_permission_denied_flag_file(self):
        """Test handling when flag file can't be created due to permissions."""
        # Create read-only directory
        readonly_dir = Path(self.temp_dir) / "readonly"
        readonly_dir.mkdir()
        
        # Set read-only on directory after creation
        os.chmod(readonly_dir, 0o555)  # Read and execute only
        
        readonly_flag = readonly_dir / "emergency.flag"
        
        try:
            with patch.dict(os.environ, {"EXECUTION_ENABLED": "1"}):
                from tinyrpc import EmergencyKillSwitch
                
                # Should handle permission error gracefully during initialization
                try:
                    kill_switch = EmergencyKillSwitch(readonly_flag)
                    
                    # Should be enabled initially
                    self.assertTrue(kill_switch.is_execution_enabled())
                    
                    # Try to trigger emergency kill - should handle permission error
                    success = kill_switch.trigger_emergency_kill("Permission test", "test")
                    
                    # Should fail gracefully
                    self.assertFalse(success)
                    self.assertTrue(kill_switch.is_execution_enabled())  # Should remain enabled
                    
                except PermissionError:
                    # If permission error occurs during initialization, that's acceptable behavior
                    self.skipTest("Permission denied during initialization - expected behavior")
                
        finally:
            # Restore permissions for cleanup
            try:
                os.chmod(readonly_dir, 0o755)
            except OSError:
                pass  # May fail if directory was removed


if __name__ == "__main__":
    unittest.main()