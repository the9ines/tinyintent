#!/usr/bin/env python3
"""
TinyIntent Environment Bootstrap

Verifies system requirements and installs TinyIntent in editable mode
with all dependencies for development and testing.

M9.1: Final Polish & Release Prep
"""

import sys
import subprocess
import os
from pathlib import Path


def check_python_version():
    """Verify Python version meets requirements."""
    print("🐍 Checking Python version...")
    
    major, minor = sys.version_info[:2]
    required_major, required_minor = 3, 11
    
    if major < required_major or (major == required_major and minor < required_minor):
        print(f"❌ Python {required_major}.{required_minor}+ required, but found {major}.{minor}")
        print(f"   Current Python: {sys.executable}")
        print(f"   Please upgrade Python to {required_major}.{required_minor} or higher")
        return False
    
    print(f"✅ Python {major}.{minor} meets requirements (>= {required_major}.{required_minor})")
    print(f"   Using: {sys.executable}")
    return True


def check_project_structure():
    """Verify we're in a valid TinyIntent project."""
    print("\n📁 Checking project structure...")
    
    project_root = Path(__file__).parent.parent
    
    required_files = [
        "pyproject.toml",
        "Makefile", 
        "bridge/tinyrpc.py",
        "helpers/registry.yaml"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not (project_root / file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ Missing required files: {', '.join(missing_files)}")
        print("   Are you running this from the TinyIntent project root?")
        return False
    
    print("✅ Project structure looks good")
    return True


def install_package():
    """Install TinyIntent in editable mode with all dependencies."""
    print("\n📦 Installing TinyIntent package...")
    
    try:
        # Install in editable mode with test dependencies
        cmd = [sys.executable, "-m", "pip", "install", "-e", ".[test,dev]"]
        print(f"   Running: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        if result.returncode == 0:
            print("✅ Package installation successful")
            return True
        else:
            print(f"❌ Package installation failed (exit code {result.returncode})")
            if result.stderr:
                print(f"   Error: {result.stderr[:500]}...")
            if result.stdout:
                print(f"   Output: {result.stdout[:500]}...")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Package installation timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Package installation failed: {e}")
        return False


def verify_installation():
    """Verify that key dependencies are available."""
    print("\n🔍 Verifying installation...")
    
    test_imports = [
        ("fastapi", "FastAPI web framework"),
        ("uvicorn", "ASGI server"),
        ("pydantic", "Data validation"),
        ("httpx", "HTTP client"),
        ("pytest", "Testing framework"),
        ("ruff", "Code linting and formatting"),
        ("mypy", "Type checking")
    ]
    
    all_good = True
    for module_name, description in test_imports:
        try:
            __import__(module_name)
            print(f"   ✅ {description} ({module_name})")
        except ImportError:
            print(f"   ❌ {description} ({module_name}) - not available")
            all_good = False
    
    return all_good


def check_system_tools():
    """Check for required system tools."""
    print("\n⚙️  Checking system tools...")
    
    tools = [
        ("swift", "Swift compiler (for router training)", False),
        ("ollama", "Ollama LLM runtime", False),
        ("node", "Node.js (for JavaScript helpers)", False),
        ("git", "Git version control", True)
    ]
    
    missing_required = []
    for tool, description, required in tools:
        try:
            result = subprocess.run(
                ["which", tool],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"   ✅ {description} ({tool})")
            else:
                if required:
                    print(f"   ❌ {description} ({tool}) - REQUIRED but not found")
                    missing_required.append(tool)
                else:
                    print(f"   ⚠️  {description} ({tool}) - optional but recommended")
        except Exception:
            if required:
                print(f"   ❌ {description} ({tool}) - REQUIRED but not found")
                missing_required.append(tool)
            else:
                print(f"   ⚠️  {description} ({tool}) - optional but could not check")
    
    return len(missing_required) == 0


def print_next_steps():
    """Print next steps for the user."""
    print("\n🎉 Bootstrap complete! Next steps:")
    print("=" * 50)
    print()
    print("1. 📋 Run system health check:")
    print("   make doctor")
    print()
    print("2. 🧪 Run the test suite:")
    print("   make test")
    print()
    print("3. 🔧 Check code quality:")
    print("   make lint")
    print("   make format")
    print("   make typecheck")
    print()
    print("4. 🚀 Start the bridge service:")
    print("   export TINYINTENT_SECRET=$(openssl rand -hex 32)")
    print("   make bridgesrv")
    print()
    print("5. 📖 Read the configuration:")
    print("   cp tinyintent.example.env .env")
    print("   # Edit .env file as needed")
    print()
    print("For more information, see the project documentation.")


def main():
    """Main bootstrap process."""
    print("🚀 TinyIntent Environment Bootstrap")
    print("=" * 40)
    
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    print(f"📍 Working directory: {project_root}")
    
    # Run all checks and setup steps
    steps = [
        ("Python Version", check_python_version),
        ("Project Structure", check_project_structure),
        ("Package Installation", install_package),
        ("Installation Verification", verify_installation),
        ("System Tools", check_system_tools)
    ]
    
    failed_steps = []
    for step_name, step_func in steps:
        try:
            if not step_func():
                failed_steps.append(step_name)
        except Exception as e:
            print(f"❌ {step_name} failed with error: {e}")
            failed_steps.append(step_name)
    
    # Summary
    print("\n" + "=" * 50)
    if not failed_steps:
        print("✅ All bootstrap steps completed successfully!")
        print_next_steps()
        sys.exit(0)
    else:
        print(f"❌ Bootstrap failed. Issues with: {', '.join(failed_steps)}")
        print("\nPlease fix the above issues and run bootstrap again.")
        print("For help, check the project documentation or requirements.")
        sys.exit(1)


if __name__ == "__main__":
    main()