#!/usr/bin/env python3
"""
Tests for Secrets Management Hardening - M6.4

Tests sanitization of sensitive secrets across helpers, bridge, and audit logs.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add bridge and helpers to path for testing
sys.path.append(str(Path(__file__).parent.parent / "bridge"))
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

from logs.rotate import AuditLogger, sanitize_audit_data, sanitize_sensitive_string
from sdk import sanitize_env, HelperExecutor, HelperRegistry


class TestEnvironmentSanitization(unittest.TestCase):
    """Test environment variable sanitization."""
    
    def test_sanitize_env_with_sensitive_keys(self):
        """Test that sensitive environment keys are redacted."""
        test_env = {
            "EXCHANGE_API_KEY": "secret123456789",
            "EXCHANGE_SECRET": "supersecret987654321",
            "DATABASE_PASSWORD": "dbpassword123",
            "AUTH_TOKEN": "bearer_token_12345",
            "NORMAL_VAR": "normal_value",
            "PATH": "/usr/bin:/bin",
            "PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----",
            "API_CREDENTIAL": "credential_value",
            "PASSPHRASE": "my_passphrase"
        }
        
        sanitized = sanitize_env(test_env)
        
        # Sensitive keys should be redacted
        self.assertEqual(sanitized["EXCHANGE_API_KEY"], "****")
        self.assertEqual(sanitized["EXCHANGE_SECRET"], "****")
        self.assertEqual(sanitized["DATABASE_PASSWORD"], "****")
        self.assertEqual(sanitized["AUTH_TOKEN"], "****")
        self.assertEqual(sanitized["PRIVATE_KEY"], "****")
        self.assertEqual(sanitized["API_CREDENTIAL"], "****")
        self.assertEqual(sanitized["PASSPHRASE"], "****")
        
        # Non-sensitive keys should remain unchanged
        self.assertEqual(sanitized["NORMAL_VAR"], "normal_value")
        self.assertEqual(sanitized["PATH"], "/usr/bin:/bin")
    
    def test_sanitize_env_case_insensitive(self):
        """Test that sanitization is case-insensitive."""
        test_env = {
            "exchange_api_key": "secret123",
            "EXCHANGE_API_KEY": "secret456",
            "Exchange_Secret": "secret789",
            "api_KEY": "secret000"
        }
        
        sanitized = sanitize_env(test_env)
        
        # All variations should be redacted
        for key in test_env.keys():
            self.assertEqual(sanitized[key], "****")
    
    def test_sanitize_env_with_empty_dict(self):
        """Test sanitization with empty dictionary."""
        result = sanitize_env({})
        self.assertEqual(result, {})
    
    def test_sanitize_env_with_non_dict(self):
        """Test sanitization with non-dictionary input."""
        result = sanitize_env("not_a_dict")
        self.assertEqual(result, "not_a_dict")


class TestStringSanitization(unittest.TestCase):
    """Test string sanitization functions."""
    
    def test_sanitize_sensitive_string_basic(self):
        """Test basic string sanitization."""
        # Test various sensitive patterns
        test_cases = [
            ("Bearer abc123def456ghi789", "Bearer ****"),
            ("Basic YWRtaW46cGFzc3dvcmQ=", "Basic ****"),
            ("sk_test_1234567890abcdef", "****"),
            ("pk_live_abcdef1234567890", "****"),
            ("api_key_very_long_string_here_123456_extra", "api_****"),  # Made longer to meet 15+ char requirement
            ("secret_key_another_long_string_extra", "secret_****"),     # Made longer to meet 10+ char requirement
        ]
        
        for input_str, expected in test_cases:
            with self.subTest(input=input_str):
                result = sanitize_sensitive_string(input_str)
                self.assertEqual(result, expected)
    
    def test_sanitize_json_patterns(self):
        """Test sanitization of JSON-like patterns."""
        test_json = '{"api_key": "very_long_secret_key_123456789", "password": "secret_password_long"}'
        result = sanitize_sensitive_string(test_json)
        
        # Should redact the sensitive JSON values
        self.assertIn('"****": "****"', result)
        self.assertNotIn("very_long_secret_key_123456789", result)
        self.assertNotIn("secret_password_long", result)
    
    def test_sanitize_environment_patterns(self):
        """Test sanitization of environment variable patterns."""
        env_string = "EXCHANGE_API_KEY=abc123def456ghi789_long DEBUG=true"  # Made longer to meet 15+ char requirement
        result = sanitize_sensitive_string(env_string)
        
        self.assertIn("REDACTED_ENV=****", result)
        self.assertNotIn("abc123def456ghi789_long", result)
        self.assertIn("DEBUG=true", result)  # Non-sensitive should remain
    
    def test_very_long_strings(self):
        """Test that very long alphanumeric strings are redacted."""
        long_secret = "a" * 45  # 45 character string should be redacted (40+ threshold)
        result = sanitize_sensitive_string(f"Token: {long_secret}")
        
        self.assertNotIn(long_secret, result)
        self.assertIn("****", result)


class TestAuditLogSanitization(unittest.TestCase):
    """Test audit log sanitization."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "test_audit.log"
        self.logger = AuditLogger(self.audit_log)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_audit_data_sanitization(self):
        """Test that audit data is sanitized before logging."""
        sensitive_data = {
            "action": "helper_execution",
            "helper_id": "test_helper",
            "exchange_api_key": "secret_key_12345",
            "user_input": {
                "password": "user_password",
                "normal_field": "normal_value"
            },
            "error": "Authentication failed with key: sk_test_abcdef123456"
        }
        
        sanitized = sanitize_audit_data(sensitive_data)
        
        # Sensitive fields should be redacted
        self.assertEqual(sanitized["exchange_api_key"], "****")
        self.assertEqual(sanitized["user_input"]["password"], "****")
        self.assertIn("****", sanitized["error"])
        
        # Non-sensitive fields should remain
        self.assertEqual(sanitized["action"], "helper_execution")
        self.assertEqual(sanitized["helper_id"], "test_helper")
        self.assertEqual(sanitized["user_input"]["normal_field"], "normal_value")
    
    def test_nested_data_sanitization(self):
        """Test sanitization of deeply nested data structures."""
        nested_data = {
            "level1": {
                "level2": {
                    "api_key": "secret123",
                    "normal_data": "safe"
                },
                "tokens": ["token1", "bearer_abc123def456ghi789"]
            }
        }
        
        sanitized = sanitize_audit_data(nested_data)
        
        self.assertEqual(sanitized["level1"]["level2"]["api_key"], "****")
        self.assertEqual(sanitized["level1"]["level2"]["normal_data"], "safe")
        # List items should be sanitized too
        self.assertIn("****", str(sanitized["level1"]["tokens"]))
    
    def test_audit_log_entry_sanitization(self):
        """Test that entries logged to audit log are sanitized."""
        entry = {
            "ts": "2025-08-17T12:00:00.000000Z",
            "action": "test_action",
            "exchange_secret": "very_secret_key_12345",
            "safe_data": "this_is_safe"
        }
        
        # Log the entry
        self.logger.log_entry(entry)
        
        # Read the log file and verify sanitization
        with open(self.audit_log, 'r') as f:
            log_content = f.read()
        
        # Should not contain the original secret
        self.assertNotIn("very_secret_key_12345", log_content)
        # Should contain redacted value
        self.assertIn('"****"', log_content)
        # Should contain safe data
        self.assertIn("this_is_safe", log_content)


class TestHelperSanitization(unittest.TestCase):
    """Test helper execution sanitization."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_helper_dir = Path(self.temp_dir) / "test_helper"
        self.test_helper_dir.mkdir()
        
        # Create a mock helper with sensitive environment requirements
        helper_manifest = {
            "purpose": "Test helper for sanitization",
            "schema": {},
            "capabilities": {"preview": True, "execute": True},
            "sandbox": {"commands": ["echo"], "timeouts": [{"name": "default", "seconds": 5}]},
            "environment": {"required": ["EXCHANGE_API_KEY", "EXCHANGE_SECRET"]}
        }
        
        manifest_file = self.test_helper_dir / "helper.yaml"
        with open(manifest_file, 'w') as f:
            import yaml
            yaml.dump(helper_manifest, f)
        
        # Set up test environment with sensitive values
        self.test_env = {
            "EXCHANGE_API_KEY": "secret_api_key_12345",
            "EXCHANGE_SECRET": "secret_exchange_key_67890",
            "DEBUG": "true"
        }
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_helper_input_sanitization(self):
        """Test that helper input data is sanitized in audit logs."""
        from sdk import HelperExecutor
        
        # Test the _sanitize_input_data method directly
        mock_registry = MagicMock()
        executor = HelperExecutor(mock_registry)
        
        # Test input with sensitive data
        sensitive_input = {
            "operation": "test",
            "api_key": "sk_live_very_long_secret_key_12345",  # This should be caught by sensitive prefixes
            "password": "user_password",
            "normal_field": "safe_value"
        }
        
        # Test the sanitization method directly
        sanitized_input = executor._sanitize_input_data(sensitive_input)
        
        # Verify sensitive data was sanitized
        self.assertEqual(sanitized_input.get("api_key"), "****")
        self.assertEqual(sanitized_input.get("password"), "****") 
        self.assertEqual(sanitized_input.get("normal_field"), "safe_value")  # Non-sensitive should remain


class TestIntegrationScenarios(unittest.TestCase):
    """Test end-to-end sanitization scenarios."""
    
    def test_helper_with_exchange_credentials(self):
        """Test that helper requiring EXCHANGE_API_KEY has secrets sanitized."""
        # Simulate a helper execution scenario
        test_env = {
            "EXCHANGE_API_KEY": "sk_live_abc123def456ghi789",
            "EXCHANGE_SECRET": "secret_exchange_key_xyz987",
            "EXCHANGE_PASSPHRASE": "my_secret_passphrase"
        }
        
        # Test environment sanitization
        sanitized_env = sanitize_env(test_env)
        
        # All exchange credentials should be redacted
        self.assertEqual(sanitized_env["EXCHANGE_API_KEY"], "****")
        self.assertEqual(sanitized_env["EXCHANGE_SECRET"], "****")
        self.assertEqual(sanitized_env["EXCHANGE_PASSPHRASE"], "****")
        
        # Test audit logging of helper execution with environment
        audit_entry = {
            "action": "helper_execution",
            "helper_id": "bot_guard",
            "environment": sanitized_env,
            "input_data": {
                "operation": "get_positions",
                "api_key": "sk_live_abc123def456ghi789"  # This should also be sanitized
            }
        }
        
        sanitized_audit = sanitize_audit_data(audit_entry)
        
        # Verify double sanitization doesn't break anything
        self.assertEqual(sanitized_audit["environment"]["EXCHANGE_API_KEY"], "****")
        self.assertEqual(sanitized_audit["input_data"]["api_key"], "****")
    
    def test_error_response_sanitization(self):
        """Test that error responses are sanitized."""
        from tinyrpc import sanitize_sensitive_string
        
        error_messages = [
            "Authentication failed with key sk_test_abc123def456",
            "API call failed: Bearer abc123def456ghi789 invalid",
            "Environment variable EXCHANGE_API_KEY=secret123456789012345 not found",  # Made longer
            "Database connection failed with password: supersecret123456789"  # Made longer
        ]
        
        for error_msg in error_messages:
            sanitized = sanitize_sensitive_string(error_msg)
            
            # Should not contain original sensitive values
            self.assertNotIn("sk_test_abc123def456", sanitized)
            self.assertNotIn("abc123def456ghi789", sanitized)
            self.assertNotIn("secret123456789012345", sanitized)
            self.assertNotIn("supersecret123456789", sanitized)
            
            # Should contain redacted placeholders
            self.assertIn("****", sanitized)
    
    def test_json_response_sanitization(self):
        """Test sanitization of JSON responses."""
        from tinyrpc import sanitize_sensitive_data
        
        response_data = {
            "status": "error",
            "error": "Invalid credentials",
            "details": {
                "provided_key": "sk_live_abc123def456ghi789",
                "expected_format": "API key format",
                "environment": {
                    "EXCHANGE_API_KEY": "sk_live_xyz987",
                    "DEBUG": "true"
                }
            },
            "trace": "Error in line 42: api_key sk_live_abc123def456ghi789 rejected"
        }
        
        sanitized = sanitize_sensitive_data(response_data)
        
        # Verify all sensitive data is redacted
        self.assertEqual(sanitized["details"]["provided_key"], "****")
        self.assertEqual(sanitized["details"]["environment"]["EXCHANGE_API_KEY"], "****")
        self.assertEqual(sanitized["details"]["environment"]["DEBUG"], "true")  # Non-sensitive preserved
        self.assertIn("****", sanitized["trace"])
        
        # Convert to JSON and verify no secrets leaked
        json_str = json.dumps(sanitized)
        self.assertNotIn("sk_live_abc123def456ghi789", json_str)
        self.assertNotIn("sk_live_xyz987", json_str)


class TestSanitizationPatterns(unittest.TestCase):
    """Test specific sanitization patterns and edge cases."""
    
    def test_partial_matches(self):
        """Test that partial matches are handled correctly."""
        # These should NOT be sanitized (too short or not matching pattern)
        safe_strings = [
            "key",  # Too short
            "secret",  # Too short  
            "api_short",  # API key but too short
            "text_with_key_word",  # Contains "key" but shorter than 40 chars
            "api_1234567890abc",  # API key but just under 15 chars
        ]
        
        for safe_str in safe_strings:
            result = sanitize_sensitive_string(safe_str)
            self.assertEqual(result, safe_str, f"'{safe_str}' was incorrectly sanitized")
    
    def test_mixed_content(self):
        """Test sanitization of mixed sensitive and non-sensitive content."""
        mixed_text = """
        Configuration:
        - API_KEY: sk_live_abcdef123456
        - DEBUG: true
        - DATABASE_URL: postgres://localhost
        - SECRET_TOKEN: secret_xyz789abc123456789
        - LOG_LEVEL: info
        """
        
        result = sanitize_sensitive_string(mixed_text)
        
        # Sensitive parts should be redacted
        self.assertNotIn("sk_live_abcdef123456", result)
        self.assertNotIn("secret_xyz789abc123456789", result)
        
        # Non-sensitive parts should remain
        self.assertIn("DEBUG: true", result)
        self.assertIn("DATABASE_URL: postgres://localhost", result)
        self.assertIn("LOG_LEVEL: info", result)
    
    def test_boundary_conditions(self):
        """Test boundary conditions for sanitization patterns."""
        # Test minimum length thresholds
        boundary_cases = [
            ("a" * 39, "a" * 39),  # 39 chars - should not be redacted
            ("a" * 40, "****"),    # 40 chars - should be redacted
            ("api_" + "a" * 14, "api_" + "a" * 14),  # API key with 14 chars - not redacted
            ("api_" + "a" * 15, "api_****"),  # API key with 15 chars - redacted
            ("secret_" + "a" * 9, "secret_" + "a" * 9),  # Secret key with 9 chars - not redacted
            ("secret_" + "a" * 10, "secret_****"),  # Secret key with 10 chars - redacted
        ]
        
        for input_str, expected in boundary_cases:
            result = sanitize_sensitive_string(input_str)
            self.assertEqual(result, expected, f"Boundary case failed: '{input_str}'")


if __name__ == "__main__":
    unittest.main()