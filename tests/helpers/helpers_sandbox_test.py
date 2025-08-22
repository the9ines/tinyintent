#!/usr/bin/env python3
"""
Tests for Helper Sandboxing Enhancements - M6.1

Tests resource limits, timeouts, and isolation for helper execution.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml

# Add helpers to path
import sys
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

from tinyintent.helpers.sandbox import HelperSandbox, SandboxViolationError
from tinyintent.helpers.executor import HelperExecutor
from tinyintent.helpers.registry import HelperRegistry


class TestHelperSandbox(unittest.TestCase):
    """Test HelperSandbox resource limits and isolation."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        self.sandbox = HelperSandbox("test_helper", self.audit_log)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_sandbox_limits_configuration(self):
        """Test that sandbox limits can be configured properly."""
        # Test default limits
        self.assertEqual(self.sandbox.max_cpu_time, 10)
        self.assertEqual(self.sandbox.max_memory_mb, 256)
        self.assertEqual(self.sandbox.max_execution_time, 15)
        self.assertEqual(self.sandbox.max_output_size, 1024 * 1024)
        
        # Test custom limits
        self.sandbox.set_limits(
            cpu_time=20,
            memory_mb=512,
            execution_time=30,
            output_size=2048 * 1024
        )
        
        self.assertEqual(self.sandbox.max_cpu_time, 20)
        self.assertEqual(self.sandbox.max_memory_mb, 512)
        self.assertEqual(self.sandbox.max_execution_time, 30)
        self.assertEqual(self.sandbox.max_output_size, 2048 * 1024)
    
    def test_successful_execution(self):
        """Test that normal helper execution works within limits."""
        # Use a simple command that should succeed
        cmd = ["echo", '{"status": "success", "message": "test"}']
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        # Set reasonable limits
        self.sandbox.set_limits(cpu_time=5, execution_time=10, output_size=1024)
        
        result = self.sandbox.execute(cmd, input_data, env, cwd)
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message"], "test")
    
    def test_execution_timeout(self):
        """Test that long-running helpers are terminated."""
        # Create a command that sleeps longer than allowed
        cmd = ["sleep", "20"]  # Sleep for 20 seconds
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        # Set short timeout
        self.sandbox.set_limits(execution_time=2)  # 2 second timeout
        
        start_time = time.time()
        with self.assertRaises(SandboxViolationError) as context:
            self.sandbox.execute(cmd, input_data, env, cwd)
        
        execution_time = time.time() - start_time
        
        # Should have timed out quickly
        self.assertLess(execution_time, 5)  # Should be much less than 20 seconds
        self.assertEqual(context.exception.error_code, "SANDBOX_TIMEOUT")
        self.assertIn("timed out after 2s", str(context.exception))
    
    def test_large_output_rejection(self):
        """Test that helpers producing too much output are rejected."""
        # Create a command that produces large output
        large_data = "x" * (1024 * 1024 + 1000)  # Just over 1MB
        cmd = ["echo", f'{{"status": "success", "data": "{large_data}"}}']
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        # Set small output limit
        self.sandbox.set_limits(output_size=1024)  # 1KB limit
        
        with self.assertRaises(SandboxViolationError) as context:
            self.sandbox.execute(cmd, input_data, env, cwd)
        
        self.assertEqual(context.exception.error_code, "SANDBOX_OUTPUT_SIZE")
        self.assertIn("exceeded size limit", str(context.exception))
    
    def test_invalid_json_output(self):
        """Test that invalid JSON output is properly handled."""
        cmd = ["echo", "invalid json output"]
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        with self.assertRaises(ValueError) as context:
            self.sandbox.execute(cmd, input_data, env, cwd)
        
        self.assertIn("invalid JSON", str(context.exception))
    
    def test_command_failure(self):
        """Test that failed commands raise proper errors."""
        cmd = ["false"]  # Command that always fails
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        with self.assertRaises(RuntimeError) as context:
            self.sandbox.execute(cmd, input_data, env, cwd)
        
        self.assertIn("Helper execution failed", str(context.exception))
    
    def test_audit_logging(self):
        """Test that sandbox violations are logged to audit log."""
        cmd = ["sleep", "10"]
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        # Set very short timeout to trigger violation
        self.sandbox.set_limits(execution_time=1)
        
        with self.assertRaises(SandboxViolationError):
            self.sandbox.execute(cmd, input_data, env, cwd)
        
        # Check that audit log was created and contains violation
        self.assertTrue(self.audit_log.exists())
        
        with open(self.audit_log, 'r') as f:
            log_content = f.read()
        
        self.assertIn("sandbox_violation", log_content)
        self.assertIn("TIMEOUT", log_content)
        self.assertIn("test_helper", log_content)


class TestCPULimitExecution(unittest.TestCase):
    """Test CPU time limits (requires Unix-like system with resource limits)."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        self.sandbox = HelperSandbox("cpu_test_helper", self.audit_log)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_cpu_intensive_helper(self):
        """Test that CPU-intensive helpers are limited (Unix systems only)."""
        try:
            import resource
        except ImportError:
            self.skipTest("Resource limits not available on this system")
        
        # Create a CPU-intensive Python script
        cpu_script = Path(self.temp_dir) / "cpu_hog.py"
        script_content = '''
import json
import time

# CPU-intensive loop
start = time.time()
i = 0
while time.time() - start < 20:  # Try to run for 20 seconds
    i += 1
    if i % 1000000 == 0:
        # Prevent optimization
        pass

print(json.dumps({"status": "success", "iterations": i}))
'''
        with open(cpu_script, 'w') as f:
            f.write(script_content)
        
        cmd = ["python3", str(cpu_script)]
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        # Set very low CPU time limit
        self.sandbox.set_limits(cpu_time=2, execution_time=30)  # 2 second CPU limit
        
        start_time = time.time()
        try:
            result = self.sandbox.execute(cmd, input_data, env, cwd)
            # If we get here, the process completed before hitting CPU limit
            # This can happen on fast systems or if resource limits aren't enforced
            execution_time = time.time() - start_time
            self.assertLess(execution_time, 15)  # Should complete quickly
        except SandboxViolationError as e:
            # Expected: CPU limit exceeded
            execution_time = time.time() - start_time
            self.assertLess(execution_time, 10)  # Should be killed quickly
            self.assertEqual(e.error_code, "SANDBOX_CPU_LIMIT")


class TestMemoryLimitExecution(unittest.TestCase):
    """Test memory limits (system-dependent)."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        self.sandbox = HelperSandbox("memory_test_helper", self.audit_log)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_memory_intensive_helper(self):
        """Test that memory-intensive helpers are limited (system-dependent)."""
        try:
            import resource
        except ImportError:
            self.skipTest("Resource limits not available on this system")
        
        # Create a memory-intensive Python script
        memory_script = Path(self.temp_dir) / "memory_hog.py"
        script_content = '''
import json
import sys

try:
    # Try to allocate a large amount of memory (512MB)
    big_list = []
    for i in range(1000):
        # Allocate 512KB chunks
        big_list.append(b"x" * (512 * 1024))
    
    print(json.dumps({"status": "success", "allocated_mb": len(big_list) * 0.5}))
except MemoryError:
    print(json.dumps({"status": "error", "message": "Memory allocation failed"}))
except:
    print(json.dumps({"status": "error", "message": "Unexpected error"}))
'''
        with open(memory_script, 'w') as f:
            f.write(script_content)
        
        cmd = ["python3", str(memory_script)]
        input_data = "{}"
        env = os.environ.copy()
        cwd = Path(self.temp_dir)
        
        # Set low memory limit (128MB)
        self.sandbox.set_limits(memory_mb=128, execution_time=30)
        
        try:
            result = self.sandbox.execute(cmd, input_data, env, cwd)
            # If execution succeeds, check that it didn't allocate too much
            if result.get("status") == "success":
                allocated_mb = result.get("allocated_mb", 0)
                # Should have been limited or failed gracefully
                self.assertLess(allocated_mb, 200)  # Less than 200MB
        except SandboxViolationError as e:
            # Expected: Memory limit exceeded or killed by OOM
            self.assertIn("MEMORY_LIMIT", e.error_code)


class TestHelperExecutorSandboxing(unittest.TestCase):
    """Test that HelperExecutor properly uses sandbox limits."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.helpers_dir = Path(self.temp_dir)
        
        # Create mock registry
        self.mock_registry = MagicMock()
        self.executor = HelperExecutor(self.mock_registry)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def create_timeout_helper_manifest(self) -> MagicMock:
        """Create a helper manifest that will trigger timeout."""
        mock_helper = MagicMock()
        mock_helper.helper_id = "timeout_helper"
        mock_helper.helper_dir = self.helpers_dir
        mock_helper.can_preview.return_value = True
        mock_helper.validate_input.return_value = True
        mock_helper.validate_output.return_value = True
        mock_helper.get_timeout.return_value = 5
        mock_helper.environment = {"required": []}
        mock_helper.sandbox = {
            "commands": ["sleep", "10"],  # Sleep longer than timeout
            "cpu": {"max_ms": 5000},
            "mem": {"max_mb": 256}
        }
        
        return mock_helper
    
    def test_executor_handles_sandbox_timeout(self):
        """Test that executor properly handles sandbox timeout violations."""
        # Set up mocks
        self.mock_registry.is_helper_valid.return_value = True
        self.mock_registry.get_helper.return_value = self.create_timeout_helper_manifest()
        
        # Should raise RuntimeError with sandbox violation message
        with self.assertRaises(RuntimeError) as context:
            self.executor.preview("timeout_helper", {"test": "data"})
        
        error_msg = str(context.exception)
        self.assertIn("Sandbox violation", error_msg)
        self.assertIn("SANDBOX_TIMEOUT", error_msg)
    
    def create_fast_helper_manifest(self) -> MagicMock:
        """Create a helper manifest for a fast, successful execution."""
        mock_helper = MagicMock()
        mock_helper.helper_id = "fast_helper"
        mock_helper.helper_dir = self.helpers_dir
        mock_helper.can_preview.return_value = True
        mock_helper.validate_input.return_value = True
        mock_helper.validate_output.return_value = True
        mock_helper.get_timeout.return_value = 5
        mock_helper.environment = {"required": []}
        mock_helper.sandbox = {
            "commands": ["echo", '{"status": "success"}'],
            "cpu": {"max_ms": 5000},
            "mem": {"max_mb": 256}
        }
        
        return mock_helper
    
    def test_executor_allows_normal_execution(self):
        """Test that executor allows normal helpers to execute successfully."""
        # Set up mocks
        self.mock_registry.is_helper_valid.return_value = True
        self.mock_registry.get_helper.return_value = self.create_fast_helper_manifest()
        
        # Mock the approval token generation
        with patch.object(self.executor, '_generate_approval_token', return_value="test_token"):
            result = self.executor.preview("fast_helper", {"test": "data"})
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["helper_id"], "fast_helper")
        self.assertEqual(result["action"], "preview")
    
    def test_sandbox_limits_from_manifest(self):
        """Test that sandbox limits are properly extracted from helper manifest."""
        mock_helper = MagicMock()
        mock_helper.helper_id = "limits_test_helper"
        mock_helper.helper_dir = self.helpers_dir
        mock_helper.can_preview.return_value = True
        mock_helper.validate_input.return_value = True
        mock_helper.validate_output.return_value = True
        mock_helper.get_timeout.return_value = 8
        mock_helper.environment = {"required": []}
        mock_helper.sandbox = {
            "commands": ["echo", '{"status": "success"}'],
            "cpu": {"max_ms": 12000},  # 12 seconds
            "mem": {"max_mb": 512}     # 512 MB
        }
        
        self.mock_registry.is_helper_valid.return_value = True
        self.mock_registry.get_helper.return_value = mock_helper
        
        # Patch the sandbox execution to capture the limits
        with patch('helpers.sdk.HelperSandbox') as mock_sandbox_class:
            mock_sandbox = MagicMock()
            mock_sandbox_class.return_value = mock_sandbox
            mock_sandbox.execute.return_value = {"status": "success"}
            
            with patch.object(self.executor, '_generate_approval_token', return_value="test_token"):
                self.executor.preview("limits_test_helper", {"test": "data"})
            
            # Verify sandbox was created and limits were set
            mock_sandbox_class.assert_called_once_with("limits_test_helper", self.executor.audit_log)
            mock_sandbox.set_limits.assert_called_once()
            
            # Check the limits that were set
            call_args = mock_sandbox.set_limits.call_args[1]  # keyword arguments
            self.assertEqual(call_args['cpu_time'], 12)    # 12000ms -> 12s
            self.assertEqual(call_args['memory_mb'], 512)  # 512 MB
            self.assertEqual(call_args['execution_time'], 8)  # timeout from manifest


if __name__ == "__main__":
    unittest.main()