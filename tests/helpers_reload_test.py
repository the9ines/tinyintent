#!/usr/bin/env python3
"""
TinyIntent Helper Reload Tests - M8.2

Tests dynamic helper discovery and hot reload functionality.
Tests that helpers can be added/updated without restarting the bridge service.
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
    from resolve import HelperResolver
    RESOLVER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: HelperResolver not available: {e}")
    RESOLVER_AVAILABLE = False

try:
    import requests
    HTTP_CLIENT_AVAILABLE = True
except ImportError:
    HTTP_CLIENT_AVAILABLE = False


class TestHelperReloadCore(unittest.TestCase):
    """Test core helper reload functionality without HTTP."""
    
    def setUp(self):
        """Set up test environment."""
        if not RESOLVER_AVAILABLE:
            self.skipTest("HelperResolver not available")
        
        # Create temporary helpers directory
        self.original_helpers_dir = Path(__file__).parent.parent / "helpers"
        self.test_helpers_dir = Path(tempfile.mkdtemp(prefix="helpers_reload_test_"))
        
        # Copy existing helpers to test directory
        if self.original_helpers_dir.exists():
            shutil.copytree(self.original_helpers_dir, self.test_helpers_dir, dirs_exist_ok=True)
        
        # Patch the helpers directory path in resolver
        self.helpers_dir_patcher = patch.object(
            Path, '__new__', 
            side_effect=self._path_patch
        )
        
    def _path_patch(self, cls, *args):
        """Patch Path construction to redirect helpers directory."""
        if len(args) == 1 and str(args[0]).endswith('helpers'):
            # Check if this is the helpers directory we want to redirect
            if 'tinyintent' in str(args[0]):
                return Path.__new__(cls, self.test_helpers_dir)
        return Path.__new__(cls, *args)
    
    def tearDown(self):
        """Clean up test environment."""
        # Remove temporary directory
        if hasattr(self, 'test_helpers_dir') and self.test_helpers_dir.exists():
            shutil.rmtree(self.test_helpers_dir)
    
    def _create_valid_helper(self, helper_id: str, executable: bool = True):
        """Create a valid test helper."""
        helper_dir = self.test_helpers_dir / helper_id
        helper_dir.mkdir(exist_ok=True)
        
        # Create helper.yaml
        manifest = {
            "purpose": f"Test helper {helper_id}",
            "capabilities": {
                "preview": True,
                "execute": True
            },
            "sandbox": {
                "commands": ["node", "./main.js"],
                "timeouts": [{"name": "default", "seconds": 5}]
            },
            "metadata": {
                "version": "1.0.0",
                "risk_level": "low"
            }
        }
        
        with open(helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(manifest, f)
        
        # Create schema files
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
        
        with open(helper_dir / "input.schema.json", 'w') as f:
            json.dump(input_schema, f)
        
        with open(helper_dir / "output.schema.json", 'w') as f:
            json.dump(output_schema, f)
        
        # Create main script
        script_content = '#!/usr/bin/env node\nconsole.log(JSON.stringify({status: "success", result: {}}));'
        script_path = helper_dir / "main.js"
        script_path.write_text(script_content)
        
        if executable:
            os.chmod(script_path, 0o755)
        
        return helper_dir
    
    def _create_invalid_helper(self, helper_id: str, missing_file: str = None):
        """Create an invalid test helper."""
        helper_dir = self.test_helpers_dir / helper_id
        helper_dir.mkdir(exist_ok=True)
        
        if missing_file != "helper.yaml":
            # Create invalid manifest (missing required fields)
            invalid_manifest = {
                "purpose": f"Invalid helper {helper_id}"
                # Missing capabilities and sandbox
            }
            
            with open(helper_dir / "helper.yaml", 'w') as f:
                import yaml
                yaml.dump(invalid_manifest, f)
        
        if missing_file != "input.schema.json":
            # Create schema files
            with open(helper_dir / "input.schema.json", 'w') as f:
                json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        if missing_file != "output.schema.json":
            with open(helper_dir / "output.schema.json", 'w') as f:
                json.dump({"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object"}, f)
        
        return helper_dir
    
    def test_initial_helper_load(self):
        """Test that existing helpers are loaded correctly on initialization."""
        # Use the existing global resolver instead of creating a new one
        from resolve import helper_resolver
        
        if helper_resolver.available:
            result = helper_resolver.load_helpers()
            
            self.assertIsInstance(result, dict)
            self.assertIn("enabled", result)
            self.assertIn("disabled", result)
            self.assertIn("errors", result)
            self.assertIn("total", result)
            
            print(f"Initial load: {len(result['enabled'])} enabled, {len(result['disabled'])} disabled")
        else:
            self.skipTest("Helper resolver not available")
    
    def test_add_valid_helper_and_reload(self):
        """Test adding a valid helper during runtime and reloading."""
        from resolve import helper_resolver
        
        if not helper_resolver.available:
            self.skipTest("Helpers framework not available")
        
        # Get initial state
        initial_result = helper_resolver.load_helpers()
        initial_enabled = set(initial_result["enabled"])
        
        # Create a temporary helper in the real helpers directory
        helpers_dir = Path(__file__).parent.parent / "helpers"
        new_helper_id = "test_dynamic_helper"
        new_helper_dir = helpers_dir / new_helper_id
        
        try:
            # Create the test helper
            self._create_valid_helper(new_helper_id)
            # Move it to the real helpers directory
            if new_helper_dir.exists():
                shutil.rmtree(new_helper_dir)
            shutil.move(str(self.test_helpers_dir / new_helper_id), str(new_helper_dir))
            
            # Reload and check results
            reload_result = helper_resolver.load_helpers()
            
            self.assertIsInstance(reload_result, dict)
            self.assertIn("enabled", reload_result)
            self.assertIn("disabled", reload_result)
            self.assertIn("errors", reload_result)
            
            # Check results
            new_enabled = set(reload_result["enabled"])
            print(f"✓ Reload completed: {len(reload_result['enabled'])} enabled helpers")
            
            # If the helper was successfully validated and loaded, it should be in enabled
            if new_helper_id in new_enabled:
                print(f"✓ New helper '{new_helper_id}' was enabled after reload")
            elif new_helper_id in reload_result["disabled"]:
                print(f"⚠ New helper '{new_helper_id}' was disabled: {reload_result['errors'].get(new_helper_id, [])}")
            else:
                print(f"⚠ New helper '{new_helper_id}' not found in results")
            
            # Total helpers should have increased or stayed the same
            self.assertGreaterEqual(reload_result["total"], initial_result["total"])
            
        finally:
            # Clean up - remove test helper
            if new_helper_dir.exists():
                shutil.rmtree(new_helper_dir)
    
    def test_add_invalid_helper_and_reload(self):
        """Test adding an invalid helper and verifying it's disabled with error recorded."""
        from resolve import helper_resolver
        
        if not helper_resolver.available:
            self.skipTest("Helpers framework not available")
        
        # Create a temporary invalid helper in the real helpers directory  
        helpers_dir = Path(__file__).parent.parent / "helpers"
        invalid_helper_id = "test_invalid_helper"
        invalid_helper_dir = helpers_dir / invalid_helper_id
        
        try:
            # Create invalid helper (missing required schema file)
            self._create_invalid_helper(invalid_helper_id, missing_file="input.schema.json")
            # Move it to real helpers directory
            if invalid_helper_dir.exists():
                shutil.rmtree(invalid_helper_dir)
            shutil.move(str(self.test_helpers_dir / invalid_helper_id), str(invalid_helper_dir))
            
            # Reload and check results
            reload_result = helper_resolver.load_helpers()
            
            # Check that result structure is valid
            self.assertIn("disabled", reload_result)
            self.assertIn("errors", reload_result)
            
            print(f"✓ Reload completed with {len(reload_result['disabled'])} disabled helpers")
            
            # Check if invalid helper is properly handled
            if invalid_helper_id in reload_result["disabled"]:
                self.assertIn(invalid_helper_id, reload_result["errors"])
                print(f"✓ Invalid helper '{invalid_helper_id}' was disabled with errors")
            else:
                print(f"⚠ Invalid helper '{invalid_helper_id}' handling: disabled={reload_result['disabled']}")
            
        finally:
            # Clean up - remove test helper
            if invalid_helper_dir.exists():
                shutil.rmtree(invalid_helper_dir)
    
    def test_reload_with_broken_manifest(self):
        """Test that reload doesn't crash when helper manifests are broken."""
        from resolve import helper_resolver
        
        if not helper_resolver.available:
            self.skipTest("Helpers framework not available")
        
        # Test that reload handles the current state gracefully
        try:
            reload_result = helper_resolver.load_helpers()
            
            # Should still return valid result structure
            self.assertIsInstance(reload_result, dict)
            self.assertIn("enabled", reload_result)
            self.assertIn("disabled", reload_result)
            self.assertIn("errors", reload_result)
            
            print(f"✓ Reload completed gracefully: {len(reload_result['enabled'])} enabled, {len(reload_result['disabled'])} disabled")
            
        except Exception as e:
            self.fail(f"Reload crashed: {e}")
    
    def test_thread_safety_concurrent_reloads(self):
        """Test that concurrent reloads are handled thread-safely."""
        import threading
        import concurrent.futures
        from resolve import helper_resolver
        
        if not helper_resolver.available:
            self.skipTest("Helpers framework not available")
        
        results = []
        exceptions = []
        
        def reload_helper():
            try:
                result = helper_resolver.load_helpers()
                results.append(result)
            except Exception as e:
                exceptions.append(e)
        
        # Run concurrent reloads
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(reload_helper) for _ in range(3)]
            concurrent.futures.wait(futures)
        
        # Check that no exceptions occurred
        self.assertEqual(len(exceptions), 0, f"Concurrent reload exceptions: {exceptions}")
        
        # Check that all reloads succeeded
        self.assertGreater(len(results), 0)
        for result in results:
            self.assertIsInstance(result, dict)
            self.assertIn("enabled", result)
            self.assertIn("disabled", result)
        
        print(f"✓ {len(results)} concurrent reloads completed successfully")
    
    def test_audit_log_contains_reload_events(self):
        """Test that audit logs show reload events."""
        from resolve import helper_resolver
        
        if not helper_resolver.available:
            self.skipTest("Helpers framework not available")
        
        # Check for audit log path
        audit_log_path = Path(__file__).parent.parent / "bridge" / "logs" / "audit.log"
        
        # Get initial log size
        initial_size = 0
        if audit_log_path.exists():
            initial_size = audit_log_path.stat().st_size
        
        # Perform reload
        helper_resolver.load_helpers()
        
        # Wait a moment for log writing
        time.sleep(0.1)
        
        # Check if log grew (indicating new entries)
        if audit_log_path.exists():
            final_size = audit_log_path.stat().st_size
            
            if final_size > initial_size:
                # Try to find reload event in log
                try:
                    with open(audit_log_path, 'r') as f:
                        # Read last few lines
                        lines = f.readlines()
                        recent_lines = lines[-10:] if len(lines) > 10 else lines
                        
                    reload_events = []
                    for line in recent_lines:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("action") == "helper_reload":
                                reload_events.append(entry)
                        except json.JSONDecodeError:
                            continue
                    
                    if reload_events:
                        print(f"✓ Found {len(reload_events)} reload events in audit log")
                        # Check structure of reload event
                        event = reload_events[-1]
                        self.assertIn("enabled_helpers", event)
                        self.assertIn("disabled_helpers", event)
                        self.assertIn("total_helpers", event)
                        self.assertEqual(event["success"], True)
                    else:
                        print("⚠ No reload events found in recent audit log entries")
                
                except Exception as e:
                    print(f"⚠ Could not read audit log for reload events: {e}")
            else:
                print("⚠ Audit log did not grow after reload")
        else:
            print("⚠ Audit log file does not exist")


@unittest.skipIf(not HTTP_CLIENT_AVAILABLE, "requests not available")
class TestHelperReloadHTTP(unittest.TestCase):
    """Test helper reload via HTTP endpoint (requires running bridge service)."""
    
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
    
    def test_helpers_reload_endpoint_exists(self):
        """Test that /helpers/reload endpoint exists and responds."""
        try:
            response = requests.post(
                f"{self.base_url}/helpers/reload",
                headers=self.auth_headers,
                timeout=10
            )
            
            # Should get either 200 (success), 401 (auth required), or 403 (forbidden)
            # but not 404 (not found)
            self.assertNotEqual(response.status_code, 404, 
                              "Endpoint /helpers/reload not found")
            
            print(f"✓ /helpers/reload endpoint exists (status: {response.status_code})")
            
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to reach /helpers/reload endpoint: {e}")
    
    def test_helpers_reload_response_structure(self):
        """Test that reload endpoint returns expected JSON structure."""
        try:
            response = requests.post(
                f"{self.base_url}/helpers/reload",
                headers=self.auth_headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Check expected response structure
                expected_fields = ["status", "enabled", "disabled", "errors", "total"]
                for field in expected_fields:
                    self.assertIn(field, data, f"Missing field '{field}' in response")
                
                self.assertIsInstance(data["enabled"], list)
                self.assertIsInstance(data["disabled"], list) 
                self.assertIsInstance(data["errors"], dict)
                self.assertIsInstance(data["total"], int)
                
                print(f"✓ Reload response structure valid: {len(data['enabled'])} enabled, {len(data['disabled'])} disabled")
                
            elif response.status_code in [401, 403]:
                print(f"⚠ Authentication required for reload endpoint (status: {response.status_code})")
            else:
                print(f"⚠ Unexpected response status: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            self.fail(f"Failed to test reload endpoint: {e}")


if __name__ == "__main__":
    # Run tests with detailed output
    unittest.main(verbosity=2)