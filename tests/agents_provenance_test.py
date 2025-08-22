#!/usr/bin/env python3
"""
Tests for M10.5: Agent Provenance, Signing & Tamper-evidence

Tests cryptographic provenance generation, verification, and tamper detection
for agent integrity and authenticity.
"""

import pytest
import json
import tempfile
import hashlib
import hmac
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add parent directory for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import provenance modules
from tinyintent.bridge.provenance import (
    compute_helper_digest,
    create_provenance,
    sign_provenance,
    verify_provenance,
    generate_and_save_provenance,
    _ensure_key_exists,
    ProvenanceError,
    ProvenanceKeyError
)


class TestProvenanceCore:
    """Test core provenance functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.helper_dir = Path(self.temp_dir) / "test_helper"
        self.helper_dir.mkdir()
        
        # Create required helper files
        self._create_helper_files()
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_helper_files(self):
        """Create minimal helper files for testing."""
        # helper.yaml
        helper_yaml = {
            "id": "test_helper",
            "name": "Test Helper",
            "description": "A test helper"
        }
        with open(self.helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(helper_yaml, f)
        
        # input.schema.json
        input_schema = {
            "type": "object",
            "properties": {
                "operation": {"type": "string"}
            },
            "required": ["operation"]
        }
        with open(self.helper_dir / "input.schema.json", 'w') as f:
            json.dump(input_schema, f)
        
        # output.schema.json
        output_schema = {
            "type": "object",
            "properties": {
                "result": {"type": "string"}
            },
            "required": ["result"]
        }
        with open(self.helper_dir / "output.schema.json", 'w') as f:
            json.dump(output_schema, f)
        
        # main.py
        main_script = '''#!/usr/bin/env python3
import json
import sys

def main():
    print(json.dumps({"result": "success"}))

if __name__ == "__main__":
    main()
'''
        with open(self.helper_dir / "main.py", 'w') as f:
            f.write(main_script)
    
    def test_compute_helper_digest(self):
        """Test computing helper file digests."""
        # Test successful digest computation
        result = compute_helper_digest(self.helper_dir)
        
        # Verify structure
        assert "helper.yaml" in result
        assert "input.schema.json" in result
        assert "output.schema.json" in result
        assert "main.py" in result
        assert "digest" in result
        
        # Verify all hashes are SHA256 (64 hex characters)
        for filename, hash_value in result.items():
            if filename != "digest":
                assert len(hash_value) == 64
                assert all(c in '0123456789abcdef' for c in hash_value)
        
        # Verify digest is deterministic
        result2 = compute_helper_digest(self.helper_dir)
        assert result["digest"] == result2["digest"]
        
        # Test missing entrypoint
        (self.helper_dir / "main.py").unlink()
        with pytest.raises(ProvenanceError, match="No entrypoint found"):
            compute_helper_digest(self.helper_dir)
    
    def test_create_provenance(self):
        """Test creating provenance records."""
        provenance = create_provenance("test_helper", self.helper_dir, "test_generator")
        
        # Verify structure
        assert provenance["version"] == "1.0"
        assert provenance["helper_id"] == "test_helper"
        assert provenance["generator"] == "test_generator"
        assert "timestamp" in provenance
        assert "files" in provenance
        assert "digest" in provenance
        
        # Verify timestamp format
        datetime.fromisoformat(provenance["timestamp"].replace('Z', '+00:00'))
        
        # Verify file hashes
        assert "helper.yaml" in provenance["files"]
        assert "input.schema.json" in provenance["files"]
        assert "output.schema.json" in provenance["files"]
        assert "main.py" in provenance["files"]
    
    def test_provenance_signing(self):
        """Test HMAC signing of provenance records."""
        # Create test provenance
        provenance = create_provenance("test_helper", self.helper_dir, "test_generator")
        
        # Sign provenance
        signed_provenance = sign_provenance(provenance)
        
        # Verify signature was added
        assert "sig" in signed_provenance
        assert len(signed_provenance["sig"]) == 64  # SHA256 HMAC is 64 hex chars
        
        # Verify all original data is preserved
        for key, value in provenance.items():
            assert signed_provenance[key] == value
        
        # Test signing deterministic with same key
        signed_provenance2 = sign_provenance(provenance)
        assert signed_provenance["sig"] == signed_provenance2["sig"]
    
    def test_provenance_verification_success(self):
        """Test successful provenance verification."""
        # Generate and save provenance
        ok, reason, provenance_data = generate_and_save_provenance(
            "test_helper", self.helper_dir, "test_generator"
        )
        
        assert ok == True
        assert reason == "Provenance generated successfully"
        assert provenance_data is not None
        
        # Verify provenance file exists
        provenance_file = self.helper_dir / "provenance.json"
        assert provenance_file.exists()
        
        # Verify provenance
        ok, reason, details = verify_provenance(self.helper_dir)
        
        assert ok == True
        assert reason == "Provenance verification successful"
        assert details["provenance_file_exists"] == True
        assert details["signature_valid"] == True
        assert details["files_valid"] == True
        assert len(details["missing_files"]) == 0
        assert len(details["file_mismatches"]) == 0
    
    def test_provenance_verification_missing_file(self):
        """Test provenance verification with missing provenance file."""
        ok, reason, details = verify_provenance(self.helper_dir)
        
        assert ok == False
        assert reason == "Provenance file missing"
        assert details["provenance_file_exists"] == False
    
    def test_provenance_verification_tampered_file(self):
        """Test provenance verification detects tampered files."""
        # Generate and save provenance
        generate_and_save_provenance("test_helper", self.helper_dir, "test_generator")
        
        # Tamper with a file
        with open(self.helper_dir / "main.py", 'a') as f:
            f.write("\n# This is tampering")
        
        # Verify provenance (should fail)
        ok, reason, details = verify_provenance(self.helper_dir)
        
        assert ok == False
        assert reason == "File integrity check failed"
        assert details["provenance_file_exists"] == True
        assert details["signature_valid"] == True
        assert details["files_valid"] == False
        assert len(details["file_mismatches"]) > 0
        
        # Check that the tampered file is detected
        tampered_files = [m["file"] for m in details["file_mismatches"]]
        assert "main.py" in tampered_files or "overall_digest" in tampered_files
    
    def test_provenance_verification_invalid_signature(self):
        """Test provenance verification detects invalid signatures."""
        # Generate and save provenance
        generate_and_save_provenance("test_helper", self.helper_dir, "test_generator")
        
        # Tamper with the signature
        provenance_file = self.helper_dir / "provenance.json"
        with open(provenance_file, 'r') as f:
            provenance = json.load(f)
        
        provenance["sig"] = "0" * 64  # Invalid signature
        
        with open(provenance_file, 'w') as f:
            json.dump(provenance, f, indent=2)
        
        # Verify provenance (should fail)
        ok, reason, details = verify_provenance(self.helper_dir)
        
        assert ok == False
        assert reason == "Invalid HMAC signature"
        assert details["provenance_file_exists"] == True
        assert details["signature_valid"] == False
    
    def test_key_management(self):
        """Test HMAC key generation and management."""
        # Test key creation in temporary location
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('tinyintent.bridge.provenance._get_key_path') as mock_path:
                key_file = Path(temp_dir) / "test_provenance.key"
                mock_path.return_value = key_file
                
                # First call should create key
                key1 = _ensure_key_exists()
                assert len(key1) >= 32  # At least 256 bits
                assert key_file.exists()
                
                # Verify file permissions are restrictive
                assert oct(key_file.stat().st_mode)[-3:] == "400"  # Read-only for owner
                
                # Second call should read existing key
                key2 = _ensure_key_exists()
                assert key1 == key2


class TestProvenanceRegistryIntegration:
    """Test provenance integration with helper registry."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.helper_dir = Path(self.temp_dir) / "test_helper"
        self.helper_dir.mkdir()
        
        # Create helper files
        self._create_helper_files()
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_helper_files(self):
        """Create minimal helper files for testing."""
        # helper.yaml
        helper_yaml = {
            "id": "test_helper",
            "name": "Test Helper",
            "description": "A test helper"
        }
        with open(self.helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(helper_yaml, f)
        
        # input.schema.json
        with open(self.helper_dir / "input.schema.json", 'w') as f:
            json.dump({"type": "object"}, f)
        
        # output.schema.json
        with open(self.helper_dir / "output.schema.json", 'w') as f:
            json.dump({"type": "object"}, f)
        
        # main.py
        with open(self.helper_dir / "main.py", 'w') as f:
            f.write("print('test')")
    
    def test_registry_entry_provenance_verification(self):
        """Test that registry entries include provenance verification."""
        from tinyintent.helpers.registry import HelperRegistryEntry
        
        # Test with valid provenance
        generate_and_save_provenance("test_helper", self.helper_dir, "test")
        
        registry_data = {
            "name": "Test Helper",
            "manifest_path": str(self.helper_dir / "helper.yaml")
        }
        
        entry = HelperRegistryEntry("test_helper", registry_data)
        
        # Should have provenance verification results
        assert hasattr(entry, 'provenance_ok')
        assert hasattr(entry, 'provenance_reason')
        assert hasattr(entry, 'provenance_details')
        
        # With valid provenance, should be OK
        assert entry.provenance_ok == True
        
        # Test with missing provenance
        (self.helper_dir / "provenance.json").unlink()
        
        entry2 = HelperRegistryEntry("test_helper", registry_data)
        assert entry2.provenance_ok == False
        assert "Provenance file missing" in entry2.provenance_reason
        
        # Should disable execution when provenance fails
        assert entry2.can_execute == False
    
    def test_registry_entry_provenance_in_validation_summary(self):
        """Test that validation summary includes provenance information."""
        from tinyintent.helpers.registry import HelperRegistryEntry
        
        registry_data = {
            "name": "Test Helper",
            "manifest_path": str(self.helper_dir / "helper.yaml")
        }
        
        entry = HelperRegistryEntry("test_helper", registry_data)
        summary = entry.get_validation_summary()
        
        # Should include provenance fields
        assert "provenance_ok" in summary
        assert "provenance_reason" in summary
        assert summary["provenance_ok"] == False  # No provenance file


class TestProvenanceAPI:
    """Test provenance API endpoints."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.helper_dir = Path(self.temp_dir) / "test_helper"
        self.helper_dir.mkdir()
        
        # Create helper files and provenance
        self._create_helper_files_with_provenance()
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_helper_files_with_provenance(self):
        """Create helper files with valid provenance."""
        # Create basic helper files
        helper_yaml = {"id": "test_helper", "name": "Test Helper"}
        with open(self.helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump(helper_yaml, f)
        
        with open(self.helper_dir / "input.schema.json", 'w') as f:
            json.dump({"type": "object"}, f)
        
        with open(self.helper_dir / "output.schema.json", 'w') as f:
            json.dump({"type": "object"}, f)
        
        with open(self.helper_dir / "main.py", 'w') as f:
            f.write("print('test')")
        
        # Generate provenance
        generate_and_save_provenance("test_helper", self.helper_dir, "test")
    
    @pytest.mark.asyncio
    async def test_provenance_endpoint_success(self):
        """Test successful provenance endpoint call."""
        from tinyintent.bridge.api_routes import get_agent_provenance
        
        # Mock dependencies
        with patch('tinyintent.bridge.api_routes.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.api_routes.get_audit_logger') as mock_audit:
            
            # Setup mocks
            mock_entry = Mock()
            mock_entry.provenance_ok = True
            mock_entry.provenance_reason = "Provenance verification successful"
            mock_entry.provenance_details = {"signature_valid": True}
            mock_entry.manifest_path = str(self.helper_dir / "helper.yaml")
            
            mock_registry.get_registry_entry.return_value = mock_entry
            mock_audit.return_value = Mock()
            
            # Call endpoint
            response = await get_agent_provenance("test_helper", auth=True)
            
            # Verify response
            assert response.helper_id == "test_helper"
            assert response.provenance_ok == True
            assert response.reason == "Provenance verification successful"
            assert response.provenance_data is not None
            assert "sig" in response.provenance_data
            
            # Verify signature is sanitized (truncated)
            sig = response.provenance_data["sig"]
            assert "..." in sig  # Should be truncated for API response
    
    @pytest.mark.asyncio
    async def test_provenance_endpoint_helper_not_found(self):
        """Test provenance endpoint with non-existent helper."""
        from tinyintent.bridge.api_routes import get_agent_provenance
        from fastapi import HTTPException
        
        # Mock dependencies
        with patch('tinyintent.bridge.api_routes.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.api_routes.get_audit_logger') as mock_audit:
            
            # Setup mocks
            mock_registry.get_registry_entry.return_value = None
            mock_audit.return_value = Mock()
            
            # Call endpoint and expect 404
            with pytest.raises(HTTPException) as exc_info:
                await get_agent_provenance("nonexistent_helper", auth=True)
            
            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail


class TestProvenanceEnforcement:
    """Test provenance enforcement in helper execution."""
    
    def test_executor_provenance_check(self):
        """Test that executor checks provenance before execution."""
        from tinyintent.helpers.executor import HelperExecutor
        
        # Mock registry with failed provenance
        mock_registry = Mock()
        mock_entry = Mock()
        mock_entry.provenance_ok = False
        mock_entry.provenance_reason = "Test provenance failure"
        
        mock_registry.is_helper_valid.return_value = True
        mock_registry.get_registry_entry.return_value = mock_entry
        
        executor = HelperExecutor(mock_registry)
        
        # Test that execution fails with provenance error
        with pytest.raises(ValueError) as exc_info:
            executor.execute("test_helper", {"test": "data"})
        
        error = exc_info.value
        assert hasattr(error, 'error_code')
        assert error.error_code == "PROVENANCE_INVALID"
        assert "Test provenance failure" in str(error)


class TestAgentCreationWithProvenance:
    """Test agent creation includes provenance generation."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_agent_generator_includes_provenance(self):
        """Test that agent generator creates provenance."""
        from tinyintent.bridge.agent_generator import AgentGenerator
        
        # Create generator with test directory
        generator = AgentGenerator(self.temp_dir)
        
        # Create test agent spec
        spec = {
            "id": "test_generated_helper",
            "description": "A test generated helper",
            "language": "python",
            "capabilities": [],
            "can_execute": False,
            "risk_level": "high",
            "inputs": {"operation": {"type": "string"}},
            "outputs": {"result": {"type": "string"}}
        }
        
        # Generate agent
        result = generator.create_agent(spec)
        
        # Verify creation was successful
        assert result["created"] == True
        assert "provenance" in result
        
        # Verify provenance result
        provenance_result = result["provenance"]
        assert "ok" in provenance_result
        assert "reason" in provenance_result
        
        # If provenance generation succeeded, verify file exists
        if provenance_result["ok"]:
            helper_dir = Path(self.temp_dir) / "test_generated_helper"
            provenance_file = helper_dir / "provenance.json"
            assert provenance_file.exists()
            
            # Verify provenance content
            with open(provenance_file, 'r') as f:
                provenance_data = json.load(f)
            
            assert provenance_data["helper_id"] == "test_generated_helper"
            assert provenance_data["generator"] == "agent_generator"
            assert "sig" in provenance_data


class TestTamperDetection:
    """Test comprehensive tamper detection scenarios."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.helper_dir = Path(self.temp_dir) / "test_helper"
        self.helper_dir.mkdir()
        
        # Create helper files and provenance
        self._create_helper_with_provenance()
    
    def teardown_method(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_helper_with_provenance(self):
        """Create helper with valid provenance."""
        # Create helper files
        files_content = {
            "helper.yaml": {"id": "test_helper", "name": "Test Helper"},
            "input.schema.json": {"type": "object"},
            "output.schema.json": {"type": "object"},
            "main.py": "print('original')"
        }
        
        for filename, content in files_content.items():
            filepath = self.helper_dir / filename
            if filename.endswith('.json') or filename.endswith('.yaml'):
                with open(filepath, 'w') as f:
                    if filename.endswith('.yaml'):
                        import yaml
                        yaml.dump(content, f)
                    else:
                        json.dump(content, f)
            else:
                with open(filepath, 'w') as f:
                    f.write(content)
        
        # Generate provenance
        generate_and_save_provenance("test_helper", self.helper_dir, "test")
        
        # Verify initial state
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == True, f"Initial provenance should be valid: {reason}"
    
    def test_detect_script_modification(self):
        """Test detection of main script modifications."""
        # Modify main script
        with open(self.helper_dir / "main.py", 'w') as f:
            f.write("print('modified')")
        
        # Verify tamper detection
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == False
        assert "File integrity check failed" in reason
        
        # Check specific file mismatch
        mismatches = details["file_mismatches"]
        file_names = [m["file"] for m in mismatches]
        assert "main.py" in file_names or "overall_digest" in file_names
    
    def test_detect_schema_modification(self):
        """Test detection of schema modifications."""
        # Modify input schema
        with open(self.helper_dir / "input.schema.json", 'w') as f:
            json.dump({"type": "object", "malicious": True}, f)
        
        # Verify tamper detection
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == False
        
        # Check specific file mismatch
        mismatches = details["file_mismatches"]
        file_names = [m["file"] for m in mismatches]
        assert "input.schema.json" in file_names or "overall_digest" in file_names
    
    def test_detect_manifest_modification(self):
        """Test detection of helper.yaml modifications."""
        # Modify helper manifest
        with open(self.helper_dir / "helper.yaml", 'w') as f:
            import yaml
            yaml.dump({
                "id": "test_helper",
                "name": "Test Helper",
                "can_execute": True  # This would be dangerous
            }, f)
        
        # Verify tamper detection
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == False
        
        # Check specific file mismatch
        mismatches = details["file_mismatches"]
        file_names = [m["file"] for m in mismatches]
        assert "helper.yaml" in file_names or "overall_digest" in file_names
    
    def test_detect_file_deletion(self):
        """Test detection of file deletion."""
        # Delete a required file
        (self.helper_dir / "main.py").unlink()
        
        # Verify tamper detection
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == False
        assert "File verification failed" in reason or "No entrypoint found" in reason
    
    def test_provenance_regeneration_after_tamper(self):
        """Test that provenance can be regenerated after tampering."""
        # Tamper with a file
        with open(self.helper_dir / "main.py", 'w') as f:
            f.write("print('updated legitimately')")
        
        # Verify tamper detection
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == False
        
        # Regenerate provenance
        ok, reason, provenance_data = generate_and_save_provenance(
            "test_helper", self.helper_dir, "manual_update"
        )
        assert ok == True
        
        # Verify new provenance passes
        ok, reason, details = verify_provenance(self.helper_dir)
        assert ok == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])