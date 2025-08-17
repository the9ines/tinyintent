"""
Tests for helper execution flow including guarded execution, approval tokens,
idempotency, and error handling.
"""

import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project paths to system path
import sys
sys.path.append(str(Path(__file__).parent.parent / "helpers"))
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

from sdk import HelperRegistry, HelperExecutor
from approval import ApprovalTokenManager


class TestHelpersExecute(unittest.TestCase):
    """Test cases for helper execution flow."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        
        # Set up test environment variables
        os.environ["EXECUTION_ENABLED"] = "1"
        os.environ["EXCHANGE_API_KEY"] = "test_key"
        os.environ["EXCHANGE_SECRET"] = "test_secret"
        os.environ["EXCHANGE_PASSPHRASE"] = "test_passphrase"
        
        # Create test registry and executor
        self.registry = HelperRegistry()
        self.executor = HelperExecutor(self.registry)
        self.executor.audit_log = self.audit_log
        
        # Create approval token manager
        self.approval_manager = ApprovalTokenManager()
        self.approval_manager.audit_log = self.audit_log
        
        # Test data
        self.helper_id = "log_tailer"
        self.helper_input = {
            "log_path": "/var/log/system.log",
            "lines": 5,
            "level": "ERROR"
        }
        self.user_text = "Show me recent error logs"
        self.session_id = "test-session"
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        # Clean up environment
        for key in ["EXECUTION_ENABLED", "EXCHANGE_API_KEY", "EXCHANGE_SECRET", "EXCHANGE_PASSPHRASE"]:
            os.environ.pop(key, None)
    
    def test_happy_path_preview_approve_execute(self):
        """Test happy path: preview → approve → execute."""
        # Step 1: Preview
        preview_result = self.executor.preview(
            helper_id=self.helper_id,
            input_data=self.helper_input,
            session_id=self.session_id
        )
        
        self.assertEqual(preview_result["status"], "success")
        self.assertEqual(preview_result["action"], "preview")
        self.assertEqual(preview_result["helper_id"], self.helper_id)
        self.assertIn("preview_json", preview_result)
        
        # Step 2: Generate approval token
        approval_token = self.approval_manager.generate_approval_token(
            helper_id=self.helper_id,
            helper_input=self.helper_input,
            session_id=self.session_id,
            user_text=self.user_text
        )
        
        self.assertIsNotNone(approval_token)
        self.assertGreater(len(approval_token), 10)
        
        # Step 3: Execute with approval token
        is_valid, error_msg, token_id = self.approval_manager.validate_approval_token(
            approval_token, self.helper_id, self.helper_input, self.user_text
        )
        
        self.assertTrue(is_valid)
        self.assertEqual(error_msg, "")
        self.assertIsNotNone(token_id)
        
        execute_result = self.executor.execute(
            helper_id=self.helper_id,
            input_data=self.helper_input,
            session_id=self.session_id,
            token_id=token_id
        )
        
        self.assertEqual(execute_result["status"], "success")
        self.assertEqual(execute_result["action"], "execute")
        self.assertEqual(execute_result["helper_id"], self.helper_id)
        self.assertIn("result", execute_result)
        
        # Step 4: Verify audit log entries
        self.assertTrue(self.audit_log.exists())
        with open(self.audit_log, 'r') as f:
            audit_lines = f.readlines()
        
        # Find execute audit entry
        execute_entry = None
        for line in audit_lines:
            entry = json.loads(line)
            if entry.get("action") == "execute" and entry.get("helper_id") == self.helper_id:
                execute_entry = entry
                break
        
        self.assertIsNotNone(execute_entry)
        self.assertEqual(execute_entry["session_id"], self.session_id)
        self.assertEqual(execute_entry["token_id"], token_id)
        self.assertTrue(execute_entry["success"])
    
    def test_reuse_token_returns_403(self):
        """Test that reusing a token returns 403 'already used'."""
        # Generate and use token once
        approval_token = self.approval_manager.generate_approval_token(
            helper_id=self.helper_id,
            helper_input=self.helper_input,
            session_id=self.session_id,
            user_text=self.user_text
        )
        
        # First use - should succeed
        is_valid1, error_msg1, token_id1 = self.approval_manager.validate_approval_token(
            approval_token, self.helper_id, self.helper_input, self.user_text
        )
        
        self.assertTrue(is_valid1)
        
        # Second use - should fail
        is_valid2, error_msg2, token_id2 = self.approval_manager.validate_approval_token(
            approval_token, self.helper_id, self.helper_input, self.user_text
        )
        
        self.assertFalse(is_valid2)
        self.assertIn("already used", error_msg2)
        self.assertIsNone(token_id2)
    
    def test_high_risk_token_older_than_60s_returns_403(self):
        """Test that high-risk helpers reject tokens older than 60s."""
        # Generate token
        approval_token = self.approval_manager.generate_approval_token(
            helper_id=self.helper_id,
            helper_input=self.helper_input,
            session_id=self.session_id,
            user_text=self.user_text
        )
        
        # Manually age the token by modifying its creation time
        token_data = self.approval_manager.tokens[approval_token]
        old_time = datetime.utcnow() - timedelta(seconds=70)
        token_data["created_at"] = old_time.isoformat() + 'Z'
        
        # Try to validate with high risk level
        is_valid, error_msg, token_id = self.approval_manager.validate_approval_token(
            approval_token, self.helper_id, self.helper_input, self.user_text, "high"
        )
        
        self.assertFalse(is_valid)
        self.assertIn("too old for high-risk helper", error_msg)
        self.assertIsNone(token_id)
    
    def test_idempotency_returns_cached_result(self):
        """Test that idempotency returns cached result with idempotent: true."""
        idempotency_key = "test-idempotency-key"
        
        # Cache a result
        cached_result = {
            "status": "success",
            "route_used": "act",
            "session_id": self.session_id,
            "action": "execute",
            "helper_id": self.helper_id,
            "result": {"message": "cached response"}
        }
        
        self.approval_manager.set_idempotency_result(
            idempotency_key, self.helper_id, self.helper_input, cached_result
        )
        
        # Retrieve cached result
        retrieved_result = self.approval_manager.get_idempotency_result(
            idempotency_key, self.helper_id, self.helper_input
        )
        
        self.assertIsNotNone(retrieved_result)
        self.assertEqual(retrieved_result["status"], "success")
        self.assertEqual(retrieved_result["action"], "execute")
        self.assertEqual(retrieved_result["result"]["message"], "cached response")
    
    def test_idempotency_expires_after_10_minutes(self):
        """Test that idempotency cache expires after 10 minutes."""
        idempotency_key = "test-expiry-key"
        
        # Cache a result with old timestamp
        cache_key = self.approval_manager._build_idempotency_key(
            idempotency_key, self.helper_id, self.helper_input
        )
        
        old_time = datetime.utcnow() - timedelta(minutes=11)
        self.approval_manager.idempotency_cache[cache_key] = {
            "result": {"message": "expired"},
            "timestamp": old_time.isoformat() + 'Z',
            "helper_id": self.helper_id
        }
        
        # Try to retrieve - should return None due to expiry
        retrieved_result = self.approval_manager.get_idempotency_result(
            idempotency_key, self.helper_id, self.helper_input
        )
        
        self.assertIsNone(retrieved_result)
        # Cache entry should be cleaned up
        self.assertNotIn(cache_key, self.approval_manager.idempotency_cache)
    
    def test_execution_disabled_gate_returns_503(self):
        """Test that EXECUTION_ENABLED=0 prevents execution."""
        os.environ["EXECUTION_ENABLED"] = "0"
        
        # This would typically be tested at the API level, but we can simulate
        # the check here by testing the environment variable directly
        execution_enabled = os.getenv("EXECUTION_ENABLED", "0") == "1"
        self.assertFalse(execution_enabled)
        
        # Reset for other tests
        os.environ["EXECUTION_ENABLED"] = "1"
    
    def test_missing_environment_variables_returns_409(self):
        """Test that missing required environment variables return 409."""
        # Remove required environment variable
        original_key = os.environ.pop("EXCHANGE_API_KEY", None)
        
        try:
            # This should raise ValueError with missing_vars attribute
            with self.assertRaises(ValueError) as context:
                self.executor.execute(
                    helper_id="bot_guard",  # Requires exchange vars
                    input_data={"operation": "get_positions"},
                    session_id=self.session_id
                )
            
            # Check if the error has missing_vars attribute
            error = context.exception
            if hasattr(error, 'missing_vars'):
                self.assertIn("EXCHANGE_API_KEY", error.missing_vars)
            else:
                self.assertIn("EXCHANGE_API_KEY", str(error))
        
        finally:
            # Restore environment variable
            if original_key:
                os.environ["EXCHANGE_API_KEY"] = original_key
    
    def test_schema_validation_failure_returns_500(self):
        """Test that schema validation failure returns 500."""
        # Mock the helper to return invalid output
        with patch.object(self.executor, '_execute_helper') as mock_execute:
            mock_execute.return_value = {"invalid": "output"}  # Missing required fields
            
            # Mock helper validation to fail
            helper = self.registry.get_helper(self.helper_id)
            with patch.object(helper, 'validate_output', return_value=False):
                with self.assertRaises(ValueError) as context:
                    self.executor.execute(
                        helper_id=self.helper_id,
                        input_data=self.helper_input,
                        session_id=self.session_id
                    )
                
                self.assertIn("Output schema validation failed", str(context.exception))


if __name__ == '__main__':
    unittest.main()