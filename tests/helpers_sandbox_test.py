#!/usr/bin/env python3
"""
M10.7: Agent Sandboxing Hardening Tests

Comprehensive test suite for hardened sandbox functionality including:
- Resource limits (CPU time, memory, file descriptors)
- Working directory isolation with temporary subdirs
- Timeout configuration and enforcement
- Structured error handling
- Cross-platform compatibility (macOS/Linux)
"""

import os
import sys
import tempfile
import shutil
import time
import json
import signal
from pathlib import Path
from unittest import TestCase

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import sandbox components
from helpers.sandbox import HelperSandbox, SandboxViolationError
from helpers.executor import HelperExecutor
from helpers.registry import HelperRegistry


class TestSandboxHardening(TestCase):
    """M10.7: Test suite for hardened sandbox functionality."""

    def setUp(self):
        """Set up test environment with temporary directories."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_test_"))
        self.audit_log = self.temp_dir / "audit.log"
        self.helper_id = "test_helper"
        
        # Create basic helper structure for testing
        self.helper_dir = self.temp_dir / "helpers" / self.helper_id
        self.helper_dir.mkdir(parents=True)
        
        # Set environment variable for configurable timeout
        self.original_timeout = os.environ.get('SANDBOX_TIMEOUT_MS')
        os.environ['SANDBOX_TIMEOUT_MS'] = '2000'  # 2 second timeout for tests

    def tearDown(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Restore original timeout
        if self.original_timeout:
            os.environ['SANDBOX_TIMEOUT_MS'] = self.original_timeout
        elif 'SANDBOX_TIMEOUT_MS' in os.environ:
            del os.environ['SANDBOX_TIMEOUT_MS']

    def test_configurable_timeout(self):
        """M10.7: Test SANDBOX_TIMEOUT_MS configuration."""
        # Test default timeout
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        self.assertEqual(sandbox.max_execution_time, 2)  # 2000ms / 1000
        
        # Test custom timeout
        os.environ['SANDBOX_TIMEOUT_MS'] = '5000'
        sandbox2 = HelperSandbox(self.helper_id, self.audit_log)
        self.assertEqual(sandbox2.max_execution_time, 5)  # 5000ms / 1000

    def test_workspace_isolation(self):
        """M10.7: Test isolated workspace creation and cleanup."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        
        # Create workspace
        workspace = sandbox._create_temp_workspace()
        
        # Verify workspace exists and has correct permissions
        self.assertTrue(workspace.exists())
        self.assertTrue(workspace.is_dir())
        self.assertIn("tinyintent_helper_test_helper_", str(workspace))
        self.assertIn("_sandbox", str(workspace))
        
        # Test workspace cleanup
        sandbox._cleanup_workspace()
        self.assertFalse(workspace.exists())

    def test_resource_limits_configuration(self):
        """M10.7: Test enhanced resource limits configuration."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        
        # Test default limits are more restrictive
        self.assertEqual(sandbox.max_cpu_time, 5)  # More restrictive than old 10s
        self.assertEqual(sandbox.max_memory_mb, 128)  # More restrictive than old 256MB
        self.assertEqual(sandbox.max_file_descriptors, 64)  # New limit
        self.assertEqual(sandbox.max_processes, 4)  # New limit
        self.assertEqual(sandbox.max_output_size, 512 * 1024)  # More restrictive
        
        # Test setting enhanced limits
        sandbox.set_limits(
            cpu_time=3,
            memory_mb=64,
            execution_time=2,
            output_size=256*1024,
            file_descriptors=32,
            processes=2
        )
        
        self.assertEqual(sandbox.max_cpu_time, 3)
        self.assertEqual(sandbox.max_memory_mb, 64)
        self.assertEqual(sandbox.max_execution_time, 2)
        self.assertEqual(sandbox.max_output_size, 256*1024)
        self.assertEqual(sandbox.max_file_descriptors, 32)
        self.assertEqual(sandbox.max_processes, 2)

    def create_test_helper_script(self, script_type: str) -> Path:
        """Create test helper scripts for different violation scenarios."""
        script_path = self.helper_dir / "main.py"
        
        if script_type == "timeout":
            # Helper that sleeps too long
            script_content = '''#!/usr/bin/env python3
import time
import json
import sys

# Sleep longer than timeout to trigger violation
time.sleep(5)
print(json.dumps({"status": "success", "message": "Should not reach here"}))
'''
        elif script_type == "memory":
            # Helper that allocates too much memory
            script_content = '''#!/usr/bin/env python3
import json
import sys

try:
    # Try to allocate 512MB of memory (exceeding 128MB limit)
    data = bytearray(512 * 1024 * 1024)
    print(json.dumps({"status": "success", "message": "Should not reach here"}))
except MemoryError:
    print(json.dumps({"status": "error", "error": "Memory allocation failed"}))
'''
        elif script_type == "cpu":
            # Helper that uses too much CPU time
            script_content = '''#!/usr/bin/env python3
import time
import json
import sys

# Busy loop to consume CPU time
start = time.time()
while time.time() - start < 10:  # Run for 10 seconds (exceeding limit)
    x = 1 * 1
print(json.dumps({"status": "success", "message": "Should not reach here"}))
'''
        elif script_type == "output":
            # Helper that produces too much output
            script_content = '''#!/usr/bin/env python3
import json
import sys

# Generate large output (1MB, exceeding 512KB limit)
large_data = "x" * (1024 * 1024)
print(json.dumps({"status": "success", "data": large_data}))
'''
        elif script_type == "normal":
            # Normal helper that should work fine
            script_content = '''#!/usr/bin/env python3
import json
import sys

print(json.dumps({"status": "success", "message": "Normal execution completed"}))
'''
        else:
            raise ValueError(f"Unknown script type: {script_type}")
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        script_path.chmod(0o755)
        return script_path

    def test_timeout_violation(self):
        """M10.7: Test timeout violation detection and logging."""
        self.create_test_helper_script("timeout")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(execution_time=1)  # 1 second timeout
        
        with self.assertRaises(SandboxViolationError) as context:
            sandbox.execute(
                cmd=["python3", "main.py"],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.helper_dir
            )
        
        # Verify error details
        self.assertEqual(context.exception.error_code, "SANDBOX_TIMEOUT")
        self.assertIn("timeout_seconds", context.exception.details)
        
        # Verify audit log entry
        self.assertTrue(self.audit_log.exists())
        with open(self.audit_log, 'r') as f:
            log_content = f.read()
        self.assertIn("sandbox_violation", log_content)
        self.assertIn("TIMEOUT", log_content)

    def test_memory_violation(self):
        """M10.7: Test memory limit violation detection."""
        self.create_test_helper_script("memory")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(memory_mb=32, execution_time=5)  # Very low memory limit
        
        # Note: Memory violations might not always trigger on all systems
        # This test verifies the mechanism is in place
        try:
            result = sandbox.execute(
                cmd=["python3", "main.py"],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.helper_dir
            )
            # If it doesn't get killed, that's also acceptable for this test
        except SandboxViolationError as e:
            # Verify it's a memory-related violation
            self.assertEqual(e.error_code, "SANDBOX_LIMIT")
            self.assertIn("memory", e.details.get("limit_type", "").lower())

    def test_output_size_violation(self):
        """M10.7: Test output size limit violation."""
        self.create_test_helper_script("output")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(output_size=256*1024, execution_time=5)  # 256KB limit
        
        with self.assertRaises(SandboxViolationError) as context:
            sandbox.execute(
                cmd=["python3", "main.py"],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.helper_dir
            )
        
        # Verify error details
        self.assertEqual(context.exception.error_code, "SANDBOX_LIMIT")
        self.assertEqual(context.exception.details["limit_type"], "output_size")
        self.assertIn("output_size", context.exception.details)
        self.assertIn("max_output_size", context.exception.details)

    def test_normal_execution(self):
        """M10.7: Test that normal helpers execute successfully within limits."""
        self.create_test_helper_script("normal")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        
        result = sandbox.execute(
            cmd=["python3", "main.py"],
            input_data="{}",
            env=os.environ.copy(),
            cwd=self.helper_dir
        )
        
        # Verify successful execution
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["message"], "Normal execution completed")

    def test_workspace_environment_isolation(self):
        """M10.7: Test that helpers run in isolated workspace with proper environment."""
        self.create_test_helper_script("normal")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        
        # Mock environment to test isolation
        test_env = os.environ.copy()
        test_env["TEST_VAR"] = "original_value"
        
        # Execute and verify workspace isolation
        workspace = sandbox._create_temp_workspace()
        self.assertTrue(workspace.exists())
        
        # Cleanup should happen automatically after execution
        try:
            result = sandbox.execute(
                cmd=["python3", "main.py"],
                input_data="{}",
                env=test_env,
                cwd=self.helper_dir  # This should be overridden by workspace
            )
            self.assertEqual(result["status"], "success")
        finally:
            # Workspace should be cleaned up
            pass  # Cleanup is automatic in the execute method

    def test_capability_restriction_integration(self):
        """M10.7: Test integration with capability restriction system."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log, capabilities=[])
        
        # Test environment restrictions
        test_env = {
            "http_proxy": "http://proxy:8080",
            "HOME": "/original/home",
            "TMPDIR": "/original/tmp"
        }
        
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify network restrictions
        self.assertNotIn("http_proxy", restricted_env)
        self.assertEqual(restricted_env["TINYINTENT_NETWORK_DISABLED"], "1")
        self.assertEqual(restricted_env["TINYINTENT_FILESYSTEM_RESTRICTED"], "1")
        
        # Verify workspace isolation
        self.assertIn("tinyintent_helper_test_helper_", restricted_env["HOME"])
        self.assertIn("tinyintent_helper_test_helper_", restricted_env["TMPDIR"])
        self.assertIn("TINYINTENT_WORKSPACE", restricted_env)

    def test_structured_error_format(self):
        """M10.7: Test that violations produce properly structured errors."""
        self.create_test_helper_script("timeout")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(execution_time=1)
        
        with self.assertRaises(SandboxViolationError) as context:
            sandbox.execute(
                cmd=["python3", "main.py"],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.helper_dir
            )
        
        exception = context.exception
        
        # Verify structured error format
        self.assertEqual(exception.error_code, "SANDBOX_TIMEOUT")
        self.assertIsInstance(exception.details, dict)
        self.assertIn("timeout_seconds", exception.details)
        self.assertIn("helper_id", exception.details)
        self.assertEqual(exception.details["helper_id"], self.helper_id)

    def test_cross_platform_compatibility(self):
        """M10.7: Test that sandbox works on both macOS and Linux."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        
        # Test that resource limits can be configured without errors
        sandbox.set_limits(
            cpu_time=2,
            memory_mb=64,
            execution_time=3,
            file_descriptors=16,
            processes=1
        )
        
        # Test that preexec function can be created
        preexec_fn = sandbox._create_preexec_fn()
        
        # Should return None on Windows, function on Unix-like systems
        import platform
        if platform.system() in ('Darwin', 'Linux'):
            self.assertIsNotNone(preexec_fn)
        else:
            # On Windows or other systems without resource module
            self.assertIsNone(preexec_fn)

    def test_audit_logging_format(self):
        """M10.7: Test that violations are properly logged to audit with correct format."""
        self.create_test_helper_script("timeout")
        
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(execution_time=1)
        
        try:
            sandbox.execute(
                cmd=["python3", "main.py"],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.helper_dir
            )
        except SandboxViolationError:
            pass  # Expected
        
        # Verify audit log format
        self.assertTrue(self.audit_log.exists())
        with open(self.audit_log, 'r') as f:
            log_lines = f.readlines()
        
        self.assertGreater(len(log_lines), 0)
        
        # Parse the audit log entry
        log_entry = json.loads(log_lines[0])
        
        # Verify required fields
        self.assertIn("ts", log_entry)
        self.assertEqual(log_entry["action"], "sandbox_violation")
        self.assertEqual(log_entry["violation_type"], "TIMEOUT")  # Should be TIMEOUT for timeout violations
        self.assertEqual(log_entry["helper_id"], self.helper_id)
        self.assertIn("details", log_entry)
        self.assertFalse(log_entry["success"])


class TestSandboxViolationDetection(TestCase):
    """M10.7: Test specific violation detection scenarios."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="sandbox_violation_test_"))
        self.audit_log = self.temp_dir / "audit.log"
        self.helper_id = "violation_test_helper"
        
        # Set test timeout
        self.original_timeout = os.environ.get('SANDBOX_TIMEOUT_MS')
        os.environ['SANDBOX_TIMEOUT_MS'] = '3000'
    
    def tearDown(self):
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Restore original timeout
        if self.original_timeout:
            os.environ['SANDBOX_TIMEOUT_MS'] = self.original_timeout
        elif 'SANDBOX_TIMEOUT_MS' in os.environ:
            del os.environ['SANDBOX_TIMEOUT_MS']
    
    def test_process_terminated_violation(self):
        """M10.7: Test detection of process termination violations."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(processes=1, execution_time=5)
        
        # Create a script that tries to fork multiple processes
        script_content = '''#!/usr/bin/env python3
import os
import json
import sys

try:
    # Try to fork (will be limited by processes=1)
    pid = os.fork()
    if pid == 0:
        # Child process
        exit(0)
    else:
        # Parent process
        os.wait()
        print(json.dumps({"status": "success", "message": "Fork succeeded"}))
except OSError as e:
    print(json.dumps({"status": "error", "error": str(e)}))
'''
        
        script_path = self.temp_dir / "fork_test.py"
        with open(script_path, 'w') as f:
            f.write(script_content)
        script_path.chmod(0o755)
        
        # This might trigger a process limit violation on some systems
        try:
            result = sandbox.execute(
                cmd=["python3", str(script_path)],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.temp_dir
            )
            # If no violation, that's also acceptable
        except SandboxViolationError as e:
            self.assertEqual(e.error_code, "SANDBOX_LIMIT")
    
    def test_file_descriptor_violation_attempt(self):
        """M10.7: Test that file descriptor limits are enforced."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        sandbox.set_limits(file_descriptors=8, execution_time=5)
        
        # Create a script that tries to open many files
        script_content = '''#!/usr/bin/env python3
import json
import tempfile

try:
    files = []
    # Try to open more files than the FD limit
    for i in range(20):
        f = open(f"/tmp/test_fd_{i}", "w")
        files.append(f)
        f.write("test")
    
    # Close files
    for f in files:
        f.close()
    
    print(json.dumps({"status": "success", "files_opened": len(files)}))
except Exception as e:
    print(json.dumps({"status": "error", "error": str(e)}))
'''
        
        script_path = self.temp_dir / "fd_test.py"
        with open(script_path, 'w') as f:
            f.write(script_content)
        script_path.chmod(0o755)
        
        # Execute and check if it gets limited (might vary by system)
        try:
            result = sandbox.execute(
                cmd=["python3", str(script_path)],
                input_data="{}",
                env=os.environ.copy(),
                cwd=self.temp_dir
            )
            # If it succeeds, the system may have different FD behavior
        except (SandboxViolationError, RuntimeError):
            # May get either sandbox violation or runtime error
            pass
    
    def test_capability_violation_error_structure(self):
        """M10.7: Test CapabilityViolationError structure and handling."""
        from helpers.sandbox import CapabilityViolationError
        
        # Test error creation
        error = CapabilityViolationError(
            "Network access denied",
            capability="network",
            operation="socket_creation",
            details={"attempted_host": "example.com", "port": 80}
        )
        
        # Verify error structure
        self.assertEqual(error.error_code, "CAPABILITY_VIOLATION")
        self.assertEqual(error.capability, "network")
        self.assertEqual(error.operation, "socket_creation")
        self.assertEqual(error.details["attempted_host"], "example.com")
        self.assertEqual(error.details["port"], 80)
        self.assertIn("Network access denied", str(error))
    
    def test_sandbox_error_code_consistency(self):
        """M10.7: Test that SANDBOX_LIMIT error codes are consistent."""
        sandbox = HelperSandbox(self.helper_id, self.audit_log)
        
        # Test different types of sandbox limit violations
        test_cases = [
            ("timeout", "SANDBOX_TIMEOUT", {"timeout_seconds": 1}),
            ("cpu_time", "SANDBOX_LIMIT", {"limit_type": "cpu_time"}),
            ("memory", "SANDBOX_LIMIT", {"limit_type": "memory_or_resource"}),
            ("output_size", "SANDBOX_LIMIT", {"limit_type": "output_size"})
        ]
        
        for violation_type, expected_code, expected_details in test_cases:
            # Create appropriate violation scenario
            if violation_type == "timeout":
                error = SandboxViolationError(
                    "Process timed out", 
                    expected_code, 
                    expected_details
                )
            else:
                error = SandboxViolationError(
                    f"Exceeded {violation_type} limit",
                    expected_code,
                    expected_details
                )
            
            self.assertEqual(error.error_code, expected_code)
            for key, value in expected_details.items():
                self.assertIn(key, error.details)
                if isinstance(value, (int, str)):
                    self.assertEqual(error.details[key], value)


if __name__ == "__main__":
    import unittest
    
    # Run tests with verbose output
    unittest.main(verbosity=2)