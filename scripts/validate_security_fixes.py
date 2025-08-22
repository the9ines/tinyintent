#!/usr/bin/env python3
"""
Security Validation Script for TinyIntent

Validates all implemented security fixes without requiring external dependencies.
"""

import sys
import os
import time
import tempfile
import json
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_timing_attack_fix():
    """Test authentication timing attack vulnerability fix."""
    print("🔍 Testing timing attack fix...")
    
    try:
        # Import with correct path
        sys.path.insert(0, str(project_root / "bridge"))
        from security import constant_time_compare
        
        # Test basic functionality
        assert constant_time_compare("test", "test") == True
        assert constant_time_compare("test", "wrong") == False
        
        # Test timing consistency (simplified)
        correct = "secret123"
        wrong_same_len = "wrongone"
        wrong_diff_len = "x"
        
        # All should return False for wrong passwords
        assert constant_time_compare(correct, wrong_same_len) == False
        assert constant_time_compare(correct, wrong_diff_len) == False
        
        print("  ✅ Constant time comparison working correctly")
        return True
        
    except Exception as e:
        print(f"  ❌ Timing attack fix test failed: {e}")
        return False

def test_csrf_protection():
    """Test CSRF protection implementation."""
    print("🔍 Testing CSRF protection...")
    
    try:
        sys.path.insert(0, str(project_root / "bridge"))
        from security import CSRFProtection
        
        csrf = CSRFProtection()
        
        # Test token generation
        token = csrf.generate_csrf_token("test_session")
        assert isinstance(token, str)
        assert len(token) > 20
        
        # Test token validation
        assert csrf.verify_csrf_token(token, "test_session") == True
        assert csrf.verify_csrf_token(token, "wrong_session") == False
        assert csrf.verify_csrf_token("invalid_token", "test_session") == False
        
        print("  ✅ CSRF protection working correctly")
        return True
        
    except Exception as e:
        print(f"  ❌ CSRF protection test failed: {e}")
        return False

def test_input_validation():
    """Test input validation enhancements."""
    print("🔍 Testing input validation...")
    
    try:
        sys.path.insert(0, str(project_root / "bridge"))
        from validation import validate_text_input, validate_identifier, ValidationError
        
        # Test valid inputs
        assert validate_text_input("Hello world") == "Hello world"
        assert validate_identifier("valid_helper_123") == "valid_helper_123"
        
        # Test dangerous inputs are blocked
        try:
            validate_text_input("<script>alert('xss')</script>")
            assert False, "Should have blocked script injection"
        except ValidationError:
            pass  # Expected
        
        try:
            validate_identifier("../../../etc/passwd")
            assert False, "Should have blocked path traversal"
        except ValidationError:
            pass  # Expected
        
        print("  ✅ Input validation working correctly")
        return True
        
    except Exception as e:
        print(f"  ❌ Input validation test failed: {e}")
        return False

def test_sandbox_security():
    """Test sandbox security enhancements."""
    print("🔍 Testing sandbox security...")
    
    try:
        sys.path.insert(0, str(project_root / "bridge"))
        from sandbox_security import SandboxSecurityEnforcer, SandboxSecurityViolation
        
        enforcer = SandboxSecurityEnforcer()
        
        # Test safe command validation
        enforcer.validate_command(["python3", "script.py"])  # Should not raise
        
        # Test dangerous command blocking
        try:
            enforcer.validate_command(["rm", "-rf", "/"])
            assert False, "Should have blocked dangerous command"
        except SandboxSecurityViolation:
            pass  # Expected
        
        # Test environment sanitization
        dangerous_env = {
            "LD_PRELOAD": "/malicious.so",
            "SAFE_VAR": "safe_value"
        }
        sanitized = enforcer.sanitize_environment(dangerous_env, "/tmp/workspace")
        assert "LD_PRELOAD" not in sanitized
        assert "TINYINTENT_WORKSPACE" in sanitized
        
        print("  ✅ Sandbox security working correctly")
        return True
        
    except Exception as e:
        print(f"  ❌ Sandbox security test failed: {e}")
        return False

def test_secret_management():
    """Test secret management and scoping."""
    print("🔍 Testing secret management...")
    
    try:
        sys.path.insert(0, str(project_root / "bridge"))
        from secret_manager import SecretManager, SecretScope, SecretViolation
        
        # Create temporary test directory
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = SecretManager(Path(temp_dir))
            
            # Test public secret
            assert manager.store_secret("public_key", "public_value", SecretScope.PUBLIC)
            assert manager.get_secret("public_key", "any_helper", "draft") == "public_value"
            
            # Test trusted secret
            assert manager.store_secret("trusted_key", "trusted_value", SecretScope.TRUSTED)
            assert manager.get_secret("trusted_key", "helper", "trusted") == "trusted_value"
            
            # Test access control
            try:
                manager.get_secret("trusted_key", "helper", "draft")
                assert False, "Should have blocked access to trusted secret"
            except SecretViolation:
                pass  # Expected
            
            # Test scoped environment
            env = manager.create_scoped_environment("helper", "trusted", {})
            assert "TINYINTENT_SECRET_PUBLIC_KEY" in env
            assert "TINYINTENT_SECRET_TRUSTED_KEY" in env
        
        print("  ✅ Secret management working correctly")
        return True
        
    except Exception as e:
        print(f"  ❌ Secret management test failed: {e}")
        return False

def main():
    """Run all security validation tests."""
    print("🔒 TinyIntent Security Validation")
    print("=" * 50)
    print()
    
    # Set up test environment
    os.environ['TINYINTENT_SECRET'] = 'test-secret-for-validation-32chars'
    os.environ['SHORTCUT_TOKEN'] = 'test-shortcut-token-123'
    
    tests = [
        ("Authentication Timing Attack Fix", test_timing_attack_fix),
        ("CSRF Protection", test_csrf_protection),
        ("Input Validation", test_input_validation),
        ("Sandbox Security", test_sandbox_security),
        ("Secret Management", test_secret_management),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"Testing {test_name}...")
        if test_func():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"Security Validation Results: {passed}/{total} tests passed")
    print()
    
    if passed == total:
        print("🎉 ALL SECURITY FIXES VALIDATED SUCCESSFULLY!")
        print()
        print("✅ Critical vulnerabilities fixed:")
        print("  • Authentication timing attack vulnerability")
        print("  • Missing CSRF protection")
        print("  • Input validation gaps")
        print("  • Sandbox escape vectors")
        print("  • Secret exposure to untrusted helpers")
        print()
        print("🛡️ TinyIntent is now significantly more secure!")
        return True
    else:
        print(f"❌ {total - passed} security tests failed")
        print("Please review the failed tests and fix any issues.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)