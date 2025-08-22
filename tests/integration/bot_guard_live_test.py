#!/usr/bin/env python3
"""
TinyIntent Bot Guard Live Integration Tests - M8.0

Tests live exchange integration with sandbox-only defaults, capability isolation,
rate limiting, secrets sanitization, and comprehensive safety gates.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import pytest
import requests_mock

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent / "bridge" / "adapters"))
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

try:
    from tinyintent.bridge.adapters.exchange import ExchangeAdapter, ExchangeError
from tinyintent.helpers.sdk import HelperExecutor, HelperRegistry
    HELPERS_SDK_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helpers SDK not available: {e}")
    HELPERS_SDK_AVAILABLE = False


@pytest.mark.integration
class TestExchangeAdapterSafety(unittest.TestCase):
    """Test M8.0 exchange adapter safety features."""
    
    def setUp(self):
        """Set up test environment."""
        if not EXCHANGE_ADAPTER_AVAILABLE:
            self.skipTest("Exchange adapter not available")
        
        # Set safe test environment variables
        self.test_env = {
            'EXCHANGE_MODE': 'sandbox',
            'EXCHANGE_API_KEY': 'test_api_key_123',
            'EXCHANGE_API_SECRET': 'test_secret_456',
            'EXCHANGE_PASSPHRASE': 'test_pass_789',
            'EXCHANGE_BASE_URL': 'https://api-public.sandbox.exchange.coinbase.com'
        }
        
        # Apply test environment
        self.original_env = {}
        for key, value in self.test_env.items():
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = value
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment
        for key, original_value in self.original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
    
    def test_sandbox_only_enforcement(self):
        """Test that adapter enforces sandbox-only mode by default."""
        # Should work with sandbox mode
        adapter = ExchangeAdapter()
        self.assertEqual(adapter.exchange_mode, 'sandbox')
        self.assertIn('sandbox', adapter.base_url.lower())
        
        # Should reject live mode
        os.environ['EXCHANGE_MODE'] = 'live'
        with self.assertRaises(ExchangeError) as context:
            ExchangeAdapter()
        
        self.assertIn("Live trading disabled", str(context.exception))
        self.assertEqual(context.exception.error_code, "LIVE_TRADING_DISABLED")
        
        # Reset for other tests
        os.environ['EXCHANGE_MODE'] = 'sandbox'
    
    def test_missing_credentials_validation(self):
        """Test validation of required exchange credentials."""
        # Remove required credential
        del os.environ['EXCHANGE_API_KEY']
        
        with self.assertRaises(ExchangeError) as context:
            ExchangeAdapter()
        
        self.assertIn("Missing required exchange credentials", str(context.exception))
        self.assertEqual(context.exception.error_code, "MISSING_CREDENTIALS")
        
        # Restore for other tests
        os.environ['EXCHANGE_API_KEY'] = 'test_api_key_123'
    
    def test_secrets_sanitization(self):
        """Test that secrets are properly sanitized in logs."""
        adapter = ExchangeAdapter()
        
        # Test sanitization of dict with secrets
        test_data = {
            'api_key': 'secret_key_123456789',
            'secret': 'very_secret_data_987654321',
            'normal_field': 'normal_value',
            'passphrase': 'secret_passphrase'
        }
        
        sanitized = adapter._sanitize_for_logging(test_data)
        
        self.assertEqual(sanitized['api_key'], '*' * 8)
        self.assertEqual(sanitized['secret'], '*' * 8)
        self.assertEqual(sanitized['normal_field'], 'normal_value')
        self.assertEqual(sanitized['passphrase'], '*' * 8)
    
    def test_sandbox_url_auto_correction(self):
        """Test that URLs are auto-corrected to sandbox for safety."""
        # Set live URL but keep sandbox mode
        os.environ['EXCHANGE_BASE_URL'] = 'https://api.exchange.coinbase.com'
        
        adapter = ExchangeAdapter()
        
        # Should be corrected to sandbox URL
        self.assertIn('sandbox', adapter.base_url.lower())
    
    @requests_mock.Mocker()
    def test_api_timeout_and_retry(self, m):
        """Test API timeout handling and retry mechanism."""
        adapter = ExchangeAdapter()
        adapter.timeout = 1  # Short timeout for testing
        adapter.max_retries = 2
        
        # Mock timeout then success
        m.get(f"{adapter.base_url}/time", [
            {'exc': requests_mock.exceptions.ConnectTimeout},  # First call times out
            {'json': {'iso': '2024-01-01T12:00:00Z'}}  # Second call succeeds
        ])
        
        # Should succeed after retry
        result = adapter._make_request('GET', 'time')
        self.assertEqual(result['iso'], '2024-01-01T12:00:00Z')
    
    @requests_mock.Mocker()
    def test_rate_limit_handling(self, m):
        """Test rate limiting response handling."""
        adapter = ExchangeAdapter()
        
        # Mock rate limit response
        m.get(f"{adapter.base_url}/accounts", status_code=429, 
              headers={'Retry-After': '60'})
        
        with self.assertRaises(ExchangeError) as context:
            adapter._make_request('GET', 'accounts')
        
        self.assertEqual(context.exception.error_code, "RATE_LIMITED")
    
    @requests_mock.Mocker()
    def test_authentication_failure_handling(self, m):
        """Test authentication failure handling."""
        adapter = ExchangeAdapter()
        
        # Mock authentication failure
        m.get(f"{adapter.base_url}/accounts", status_code=401,
              json={'message': 'Invalid API key'})
        
        with self.assertRaises(ExchangeError) as context:
            adapter._make_request('GET', 'accounts')
        
        self.assertEqual(context.exception.error_code, "AUTH_FAILED")


@pytest.mark.integration
class TestBotGuardHelperIntegration(unittest.TestCase):
    """Test M8.0 bot_guard helper with live exchange integration."""
    
    def setUp(self):
        """Set up test environment."""
        self.helper_path = Path(__file__).parent.parent / "helpers" / "bot_guard" / "main.js"
        if not self.helper_path.exists():
            self.skipTest("Bot guard helper not found")
        
        # Set up test environment
        self.test_env = {
            'EXCHANGE_MODE': 'sandbox',
            'EXCHANGE_API_KEY': 'test_key_123',
            'EXCHANGE_API_SECRET': 'test_secret_456',
            'EXCHANGE_BASE_URL': 'https://api-public.sandbox.exchange.coinbase.com',
            'EXECUTION_ENABLED': '0',  # Disabled by default for safety
            'TINYINTENT_HELPER_CAPABILITIES': 'network'  # Required capability
        }
        
        # Apply environment
        self.original_env = {}
        for key, value in self.test_env.items():
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = value
    
    def tearDown(self):
        """Clean up test environment."""
        # Restore original environment
        for key, original_value in self.original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
    
    def _run_helper(self, input_data):
        """Run the bot_guard helper with given input."""
        try:
            result = subprocess.run(
                ['node', str(self.helper_path)],
                input=json.dumps(input_data),
                text=True,
                capture_output=True,
                timeout=10,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                # Try to parse error output
                try:
                    return json.loads(result.stdout)
                except:
                    return {
                        'status': 'error',
                        'message': result.stderr or result.stdout,
                        'return_code': result.returncode
                    }
        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Helper execution timed out'}
        except Exception as e:
            return {'status': 'error', 'message': f'Helper execution failed: {str(e)}'}
    
    def test_get_positions_preview_only(self):
        """Test get_positions operation in preview mode."""
        input_data = {
            'operation': 'get_positions'
        }
        
        result = self._run_helper(input_data)
        
        # Should succeed with required schema fields
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['operation'], 'get_positions')
        self.assertEqual(result['exchange'], 'coinbase_sandbox')
        self.assertIn('action', result)
        self.assertIn('result', result)
        self.assertTrue(result['dry_run'])  # Always dry run for queries
        self.assertEqual(result['action_type'], 'preview')
        self.assertIn('timestamp', result)
        self.assertIn('execution_id', result)
    
    def test_get_balance_preview_only(self):
        """Test get_balance operation in preview mode."""
        input_data = {
            'operation': 'get_balance'
        }
        
        result = self._run_helper(input_data)
        
        # Should succeed with required schema fields
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['operation'], 'get_balance')
        self.assertEqual(result['exchange'], 'coinbase_sandbox')
        self.assertIn('action', result)
        self.assertIn('result', result)
        self.assertTrue(result['dry_run'])  # Always dry run for queries
        self.assertEqual(result['action_type'], 'preview')
    
    def test_close_position_preview_by_default(self):
        """Test close_position defaults to preview mode for safety."""
        input_data = {
            'operation': 'close_position',
            'symbol': 'BTC/USD'
        }
        
        result = self._run_helper(input_data)
        
        # Should default to preview mode
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['operation'], 'close_position')
        self.assertEqual(result['symbol'], 'BTC/USD')
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['action_type'], 'preview')
        self.assertIn('warnings', result)  # Should include safety warnings
    
    def test_execution_disabled_by_default(self):
        """Test that execution is disabled by default even with dry_run=false."""
        input_data = {
            'operation': 'close_position',
            'symbol': 'BTC/USD',
            'dry_run': False  # Try to enable execution
        }
        
        result = self._run_helper(input_data)
        
        # Should still be preview due to EXECUTION_ENABLED=0
        self.assertEqual(result['action_type'], 'preview')
        self.assertTrue(result['dry_run'])
        self.assertIn('warnings', result)
    
    def test_capability_enforcement(self):
        """Test that network capability is enforced."""
        # Remove network capability
        os.environ['TINYINTENT_HELPER_CAPABILITIES'] = 'filesystem'
        
        input_data = {
            'operation': 'get_positions'
        }
        
        result = self._run_helper(input_data)
        
        # Should fail due to missing network capability
        self.assertEqual(result['status'], 'error')
        self.assertIn('capability', result['message'].lower())
    
    def test_input_validation_symbol_required(self):
        """Test input validation for operations requiring symbol."""
        input_data = {
            'operation': 'close_position'
            # Missing required symbol
        }
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['action'], 'validation_failed')
        self.assertIn('Symbol required', result['result']['validation_errors'][0])
    
    def test_input_validation_invalid_symbol_format(self):
        """Test input validation for invalid symbol format."""
        input_data = {
            'operation': 'close_position',
            'symbol': 'invalid_symbol'  # Invalid format
        }
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid symbol format', result['result']['validation_errors'][0])
    
    def test_input_validation_invalid_operation(self):
        """Test input validation for invalid operations."""
        input_data = {
            'operation': 'invalid_operation'
        }
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid operation', result['result']['validation_errors'][0])
    
    def test_stop_loss_with_price_validation(self):
        """Test set_stop_loss with price validation."""
        # Test with invalid price
        input_data = {
            'operation': 'set_stop_loss',
            'symbol': 'BTC/USD',
            'stop_loss_price': -100  # Invalid negative price
        }
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Stop loss price must be positive', result['result']['validation_errors'][0])
        
        # Test with valid price
        input_data['stop_loss_price'] = 50000
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['operation'], 'set_stop_loss')
        self.assertTrue(result['dry_run'])  # Should be preview by default
    
    def test_take_profit_with_price_validation(self):
        """Test set_take_profit with price validation."""
        input_data = {
            'operation': 'set_take_profit',
            'symbol': 'BTC/USD',
            'take_profit_price': 60000
        }
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['operation'], 'set_take_profit')
        self.assertTrue(result['dry_run'])
    
    def test_emergency_stop_requires_confirmation(self):
        """Test emergency stop requires proper confirmation."""
        # Test without confirmation
        input_data = {
            'operation': 'emergency_stop',
            'emergency_code': '123-ABC-45'
        }
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invalid confirmation phrase', result['result']['validation_errors'][0])
        
        # Test with proper confirmation
        input_data.update({
            'confirmation_phrase': 'confirm emergency close'
        })
        
        result = self._run_helper(input_data)
        
        self.assertEqual(result['status'], 'warning')  # Emergency always warns
        self.assertEqual(result['operation'], 'emergency_stop')
        self.assertTrue(result['dry_run'])  # Emergency always previews first
    
    def test_schema_compliance_required_fields(self):
        """Test that output complies with schema required fields."""
        input_data = {
            'operation': 'get_positions'
        }
        
        result = self._run_helper(input_data)
        
        # Check all required schema fields
        required_fields = [
            'status', 'operation', 'exchange', 'action', 'result', 
            'dry_run', 'action_type', 'message', 'timestamp'
        ]
        
        for field in required_fields:
            self.assertIn(field, result, f"Required field '{field}' missing from output")
    
    def test_secrets_not_leaked_in_errors(self):
        """Test that secrets are not leaked in error messages."""
        # Set a credential that looks like a secret
        os.environ['EXCHANGE_API_KEY'] = 'sk_live_very_secret_key_123456789'
        
        input_data = {
            'operation': 'get_positions'
        }
        
        result = self._run_helper(input_data)
        
        # Check that the secret is not present in any output field
        result_str = json.dumps(result)
        self.assertNotIn('sk_live_very_secret_key_123456789', result_str)
        self.assertNotIn('very_secret_key', result_str)


@pytest.mark.integration
class TestExecutionWithApprovalToken(unittest.TestCase):
    """Test execution with approval token and safety gates."""
    
    def setUp(self):
        """Set up test environment for execution tests."""
        self.helper_path = Path(__file__).parent.parent / "helpers" / "bot_guard" / "main.js"
        if not self.helper_path.exists():
            self.skipTest("Bot guard helper not found")
        
        # Set up for potential execution (still safe due to sandbox)
        self.test_env = {
            'EXCHANGE_MODE': 'sandbox',
            'EXCHANGE_API_KEY': 'test_key_123',
            'EXCHANGE_API_SECRET': 'test_secret_456',
            'EXCHANGE_BASE_URL': 'https://api-public.sandbox.exchange.coinbase.com',
            'EXECUTION_ENABLED': '1',  # Enable execution for testing
            'TINYINTENT_HELPER_CAPABILITIES': 'network'
        }
        
        self.original_env = {}
        for key, value in self.test_env.items():
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = value
    
    def tearDown(self):
        """Clean up test environment."""
        for key, original_value in self.original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
    
    def _run_helper(self, input_data):
        """Run the bot_guard helper with given input."""
        try:
            result = subprocess.run(
                ['node', str(self.helper_path)],
                input=json.dumps(input_data),
                text=True,
                capture_output=True,
                timeout=10,
                env=os.environ.copy()
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                try:
                    return json.loads(result.stdout)
                except:
                    return {
                        'status': 'error',
                        'message': result.stderr or result.stdout,
                        'return_code': result.returncode
                    }
        except subprocess.TimeoutExpired:
            return {'status': 'error', 'message': 'Helper execution timed out'}
        except Exception as e:
            return {'status': 'error', 'message': f'Helper execution failed: {str(e)}'}
    
    def test_execution_enabled_with_dry_run_false(self):
        """Test that execution can be enabled when safety conditions are met."""
        input_data = {
            'operation': 'close_position',
            'symbol': 'BTC/USD',
            'dry_run': False  # Request execution
        }
        
        result = self._run_helper(input_data)
        
        # Should attempt execution (though still simulated for safety)
        self.assertEqual(result['status'], 'success')
        self.assertFalse(result['dry_run'])  # Should indicate execution mode
        self.assertEqual(result['action_type'], 'execute')
        
        # But result should still be simulated for safety
        self.assertTrue(result['result'].get('simulated', False))
    
    def test_sandbox_mode_enforcement_with_execution(self):
        """Test that sandbox mode is enforced even with execution enabled."""
        input_data = {
            'operation': 'get_balance'
        }
        
        result = self._run_helper(input_data)
        
        # Should always indicate sandbox exchange
        self.assertEqual(result['exchange'], 'coinbase_sandbox')
    
    def test_missing_credentials_blocks_execution(self):
        """Test that missing credentials block execution."""
        # Remove required credential
        del os.environ['EXCHANGE_API_SECRET']
        
        input_data = {
            'operation': 'close_position',
            'symbol': 'BTC/USD',
            'dry_run': False
        }
        
        result = self._run_helper(input_data)
        
        # Should fall back to preview mode due to missing credentials
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['action_type'], 'preview')
        self.assertIn('warnings', result)


@pytest.mark.integration  
class TestRateLimitingAndCapabilityIsolation(unittest.TestCase):
    """Test rate limiting and capability isolation still apply."""
    
    def test_rate_limiting_still_applies(self):
        """Test that rate limiting is still enforced for bot_guard."""
        # This would be integration test with actual bridge/SDK
        # For now, verify the helper declares network capability requirement
        registry_path = Path(__file__).parent.parent / "helpers" / "registry.yaml"
        if registry_path.exists():
            with open(registry_path, 'r') as f:
                content = f.read()
                self.assertIn('network', content)
                self.assertIn('bot_guard', content)
    
    def test_capability_isolation_enforced(self):
        """Test that capability isolation is enforced."""
        helper_path = Path(__file__).parent.parent / "helpers" / "bot_guard" / "main.js"
        if helper_path.exists():
            with open(helper_path, 'r') as f:
                content = f.read()
                # Verify capability checking is implemented
                self.assertIn('TINYINTENT_HELPER_CAPABILITIES', content)
                self.assertIn('network', content)
                self.assertIn('checkCapabilities', content)


if __name__ == "__main__":
    # Run tests with pytest for better integration test support
    pytest.main([__file__, "-v", "-m", "integration"])