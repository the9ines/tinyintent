#!/usr/bin/env python3
"""
TinyIntent Helper Capability Isolation Tests - M6.5

Tests capability restrictions for helpers to ensure they only operate 
within explicitly declared capabilities.
"""

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add helpers to path
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

try:
    from sdk import (
        HelperRegistry, HelperExecutor, HelperSandbox, 
        CapabilityViolationError, HelperRegistryEntry
    )
    HELPERS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helpers framework not available: {e}")
    HELPERS_AVAILABLE = False


class TestCapabilityIsolation(unittest.TestCase):
    """Test helper capability isolation enforcement."""
    
    def setUp(self):
        """Set up test environment."""
        if not HELPERS_AVAILABLE:
            self.skipTest("Helpers framework not available")
        
        self.temp_dir = Path(tempfile.mkdtemp())
        self.audit_log_path = self.temp_dir / "audit.log"
        
        # Create minimal test registry data
        self.test_registry_data = {
            "version": "1.0",
            "helpers": {
                "network_helper": {
                    "name": "Network Helper",
                    "enabled": True,
                    "capabilities": ["network"],
                    "manifest_path": "test/network_helper.yaml"
                },
                "filesystem_helper": {
                    "name": "Filesystem Helper", 
                    "enabled": True,
                    "capabilities": ["filesystem"],
                    "manifest_path": "test/filesystem_helper.yaml"
                },
                "both_caps_helper": {
                    "name": "Both Capabilities Helper",
                    "enabled": True,
                    "capabilities": ["network", "filesystem"],
                    "manifest_path": "test/both_caps_helper.yaml"
                },
                "no_caps_helper": {
                    "name": "No Capabilities Helper",
                    "enabled": True,
                    "capabilities": [],
                    "manifest_path": "test/no_caps_helper.yaml"
                }
            }
        }
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
    
    def test_capability_violation_error_creation(self):
        """Test CapabilityViolationError creation and attributes."""
        error = CapabilityViolationError(
            message="Network access denied",
            capability="network",
            operation="socket_creation",
            details={"attempted_host": "example.com", "port": 80}
        )
        
        self.assertEqual(error.error_code, "CAPABILITY_VIOLATION")
        self.assertEqual(error.capability, "network")
        self.assertEqual(error.operation, "socket_creation")
        self.assertEqual(error.details["attempted_host"], "example.com")
        self.assertIn("Network access denied", str(error))
    
    def test_sandbox_capability_enforcement_network_restriction(self):
        """Test network capability restriction in sandbox."""
        # Test helper without network capability
        sandbox = HelperSandbox("no_caps_helper", self.audit_log_path, capabilities=[])
        
        # Mock environment
        test_env = {
            "http_proxy": "http://proxy.example.com:8080",
            "https_proxy": "https://proxy.example.com:8080",
            "HTTP_PROXY": "http://proxy.example.com:8080",
            "HTTPS_PROXY": "https://proxy.example.com:8080",
            "ftp_proxy": "ftp://proxy.example.com:21",
            "no_proxy": "localhost,127.0.0.1",
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user"
        }
        
        # Apply capability restrictions
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify network environment variables are removed
        self.assertNotIn("http_proxy", restricted_env)
        self.assertNotIn("https_proxy", restricted_env)
        self.assertNotIn("HTTP_PROXY", restricted_env)
        self.assertNotIn("HTTPS_PROXY", restricted_env)
        self.assertNotIn("ftp_proxy", restricted_env)
        self.assertNotIn("no_proxy", restricted_env)
        
        # Verify network restriction flag is set
        self.assertEqual(restricted_env["TINYINTENT_NETWORK_DISABLED"], "1")
        
        # Verify non-network vars are preserved
        self.assertEqual(restricted_env["PATH"], "/usr/bin:/bin")
        self.assertEqual(restricted_env["HOME"], "/home/user")
    
    def test_sandbox_capability_enforcement_filesystem_restriction(self):
        """Test filesystem capability restriction in sandbox."""
        # Test helper without filesystem capability
        sandbox = HelperSandbox("no_caps_helper", self.audit_log_path, capabilities=[])
        
        test_env = {
            "HOME": "/home/user",
            "PATH": "/usr/bin:/bin",
            "TMPDIR": "/tmp"
        }
        
        # Apply capability restrictions
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify filesystem restriction flag is set
        self.assertEqual(restricted_env["TINYINTENT_FILESYSTEM_RESTRICTED"], "1")
        
        # Verify TMPDIR is set to a restricted temporary location
        tmpdir = restricted_env.get("TMPDIR", "")
        self.assertTrue(tmpdir.startswith("/tmp/") or tmpdir.startswith("/var/folders/"), 
                       f"TMPDIR should be in a temporary location: {tmpdir}")
        self.assertIn("helper_", tmpdir, "TMPDIR should contain helper identifier")
    
    def test_sandbox_capability_enforcement_network_allowed(self):
        """Test helper with network capability gets full network access."""
        # Test helper with network capability
        sandbox = HelperSandbox("network_helper", self.audit_log_path, capabilities=["network"])
        
        test_env = {
            "http_proxy": "http://proxy.example.com:8080",
            "https_proxy": "https://proxy.example.com:8080",
            "PATH": "/usr/bin:/bin"
        }
        
        # Apply capability restrictions
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify network environment variables are preserved
        self.assertEqual(restricted_env["http_proxy"], "http://proxy.example.com:8080")
        self.assertEqual(restricted_env["https_proxy"], "https://proxy.example.com:8080")
        
        # Verify network disabled flag is NOT set
        self.assertNotIn("TINYINTENT_NETWORK_DISABLED", restricted_env)
    
    def test_sandbox_capability_enforcement_filesystem_allowed(self):
        """Test helper with filesystem capability gets full filesystem access."""
        # Test helper with filesystem capability
        sandbox = HelperSandbox("filesystem_helper", self.audit_log_path, capabilities=["filesystem"])
        
        test_env = {
            "HOME": "/home/user",
            "TMPDIR": "/tmp"
        }
        
        # Apply capability restrictions
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify filesystem restriction flag is NOT set
        self.assertNotIn("TINYINTENT_FILESYSTEM_RESTRICTED", restricted_env)
        
        # Verify TMPDIR is preserved
        self.assertEqual(restricted_env["TMPDIR"], "/tmp")
    
    def test_sandbox_capability_enforcement_both_capabilities(self):
        """Test helper with both capabilities gets full access."""
        # Test helper with both capabilities
        sandbox = HelperSandbox("both_caps_helper", self.audit_log_path, capabilities=["network", "filesystem"])
        
        test_env = {
            "http_proxy": "http://proxy.example.com:8080",
            "HOME": "/home/user",
            "TMPDIR": "/tmp"
        }
        
        # Apply capability restrictions
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify network vars preserved
        self.assertEqual(restricted_env["http_proxy"], "http://proxy.example.com:8080")
        self.assertNotIn("TINYINTENT_NETWORK_DISABLED", restricted_env)
        
        # Verify filesystem vars preserved
        self.assertEqual(restricted_env["TMPDIR"], "/tmp")
        self.assertNotIn("TINYINTENT_FILESYSTEM_RESTRICTED", restricted_env)
    
    def test_registry_entry_capability_loading(self):
        """Test that registry entries load capabilities correctly."""
        # Test helper with capabilities
        entry_data = self.test_registry_data["helpers"]["network_helper"]
        entry = HelperRegistryEntry("network_helper", entry_data)
        
        self.assertEqual(entry.capabilities, ["network"])
        
        # Test helper without capabilities (default to empty)
        entry_data_no_caps = {
            "name": "No Caps Helper",
            "enabled": True,
            "manifest_path": "test/no_caps.yaml"
        }
        entry_no_caps = HelperRegistryEntry("no_caps_helper", entry_data_no_caps)
        
        self.assertEqual(entry_no_caps.capabilities, [])
    
    @patch('subprocess.Popen')
    def test_helper_execution_with_capability_restrictions(self, mock_popen):
        """Test that helper execution applies capability restrictions."""
        # Mock successful process
        mock_process = MagicMock()
        mock_process.communicate.return_value = ('{"status": "success"}', "")
        mock_process.returncode = 0
        mock_popen.return_value = mock_process
        
        # Create test sandbox with no capabilities
        sandbox = HelperSandbox("no_caps_helper", self.audit_log_path, capabilities=[])
        
        # Mock helper manifest
        test_manifest = {
            "name": "Test Helper",
            "version": "1.0",
            "runtime": "node",
            "entrypoint": "main.js",
            "timeout": 5
        }
        
        # Execute helper using sandbox's execute method signature
        input_data = {"test": "data"}
        cmd = ["node", "main.js"]
        result = sandbox.execute(cmd, json.dumps(input_data), {}, Path("/tmp"))
        
        # Verify subprocess was called
        self.assertTrue(mock_popen.called)
        
        # Verify environment restrictions were applied
        call_args = mock_popen.call_args
        env_arg = call_args[1]['env']
        
        # Check that network restrictions were applied
        self.assertEqual(env_arg.get("TINYINTENT_NETWORK_DISABLED"), "1")
        self.assertEqual(env_arg.get("TINYINTENT_FILESYSTEM_RESTRICTED"), "1")
        
        # Verify proxy vars were removed
        self.assertNotIn("http_proxy", env_arg)
        self.assertNotIn("HTTP_PROXY", env_arg)
    
    @patch('subprocess.Popen')
    def test_helper_execution_capability_violation_detection(self, mock_popen):
        """Test detection and raising of capability violations."""
        # Mock process that attempts network access without permission
        mock_process = MagicMock()
        mock_process.communicate.return_value = ("", "Network access denied")
        mock_process.returncode = 1
        mock_popen.return_value = mock_process
        
        # Create test sandbox with no network capability
        sandbox = HelperSandbox("no_caps_helper", self.audit_log_path, capabilities=[])
        
        test_manifest = {
            "name": "Test Helper",
            "version": "1.0", 
            "runtime": "node",
            "entrypoint": "main.js",
            "timeout": 5
        }
        
        # Should not raise CapabilityViolationError for general failure
        # (Helper itself would need to detect and report capability violations)
        input_data = {"test": "data"}
        cmd = ["node", "main.js"]
        
        with self.assertRaises(RuntimeError):
            sandbox.execute(cmd, json.dumps(input_data), {}, Path("/tmp"))
    
    def test_fail_closed_behavior(self):
        """Test that helpers without declared capabilities are restricted by default."""
        # Create sandbox with no capabilities specified (should default to empty)
        sandbox = HelperSandbox("unknown_helper", self.audit_log_path)
        
        test_env = {
            "http_proxy": "http://proxy.example.com:8080",
            "HOME": "/home/user"
        }
        
        # Apply restrictions
        restricted_env = sandbox._enforce_capability_restrictions(test_env)
        
        # Verify fail-closed behavior - both restrictions applied
        self.assertEqual(restricted_env.get("TINYINTENT_NETWORK_DISABLED"), "1")
        self.assertEqual(restricted_env.get("TINYINTENT_FILESYSTEM_RESTRICTED"), "1")
        self.assertNotIn("http_proxy", restricted_env)
    
    def test_capability_violation_error_serialization(self):
        """Test that CapabilityViolationError can be properly serialized."""
        error = CapabilityViolationError(
            message="Filesystem write denied",
            capability="filesystem", 
            operation="file_write",
            details={"path": "/etc/passwd", "reason": "restricted_location"}
        )
        
        # Test string representation
        error_str = str(error)
        self.assertIn("Filesystem write denied", error_str)
        
        # Test that all attributes are accessible
        self.assertEqual(error.error_code, "CAPABILITY_VIOLATION")
        self.assertEqual(error.capability, "filesystem")
        self.assertEqual(error.operation, "file_write")
        self.assertIsInstance(error.details, dict)
    
    def test_network_environment_variable_comprehensive_removal(self):
        """Test comprehensive removal of all network-related environment variables."""
        sandbox = HelperSandbox("no_caps_helper", self.audit_log_path, capabilities=[])
        
        # Comprehensive set of network environment variables
        network_env = {
            "http_proxy": "http://proxy:8080",
            "https_proxy": "https://proxy:8080", 
            "HTTP_PROXY": "http://proxy:8080",
            "HTTPS_PROXY": "https://proxy:8080",
            "ftp_proxy": "ftp://proxy:21",
            "FTP_PROXY": "ftp://proxy:21",
            "no_proxy": "localhost,127.0.0.1,.local",
            "NO_PROXY": "localhost,127.0.0.1,.local",
            "all_proxy": "socks://proxy:1080",
            "ALL_PROXY": "socks://proxy:1080",
            "socks_proxy": "socks://proxy:1080",
            "SOCKS_PROXY": "socks://proxy:1080",
            # Non-network vars that should be preserved
            "PATH": "/usr/bin:/bin",
            "HOME": "/home/user",
            "USER": "testuser"
        }
        
        # Apply restrictions
        restricted_env = sandbox._enforce_capability_restrictions(network_env)
        
        # Verify all network proxy vars are removed
        network_vars = [
            "http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY",
            "ftp_proxy", "FTP_PROXY", "no_proxy", "NO_PROXY", 
            "all_proxy", "ALL_PROXY", "socks_proxy", "SOCKS_PROXY"
        ]
        
        for var in network_vars:
            self.assertNotIn(var, restricted_env, f"Network variable {var} should be removed")
        
        # Verify non-network vars are preserved  
        self.assertEqual(restricted_env["PATH"], "/usr/bin:/bin")
        self.assertEqual(restricted_env["HOME"], "/home/user")
        self.assertEqual(restricted_env["USER"], "testuser")
        
        # Verify restriction flag is set
        self.assertEqual(restricted_env["TINYINTENT_NETWORK_DISABLED"], "1")


class TestCapabilityIntegration(unittest.TestCase):
    """Integration tests for capability isolation across the system."""
    
    def setUp(self):
        """Set up integration test environment."""
        if not HELPERS_AVAILABLE:
            self.skipTest("Helpers framework not available")
    
    def test_registry_capability_integration(self):
        """Test that registry properly passes capabilities to executor."""
        # Mock registry data
        registry_data = {
            "version": "1.0",
            "helpers": {
                "test_helper": {
                    "name": "Test Helper",
                    "enabled": True,
                    "capabilities": ["network"],
                    "manifest_path": "test/helper.yaml"
                }
            }
        }
        
        # Create registry entry
        entry = HelperRegistryEntry("test_helper", registry_data["helpers"]["test_helper"])
        
        # Verify capabilities are properly loaded
        self.assertEqual(entry.capabilities, ["network"])
        
        # Verify capability checking methods work
        self.assertTrue(entry.has_capability("network"))
        self.assertFalse(entry.has_capability("filesystem"))
    
    def test_macOS_compatibility(self):
        """Test that capability restrictions work on macOS without system calls."""
        # This test verifies our approach works on macOS using environment 
        # variable manipulation rather than system calls like chroot
        
        sandbox = HelperSandbox("test_helper", Path("/tmp/audit.log"), capabilities=[])
        
        test_env = {"HOME": "/Users/testuser", "TMPDIR": "/tmp"}
        
        # Should not raise any system-level errors on macOS
        try:
            restricted_env = sandbox._enforce_capability_restrictions(test_env)
            
            # Verify restriction was applied via environment variables
            self.assertEqual(restricted_env.get("TINYINTENT_FILESYSTEM_RESTRICTED"), "1")
            
            # Verify TMPDIR was modified to restricted location
            tmpdir = restricted_env.get("TMPDIR", "")
            self.assertTrue(tmpdir.startswith("/tmp/") or tmpdir.startswith("/var/folders/"), 
                           f"TMPDIR should be in a temporary location: {tmpdir}")
            self.assertIn("helper_", tmpdir, "TMPDIR should contain helper identifier")
            
        except Exception as e:
            self.fail(f"Capability restrictions should work on macOS without system calls: {e}")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)