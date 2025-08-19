#!/usr/bin/env python3
"""
TinyIntent Helper Lifecycle & Versioning Tests - M8.3

Tests helper versioning metadata including version numbers, dates, and maintainers.
Validates that helpers with valid metadata are loaded and invalid metadata disables helpers.
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
    from resolve import helper_resolver
    from sdk import validate_helper_manifest, _is_valid_semver, _is_valid_date, HelperRegistryEntry
    VERSIONING_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helper versioning not available: {e}")
    VERSIONING_AVAILABLE = False

try:
    import requests
    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False


class TestHelperVersionValidation(unittest.TestCase):
    """Test helper version metadata validation."""
    
    def setUp(self):
        """Set up test environment."""
        if not VERSIONING_AVAILABLE:
            self.skipTest("Helper versioning not available")
        
        # Create temporary directory for test helpers
        self.test_dir = Path(tempfile.mkdtemp(prefix="helper_version_test_"))
        
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary directory
        if hasattr(self, 'test_dir') and self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def _create_helper_manifest(self, helper_id: str, version: str = None, 
                               added: str = None, updated: str = None, 
                               maintainer: str = None):
        """Create a helper with version metadata."""
        helper_dir = self.test_dir / helper_id
        helper_dir.mkdir(parents=True, exist_ok=True)
        
        # Base manifest
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
            }
        }
        
        # Add version metadata if provided
        if version is not None:
            manifest["version"] = version
        if added is not None:
            manifest["added"] = added
        if updated is not None:
            manifest["updated"] = updated
        if maintainer is not None:
            manifest["maintainer"] = maintainer
        
        # Create manifest file
        with open(helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(manifest, f)
        
        # Create required schema files
        input_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"operation": {"type": "string"}},
            "required": ["operation"]
        }
        
        output_schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object", 
            "properties": {"status": {"type": "string"}},
            "required": ["status"]
        }
        
        with open(helper_dir / "input.schema.json", 'w') as f:
            json.dump(input_schema, f)
        
        with open(helper_dir / "output.schema.json", 'w') as f:
            json.dump(output_schema, f)
        
        return helper_dir
    
    def test_valid_semver_versions(self):
        """Test that valid semantic versions are accepted."""
        valid_versions = [
            "1.0.0",
            "2.1.3", 
            "0.0.1",
            "10.20.30",
            "1.0.0-alpha",
            "1.0.0-alpha.1",
            "1.0.0-beta.2",
            "1.0.0-rc.1",
            "1.0.0+build.1",
            "1.0.0-alpha+build.1",
            "2.0.0-alpha.1+build.123"
        ]
        
        for version in valid_versions:
            with self.subTest(version=version):
                self.assertTrue(_is_valid_semver(version), 
                              f"Version {version} should be valid")
                
                # Test with manifest validation
                helper_dir = self._create_helper_manifest("test_valid_version", version=version)
                result = validate_helper_manifest(helper_dir)
                
                self.assertTrue(result["valid"], 
                              f"Helper with version {version} should be valid: {result['errors']}")
    
    def test_invalid_semver_versions(self):
        """Test that invalid semantic versions are rejected."""
        invalid_versions = [
            "1",
            "1.0", 
            "1.0.0.0",
            "1.0.0-",
            "1.0.0+",
            "1.0.0-alpha..1",
            "1.0.0-alpha.",
            "1.0.0+build.",
            "01.0.0",  # Leading zeros
            "1.01.0",
            "1.0.01",
            "v1.0.0",  # v prefix
            "1.0.0-alpha_1",  # Invalid pre-release
            "1.0.0+build/1"   # Invalid build metadata
        ]
        
        for version in invalid_versions:
            with self.subTest(version=version):
                self.assertFalse(_is_valid_semver(version), 
                               f"Version {version} should be invalid")
                
                # Test with manifest validation
                helper_dir = self._create_helper_manifest("test_invalid_version", version=version)
                result = validate_helper_manifest(helper_dir)
                
                self.assertFalse(result["valid"], 
                               f"Helper with version {version} should be invalid")
                self.assertTrue(any("Invalid version format" in error for error in result["errors"]))
    
    def test_valid_date_formats(self):
        """Test that valid date formats are accepted."""
        valid_dates = [
            "2024-01-01",
            "2025-08-19", 
            "1999-12-31",
            "2000-02-29",  # Leap year
            "2024-02-29"   # Leap year
        ]
        
        for date in valid_dates:
            with self.subTest(date=date):
                self.assertTrue(_is_valid_date(date), 
                              f"Date {date} should be valid")
                
                # Test with manifest validation
                helper_dir = self._create_helper_manifest("test_valid_date", added=date)
                result = validate_helper_manifest(helper_dir)
                
                self.assertTrue(result["valid"], 
                              f"Helper with added date {date} should be valid: {result['errors']}")
    
    def test_invalid_date_formats(self):
        """Test that invalid date formats are rejected."""
        invalid_dates = [
            "2024-13-01",  # Invalid month
            "2024-02-30",  # Invalid day for February
            "2024-04-31",  # Invalid day for April
            "2023-02-29",  # Not a leap year
            "24-01-01",    # Invalid year format
            "2024-1-1",    # Missing leading zeros
            "2024/01/01",  # Wrong separator
            "01-01-2024",  # Wrong order
            "2024-01",     # Missing day
            "invalid"      # Not a date
        ]
        
        for date in invalid_dates:
            with self.subTest(date=date):
                self.assertFalse(_is_valid_date(date), 
                               f"Date {date} should be invalid")
                
                # Test with manifest validation
                helper_dir = self._create_helper_manifest("test_invalid_date", added=date)
                result = validate_helper_manifest(helper_dir)
                
                self.assertFalse(result["valid"], 
                               f"Helper with added date {date} should be invalid")
                self.assertTrue(any("Invalid added date format" in error for error in result["errors"]))
    
    def test_date_consistency_validation(self):
        """Test that updated date cannot be before added date."""
        # Valid case: updated after added
        helper_dir = self._create_helper_manifest(
            "test_valid_dates",
            added="2024-01-15", 
            updated="2024-08-19"
        )
        result = validate_helper_manifest(helper_dir)
        self.assertTrue(result["valid"], f"Valid date sequence should pass: {result['errors']}")
        
        # Invalid case: updated before added
        helper_dir = self._create_helper_manifest(
            "test_invalid_dates",
            added="2024-08-19", 
            updated="2024-01-15"
        )
        result = validate_helper_manifest(helper_dir)
        self.assertFalse(result["valid"], "Updated date before added date should fail")
        self.assertTrue(any("Updated date" in error and "before added date" in error 
                          for error in result["errors"]))
        
        # Same dates should be valid
        helper_dir = self._create_helper_manifest(
            "test_same_dates",
            added="2024-08-19",
            updated="2024-08-19"
        )
        result = validate_helper_manifest(helper_dir)
        self.assertTrue(result["valid"], f"Same added/updated dates should be valid: {result['errors']}")
    
    def test_helper_with_complete_metadata(self):
        """Test helper with all version metadata fields."""
        helper_dir = self._create_helper_manifest(
            "complete_metadata_helper",
            version="1.2.3-beta.1",
            added="2024-01-15",
            updated="2025-08-19", 
            maintainer="Test Team <test@example.com>"
        )
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertTrue(result["valid"], f"Complete metadata helper should be valid: {result['errors']}")
        self.assertEqual(result["helper_id"], "complete_metadata_helper")
        
        # Should not have version/maintainer warnings
        version_warnings = [w for w in result["warnings"] if "version" in w or "maintainer" in w]
        self.assertEqual(len(version_warnings), 0, "Should not have version/maintainer warnings")
    
    def test_helper_with_missing_metadata(self):
        """Test helper without version metadata gets warnings."""
        helper_dir = self._create_helper_manifest("minimal_helper")
        
        result = validate_helper_manifest(helper_dir)
        
        self.assertTrue(result["valid"], "Minimal helper should still be valid (backward compatible)")
        
        # Should have warnings for missing metadata
        warning_messages = ' '.join(result["warnings"])
        self.assertIn("version", warning_messages)
        self.assertIn("maintainer", warning_messages)
    
    def test_registry_entry_version_metadata(self):
        """Test that registry entries capture version metadata correctly."""
        # Test with complete metadata
        registry_data = {
            "name": "Test Helper",
            "description": "A test helper",
            "version": "2.1.0",
            "added": "2024-12-15",
            "updated": "2025-08-19",
            "maintainer": "Test Team <test@example.com>",
            "capabilities": ["network"]
        }
        
        entry = HelperRegistryEntry("test_helper", registry_data)
        
        self.assertEqual(entry.version, "2.1.0")
        self.assertEqual(entry.added, "2024-12-15")
        self.assertEqual(entry.updated, "2025-08-19")
        self.assertEqual(entry.maintainer, "Test Team <test@example.com>")
        
        # Test validation summary includes metadata
        summary = entry.get_validation_summary()
        self.assertIn("version", summary)
        self.assertIn("added", summary)
        self.assertIn("updated", summary)
        self.assertIn("maintainer", summary)
        
        # Test with missing metadata (backward compatibility)
        minimal_data = {
            "name": "Minimal Helper",
            "description": "Minimal test helper"
        }
        
        minimal_entry = HelperRegistryEntry("minimal_helper", minimal_data)
        self.assertIsNone(minimal_entry.version)
        self.assertIsNone(minimal_entry.added)
        self.assertIsNone(minimal_entry.updated)
        self.assertIsNone(minimal_entry.maintainer)
        
        minimal_summary = minimal_entry.get_validation_summary()
        self.assertNotIn("version", minimal_summary)
        self.assertNotIn("added", minimal_summary)
        self.assertNotIn("updated", minimal_summary)
        self.assertNotIn("maintainer", minimal_summary)
    
    def test_registry_entry_invalid_metadata(self):
        """Test that registry entries validate version metadata."""
        # Test with invalid version
        invalid_registry_data = {
            "name": "Invalid Helper", 
            "description": "Helper with invalid metadata",
            "version": "invalid-version",
            "added": "2024-13-45",  # Invalid date
            "updated": "2024-01-01",
            "maintainer": "Test Team"
        }
        
        entry = HelperRegistryEntry("invalid_helper", invalid_registry_data)
        
        # Should be marked invalid
        self.assertFalse(entry.is_valid)
        
        # Should have validation errors
        self.assertGreater(len(entry.validation_errors), 0)
        
        # Check specific errors
        error_messages = ' '.join(entry.validation_errors)
        self.assertIn("Invalid version format", error_messages)
        self.assertIn("Invalid added date format", error_messages)


class TestHelperVersioningIntegration(unittest.TestCase):
    """Test helper versioning integration with resolver and registry."""
    
    def setUp(self):
        """Set up integration test environment."""
        if not VERSIONING_AVAILABLE:
            self.skipTest("Helper versioning not available")
    
    def test_reload_includes_version_metadata(self):
        """Test that helper reload includes version metadata in response."""
        if not helper_resolver.available:
            self.skipTest("Helper resolver not available")
        
        # Perform reload
        reload_result = helper_resolver.load_helpers()
        
        self.assertIn("enabled_metadata", reload_result)
        self.assertIsInstance(reload_result["enabled_metadata"], dict)
        
        # Check that enabled helpers with metadata are included
        enabled_metadata = reload_result["enabled_metadata"]
        
        # Should have metadata for helpers that define it
        if "bot_guard" in reload_result["enabled"]:
            self.assertIn("bot_guard", enabled_metadata)
            bot_guard_meta = enabled_metadata["bot_guard"]
            self.assertIn("version", bot_guard_meta)
            self.assertEqual(bot_guard_meta["version"], "2.1.0")
            self.assertIn("updated", bot_guard_meta)
            
        if "log_tailer" in reload_result["enabled"]:
            self.assertIn("log_tailer", enabled_metadata)
            log_tailer_meta = enabled_metadata["log_tailer"]
            self.assertIn("version", log_tailer_meta)
            self.assertEqual(log_tailer_meta["version"], "1.2.1")
        
        print(f"✓ Reload metadata: {enabled_metadata}")
    
    def test_get_validation_summary_includes_metadata(self):
        """Test that validation summary includes version metadata."""
        if not helper_resolver.available:
            self.skipTest("Helper resolver not available")
        
        validation_summary = helper_resolver.get_validation_summary()
        
        self.assertIn("helpers", validation_summary)
        helpers = validation_summary["helpers"]
        
        # Check that helpers include version metadata
        for helper_id, helper_info in helpers.items():
            if helper_info.get("is_valid"):
                # All valid helpers should have basic fields
                self.assertIn("name", helper_info)
                self.assertIn("description", helper_info)
                
                # Check if version metadata is included where present
                if helper_id in ["bot_guard", "log_tailer"]:
                    self.assertIn("version", helper_info, f"Helper {helper_id} should have version")
                    self.assertIn("updated", helper_info, f"Helper {helper_id} should have updated date")
                    self.assertIn("maintainer", helper_info, f"Helper {helper_id} should have maintainer")
                
                # ssh_ops should not have metadata (testing backward compatibility)
                if helper_id == "ssh_ops":
                    self.assertNotIn("version", helper_info, "Helper ssh_ops should not have version metadata")
        
        print(f"✓ Validation summary includes metadata for enabled helpers")


@unittest.skipIf(not HTTP_CLIENT_AVAILABLE, "requests not available")
class TestHelperVersioningHTTP(unittest.TestCase):
    """Test helper versioning via HTTP endpoints."""
    
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
    
    def test_get_helpers_endpoint_exists(self):
        """Test that GET /helpers endpoint exists and responds."""
        try:
            response = requests.get(
                f"{self.base_url}/helpers",
                headers=self.auth_headers,
                timeout=10
            )
            
            # Should not be 404 (not found)
            self.assertNotEqual(response.status_code, 404, 
                              "GET /helpers endpoint not found")
            
            print(f"✓ GET /helpers endpoint exists (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to reach GET /helpers endpoint: {e}")
    
    def test_get_helpers_response_structure(self):
        """Test that GET /helpers returns expected structure with metadata."""
        try:
            response = requests.get(
                f"{self.base_url}/helpers",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check expected response structure
                expected_fields = ["status", "helpers", "total", "timestamp"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertIsInstance(data["helpers"], list)
                self.assertIsInstance(data["total"], int)
                
                # Check helper structure and metadata
                for helper in data["helpers"]:
                    required_helper_fields = ["id", "name", "description", "capabilities"]
                    for field in required_helper_fields:
                        self.assertIn(field, helper, f"Missing field '{field}' in helper")
                    
                    # Check if version metadata is included where present
                    helper_id = helper["id"]
                    if helper_id in ["bot_guard", "log_tailer"]:
                        self.assertIn("version", helper, f"Helper {helper_id} should have version")
                        self.assertIn("updated", helper, f"Helper {helper_id} should have updated date")
                        self.assertIn("maintainer", helper, f"Helper {helper_id} should have maintainer")
                
                print(f"✓ GET /helpers response structure valid with {len(data['helpers'])} helpers")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for GET /helpers endpoint (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test GET /helpers endpoint: {e}")
    
    def test_helpers_reload_includes_metadata(self):
        """Test that POST /helpers/reload includes version metadata in response."""
        try:
            response = requests.post(
                f"{self.base_url}/helpers/reload",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check for metadata field
                self.assertIn("enabled_metadata", data, "Response should include enabled_metadata")
                self.assertIsInstance(data["enabled_metadata"], dict)
                
                # Check that helpers with version info have metadata
                enabled_metadata = data["enabled_metadata"]
                enabled = data["enabled"]
                
                if "bot_guard" in enabled:
                    self.assertIn("bot_guard", enabled_metadata)
                    bot_guard_meta = enabled_metadata["bot_guard"]
                    self.assertIn("version", bot_guard_meta)
                
                print(f"✓ POST /helpers/reload includes metadata: {enabled_metadata}")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for reload endpoint (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected reload response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test reload endpoint metadata: {e}")


if __name__ == "__main__":
    # Run tests with detailed output
    unittest.main(verbosity=2)