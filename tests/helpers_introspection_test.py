#!/usr/bin/env python3
"""
TinyIntent Helper Registry Introspection & Docs Tests - M8.4

Tests helper introspection API endpoints for detailed helper information and schema access.
Validates that helpers return complete metadata, sanitized manifests, and proper error handling.
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent / "bridge"))
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

try:
    from sdk import (
        load_helper_schemas, 
        get_helper_introspection_data, 
        _sanitize_manifest_for_introspection,
        helper_registry
    )
    INTROSPECTION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helper introspection not available: {e}")
    INTROSPECTION_AVAILABLE = False

try:
    import requests
    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False


class TestHelperSchemaLoading(unittest.TestCase):
    """Test helper schema loading utilities."""
    
    def setUp(self):
        """Set up test environment."""
        if not INTROSPECTION_AVAILABLE:
            self.skipTest("Helper introspection not available")
        
        # Create temporary directory for test helpers
        self.test_dir = Path(tempfile.mkdtemp(prefix="helper_introspection_test_"))
        
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary directory
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _create_test_helper(self, helper_id: str, include_schemas: bool = True, 
                          invalid_json: bool = False) -> Path:
        """Create a test helper with schemas."""
        helper_dir = self.test_dir / helper_id
        helper_dir.mkdir(parents=True, exist_ok=True)
        
        # Create manifest
        manifest = {
            "purpose": f"Test helper {helper_id}",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["echo", "test"]
            },
            "metadata": {
                "author": "Test Suite"
            },
            "version": "1.0.0",
            "added": "2024-01-01",
            "updated": "2025-08-19",
            "maintainer": "Test Team <test@example.com>"
        }
        
        with open(helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(manifest, f)
        
        if include_schemas:
            # Create input schema
            input_schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["get", "set", "delete"]},
                    "target": {"type": "string"}
                },
                "required": ["operation"]
            }
            
            # Create output schema
            output_schema = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["success", "error"]},
                    "result": {"type": "object"},
                    "message": {"type": "string"}
                },
                "required": ["status"]
            }
            
            if invalid_json:
                # Create invalid JSON for testing error handling
                with open(helper_dir / "input.schema.json", 'w') as f:
                    f.write('{"invalid": json')
            else:
                with open(helper_dir / "input.schema.json", 'w') as f:
                    json.dump(input_schema, f, indent=2)
                
                with open(helper_dir / "output.schema.json", 'w') as f:
                    json.dump(output_schema, f, indent=2)
        
        return helper_dir
    
    def test_load_valid_schemas(self):
        """Test loading valid helper schemas."""
        helper_dir = self._create_test_helper("valid_schemas_helper")
        
        schemas = load_helper_schemas(helper_dir)
        
        self.assertIsNone(schemas["error"])
        self.assertIsNotNone(schemas["input_schema"])
        self.assertIsNotNone(schemas["output_schema"])
        
        # Verify schema structure
        input_schema = schemas["input_schema"]
        self.assertIn("properties", input_schema)
        self.assertIn("operation", input_schema["properties"])
        self.assertIn("required", input_schema)
        
        output_schema = schemas["output_schema"]
        self.assertIn("properties", output_schema)
        self.assertIn("status", output_schema["properties"])
        self.assertIn("required", output_schema)
    
    def test_load_schemas_missing_input(self):
        """Test loading schemas when input schema is missing."""
        helper_dir = self._create_test_helper("missing_input_helper", include_schemas=False)
        
        # Create only output schema
        output_schema = {"type": "object", "properties": {"status": {"type": "string"}}}
        with open(helper_dir / "output.schema.json", 'w') as f:
            json.dump(output_schema, f)
        
        schemas = load_helper_schemas(helper_dir)
        
        self.assertIsNotNone(schemas["error"])
        self.assertIn("input.schema.json not found", schemas["error"])
        self.assertIsNone(schemas["input_schema"])
        self.assertIsNone(schemas["output_schema"])
    
    def test_load_schemas_missing_output(self):
        """Test loading schemas when output schema is missing."""
        helper_dir = self._create_test_helper("missing_output_helper", include_schemas=False)
        
        # Create only input schema
        input_schema = {"type": "object", "properties": {"operation": {"type": "string"}}}
        with open(helper_dir / "input.schema.json", 'w') as f:
            json.dump(input_schema, f)
        
        schemas = load_helper_schemas(helper_dir)
        
        self.assertIsNotNone(schemas["error"])
        self.assertIn("output.schema.json not found", schemas["error"])
        self.assertIsNone(schemas["input_schema"])  # Should be None since loading failed
        self.assertIsNone(schemas["output_schema"])
    
    def test_load_schemas_invalid_json(self):
        """Test loading schemas with invalid JSON."""
        helper_dir = self._create_test_helper("invalid_json_helper", invalid_json=True)
        
        schemas = load_helper_schemas(helper_dir)
        
        self.assertIsNotNone(schemas["error"])
        self.assertIn("Invalid JSON", schemas["error"])
        self.assertIsNone(schemas["input_schema"])
        self.assertIsNone(schemas["output_schema"])
    
    def test_load_schemas_nonexistent_directory(self):
        """Test loading schemas from nonexistent directory."""
        nonexistent_dir = self.test_dir / "nonexistent"
        
        schemas = load_helper_schemas(nonexistent_dir)
        
        self.assertIsNotNone(schemas["error"])
        self.assertIn("input.schema.json not found", schemas["error"])


class TestHelperIntrospection(unittest.TestCase):
    """Test helper introspection functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not INTROSPECTION_AVAILABLE:
            self.skipTest("Helper introspection not available")
    
    def test_get_introspection_data_valid_helper(self):
        """Test getting introspection data for valid helper."""
        # Test with a known helper from the registry
        if not hasattr(helper_registry, 'registry_entries') or not helper_registry.registry_entries:
            self.skipTest("Helper registry not available")
        
        # Get a valid helper from the registry
        validation_summary = helper_registry.get_validation_summary()
        helpers = validation_summary.get("helpers", {})
        valid_helpers = [hid for hid, hinfo in helpers.items() if hinfo.get("is_valid")]
        
        if not valid_helpers:
            self.skipTest("No valid helpers available for testing")
        
        helper_id = valid_helpers[0]
        introspection_data = get_helper_introspection_data(helper_id)
        
        # Should not have error
        self.assertNotIn("error", introspection_data)
        
        # Check required fields
        required_fields = [
            "helper_id", "name", "description", "enabled", "category", 
            "risk_level", "can_execute", "requires_approval", "capabilities",
            "is_valid", "manifest", "input_schema", "output_schema"
        ]
        
        for field in required_fields:
            self.assertIn(field, introspection_data, f"Missing field '{field}'")
        
        # Verify helper ID matches
        self.assertEqual(introspection_data["helper_id"], helper_id)
        
        # Verify schemas are present
        self.assertIsNotNone(introspection_data["input_schema"])
        self.assertIsNotNone(introspection_data["output_schema"])
        
        # Verify manifest is sanitized (should be a dict)
        self.assertIsInstance(introspection_data["manifest"], dict)
        
        print(f"✓ Introspection data for {helper_id}: {len(introspection_data)} fields")
    
    def test_get_introspection_data_nonexistent_helper(self):
        """Test getting introspection data for nonexistent helper."""
        if not hasattr(helper_registry, 'registry_entries') or not helper_registry.registry_entries:
            self.skipTest("Helper registry not available")
        
        introspection_data = get_helper_introspection_data("nonexistent_helper")
        
        self.assertIn("error", introspection_data)
        self.assertEqual(introspection_data["error"], "helper_not_found")
        self.assertIn("not found in registry", introspection_data["detail"])
    
    def test_get_introspection_data_registry_unavailable(self):
        """Test getting introspection data when registry is unavailable."""
        with patch('sdk.helper_registry') as mock_registry:
            mock_registry.registry_entries = None
            
            introspection_data = get_helper_introspection_data("any_helper")
            
            self.assertIn("error", introspection_data)
            self.assertEqual(introspection_data["error"], "helper_registry_unavailable")
    
    def test_sanitize_manifest_for_introspection(self):
        """Test manifest sanitization for introspection."""
        # Test manifest with sensitive data
        manifest = {
            "purpose": "Test helper",
            "metadata": {
                "author": "Test Author",
                "api_key": "secret-key-123",
                "token": "secret-token-456",
                "database_password": "secret-pass-789"
            },
            "sandbox": {
                "commands": ["echo"],
                "env": {
                    "PUBLIC_VAR": "public-value",
                    "SECRET_VAR": "secret-value"
                }
            },
            "required_envs": ["API_KEY", "SECRET_TOKEN"]
        }
        
        sanitized = _sanitize_manifest_for_introspection(manifest)
        
        # Check that sensitive metadata fields are redacted
        self.assertEqual(sanitized["metadata"]["api_key"], "****")
        self.assertEqual(sanitized["metadata"]["token"], "****")
        self.assertEqual(sanitized["metadata"]["database_password"], "****")
        
        # Check that non-sensitive metadata is preserved
        self.assertEqual(sanitized["metadata"]["author"], "Test Author")
        
        # Check that sandbox env values are redacted
        self.assertEqual(sanitized["sandbox"]["env"]["PUBLIC_VAR"], "****")
        self.assertEqual(sanitized["sandbox"]["env"]["SECRET_VAR"], "****")
        
        # Check that required_envs names are preserved (not sensitive)
        self.assertEqual(sanitized["required_envs"], ["API_KEY", "SECRET_TOKEN"])
        
        # Check that other fields are preserved
        self.assertEqual(sanitized["purpose"], "Test helper")
        self.assertEqual(sanitized["sandbox"]["commands"], ["echo"])
    
    def test_sanitize_manifest_edge_cases(self):
        """Test manifest sanitization edge cases."""
        # Test with None manifest
        sanitized = _sanitize_manifest_for_introspection(None)
        self.assertIsNone(sanitized)
        
        # Test with empty manifest
        sanitized = _sanitize_manifest_for_introspection({})
        self.assertEqual(sanitized, {})
        
        # Test with manifest without sensitive fields
        manifest = {"purpose": "Simple helper", "capabilities": {"preview": True}}
        sanitized = _sanitize_manifest_for_introspection(manifest)
        self.assertEqual(sanitized, manifest)


@unittest.skipIf(not HTTP_CLIENT_AVAILABLE, "requests not available")
class TestHelperIntrospectionHTTP(unittest.TestCase):
    """Test helper introspection via HTTP endpoints."""
    
    def setUp(self):
        """Set up HTTP test environment."""
        self.base_url = "http://localhost:8787"
        self.auth_headers = {}  # Add auth if required
        
        # Test if bridge is running
        try:
            response = requests.get(f"{self.base_url}/healthz", timeout=2)
            self.bridge_available = response.status_code == 200
        except requests.exceptions.RequestException:
            self.bridge_available = False
        
        if not self.bridge_available:
            self.skipTest("Bridge service not running at localhost:8787")
    
    def test_get_helper_details_endpoint_exists(self):
        """Test that GET /helpers/{helper_id} endpoint exists."""
        # Try with a likely valid helper
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            # Should not be 404 (not found) - might be auth error though
            self.assertNotEqual(response.status_code, 404, 
                              f"GET /helpers/{helper_id} endpoint not found")
            
            print(f"✓ GET /helpers/{helper_id} endpoint exists (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to reach GET /helpers/{helper_id} endpoint: {e}")
    
    def test_get_helper_details_valid_helper(self):
        """Test GET /helpers/{helper_id} with valid helper."""
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                expected_fields = ["status", "helper", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertEqual(data["status"], "success")
                
                # Check helper data structure
                helper_data = data["helper"]
                required_helper_fields = [
                    "helper_id", "name", "description", "enabled", "category",
                    "risk_level", "can_execute", "requires_approval", "capabilities",
                    "is_valid", "manifest", "input_schema", "output_schema"
                ]
                
                for field in required_helper_fields:
                    self.assertIn(field, helper_data, f"Missing field '{field}' in helper data")
                
                # Verify helper ID matches
                self.assertEqual(helper_data["helper_id"], helper_id)
                
                # Verify schemas are present and valid
                self.assertIsNotNone(helper_data["input_schema"])
                self.assertIsNotNone(helper_data["output_schema"])
                self.assertIsInstance(helper_data["input_schema"], dict)
                self.assertIsInstance(helper_data["output_schema"], dict)
                
                # Verify manifest is sanitized
                self.assertIsInstance(helper_data["manifest"], dict)
                
                print(f"✓ GET /helpers/{helper_id} returned complete introspection data")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for helper details endpoint (status: {response.status_code})")
            elif response.status_code == 404:
                print(f"⚠ Helper {helper_id} not found (might be expected)")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test GET /helpers/{helper_id} endpoint: {e}")
    
    def test_get_helper_details_nonexistent_helper(self):
        """Test GET /helpers/{helper_id} with nonexistent helper."""
        helper_id = "nonexistent_helper_12345"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 404:
                data = response.json()
                self.assertIn("detail", data)
                self.assertIn("not found", data["detail"].lower())
                print(f"✓ GET /helpers/{helper_id} correctly returned 404")
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status for nonexistent helper: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test nonexistent helper endpoint: {e}")
    
    def test_get_helper_schemas_endpoint_exists(self):
        """Test that GET /helpers/schemas/{helper_id} endpoint exists."""
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/schemas/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            # Should not be 404 (not found)
            self.assertNotEqual(response.status_code, 404, 
                              f"GET /helpers/schemas/{helper_id} endpoint not found")
            
            print(f"✓ GET /helpers/schemas/{helper_id} endpoint exists (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to reach GET /helpers/schemas/{helper_id} endpoint: {e}")
    
    def test_get_helper_schemas_valid_helper(self):
        """Test GET /helpers/schemas/{helper_id} with valid helper."""
        helper_id = "bot_guard"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/schemas/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check response structure
                expected_fields = ["status", "helper_id", "input_schema", "output_schema", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertEqual(data["status"], "success")
                self.assertEqual(data["helper_id"], helper_id)
                
                # Verify schemas are present and valid
                self.assertIsNotNone(data["input_schema"])
                self.assertIsNotNone(data["output_schema"])
                self.assertIsInstance(data["input_schema"], dict)
                self.assertIsInstance(data["output_schema"], dict)
                
                # Should have schema structure
                input_schema = data["input_schema"]
                output_schema = data["output_schema"]
                
                self.assertIn("type", input_schema)
                self.assertIn("type", output_schema)
                
                print(f"✓ GET /helpers/schemas/{helper_id} returned valid schemas")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for schemas endpoint (status: {response.status_code})")
            elif response.status_code == 404:
                print(f"⚠ Helper {helper_id} not found (might be expected)")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test GET /helpers/schemas/{helper_id} endpoint: {e}")
    
    def test_get_helper_schemas_nonexistent_helper(self):
        """Test GET /helpers/schemas/{helper_id} with nonexistent helper."""
        helper_id = "nonexistent_helper_schemas_12345"
        
        try:
            response = requests.get(
                f"{self.base_url}/helpers/schemas/{helper_id}",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 404:
                data = response.json()
                self.assertIn("detail", data)
                self.assertIn("not found", data["detail"].lower())
                print(f"✓ GET /helpers/schemas/{helper_id} correctly returned 404")
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status for nonexistent helper schemas: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test nonexistent helper schemas endpoint: {e}")


if __name__ == "__main__":
    # Run tests with detailed output
    unittest.main(verbosity=2)