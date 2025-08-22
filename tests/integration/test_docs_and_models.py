#!/usr/bin/env python3
"""
Integration tests for documentation endpoints and model discovery.

Addresses audit findings:
- Test documentation endpoints (/docs, /redoc, /openapi.json)
- Test API discovery endpoint (/endpoints)
- Test model discovery logic in doctor.py with mocked scenarios
"""

import pytest
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# Test the main FastAPI app
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from bridge.tinyrpc import create_app
from scripts.doctor import SystemDoctor


class TestDocumentationEndpoints:
    """Test documentation endpoints are accessible."""
    
    @classmethod
    def setup_class(cls):
        """Set up test client."""
        # Mock the settings to avoid configuration issues
        with patch('tinyintent.config.settings') as mock_settings:
            mock_settings.logging.structured_logging = False
            mock_settings.server.log_level = "INFO"
            mock_settings.environment = "test"
            mock_settings.debug = True
            mock_settings.security.secret = "test-secret"
            mock_settings.is_production.return_value = False
            mock_settings.is_development.return_value = True
            
            # Mock async components
            with patch('tinyintent.bridge.tinyrpc.async_ollama_client') as mock_client:
                mock_client.health_check.return_value = None
                mock_client.close.return_value = None
                
                with patch('tinyintent.bridge.tinyrpc.initialize_audit_logger'):
                    app = create_app()
                    cls.client = TestClient(app)
    
    def test_openapi_json_endpoint(self):
        """Test that /openapi.json returns valid OpenAPI spec."""
        response = self.client.get("/openapi.json")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        
        # Parse JSON to ensure it's valid
        openapi_spec = response.json()
        assert "openapi" in openapi_spec
        assert "info" in openapi_spec
        assert openapi_spec["info"]["title"] == "TinyIntent Bridge"
        assert "paths" in openapi_spec
        
        # Ensure core endpoints are documented
        paths = openapi_spec["paths"]
        assert "/healthz" in paths or "/health" in paths
        assert "/route" in paths
    
    def test_docs_endpoint_accessibility(self):
        """Test that /docs endpoint is accessible."""
        response = self.client.get("/docs")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Check that it contains Swagger UI indicators
        content = response.text
        assert "swagger" in content.lower() or "openapi" in content.lower()
    
    def test_redoc_endpoint_accessibility(self):
        """Test that /redoc endpoint is accessible."""
        response = self.client.get("/redoc")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        
        # Check that it contains ReDoc indicators
        content = response.text
        assert "redoc" in content.lower()
    
    def test_endpoints_discovery_route(self):
        """Test the custom /endpoints route for API discovery."""
        response = self.client.get("/endpoints")
        
        assert response.status_code == 200
        
        data = response.json()
        assert "endpoints" in data
        assert "total_count" in data
        assert "service" in data
        assert "version" in data
        
        assert data["service"] == "TinyIntent Bridge"
        assert data["version"] == "2.0.0"
        assert isinstance(data["endpoints"], list)
        assert data["total_count"] == len(data["endpoints"])
        
        # Check that core endpoints are present
        endpoint_paths = [ep["path"] for ep in data["endpoints"]]
        assert "/" in endpoint_paths  # Root endpoint
        assert "/endpoints" in endpoint_paths  # Self-reference
        
        # Verify endpoint structure
        for endpoint in data["endpoints"]:
            assert "path" in endpoint
            assert "methods" in endpoint
            assert isinstance(endpoint["methods"], list)
            
            # Ensure no HEAD/OPTIONS methods are exposed
            assert "HEAD" not in endpoint["methods"]
            assert "OPTIONS" not in endpoint["methods"]
    
    def test_endpoints_include_core_routes(self):
        """Test that endpoints list includes expected core routes."""
        response = self.client.get("/endpoints")
        assert response.status_code == 200
        
        data = response.json()
        endpoint_paths = [ep["path"] for ep in data["endpoints"]]
        
        # Check for key functional endpoints
        expected_patterns = [
            "/",  # Root
            "/endpoints",  # API discovery
            "/route",  # Main routing
        ]
        
        for pattern in expected_patterns:
            matches = [path for path in endpoint_paths if pattern in path]
            assert len(matches) >= 1, f"Expected endpoint pattern '{pattern}' not found in {endpoint_paths}"


class TestModelDiscovery:
    """Test model discovery logic in doctor.py."""
    
    def setup_method(self):
        """Set up test environment with temporary directories."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Create basic project structure
        (self.project_root / "router").mkdir()
        (self.project_root / "router" / "data").mkdir()
        (self.project_root / "scripts").mkdir()
        (self.project_root / "bridge" / "logs").mkdir(parents=True)
        
        self.doctor = SystemDoctor(self.project_root)
    
    def teardown_method(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)
    
    def test_models_present_returns_ok(self):
        """Test that when models are present, check returns success."""
        # Create mock model files
        (self.project_root / "router" / "SmallIntent.mlmodel").touch()
        (self.project_root / "router" / "TinyIntent.mlmodel").touch()
        (self.project_root / "router" / "data" / "intents.tsv").write_text("intent\ttext\ngen\tHello\n")
        (self.project_root / "models.yaml").write_text("models:\n  small: test\n")
        
        # Mock print to capture output
        with patch('builtins.print') as mock_print:
            result = self.doctor.check_models()
        
        assert result is True
        self.assert_print_called_with(mock_print, "✅ SmallIntent.mlmodel present")
        self.assert_print_called_with(mock_print, "✅ TinyIntent.mlmodel present")
        
        # Check result structure
        check_result = self.doctor.results["checks"]["models"]
        assert check_result["status"] == "pass"
        assert check_result["details"]["present"] is True
        assert check_result["details"]["severity"] == "ok"
    
    def test_models_missing_with_training_infrastructure_returns_warning(self):
        """Test that missing models with training infrastructure returns warning."""
        # Create training infrastructure but no models
        (self.project_root / "router" / "train_router.swift").touch()
        (self.project_root / "router" / "eval_router.swift").touch()
        (self.project_root / "scripts" / "promote_model.py").touch()
        (self.project_root / "router" / "data" / "intents.tsv").write_text("intent\ttext\ngen\tHello\n")
        (self.project_root / "models.yaml").write_text("models:\n  small: test\n")
        
        # Mock print to capture output
        with patch('builtins.print') as mock_print:
            result = self.doctor.check_models()
        
        # Should return True because training infrastructure is present
        assert result is True
        self.assert_print_called_with(mock_print, "⚠️  CoreML models missing but training infrastructure present")
        
        # Check result structure matches audit requirements
        check_result = self.doctor.results["checks"]["models"]
        assert check_result["status"] == "warning"
        assert check_result["details"]["present"] is False
        assert check_result["details"]["severity"] == "warning"
        assert check_result["details"]["hint"] == "Run `make learn && make promote` to build models."
        
        # Check training infrastructure detection
        training_infra = check_result["details"]["training_infrastructure"]
        assert training_infra["train_script"] is True
        assert training_infra["eval_script"] is True
        assert training_infra["promote_script"] is True
        assert training_infra["complete"] is True
        
        # Check recommendations
        recommendations = self.doctor.results["recommendations"]
        assert any("make learn && make promote" in rec for rec in recommendations)
    
    def test_models_missing_without_training_infrastructure_returns_failure(self):
        """Test that missing models without training infrastructure returns failure."""
        # Create only basic files, no training infrastructure
        (self.project_root / "router" / "data" / "intents.tsv").write_text("intent\ttext\ngen\tHello\n")
        (self.project_root / "models.yaml").write_text("models:\n  small: test\n")
        
        # Mock print to capture output
        with patch('builtins.print') as mock_print:
            result = self.doctor.check_models()
        
        # Should return False because both models missing and no training infrastructure
        assert result is False
        self.assert_print_called_with(mock_print, "❌ CoreML models missing and training infrastructure not found")
        
        # Check result structure
        check_result = self.doctor.results["checks"]["models"]
        assert check_result["status"] == "fail"
        assert check_result["details"]["present"] is False
        assert check_result["details"]["severity"] == "error"
        assert check_result["details"]["hint"] == "Training infrastructure missing"
        
        # Check training infrastructure detection
        training_infra = check_result["details"]["training_infrastructure"]
        assert training_infra["complete"] is False
    
    def test_one_model_present_returns_success(self):
        """Test that having one model present is sufficient for success."""
        # Create only one model and training infrastructure
        (self.project_root / "router" / "SmallIntent.mlmodel").touch()
        # TinyIntent.mlmodel deliberately missing
        (self.project_root / "router" / "train_router.swift").touch()
        (self.project_root / "router" / "eval_router.swift").touch()
        (self.project_root / "scripts" / "promote_model.py").touch()
        (self.project_root / "router" / "data" / "intents.tsv").write_text("intent\ttext\ngen\tHello\n")
        (self.project_root / "models.yaml").write_text("models:\n  small: test\n")
        
        with patch('builtins.print'):
            result = self.doctor.check_models()
        
        # Should return True because at least one model is present
        assert result is True
        
        check_result = self.doctor.results["checks"]["models"]
        assert check_result["status"] == "pass"
        assert check_result["details"]["present"] is True
        assert check_result["details"]["small_model"] is True
        assert check_result["details"]["tiny_model"] is False
    
    def test_doctor_results_saved_to_correct_path(self):
        """Test that doctor results are saved to bridge/logs/doctor.json."""
        # Create minimal setup
        (self.project_root / "router" / "SmallIntent.mlmodel").touch()
        (self.project_root / "router" / "data" / "intents.tsv").write_text("intent\ttext\ngen\tHello\n")
        (self.project_root / "models.yaml").write_text("models:\n  small: test\n")
        
        # Mock the other checks to focus on file output
        with patch.object(self.doctor, 'check_ci_results', return_value=True), \
             patch.object(self.doctor, 'check_helpers_health', return_value=True), \
             patch.object(self.doctor, 'check_system_deps', return_value=True), \
             patch.object(self.doctor, 'check_services', return_value=True), \
             patch.object(self.doctor, 'check_environment', return_value=True), \
             patch('builtins.print'):  # Suppress output
            
            self.doctor.run_comprehensive_check()
        
        # Check that results are saved in the expected location
        results_file = self.project_root / "bridge" / "logs" / "doctor.json"
        assert results_file.exists()
        
        # Verify JSON content
        with open(results_file) as f:
            results = json.load(f)
        
        assert "timestamp" in results
        assert "overall_status" in results
        assert "checks" in results
        assert "models" in results["checks"]
    
    def assert_print_called_with(self, mock_print, expected_text):
        """Helper to assert that print was called with expected text."""
        print_calls = [call[0][0] for call in mock_print.call_args_list if call[0]]
        assert any(expected_text in call for call in print_calls), \
            f"Expected '{expected_text}' in print calls: {print_calls}"


class TestIntegrationScenarios:
    """Test complete integration scenarios."""
    
    def test_documentation_endpoints_integration(self):
        """Test that all documentation endpoints work together."""
        with patch('tinyintent.config.settings') as mock_settings:
            mock_settings.logging.structured_logging = False
            mock_settings.server.log_level = "INFO"
            mock_settings.environment = "test"
            mock_settings.debug = True
            mock_settings.security.secret = "test-secret"
            mock_settings.is_production.return_value = False
            mock_settings.is_development.return_value = True
            
            with patch('tinyintent.bridge.tinyrpc.async_ollama_client') as mock_client:
                mock_client.health_check.return_value = None
                mock_client.close.return_value = None
                
                with patch('tinyintent.bridge.tinyrpc.initialize_audit_logger'):
                    app = create_app()
                    client = TestClient(app)
                    
                    # Test all documentation endpoints
                    endpoints_to_test = ["/docs", "/redoc", "/openapi.json", "/endpoints"]
                    
                    for endpoint in endpoints_to_test:
                        response = client.get(endpoint)
                        assert response.status_code == 200, f"Endpoint {endpoint} failed with {response.status_code}"
                    
                    # Verify that /endpoints includes references to documentation
                    endpoints_response = client.get("/endpoints")
                    endpoints_data = endpoints_response.json()
                    
                    # Should include internal routes
                    endpoint_paths = [ep["path"] for ep in endpoints_data["endpoints"]]
                    assert "/endpoints" in endpoint_paths


if __name__ == "__main__":
    # Run tests
    import subprocess
    
    print("🧪 Running Documentation and Model Discovery Integration Tests...")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            __file__, 
            "-v", 
            "--tb=short"
        ], capture_output=True, text=True)
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ All documentation and model tests passed!")
        else:
            print("❌ Some tests failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        sys.exit(1)