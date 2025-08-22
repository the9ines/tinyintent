#!/usr/bin/env python3
"""
TinyIntent System Doctor

Comprehensive system health and readiness validation including:
- CI pipeline results
- Helper health checks
- Model availability and readiness
- System dependencies and configuration
- Network connectivity and services

M9.0: Packaging & Operator UX
"""

import json
import os
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


class SystemDoctor:
    """Comprehensive system health checker for TinyIntent."""
    
    def __init__(self, project_root: Path = None):
        """Initialize doctor with project root."""
        if project_root is None:
            self.project_root = Path(__file__).parent.parent
        else:
            self.project_root = project_root
        
        self.results: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "overall_status": "pending",
            "checks": {},
            "recommendations": [],
            "summary": {}
        }
    
    def run_command(self, cmd: List[str], cwd: Path = None, timeout: int = 30) -> Tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        if cwd is None:
            cwd = self.project_root
            
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", f"Command timed out after {timeout}s"
        except Exception as e:
            return 1, "", f"Command failed: {e}"
    
    def check_ci_results(self) -> bool:
        """Check recent CI pipeline results."""
        print("🔍 Checking CI pipeline results...")
        
        ci_results_file = self.project_root / "data" / "ci_results.json"
        
        if not ci_results_file.exists():
            self.results["checks"]["ci"] = {
                "status": "warn",
                "message": "No CI results found - run 'make doctor' to execute CI pipeline",
                "recommendation": "Run local CI pipeline"
            }
            print("  ⚠️  No CI results found")
            self.results["recommendations"].append("Run 'python scripts/ci_local.py' to execute CI pipeline")
            return False
        
        try:
            with open(ci_results_file, 'r') as f:
                ci_data = json.load(f)
            
            overall_status = ci_data.get("overall_status", "unknown")
            summary = ci_data.get("summary", {})
            
            # Check if CI results are recent (within last hour)
            ci_timestamp = ci_data.get("timestamp", "")
            age_hours = 999
            if ci_timestamp:
                try:
                    ci_time = datetime.fromisoformat(ci_timestamp.replace('Z', '+00:00'))
                    now = datetime.now().astimezone()
                    age_hours = (now - ci_time).total_seconds() / 3600
                except:
                    pass
            
            if overall_status == "pass":
                print(f"  ✅ CI pipeline passed ({summary.get('passed_checks', 0)}/{summary.get('total_checks', 0)} checks)")
                status = "pass"
            else:
                print(f"  ❌ CI pipeline failed ({summary.get('failed_checks', 0)} failed, {summary.get('error_checks', 0)} errors)")
                status = "fail"
                self.results["recommendations"].append("Fix CI failures and re-run pipeline")
            
            if age_hours > 1:
                print(f"  ⚠️  CI results are {age_hours:.1f} hours old")
                self.results["recommendations"].append("Re-run CI pipeline for fresh results")
            
            self.results["checks"]["ci"] = {
                "status": status,
                "overall_status": overall_status,
                "age_hours": age_hours,
                "summary": summary,
                "details": ci_data.get("checks", {})
            }
            
            return status == "pass"
            
        except Exception as e:
            self.results["checks"]["ci"] = {
                "status": "error",
                "error": str(e),
                "message": "Failed to read CI results"
            }
            print(f"  ❌ Failed to read CI results: {e}")
            return False
    
    def check_helpers_health(self) -> bool:
        """Check helper health via SDK."""
        print("🔧 Checking helper health...")
        
        try:
            # Import helpers SDK
            sys.path.append(str(self.project_root / "helpers"))
            from sdk import run_all_helper_health_checks
            
            health_results = run_all_helper_health_checks(timeout_seconds=10)
            
            healthy_count = 0
            total_count = len(health_results)
            
            for helper_id, result in health_results.items():
                if result.get("status") == "healthy":
                    healthy_count += 1
                    print(f"  ✅ {helper_id} is healthy")
                else:
                    status = result.get("status", "unknown")
                    print(f"  ❌ {helper_id} is {status}")
                    if result.get("error"):
                        print(f"     Error: {result['error'][:100]}...")
            
            self.results["checks"]["helpers"] = {
                "status": "pass" if healthy_count == total_count else "fail",
                "healthy_count": healthy_count,
                "total_count": total_count,
                "details": health_results
            }
            
            if healthy_count < total_count:
                self.results["recommendations"].append("Fix unhealthy helpers before deployment")
            
            return healthy_count == total_count
            
        except Exception as e:
            self.results["checks"]["helpers"] = {
                "status": "error",
                "error": str(e),
                "message": "Failed to check helper health"
            }
            print(f"  ❌ Failed to check helper health: {e}")
            return False
    
    def check_models(self) -> bool:
        """Check model availability and readiness."""
        print("🧠 Checking model availability...")
        
        router_model = self.project_root / "router" / "SmallIntent.mlmodel"
        tiny_model = self.project_root / "router" / "TinyIntent.mlmodel"
        training_data = self.project_root / "router" / "data" / "intents.tsv"
        models_config = self.project_root / "models.yaml"
        
        # Check training infrastructure
        train_script = self.project_root / "router" / "train_router.swift"
        eval_script = self.project_root / "router" / "eval_router.swift"
        promote_script = self.project_root / "scripts" / "promote_model.py"
        
        training_infra_present = (
            train_script.exists() and 
            eval_script.exists() and 
            promote_script.exists()
        )
        
        all_good = True
        model_status = {}
        
        # Check CoreML models with infrastructure-aware logic
        small_model_present = router_model.exists()
        tiny_model_present = tiny_model.exists()
        
        if small_model_present:
            print("  ✅ SmallIntent.mlmodel present")
            model_status["small_model"] = True
        else:
            print("  ❌ SmallIntent.mlmodel missing")
            model_status["small_model"] = False
            
        if tiny_model_present:
            print("  ✅ TinyIntent.mlmodel present")
            model_status["tiny_model"] = True
        else:
            print("  ❌ TinyIntent.mlmodel missing")
            model_status["tiny_model"] = False
        
        # M10.6: Models are required for bridge startup - treat missing models as critical
        models_missing = not small_model_present and not tiny_model_present
        
        if models_missing:
            if training_infra_present:
                # Training infrastructure exists - models can be built
                print("  ❌ CoreML models missing - BRIDGE WILL NOT START")
                print("      Training infrastructure present - models can be generated")
                model_status["present"] = False
                model_status["severity"] = "critical"
                model_status["hint"] = "Run `make learn` to build required models before starting bridge."
                model_status["bridge_startup"] = "blocked"
                self.results["recommendations"].append("CRITICAL: Run 'make learn' to build CoreML models before starting bridge")
                all_good = False  # M10.6: Models are required, mark as failure
            else:
                # No training infrastructure - this is a severe failure
                print("  ❌ CoreML models missing and training infrastructure not found")
                print("      BRIDGE CANNOT START - models are required")
                model_status["present"] = False
                model_status["severity"] = "critical"
                model_status["hint"] = "Training infrastructure missing - setup required"
                model_status["bridge_startup"] = "blocked"
                all_good = False
                self.results["recommendations"].append("CRITICAL: Set up training infrastructure and build CoreML models")
        else:
            model_status["present"] = True
            model_status["severity"] = "ok"
            model_status["bridge_startup"] = "ready"
            
            # Check model file sizes and metadata
            if small_model_present:
                small_size = router_model.stat().st_size
                model_status["small_model_size_mb"] = round(small_size / (1024 * 1024), 1)
                print(f"     SmallIntent.mlmodel: {model_status['small_model_size_mb']}MB")
                
            if tiny_model_present:
                tiny_size = tiny_model.stat().st_size
                model_status["tiny_model_size_mb"] = round(tiny_size / (1024 * 1024), 1)
                print(f"     TinyIntent.mlmodel: {model_status['tiny_model_size_mb']}MB")
        
        # Check training infrastructure details
        model_status["training_infrastructure"] = {
            "train_script": train_script.exists(),
            "eval_script": eval_script.exists(), 
            "promote_script": promote_script.exists(),
            "complete": training_infra_present
        }
        
        # Check training data
        if training_data.exists():
            print("  ✅ Training data present")
            model_status["training_data"] = True
            
            # Check data quality
            try:
                with open(training_data, 'r') as f:
                    lines = f.readlines()
                    line_count = len([l for l in lines if l.strip()])
                    print(f"     {line_count} training examples")
                    model_status["training_examples"] = line_count
                    if line_count < 10:
                        print("  ⚠️  Very few training examples")
                        self.results["recommendations"].append("Gather more training data for better accuracy")
            except Exception as e:
                print(f"  ⚠️  Could not read training data: {e}")
                model_status["training_data_error"] = str(e)
        else:
            print("  ❌ Training data missing")
            model_status["training_data"] = False
            all_good = False
            self.results["recommendations"].append("Create training data at router/data/intents.tsv")
        
        # Check models config
        if models_config.exists():
            print("  ✅ models.yaml configuration present")
            model_status["models_config"] = True
        else:
            print("  ❌ models.yaml missing")
            model_status["models_config"] = False
            all_good = False
            self.results["recommendations"].append("Create models.yaml configuration")
        
        # Status determination: only fail if both models missing AND no training infrastructure
        status = "pass" if all_good else ("warning" if training_infra_present and models_missing else "fail")
        
        self.results["checks"]["models"] = {
            "status": status,
            "details": model_status
        }
        
        # Return success if either models present or training infrastructure available
        return all_good or (training_infra_present and not models_missing)
    
    def check_system_deps(self) -> bool:
        """Check system dependencies."""
        print("⚙️  Checking system dependencies...")
        
        deps = ["python3", "swift", "ollama", "node"]
        all_present = True
        dep_status = {}
        
        for dep in deps:
            exit_code, stdout, stderr = self.run_command(["which", dep])
            if exit_code == 0:
                print(f"  ✅ {dep} available")
                dep_status[dep] = {"available": True, "path": stdout.strip()}
                
                # Get version info where possible
                if dep == "python3":
                    exit_code, version_out, _ = self.run_command([dep, "--version"])
                    if exit_code == 0:
                        dep_status[dep]["version"] = version_out.strip()
                elif dep == "swift":
                    exit_code, version_out, _ = self.run_command([dep, "--version"])
                    if exit_code == 0:
                        dep_status[dep]["version"] = version_out.split('\n')[0]
                elif dep == "ollama":
                    exit_code, version_out, _ = self.run_command([dep, "--version"])
                    if exit_code == 0:
                        dep_status[dep]["version"] = version_out.strip()
                elif dep == "node":
                    exit_code, version_out, _ = self.run_command([dep, "--version"])
                    if exit_code == 0:
                        dep_status[dep]["version"] = version_out.strip()
            else:
                print(f"  ❌ {dep} missing")
                dep_status[dep] = {"available": False}
                all_present = False
                
                if dep == "ollama":
                    self.results["recommendations"].append("Install Ollama from https://ollama.ai")
                elif dep == "swift":
                    self.results["recommendations"].append("Install Xcode or Swift toolchain")
                elif dep == "node":
                    self.results["recommendations"].append("Install Node.js for JavaScript helpers")
        
        self.results["checks"]["dependencies"] = {
            "status": "pass" if all_present else "fail",
            "details": dep_status
        }
        
        return all_present
    
    def check_services(self) -> bool:
        """Check service availability."""
        print("🌐 Checking service availability...")
        
        # Check if Ollama is running
        ollama_running = False
        exit_code, stdout, stderr = self.run_command(["ollama", "list"], timeout=5)
        if exit_code == 0:
            print("  ✅ Ollama service is running")
            ollama_running = True
            
            # Check available models
            models = [line for line in stdout.split('\n') if line.strip() and not line.startswith('NAME')]
            if models:
                print(f"     {len(models)} models available")
            else:
                print("  ⚠️  No models installed in Ollama")
                self.results["recommendations"].append("Install a model with 'ollama pull llama2'")
        else:
            print("  ❌ Ollama service not running")
            self.results["recommendations"].append("Start Ollama service")
        
        # Check bridge API (if running)
        bridge_running = False
        try:
            import requests
            response = requests.get("http://localhost:8787/health", timeout=2)
            if response.status_code == 200:
                print("  ✅ Bridge API is running")
                bridge_running = True
            else:
                print(f"  ⚠️  Bridge API returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            print("  ℹ️  Bridge API not running (start with 'make bridgesrv')")
        except Exception as e:
            print(f"  ⚠️  Could not check Bridge API: {e}")
        
        self.results["checks"]["services"] = {
            "status": "pass" if ollama_running else "warn",
            "ollama_running": ollama_running,
            "bridge_running": bridge_running
        }
        
        return ollama_running  # Ollama is required, bridge is optional
    
    def check_environment(self) -> bool:
        """Check environment configuration."""
        print("🔐 Checking environment configuration...")
        
        # Check for TINYINTENT_SECRET
        secret_set = "TINYINTENT_SECRET" in os.environ
        if secret_set:
            print("  ✅ TINYINTENT_SECRET configured")
        else:
            print("  ⚠️  TINYINTENT_SECRET not set")
            self.results["recommendations"].append("Set TINYINTENT_SECRET environment variable")
        
        # Check data directory
        data_dir = self.project_root / "data"
        if data_dir.exists():
            print("  ✅ Data directory present")
            
            # Check permissions
            if os.access(data_dir, os.R_OK | os.W_OK):
                print("  ✅ Data directory writable")
                data_writable = True
            else:
                print("  ❌ Data directory not writable")
                data_writable = False
                self.results["recommendations"].append("Fix data directory permissions")
        else:
            print("  ❌ Data directory missing")
            data_writable = False
            self.results["recommendations"].append("Create data directory")
        
        self.results["checks"]["environment"] = {
            "status": "pass" if secret_set and data_writable else "warn",
            "secret_set": secret_set,
            "data_writable": data_writable
        }
        
        return secret_set and data_writable
    
    def run_comprehensive_check(self) -> bool:
        """Run all system health checks."""
        print("🩺 Starting TinyIntent System Doctor")
        print("=" * 50)
        
        checks = [
            ("System Dependencies", self.check_system_deps),
            ("CI Results", self.check_ci_results),
            ("Models", self.check_models),
            ("Helper Health", self.check_helpers_health),
            ("Services", self.check_services),
            ("Environment", self.check_environment)
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
        
        # Determine overall status
        critical_checks = ["system_dependencies", "models"]
        critical_passed = all(
            self.results["checks"].get(check, {}).get("status") == "pass"
            for check in critical_checks
        )
        
        if passed == total:
            self.results["overall_status"] = "healthy"
            print(f"\n🎉 System is healthy! ({passed}/{total} checks passed)")
            print("✅ TinyIntent is ready for production use")
            return True
        elif critical_passed and passed >= total - 2:
            self.results["overall_status"] = "ready"
            print(f"\n⚠️  System is ready with warnings ({passed}/{total} checks passed)")
            print("🔧 Address warnings below for optimal performance")
            return True
        else:
            self.results["overall_status"] = "unhealthy"
            failed = total - passed
            print(f"\n❌ System is unhealthy: {failed} checks failed ({passed}/{total} passed)")
            print("🔧 Fix critical issues before deployment")
            return False
    
    def print_recommendations(self):
        """Print actionable recommendations."""
        if self.results["recommendations"]:
            print(f"\n💡 Recommendations ({len(self.results['recommendations'])}):")
            for i, rec in enumerate(self.results["recommendations"], 1):
                print(f"  {i}. {rec}")
        else:
            print("\n✨ No recommendations - system is optimal!")
    
    def get_results(self) -> Dict[str, Any]:
        """Get doctor results."""
        self.results["summary"] = {
            "total_checks": len(self.results["checks"]),
            "passed_checks": len([c for c in self.results["checks"].values() if c.get("status") == "pass"]),
            "failed_checks": len([c for c in self.results["checks"].values() if c.get("status") == "fail"]),
            "warning_checks": len([c for c in self.results["checks"].values() if c.get("status") == "warn"]),
            "error_checks": len([c for c in self.results["checks"].values() if c.get("status") == "error"]),
            "recommendation_count": len(self.results["recommendations"])
        }
        return self.results


def main():
    """Main entry point."""
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    doctor = SystemDoctor(project_root)
    success = doctor.run_comprehensive_check()
    doctor.print_recommendations()
    
    # Save results for API endpoint to read
    results_file = project_root / "bridge" / "logs" / "doctor.json"
    results_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump(doctor.get_results(), f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {results_file}")
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()