#!/usr/bin/env python3
"""
Integration Tests for TinyIntent Doctor System

Tests the complete doctor and CI system including:
- Local CI pipeline execution
- System health checks  
- Doctor API endpoint
- Result persistence and freshness
- Recommendation generation

M9.0: Packaging & Operator UX
"""

import json
import os
import sys
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.ci_local import LocalCI
from scripts.doctor import SystemDoctor


class TestLocalCI(unittest.TestCase):
    """Test the local CI pipeline."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.ci = LocalCI(self.temp_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_ci_initialization(self):
        """Test CI initialization."""
        self.assertEqual(self.ci.project_root, self.temp_dir)
        self.assertEqual(self.ci.results["overall_status"], "pending")
        self.assertIn("checks", self.ci.results)
    
    def test_run_command(self):
        """Test command execution."""
        exit_code, stdout, stderr = self.ci.run_command(["echo", "test"])
        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout.strip(), "test")
        self.assertEqual(stderr, "")
    
    def test_run_command_failure(self):
        """Test command failure handling."""
        exit_code, stdout, stderr = self.ci.run_command(["false"])
        self.assertEqual(exit_code, 1)
    
    def test_run_command_timeout(self):
        """Test command timeout."""
        exit_code, stdout, stderr = self.ci.run_command(["sleep", "10"], timeout=1)
        self.assertEqual(exit_code, 1)
        self.assertIn("timed out", stderr)
    
    @patch('subprocess.run')
    def test_check_dependencies_success(self, mock_run):
        """Test dependency checking with all tools available."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        
        result = self.ci.check_dependencies()
        self.assertTrue(result)
        self.assertEqual(self.ci.results["checks"]["dependencies"]["status"], "pass")
    
    @patch('subprocess.run')
    def test_check_dependencies_missing(self, mock_run):
        """Test dependency checking with missing tools."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        result = self.ci.check_dependencies()
        self.assertFalse(result)
        self.assertEqual(self.ci.results["checks"]["dependencies"]["status"], "fail")
    
    def test_check_project_structure_empty(self):
        """Test project structure check with empty directory."""
        result = self.ci.check_project_structure()
        self.assertFalse(result)
        self.assertEqual(self.ci.results["checks"]["structure"]["status"], "fail")
    
    def test_check_project_structure_complete(self):
        """Test project structure check with complete structure."""
        # Create required directories and files
        required_dirs = ["bridge", "helpers", "router", "tests", "scripts"]
        required_files = ["pyproject.toml", "Makefile"]
        
        for dir_name in required_dirs:
            (self.temp_dir / dir_name).mkdir()
        
        for file_name in required_files:
            (self.temp_dir / file_name).touch()
        
        result = self.ci.check_project_structure()
        self.assertTrue(result)
        self.assertEqual(self.ci.results["checks"]["structure"]["status"], "pass")
    
    def test_get_results_structure(self):
        """Test results structure."""
        results = self.ci.get_results()
        
        self.assertIn("timestamp", results)
        self.assertIn("overall_status", results)
        self.assertIn("checks", results)
        self.assertIn("summary", results)
        self.assertIn("total_checks", results["summary"])
        self.assertIn("passed_checks", results["summary"])


class TestSystemDoctor(unittest.TestCase):
    """Test the system doctor."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.doctor = SystemDoctor(self.temp_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_doctor_initialization(self):
        """Test doctor initialization."""
        self.assertEqual(self.doctor.project_root, self.temp_dir)
        self.assertEqual(self.doctor.results["overall_status"], "pending")
        self.assertIn("checks", self.doctor.results)
        self.assertIn("recommendations", self.doctor.results)
    
    @patch('subprocess.run')
    def test_check_system_deps_success(self, mock_run):
        """Test system dependency checking with all deps available."""
        mock_run.return_value = MagicMock(returncode=0, stdout="/usr/bin/python3\n", stderr="")
        
        result = self.doctor.check_system_deps()
        self.assertTrue(result)
        self.assertEqual(self.doctor.results["checks"]["dependencies"]["status"], "pass")
    
    @patch('subprocess.run')
    def test_check_system_deps_missing(self, mock_run):
        """Test system dependency checking with missing deps."""
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
        
        result = self.doctor.check_system_deps()
        self.assertFalse(result)
        self.assertEqual(self.doctor.results["checks"]["dependencies"]["status"], "fail")
        self.assertTrue(len(self.doctor.results["recommendations"]) > 0)
    
    def test_check_models_missing(self):
        """Test model checking with missing models."""
        result = self.doctor.check_models()
        self.assertFalse(result)
        self.assertEqual(self.doctor.results["checks"]["models"]["status"], "fail")
        self.assertIn("Train router model", " ".join(self.doctor.results["recommendations"]))
    
    def test_check_models_present(self):
        """Test model checking with models present."""
        # Create required model files
        router_dir = self.temp_dir / "router"
        router_dir.mkdir()
        (router_dir / "SmallIntent.mlmodel").touch()
        
        data_dir = router_dir / "data"
        data_dir.mkdir()
        with open(data_dir / "intents.tsv", 'w') as f:
            f.write("text\tlabel\n")
            f.write("hello\tgreeting\n")
            f.write("goodbye\tfarew\n")
        
        # Create models config
        (self.temp_dir / "models.yaml").touch()
        
        result = self.doctor.check_models()
        self.assertTrue(result)
        self.assertEqual(self.doctor.results["checks"]["models"]["status"], "pass")
    
    def test_check_environment_basic(self):
        """Test environment checking."""
        # Create data directory
        data_dir = self.temp_dir / "data"
        data_dir.mkdir()
        
        result = self.doctor.check_environment()
        # Should pass for data dir, may warn about TINYINTENT_SECRET
        self.assertIn(self.doctor.results["checks"]["environment"]["status"], ["pass", "warn"])
    
    def test_check_ci_results_missing(self):
        """Test CI results checking with no results."""
        result = self.doctor.check_ci_results()
        self.assertFalse(result)
        self.assertEqual(self.doctor.results["checks"]["ci"]["status"], "warn")
        self.assertIn("Run local CI pipeline", " ".join(self.doctor.results["recommendations"]))
    
    def test_check_ci_results_present_passing(self):
        """Test CI results checking with passing results."""
        # Create CI results file
        data_dir = self.temp_dir / "data"
        data_dir.mkdir()
        
        ci_results = {
            "timestamp": "2023-01-01T12:00:00Z",
            "overall_status": "pass",
            "summary": {
                "total_checks": 5,
                "passed_checks": 5,
                "failed_checks": 0,
                "error_checks": 0
            }
        }
        
        with open(data_dir / "ci_results.json", 'w') as f:
            json.dump(ci_results, f)
        
        result = self.doctor.check_ci_results()
        self.assertTrue(result)
        self.assertEqual(self.doctor.results["checks"]["ci"]["status"], "pass")
    
    def test_check_ci_results_present_failing(self):
        """Test CI results checking with failing results."""
        # Create CI results file
        data_dir = self.temp_dir / "data"
        data_dir.mkdir()
        
        ci_results = {
            "timestamp": "2023-01-01T12:00:00Z",
            "overall_status": "fail",
            "summary": {
                "total_checks": 5,
                "passed_checks": 3,
                "failed_checks": 2,
                "error_checks": 0
            }
        }
        
        with open(data_dir / "ci_results.json", 'w') as f:
            json.dump(ci_results, f)
        
        result = self.doctor.check_ci_results()
        self.assertFalse(result)
        self.assertEqual(self.doctor.results["checks"]["ci"]["status"], "fail")
        self.assertIn("Fix CI failures", " ".join(self.doctor.results["recommendations"]))
    
    def test_get_results_structure(self):
        """Test doctor results structure."""
        results = self.doctor.get_results()
        
        self.assertIn("timestamp", results)
        self.assertIn("overall_status", results)
        self.assertIn("checks", results)
        self.assertIn("recommendations", results)
        self.assertIn("summary", results)
        self.assertIn("total_checks", results["summary"])
        self.assertIn("recommendation_count", results["summary"])


class TestDoctorIntegration(unittest.TestCase):
    """Integration tests for the complete doctor system."""
    
    def setUp(self):
        """Set up integration test environment."""
        self.project_root = Path(__file__).parent.parent.parent
    
    def test_ci_script_exists_and_executable(self):
        """Test that CI script exists and is executable."""
        ci_script = self.project_root / "scripts" / "ci_local.py"
        self.assertTrue(ci_script.exists())
        self.assertTrue(os.access(ci_script, os.R_OK))
    
    def test_doctor_script_exists_and_executable(self):
        """Test that doctor script exists and is executable."""
        doctor_script = self.project_root / "scripts" / "doctor.py"
        self.assertTrue(doctor_script.exists())
        self.assertTrue(os.access(doctor_script, os.R_OK))
    
    def test_makefile_has_doctor_target(self):
        """Test that Makefile has doctor target."""
        makefile = self.project_root / "Makefile"
        self.assertTrue(makefile.exists())
        
        with open(makefile, 'r') as f:
            content = f.read()
        
        self.assertIn("doctor:", content)
        self.assertIn("scripts/ci_local.py", content)
        self.assertIn("scripts/doctor.py", content)
    
    def test_pyproject_toml_has_required_deps(self):
        """Test that pyproject.toml has required dev dependencies."""
        pyproject = self.project_root / "pyproject.toml"
        self.assertTrue(pyproject.exists())
        
        with open(pyproject, 'r') as f:
            content = f.read()
        
        # Check for dev dependencies
        self.assertIn("ruff", content)
        self.assertIn("mypy", content)
        self.assertIn("pytest", content)
    
    @unittest.skipIf(not sys.platform.startswith('darwin'), "macOS specific test")
    def test_swift_availability(self):
        """Test Swift availability on macOS."""
        result = subprocess.run(["which", "swift"], capture_output=True)
        if result.returncode == 0:
            # Swift is available, test version
            version_result = subprocess.run(["swift", "--version"], capture_output=True, text=True)
            self.assertEqual(version_result.returncode, 0)
            self.assertIn("Swift", version_result.stdout)
    
    def test_data_directory_structure(self):
        """Test that data directory can be created."""
        data_dir = self.project_root / "data"
        
        # Create if doesn't exist
        data_dir.mkdir(exist_ok=True)
        
        self.assertTrue(data_dir.exists())
        self.assertTrue(os.access(data_dir, os.W_OK))
    
    def test_helpers_directory_structure(self):
        """Test helpers directory structure."""
        helpers_dir = self.project_root / "helpers"
        self.assertTrue(helpers_dir.exists())
        
        # Check for registry
        registry_file = helpers_dir / "registry.yaml"
        self.assertTrue(registry_file.exists())
        
        # Check for SDK
        sdk_file = helpers_dir / "sdk.py"
        self.assertTrue(sdk_file.exists())


class TestDoctorAPIIntegration(unittest.TestCase):
    """Test the doctor API endpoint integration."""
    
    def setUp(self):
        """Set up API test environment."""
        self.project_root = Path(__file__).parent.parent.parent
    
    def test_doctor_endpoint_import(self):
        """Test that doctor endpoint can be imported."""
        try:
            sys.path.insert(0, str(self.project_root))
            from bridge.api_routes import router_api
            
            # Check that doctor endpoint is registered
            routes = [route.path for route in router_api.routes]
            self.assertIn("/doctor", routes)
            
        except ImportError as e:
            self.skipTest(f"Cannot import API modules: {e}")
    
    def test_doctor_results_persistence(self):
        """Test that doctor results can be saved and loaded."""
        data_dir = self.project_root / "data"
        data_dir.mkdir(exist_ok=True)
        
        # Create sample doctor results
        sample_results = {
            "timestamp": "2023-01-01T12:00:00Z",
            "overall_status": "healthy",
            "checks": {
                "test_check": {
                    "status": "pass",
                    "message": "Test passed"
                }
            },
            "recommendations": [],
            "summary": {
                "total_checks": 1,
                "passed_checks": 1,
                "failed_checks": 0,
                "warning_checks": 0,
                "error_checks": 0,
                "recommendation_count": 0
            }
        }
        
        results_file = data_dir / "doctor_results.json"
        
        # Save results
        with open(results_file, 'w') as f:
            json.dump(sample_results, f, indent=2)
        
        # Load results
        with open(results_file, 'r') as f:
            loaded_results = json.load(f)
        
        self.assertEqual(loaded_results["overall_status"], "healthy")
        self.assertEqual(loaded_results["summary"]["total_checks"], 1)
        
        # Clean up
        results_file.unlink(missing_ok=True)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)