#!/usr/bin/env python3
"""
Tests for TinyIntent Agent Generator

Tests the complete agent creation flow:
- Agent specification validation
- Helper folder generation 
- Python and Node.js template generation
- API endpoint functionality
- Security validation
- Hot-reload integration

M10.0: Self-Replicating Agent Generator
"""

import json
import os
import sys
import tempfile
import unittest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, call

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tinyintent.helpers.manifest import validate_agent_spec
from tinyintent.bridge.agent_generator import AgentGenerator


class TestAgentSpecValidation(unittest.TestCase):
    """Test agent specification validation."""
    
    def test_valid_python_spec(self):
        """Test valid Python agent specification."""
        spec = {
            "id": "url_summarizer",
            "description": "Fetch a URL and return a markdown summary",
            "language": "python",
            "capabilities": ["network"],
            "can_execute": False,
            "risk_level": "high",
            "inputs": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri"}
                },
                "required": ["url"]
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"}
                },
                "required": ["summary", "status"]
            }
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertTrue(is_valid, f"Spec should be valid, but got errors: {errors}")
        self.assertEqual(errors, [])
    
    def test_valid_node_spec(self):
        """Test valid Node.js agent specification."""
        spec = {
            "id": "file_processor",
            "description": "Process files and extract metadata",
            "language": "node",
            "capabilities": ["filesystem"],
            "inputs": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"}
                },
                "required": ["file_path"]
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "metadata": {"type": "object"},
                    "status": {"type": "string"}
                },
                "required": ["metadata", "status"]
            }
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertTrue(is_valid, f"Spec should be valid, but got errors: {errors}")
        self.assertEqual(errors, [])
    
    def test_invalid_id_formats(self):
        """Test invalid agent ID formats."""
        base_spec = {
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        invalid_ids = [
            "../bad",           # Path traversal
            "UPPERCASE",        # Uppercase not allowed
            "too-long-name-that-exceeds-the-forty-character-limit-by-a-lot",  # Too long
            "ab",               # Too short
            "with/slash",       # Path separator
            "with\\backslash",  # Windows path separator
            "with.dot",         # Contains dot
            "123-dash",         # Contains dash
            ""                  # Empty
        ]
        
        for invalid_id in invalid_ids:
            with self.subTest(id=invalid_id):
                spec = base_spec.copy()
                spec["id"] = invalid_id
                
                is_valid, errors = validate_agent_spec(spec)
                self.assertFalse(is_valid, f"ID '{invalid_id}' should be invalid")
                self.assertTrue(any("id" in error.lower() for error in errors))
    
    def test_missing_required_fields(self):
        """Test missing required fields."""
        base_spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        required_fields = ["id", "description", "language", "inputs", "outputs"]
        
        for field in required_fields:
            with self.subTest(field=field):
                spec = base_spec.copy()
                del spec[field]
                
                is_valid, errors = validate_agent_spec(spec)
                self.assertFalse(is_valid, f"Missing '{field}' should make spec invalid")
                self.assertTrue(any(field in error for error in errors))
    
    def test_invalid_language(self):
        """Test invalid language specification."""
        spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "ruby",  # Not supported
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertFalse(is_valid)
        self.assertTrue(any("language" in error.lower() for error in errors))
    
    def test_invalid_capabilities(self):
        """Test invalid capabilities."""
        spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "python",
            "capabilities": ["network", "invalid_capability"],
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertFalse(is_valid)
        self.assertTrue(any("capability" in error.lower() for error in errors))
    
    def test_can_execute_must_be_false(self):
        """Test that can_execute must be false for safety."""
        spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "python",
            "can_execute": True,  # Not allowed
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertFalse(is_valid)
        self.assertTrue(any("can_execute" in error for error in errors))
    
    def test_invalid_json_schemas(self):
        """Test invalid JSON schemas."""
        # Invalid input schema
        spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "invalid_type"},  # Invalid JSON Schema
            "outputs": {"type": "object"}
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertFalse(is_valid)
        self.assertTrue(any("inputs" in error.lower() for error in errors))
        
        # Invalid output schema
        spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "object"},
            "outputs": {"type": "invalid_type"}  # Invalid JSON Schema
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertFalse(is_valid)
        self.assertTrue(any("outputs" in error.lower() for error in errors))
    
    def test_dangerous_helper_names(self):
        """Test rejection of dangerous helper names."""
        dangerous_names = ["admin", "root", "sudo", "exec", "eval", "shell", "cmd"]
        
        for dangerous_name in dangerous_names:
            with self.subTest(name=dangerous_name):
                spec = {
                    "id": dangerous_name,
                    "description": "Test helper",
                    "language": "python",
                    "inputs": {"type": "object"},
                    "outputs": {"type": "object"}
                }
                
                is_valid, errors = validate_agent_spec(spec)
                self.assertFalse(is_valid, f"Dangerous name '{dangerous_name}' should be rejected")
                self.assertTrue(any("not allowed" in error for error in errors))
    
    def test_system_prefix_rejection(self):
        """Test rejection of system_ prefix."""
        spec = {
            "id": "system_helper",
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        is_valid, errors = validate_agent_spec(spec)
        self.assertFalse(is_valid)
        self.assertTrue(any("system_" in error for error in errors))


class TestAgentGenerator(unittest.TestCase):
    """Test the agent generator functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.generator = AgentGenerator(self.temp_dir)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_create_python_agent_success(self):
        """Test successful Python agent creation."""
        spec = {
            "id": "url_summarizer",
            "description": "Fetch a URL and return a markdown summary",
            "language": "python",
            "capabilities": ["network"],
            "inputs": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri"}
                },
                "required": ["url"]
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "status": {"type": "string"}
                },
                "required": ["summary", "status"]
            }
        }
        
        with patch.object(self.generator, 'audit_logger') as mock_logger:
            result = self.generator.create_agent(spec)
        
        # Check result
        self.assertTrue(result["created"])
        self.assertEqual(result["helper_id"], "url_summarizer")
        self.assertTrue(result["enabled"])
        self.assertTrue(result["validation"]["passed"])
        
        # Check files were created
        helper_dir = self.temp_dir / "url_summarizer"
        self.assertTrue(helper_dir.exists())
        self.assertTrue((helper_dir / "helper.yaml").exists())
        self.assertTrue((helper_dir / "input.schema.json").exists())
        self.assertTrue((helper_dir / "output.schema.json").exists())
        self.assertTrue((helper_dir / "main.py").exists())
        
        # Check helper.yaml content
        with open(helper_dir / "helper.yaml", 'r') as f:
            manifest = yaml.safe_load(f)
        
        self.assertEqual(manifest["id"], "url_summarizer")
        self.assertFalse(manifest["capabilities"]["execute"])  # Should be disabled
        self.assertIn("Generated by Agent Generator", manifest["generated"]["safety_notes"])
        self.assertEqual(manifest["generated"]["language"], "python")
        
        # Check schemas
        with open(helper_dir / "input.schema.json", 'r') as f:
            input_schema = json.load(f)
        self.assertEqual(input_schema, spec["inputs"])
        
        with open(helper_dir / "output.schema.json", 'r') as f:
            output_schema = json.load(f)
        self.assertEqual(output_schema, spec["outputs"])
        
        # Check main.py is executable and contains expected content
        main_script = helper_dir / "main.py"
        self.assertTrue(os.access(main_script, os.X_OK))
        
        with open(main_script, 'r') as f:
            content = f.read()
        self.assertIn("import json", content)
        self.assertIn("sys.stdin.read", content)
        self.assertIn("Generated by TinyIntent Agent Generator", content)
        
        # Check audit logging
        mock_logger.log_entry.assert_called()
        audit_call = mock_logger.log_entry.call_args[0][0]
        self.assertEqual(audit_call["action"], "agent_create")
        self.assertEqual(audit_call["helper_id"], "url_summarizer")
        self.assertTrue(audit_call["success"])
    
    def test_create_node_agent_success(self):
        """Test successful Node.js agent creation."""
        spec = {
            "id": "file_processor",
            "description": "Process files and extract metadata",
            "language": "node",
            "capabilities": ["filesystem"],
            "inputs": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"}
                },
                "required": ["file_path"]
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "metadata": {"type": "object"}
                },
                "required": ["metadata"]
            }
        }
        
        with patch.object(self.generator, 'audit_logger') as mock_logger:
            result = self.generator.create_agent(spec)
        
        # Check result
        self.assertTrue(result["created"])
        self.assertEqual(result["helper_id"], "file_processor")
        
        # Check Node.js specific files
        helper_dir = self.temp_dir / "file_processor"
        main_script = helper_dir / "main.js"
        self.assertTrue(main_script.exists())
        self.assertTrue(os.access(main_script, os.X_OK))
        
        with open(main_script, 'r') as f:
            content = f.read()
        self.assertIn("const fs = require('fs')", content)
        self.assertIn("process.stdin", content)
        self.assertIn("Generated by TinyIntent Agent Generator", content)
    
    def test_create_agent_invalid_spec(self):
        """Test agent creation with invalid specification."""
        spec = {
            "id": "invalid-id",  # Invalid ID format
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        with patch.object(self.generator, 'audit_logger') as mock_logger:
            result = self.generator.create_agent(spec)
        
        # Check result
        self.assertFalse(result["created"])
        self.assertIn("errors", result)
        self.assertFalse(result["validation"]["passed"])
        
        # Check no files were created
        helper_dir = self.temp_dir / "invalid-id"
        self.assertFalse(helper_dir.exists())
        
        # Check audit logging
        mock_logger.log_entry.assert_called()
        audit_call = mock_logger.log_entry.call_args[0][0]
        self.assertEqual(audit_call["action"], "agent_create")
        self.assertFalse(audit_call["success"])
    
    def test_create_agent_already_exists(self):
        """Test agent creation when helper already exists."""
        # Create helper directory first
        helper_dir = self.temp_dir / "existing_helper"
        helper_dir.mkdir()
        
        spec = {
            "id": "existing_helper",
            "description": "Test helper",
            "language": "python",
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        with patch.object(self.generator, 'audit_logger') as mock_logger:
            result = self.generator.create_agent(spec)
        
        # Check result
        self.assertFalse(result["created"])
        self.assertIn("already exists", result["errors"][0])
        
        # Check audit logging
        mock_logger.log_entry.assert_called()
        audit_call = mock_logger.log_entry.call_args[0][0]
        self.assertFalse(audit_call["success"])
        self.assertIn("already exists", audit_call["errors"][0])
    
    def test_safe_defaults_applied(self):
        """Test that safe defaults are applied."""
        spec = {
            "id": "test_helper",
            "description": "Test helper",
            "language": "python",
            "can_execute": True,  # Should be overridden to false
            "risk_level": "low",  # Should be kept as specified
            "inputs": {"type": "object"},
            "outputs": {"type": "object"}
        }
        
        with patch.object(self.generator, 'audit_logger'):
            result = self.generator.create_agent(spec)
        
        # Check that safe defaults were applied
        helper_dir = self.temp_dir / "test_helper"
        with open(helper_dir / "helper.yaml", 'r') as f:
            manifest = yaml.safe_load(f)
        
        # Execution should be disabled despite spec requesting it
        self.assertFalse(manifest["capabilities"]["execute"])
        
        # Safety notes should be added
        self.assertIn("Generated by Agent Generator", manifest["generated"]["safety_notes"])
    
    def test_file_extension_mapping(self):
        """Test file extension mapping for different languages."""
        self.assertEqual(self.generator._get_file_extension("python"), "py")
        self.assertEqual(self.generator._get_file_extension("node"), "js")
        self.assertEqual(self.generator._get_file_extension("unknown"), "txt")


# Mock FastAPI test client for API endpoint testing
try:
    from fastapi.testclient import TestClient
    from tinyintent.bridge.api_routes import router_api
    
    class TestAgentCreateAPI(unittest.TestCase):
        """Test the agent creation API endpoint."""
        
        def setUp(self):
            """Set up test client."""
            # Create a simple FastAPI app with just our router
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router_api)
            self.client = TestClient(app)
            
            # Mock authentication
            self.auth_headers = {"Authorization": "Bearer test-secret"}
        
        @patch('tinyintent.bridge.api_routes.agent_generator')
        @patch('tinyintent.bridge.api_routes.helper_registry')
        @patch('tinyintent.bridge.api_routes.episode_logger')
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_create_agent_success(self, mock_rate_limiter, mock_episode_logger, 
                                    mock_helper_registry, mock_agent_generator):
            """Test successful agent creation via API."""
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_agent_generator.create_agent.return_value = {
                "created": True,
                "helper_id": "test_agent",
                "enabled": True,
                "validation": {"passed": True, "errors": [], "warnings": []},
                "files_created": ["test_agent/helper.yaml", "test_agent/main.py"]
            }
            
            # Make request
            spec = {
                "id": "test_agent",
                "description": "Test agent",
                "language": "python",
                "capabilities": ["network"],
                "inputs": {"type": "object", "properties": {"input": {"type": "string"}}},
                "outputs": {"type": "object", "properties": {"output": {"type": "string"}}}
            }
            
            response = self.client.post("/agents/create", json=spec, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 200)
            result = response.json()
            self.assertTrue(result["created"])
            self.assertEqual(result["helper_id"], "test_agent")
            self.assertTrue(result["enabled"])
            
            # Check that generator was called with correct spec
            mock_agent_generator.create_agent.assert_called_once()
            called_spec = mock_agent_generator.create_agent.call_args[0][0]
            self.assertEqual(called_spec["id"], "test_agent")
            self.assertFalse(called_spec["can_execute"])  # Should be forced to false
            
            # Check that helper registry was reloaded
            mock_helper_registry.reload.assert_called_once()
            
            # Check that episode was logged
            mock_episode_logger.log_event.assert_called_once()
        
        @patch('tinyintent.bridge.api_routes.agent_generator')
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_create_agent_validation_failure(self, mock_rate_limiter, mock_agent_generator):
            """Test agent creation with validation failure."""
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_agent_generator.create_agent.return_value = {
                "created": False,
                "helper_id": "invalid_agent",
                "errors": ["Invalid ID format"],
                "validation": {"passed": False, "errors": ["Invalid ID format"]}
            }
            
            # Make request with invalid data
            spec = {
                "id": "INVALID-ID",  # Invalid format
                "description": "Test agent",
                "language": "python",
                "inputs": {"type": "object"},
                "outputs": {"type": "object"}
            }
            
            response = self.client.post("/agents/create", json=spec, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 400)
            result = response.json()
            self.assertIn("errors", result["detail"])
        
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_create_agent_rate_limited(self, mock_rate_limiter):
            """Test agent creation when rate limited."""
            # Setup rate limit
            mock_rate_limiter.check_rate_limit.return_value = (False, 60)
            
            spec = {
                "id": "test_agent",
                "description": "Test agent",
                "language": "python",
                "inputs": {"type": "object"},
                "outputs": {"type": "object"}
            }
            
            response = self.client.post("/agents/create", json=spec, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response.headers)
            self.assertEqual(response.headers["Retry-After"], "60")
        
        def test_create_agent_invalid_request_format(self):
            """Test agent creation with invalid request format."""
            # Missing required fields
            spec = {
                "description": "Test agent"
                # Missing id, language, inputs, outputs
            }
            
            response = self.client.post("/agents/create", json=spec, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 422)  # Validation error
        
        def test_create_agent_can_execute_override(self):
            """Test that can_execute is always forced to false."""
            spec = {
                "id": "test_agent",
                "description": "Test agent",
                "language": "python",
                "can_execute": True,  # Should be rejected by validation
                "inputs": {"type": "object"},
                "outputs": {"type": "object"}
            }
            
            response = self.client.post("/agents/create", json=spec, headers=self.auth_headers)
            
            # Check response - should fail validation
            self.assertEqual(response.status_code, 422)

except ImportError:
    # FastAPI not available - skip API tests
    print("FastAPI not available - skipping API tests")
    
    class TestAgentCreateAPI(unittest.TestCase):
        """Placeholder for when FastAPI is not available."""
        
        def test_skip_api_tests(self):
            """Skip API tests when FastAPI not available."""
            self.skipTest("FastAPI not available")


if __name__ == '__main__':
    unittest.main(verbosity=2)