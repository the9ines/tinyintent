#!/usr/bin/env python3
"""
TinyIntent Local CI Pipeline

Runs a complete local CI pipeline including:
- Code linting with ruff
- Type checking with mypy  
- Unit tests with pytest
- Helper health checks
- System readiness validation

M9.0: Packaging & Operator UX
"""

import subprocess
import sys
import os
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple


class LocalCI:
    """Local CI pipeline runner for TinyIntent."""
    
    def __init__(self, project_root: Path = None):
        """Initialize CI with project root."""
        if project_root is None:
            self.project_root = Path(__file__).parent.parent
        else:
            self.project_root = project_root
        
        self.results: Dict[str, Any] = {
            "timestamp": None,
            "overall_status": "pending", 
            "checks": {},
            "summary": {}
        }
    
    def run_command(self, cmd: List[str], cwd: Path = None) -> Tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        if cwd is None:
            cwd = self.project_root
            
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out after 5 minutes"
        except Exception as e:
            return 1, "", f"Command failed: {e}"
    
    def check_lint(self) -> bool:
        """Run ruff linting."""
        print("🔍 Running ruff linting...")
        exit_code, stdout, stderr = self.run_command(["ruff", "check", "."])
        
        self.results["checks"]["lint"] = {
            "status": "pass" if exit_code == 0 else "fail",
            "exit_code": exit_code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip()
        }
        
        if exit_code == 0:
            print("  ✅ Linting passed")
            return True
        else:
            print(f"  ❌ Linting failed (exit {exit_code})")
            if stderr:
                print(f"     Error: {stderr[:200]}...")
            return False
    
    def check_format(self) -> bool:
        """Check code formatting with ruff."""
        print("📝 Checking code formatting...")
        exit_code, stdout, stderr = self.run_command(["ruff", "format", "--check", "."])
        
        self.results["checks"]["format"] = {
            "status": "pass" if exit_code == 0 else "fail",
            "exit_code": exit_code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip()
        }
        
        if exit_code == 0:
            print("  ✅ Formatting check passed")
            return True
        else:
            print(f"  ❌ Formatting check failed (exit {exit_code})")
            print("     Run 'make format' to fix formatting issues")
            return False
    
    def check_types(self) -> bool:
        """Run mypy type checking."""
        print("🔍 Running mypy type checking...")
        exit_code, stdout, stderr = self.run_command(["mypy", "."])
        
        self.results["checks"]["typecheck"] = {
            "status": "pass" if exit_code == 0 else "fail",
            "exit_code": exit_code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip()
        }
        
        if exit_code == 0:
            print("  ✅ Type checking passed")
            return True
        else:
            print(f"  ❌ Type checking failed (exit {exit_code})")
            if stdout:
                # Show first few type errors
                lines = stdout.split('\n')[:5]
                for line in lines:
                    if line.strip():
                        print(f"     {line}")
            return False
    
    def check_tests(self) -> bool:
        """Run pytest unit tests."""
        print("🧪 Running pytest tests...")
        exit_code, stdout, stderr = self.run_command(["pytest", "tests/", "-v", "--tb=short"])
        
        self.results["checks"]["tests"] = {
            "status": "pass" if exit_code == 0 else "fail",
            "exit_code": exit_code,
            "stdout": stdout.strip(),
            "stderr": stderr.strip()
        }
        
        if exit_code == 0:
            print("  ✅ Tests passed")
            return True
        else:
            print(f"  ❌ Tests failed (exit {exit_code})")
            if stdout:
                # Show test summary
                lines = stdout.split('\n')
                for line in lines:
                    if "FAILED" in line or "ERROR" in line or "failed," in line:
                        print(f"     {line}")
            return False
    
    def check_dependencies(self) -> bool:
        """Check that required tools are available."""
        print("🔧 Checking development dependencies...")
        
        tools = ["ruff", "mypy", "pytest"]
        all_present = True
        
        deps_status = {}
        for tool in tools:
            exit_code, _, _ = self.run_command(["which", tool])
            if exit_code == 0:
                print(f"  ✅ {tool} available")
                deps_status[tool] = True
            else:
                print(f"  ❌ {tool} missing (install with: pip install {tool})")
                deps_status[tool] = False
                all_present = False
        
        self.results["checks"]["dependencies"] = {
            "status": "pass" if all_present else "fail",
            "tools": deps_status
        }
        
        return all_present
    
    def check_project_structure(self) -> bool:
        """Validate project structure."""
        print("📁 Checking project structure...")
        
        required_dirs = ["bridge", "helpers", "router", "tests", "scripts"]
        required_files = ["pyproject.toml", "Makefile"]
        
        all_present = True
        structure_status = {"dirs": {}, "files": {}}
        
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if dir_path.exists():
                print(f"  ✅ {dir_name}/ directory present")
                structure_status["dirs"][dir_name] = True
            else:
                print(f"  ❌ {dir_name}/ directory missing")
                structure_status["dirs"][dir_name] = False
                all_present = False
        
        for file_name in required_files:
            file_path = self.project_root / file_name
            if file_path.exists():
                print(f"  ✅ {file_name} present")
                structure_status["files"][file_name] = True
            else:
                print(f"  ❌ {file_name} missing")
                structure_status["files"][file_name] = False
                all_present = False
        
        self.results["checks"]["structure"] = {
            "status": "pass" if all_present else "fail",
            "details": structure_status
        }
        
        return all_present
    
    def run_all_checks(self) -> bool:
        """Run all CI checks."""
        import datetime
        self.results["timestamp"] = datetime.datetime.utcnow().isoformat() + 'Z'
        
        print("🚀 Starting TinyIntent Local CI Pipeline")
        print("=" * 50)
        
        checks = [
            ("Dependencies", self.check_dependencies),
            ("Project Structure", self.check_project_structure),
            ("Linting", self.check_lint),
            ("Formatting", self.check_format),
            ("Type Checking", self.check_types),
            ("Tests", self.check_tests)
        ]
        
        passed = 0
        total = len(checks)
        
        for check_name, check_func in checks:
            try:
                if check_func():
                    passed += 1
            except Exception as e:
                print(f"  ❌ {check_name} check failed with exception: {e}")
                self.results["checks"][check_name.lower().replace(" ", "_")] = {
                    "status": "error",
                    "error": str(e)
                }
        
        # Overall status
        if passed == total:
            self.results["overall_status"] = "pass"
            print(f"\n🎉 All checks passed! ({passed}/{total})")
            print("✅ TinyIntent is ready for development")
            return True
        else:
            self.results["overall_status"] = "fail"
            failed = total - passed
            print(f"\n❌ CI failed: {failed} checks failed, {passed} passed ({passed}/{total})")
            print("🔧 Fix the issues above and re-run 'make doctor'")
            return False
    
    def get_results(self) -> Dict[str, Any]:
        """Get CI results."""
        self.results["summary"] = {
            "total_checks": len(self.results["checks"]),
            "passed_checks": len([c for c in self.results["checks"].values() if c.get("status") == "pass"]),
            "failed_checks": len([c for c in self.results["checks"].values() if c.get("status") == "fail"]),
            "error_checks": len([c for c in self.results["checks"].values() if c.get("status") == "error"])
        }
        return self.results


def main():
    """Main entry point."""
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    ci = LocalCI(project_root)
    success = ci.run_all_checks()
    
    # Save results for doctor.py to read
    results_file = project_root / "data" / "ci_results.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump(ci.get_results(), f, indent=2)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()