#!/usr/bin/env python3
"""
Security Test Runner for TinyIntent

Runs comprehensive security tests for all implemented security fixes.
"""

import sys
import subprocess
import os
from pathlib import Path

def main():
    """Run security tests and report results."""
    print("🔒 TinyIntent Security Test Suite")
    print("=" * 50)
    
    # Set up environment
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    # Add project to Python path
    env = os.environ.copy()
    env['PYTHONPATH'] = str(project_root)
    
    # Set test environment variables
    env['TINYINTENT_SECRET'] = 'test-secret-for-testing-32chars'
    env['SHORTCUT_TOKEN'] = 'test-shortcut-token-123'
    
    print("Running security tests...")
    print()
    
    try:
        # Run security tests
        result = subprocess.run([
            sys.executable, '-m', 'pytest', 
            'tests/test_security_fixes.py',
            '-v',
            '--tb=short',
            '--color=yes'
        ], env=env, capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ All security tests passed!")
            print()
            print("Security fixes validated:")
            print("  ✅ Authentication timing attack vulnerability fixed")
            print("  ✅ CSRF protection implemented")
            print("  ✅ Input validation gaps closed")
            print("  ✅ Sandbox security strengthened")
            print("  ✅ Secret scoping implemented")
            print()
            print("🎉 TinyIntent security hardening complete!")
        else:
            print("❌ Some security tests failed!")
            print(f"Exit code: {result.returncode}")
            return False
    
    except FileNotFoundError:
        print("❌ pytest not found. Please install with: pip install pytest")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)