#!/usr/bin/env python3
"""
TinyIntent Helper Manifest Validation Tests - M8.1

Tests helper manifest validation framework with valid and invalid helpers.
Ensures validate_helper_manifest() correctly identifies validation errors.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent / "helpers"))

try:
    from tinyintent.helpers.manifest import validate_helper_manifest
    VALIDATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helper validation not available: {e}")
    VALIDATION_AVAILABLE = False


class TestHelperManifestValidation(unittest.TestCase):
    """Test helper manifest validation functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not VALIDATION_AVAILABLE:
            self.skipTest("Helper validation not available")
        
        # Create temporary directory for test helpers
        self.test_dir = Path(tempfile.mkdtemp(prefix="helper_test_"))
        
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary directory
        import shutil
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _create_helper_files(self, helper_id: str, manifest_data: dict = None, 
                           input_schema: dict = None, output_schema: dict = None,
                           create_script: bool = True, executable: bool = True):
        """Create test helper files."""
        helper_dir = self.test_dir / helper_id
        helper_dir.mkdir(parents=True, exist_ok=True)
        
        # Create helper.yaml
        if manifest_data is not None:
            with open(helper_dir / "helper.yaml", 'w') as f:
                import yaml
                yaml.dump(manifest_data, f)
        
        # Create input.schema.json
        if input_schema is not None:
            with open(helper_dir / "input.schema.json", 'w') as f:
                json.dump(input_schema, f)
        
        # Create output.schema.json  
        if output_schema is not None:
            with open(helper_dir / "output.schema.json", 'w') as f:
                json.dump(output_schema, f)
        
        # Create main script
        if create_script and manifest_data and "sandbox" in manifest_data:
            commands = manifest_data["sandbox"].get("commands", [])
            if len(commands) > 1:
                script_name = commands[1]
                script_path = helper_dir / script_name
                script_path.write_text("#!/usr/bin/env node\nconsole.log('test');\n")
                if executable:
                    os.chmod(script_path, 0o755)
        
        return helper_dir
    
    def test_valid_helper_manifest(self):
        """Test validation passes for a complete, valid helper."""
        manifest = {
            "purpose": "Test helper for validation",
            "capabilities": {
                "preview": True,
                "execute": True,
                "emergency_close": False
            },
            "sandbox": {
                "commands": ["node", "./main.js"],
                "timeouts": [{"name": "default", "seconds": 5}],
                "cpu": {"max_ms": 1000},
                "mem": {"max_mb": 50}
            },
            "schema": {
                "input": "./input.schema.json",
                "output": "./output.schema.json"
            },
            "environment": {
                "required": ["TEST_VAR"],
                "optional": ["OPTIONAL_VAR"]
            },
            "metadata": {
                "version": "1.0.0",
                "author": "TinyIntent",
                "risk_level": "low"
            }
        }
        
        input_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "operation": {"type": "string"}
            },
            "required": ["operation"]
        }
        
        output_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema", 
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"}
            },
            "required": ["status"]
        }
        
        helper_dir = self._create_helper_files(
            "valid_helper", manifest, input_schema, output_schema
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertTrue(result["valid"], f"Validation failed: {result['errors']}")
        self.assertEqual(result["helper_id"], "valid_helper")
        self.assertIsInstance(result["errors"], list)
        self.assertIsInstance(result["warnings"], list)
        # Should have some warnings for best practices
        self.assertEqual(len(result["errors"]), 0)
    
    def test_missing_required_files(self):
        """Test validation fails when required files are missing."""
        # Create helper directory without required files
        helper_dir = self.test_dir / "incomplete_helper"
        helper_dir.mkdir()
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertGreaterEqual(len(result["errors"]), 3)  # At least 3 missing files
        
        # Check for specific missing file errors
        error_messages = ' '.join(result["errors"])
        self.assertIn("helper.yaml", error_messages)
        self.assertIn("input.schema.json", error_messages) 
        self.assertIn("output.schema.json", error_messages)
    
    def test_invalid_yaml_syntax(self):
        """Test validation fails for invalid YAML syntax."""
        helper_dir = self.test_dir / "invalid_yaml_helper"
        helper_dir.mkdir()
        
        # Create invalid YAML file
        with open(helper_dir / "helper.yaml", 'w') as f:
            f.write("invalid: yaml: content:\n  - missing\n    indentation")
        
        # Create required schema files
        self._create_helper_files("", {}, {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object"
        }, {
            "$schema": "https://json-schema.org/draft/2020-12/schema", 
            "type": "object"
        }, False)
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("parse helper.yaml" in error for error in result["errors"]))
    
    def test_missing_required_manifest_fields(self):
        """Test validation fails when required manifest fields are missing."""
        # Manifest missing purpose, capabilities, sandbox
        incomplete_manifest = {
            "description": "Missing required fields"
        }
        
        helper_dir = self._create_helper_files(
            "incomplete_manifest",
            incomplete_manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        
        error_messages = ' '.join(result["errors"])
        self.assertIn("purpose", error_messages)
        self.assertIn("capabilities", error_messages) 
        self.assertIn("sandbox", error_messages)
    
    def test_invalid_capabilities_structure(self):
        """Test validation fails for invalid capabilities structure."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": "invalid_string_instead_of_object",  # Should be dict
            "sandbox": {
                "commands": ["node", "./main.js"]
            }
        }
        
        helper_dir = self._create_helper_files(
            "invalid_capabilities",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("capabilities must be an object" in error for error in result["errors"]))
    
    def test_missing_required_capabilities(self):
        """Test validation fails when required capabilities are missing."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                # Missing required 'preview' and 'execute' capabilities
                "emergency_close": False
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            }
        }
        
        helper_dir = self._create_helper_files(
            "missing_capabilities", 
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        
        error_messages = ' '.join(result["errors"])
        self.assertIn("preview", error_messages)
        self.assertIn("execute", error_messages)
    
    def test_invalid_capability_types(self):
        """Test validation fails when capabilities have wrong types."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": "yes",  # Should be boolean
                "execute": 1,      # Should be boolean
                "emergency_close": False
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            }
        }
        
        helper_dir = self._create_helper_files(
            "invalid_capability_types",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        
        error_messages = ' '.join(result["errors"])
        self.assertIn("must be boolean", error_messages)
    
    def test_invalid_sandbox_structure(self):
        """Test validation fails for invalid sandbox configuration."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": "invalid_string_instead_of_object"  # Should be dict
        }
        
        helper_dir = self._create_helper_files(
            "invalid_sandbox",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("sandbox must be an object" in error for error in result["errors"]))
    
    def test_missing_sandbox_commands(self):
        """Test validation fails when sandbox commands are missing."""
        manifest = {
            "purpose": "Test helper", 
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                # Missing required 'commands' field
                "cpu": {"max_ms": 1000}
            }
        }
        
        helper_dir = self._create_helper_files(
            "missing_commands",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("sandbox.commands is required" in error for error in result["errors"]))
    
    def test_empty_sandbox_commands(self):
        """Test validation fails for empty sandbox commands."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": []  # Empty array
            }
        }
        
        helper_dir = self._create_helper_files(
            "empty_commands",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("must be non-empty array" in error for error in result["errors"]))
    
    def test_invalid_risk_level(self):
        """Test validation fails for invalid risk level."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            },
            "metadata": {
                "risk_level": "invalid_level"  # Should be low/medium/high
            }
        }
        
        helper_dir = self._create_helper_files(
            "invalid_risk_level",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("Invalid risk_level" in error for error in result["errors"]))
        self.assertTrue(any("Must be one of: low, medium, high" in error for error in result["errors"]))
    
    def test_invalid_json_schema(self):
        """Test validation fails for invalid JSON schema files."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            }
        }
        
        # Create invalid JSON schema
        invalid_schema = {
            "type": "invalid_type",  # Invalid JSON Schema type
            "properties": "should_be_object"  # Invalid properties structure
        }
        
        helper_dir = self._create_helper_files(
            "invalid_schema",
            manifest,
            invalid_schema,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("schema.json: Invalid JSON Schema" in error for error in result["errors"]))
    
    def test_malformed_json_in_schema(self):
        """Test validation fails for malformed JSON in schema files."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            }
        }
        
        helper_dir = self.test_dir / "malformed_json_helper"
        helper_dir.mkdir()
        
        # Create helper.yaml
        with open(helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(manifest, f)
        
        # Create malformed JSON schema
        with open(helper_dir / "input.schema.json", 'w') as f:
            f.write('{"type": "object", "missing_quote: true}')  # Missing quote
        
        # Create valid output schema
        with open(helper_dir / "output.schema.json", 'w') as f:
            json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("Invalid JSON" in error for error in result["errors"]))
    
    def test_missing_schema_path(self):
        """Test validation fails when schema path referenced in manifest doesn't exist."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            },
            "schema": {
                "input": "./nonexistent_input.schema.json",
                "output": "./output.schema.json"
            }
        }
        
        helper_dir = self._create_helper_files(
            "missing_schema_path",
            manifest,
            None,  # Don't create input schema
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertFalse(result["valid"])
        self.assertTrue(any("Schema path not found" in error for error in result["errors"]))
        self.assertTrue(any("nonexistent_input.schema.json" in error for error in result["errors"]))
    
    def test_warnings_for_missing_best_practices(self):
        """Test warnings are generated for missing recommended sections."""
        # Minimal valid manifest without metadata/environment
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": False
            },
            "sandbox": {
                "commands": ["echo", "test"]
            }
        }
        
        helper_dir = self._create_helper_files(
            "minimal_helper",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            False
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertTrue(result["valid"])  # Should still be valid
        self.assertGreater(len(result["warnings"]), 0)  # Should have warnings
        
        warning_messages = ' '.join(result["warnings"])
        self.assertIn("metadata", warning_messages)
        self.assertIn("environment", warning_messages)
    
    def test_executable_permission_warning(self):
        """Test warning for non-executable script files."""
        manifest = {
            "purpose": "Test helper",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["node", "./main.js"]
            }
        }
        
        helper_dir = self._create_helper_files(
            "non_executable",
            manifest,
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"},
            True,  # Create script
            False  # But not executable
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertTrue(result["valid"])  # Should still be valid
        self.assertTrue(any("not executable" in warning for warning in result["warnings"]))


class TestHelperManifestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions in manifest validation."""
    
    def setUp(self):
        """Set up test environment."""
        if not VALIDATION_AVAILABLE:
            self.skipTest("Helper validation not available")
        
        self.test_dir = Path(tempfile.mkdtemp(prefix="helper_edge_test_"))
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_nonexistent_helper_directory(self):
        """Test validation handles nonexistent helper directory gracefully."""
        nonexistent_dir = self.test_dir / "does_not_exist"
        
        result = validate_helper_manifest(nonexistent_dir)
        
        self.assertFalse(result["valid"])
        self.assertEqual(result["helper_id"], "does_not_exist")
        self.assertGreater(len(result["errors"]), 0)
    
    def test_helper_directory_is_file(self):
        """Test validation handles case where helper path is a file, not directory."""
        # Create a file instead of directory
        helper_file = self.test_dir / "helper_file.txt"
        helper_file.write_text("not a directory")
        
        result = validate_helper_manifest(helper_file)
        
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["errors"]), 0)
    
    def test_absolute_schema_paths(self):
        """Test validation handles absolute schema paths correctly."""
        # Create schemas in a different location
        schema_dir = self.test_dir / "schemas"
        schema_dir.mkdir()
        
        input_schema_path = schema_dir / "input.schema.json"
        output_schema_path = schema_dir / "output.schema.json"
        
        with open(input_schema_path, 'w') as f:
            json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        with open(output_schema_path, 'w') as f:
            json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        manifest = {
            "purpose": "Test helper with absolute paths",
            "capabilities": {
                "preview": True,
                "execute": False
            },
            "sandbox": {
                "commands": ["echo", "test"]
            },
            "schema": {
                "input": str(input_schema_path),
                "output": str(output_schema_path)
            }
        }
        
        helper_dir = self.test_dir / "absolute_paths_helper"
        helper_dir.mkdir()
        
        with open(helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(manifest, f)
        
        # Create the default schema files too
        with open(helper_dir / "input.schema.json", 'w') as f:
            json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        with open(helper_dir / "output.schema.json", 'w') as f:
            json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertTrue(result["valid"], f"Validation failed: {result['errors']}")


if __name__ == "__main__":
    # Run tests with specific test methods for debugging
    unittest.main(verbosity=2)