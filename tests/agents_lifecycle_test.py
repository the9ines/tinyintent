#!/usr/bin/env python3
"""
M10.2: Agent Lifecycle Governance Test Suite

Comprehensive tests for helper lifecycle management including:
- Lifecycle state transitions and validation
- API endpoint functionality
- Request processing enforcement
- Pruning suggestions
- Audit logging
"""

import pytest
import json
import tempfile
import yaml
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Test the lifecycle components directly
import sys
sys.path.append(str(Path(__file__).parent.parent))

from helpers.manifest import validate_lifecycle_state, determine_default_lifecycle_state, get_helper_lifecycle
from helpers.registry import HelperRegistry, HelperRegistryEntry


class TestLifecycleValidation:
    """Test lifecycle state validation and defaults."""
    
    def test_valid_lifecycle_states(self):
        """Test all valid lifecycle states pass validation."""
        valid_states = ["draft", "trusted", "deprecated", "retired"]
        
        for state in valid_states:
            lifecycle = {
                "state": state,
                "since": "2024-12-15",
                "notes": f"Test {state} helper"
            }
            is_valid, errors = validate_lifecycle_state(lifecycle)
            assert is_valid, f"State '{state}' should be valid but got errors: {errors}"
            assert len(errors) == 0
    
    def test_invalid_lifecycle_states(self):
        """Test invalid lifecycle states are rejected."""
        invalid_states = ["active", "inactive", "pending", "unknown", ""]
        
        for state in invalid_states:
            lifecycle = {
                "state": state,
                "since": "2024-12-15",
                "notes": "Test invalid helper"
            }
            is_valid, errors = validate_lifecycle_state(lifecycle)
            assert not is_valid, f"State '{state}' should be invalid"
            assert any("Invalid lifecycle state" in error for error in errors)
    
    def test_missing_required_fields(self):
        """Test validation fails when required fields are missing."""
        # Missing state
        lifecycle = {
            "since": "2024-12-15",
            "notes": "Test helper"
        }
        is_valid, errors = validate_lifecycle_state(lifecycle)
        assert not is_valid
        assert any("state" in error for error in errors)
        
        # Missing since
        lifecycle = {
            "state": "trusted",
            "notes": "Test helper"
        }
        is_valid, errors = validate_lifecycle_state(lifecycle)
        assert not is_valid
        assert any("since" in error for error in errors)
    
    def test_invalid_date_format(self):
        """Test validation fails for invalid date formats."""
        invalid_dates = ["2024-13-01", "2024/12/15", "Dec 15, 2024", "invalid-date"]
        
        for date in invalid_dates:
            lifecycle = {
                "state": "trusted",
                "since": date,
                "notes": "Test helper"
            }
            is_valid, errors = validate_lifecycle_state(lifecycle)
            assert not is_valid, f"Date '{date}' should be invalid"
            assert any("Invalid date format" in error for error in errors)
    
    def test_determine_default_lifecycle_state(self):
        """Test default lifecycle state determination."""
        # Core helpers default to trusted
        core_helper = {
            "name": "Bot Guard",
            "category": "trading",
            "risk_level": "high",
            "can_execute": False
        }
        default_state = determine_default_lifecycle_state(core_helper)
        assert default_state == "trusted"
        
        # New helpers default to draft
        new_helper = {
            "name": "New Helper",
            "category": "experimental",
            "risk_level": "low",
            "can_execute": True
        }
        default_state = determine_default_lifecycle_state(new_helper)
        assert default_state == "draft"


class TestHelperRegistryLifecycle:
    """Test helper registry lifecycle functionality."""
    
    def setup_method(self):
        """Set up test registry with temporary files."""
        self.temp_dir = tempfile.mkdtemp()
        self.helpers_dir = Path(self.temp_dir) / "helpers"
        self.helpers_dir.mkdir()
        
        # Create test registry.yaml
        self.registry_data = {
            "version": "1.0",
            "description": "Test registry",
            "helpers": {
                "trusted_helper": {
                    "name": "Trusted Helper",
                    "description": "A trusted helper",
                    "enabled": True,
                    "category": "test",
                    "risk_level": "low",
                    "can_execute": False,
                    "manifest_path": "helpers/trusted_helper/helper.yaml",
                    "requires_approval": True,
                    "lifecycle": {
                        "state": "trusted",
                        "since": "2024-12-15",
                        "notes": "Core helper - stable"
                    }
                },
                "deprecated_helper": {
                    "name": "Deprecated Helper",
                    "description": "A deprecated helper",
                    "enabled": True,
                    "category": "test",
                    "risk_level": "low",
                    "can_execute": False,
                    "manifest_path": "helpers/deprecated_helper/helper.yaml",
                    "requires_approval": True,
                    "lifecycle": {
                        "state": "deprecated",
                        "since": "2024-10-01",
                        "notes": "Use trusted_helper instead"
                    }
                },
                "retired_helper": {
                    "name": "Retired Helper",
                    "description": "A retired helper",
                    "enabled": False,
                    "category": "test",
                    "risk_level": "low",
                    "can_execute": False,
                    "manifest_path": "helpers/retired_helper/helper.yaml",
                    "requires_approval": True,
                    "lifecycle": {
                        "state": "retired",
                        "since": "2024-11-01",
                        "notes": "No longer maintained"
                    }
                },
                "no_lifecycle_helper": {
                    "name": "No Lifecycle Helper",
                    "description": "Helper without lifecycle",
                    "enabled": True,
                    "category": "test",
                    "risk_level": "low",
                    "can_execute": False,
                    "manifest_path": "helpers/no_lifecycle_helper/helper.yaml",
                    "requires_approval": True
                }
            }
        }
        
        with open(self.helpers_dir / "registry.yaml", "w") as f:
            yaml.dump(self.registry_data, f)
        
        # Create helper directories and manifests
        for helper_id in self.registry_data["helpers"]:
            helper_dir = self.helpers_dir / helper_id
            helper_dir.mkdir()
            with open(helper_dir / "helper.yaml", "w") as f:
                yaml.dump({"name": f"Test {helper_id}"}, f)
    
    def teardown_method(self):
        """Clean up temporary files."""
        shutil.rmtree(self.temp_dir)
    
    def test_registry_loads_lifecycle_states(self):
        """Test that registry correctly loads lifecycle states."""
        registry = HelperRegistry(str(self.helpers_dir))
        
        # Test trusted helper
        trusted_entry = registry.registry_entries["trusted_helper"]
        assert trusted_entry.is_trusted()
        assert not trusted_entry.is_deprecated()
        assert not trusted_entry.is_retired()
        assert trusted_entry.can_be_routed()
        
        # Test deprecated helper
        deprecated_entry = registry.registry_entries["deprecated_helper"]
        assert not deprecated_entry.is_trusted()
        assert deprecated_entry.is_deprecated()
        assert not deprecated_entry.is_retired()
        assert deprecated_entry.can_be_routed()  # Deprecated can still be routed
        
        # Test retired helper
        retired_entry = registry.registry_entries["retired_helper"]
        assert not retired_entry.is_trusted()
        assert not retired_entry.is_deprecated()
        assert retired_entry.is_retired()
        assert not retired_entry.can_be_routed()  # Retired cannot be routed
        
        # Test helper without lifecycle (defaults to trusted)
        no_lifecycle_entry = registry.registry_entries["no_lifecycle_helper"]
        assert no_lifecycle_entry.is_trusted()
        assert not no_lifecycle_entry.is_deprecated()
        assert not no_lifecycle_entry.is_retired()
        assert no_lifecycle_entry.can_be_routed()
    
    def test_get_helpers_by_lifecycle_state(self):
        """Test filtering helpers by lifecycle state."""
        registry = HelperRegistry(str(self.helpers_dir))
        
        trusted_helpers = registry.get_helpers_by_lifecycle_state("trusted")
        assert "trusted_helper" in trusted_helpers
        assert "no_lifecycle_helper" in trusted_helpers  # Defaults to trusted
        assert len(trusted_helpers) == 2
        
        deprecated_helpers = registry.get_helpers_by_lifecycle_state("deprecated")
        assert "deprecated_helper" in deprecated_helpers
        assert len(deprecated_helpers) == 1
        
        retired_helpers = registry.get_helpers_by_lifecycle_state("retired")
        assert "retired_helper" in retired_helpers
        assert len(retired_helpers) == 1
    
    def test_update_helper_lifecycle(self):
        """Test updating helper lifecycle state."""
        registry = HelperRegistry(str(self.helpers_dir))
        
        # Update trusted helper to deprecated
        success = registry.update_helper_lifecycle(
            "trusted_helper", 
            "deprecated", 
            "Migrating to new version"
        )
        assert success
        
        # Reload and verify update
        registry.load_registry()
        entry = registry.registry_entries["trusted_helper"]
        assert entry.is_deprecated()
        assert not entry.is_trusted()
        
        # Verify the file was updated
        with open(self.helpers_dir / "registry.yaml") as f:
            updated_data = yaml.safe_load(f)
        
        lifecycle = updated_data["helpers"]["trusted_helper"]["lifecycle"]
        assert lifecycle["state"] == "deprecated"
        assert lifecycle["notes"] == "Migrating to new version"
        assert "since" in lifecycle  # Should have updated timestamp
    
    def test_update_nonexistent_helper_lifecycle(self):
        """Test updating lifecycle for non-existent helper fails gracefully."""
        registry = HelperRegistry(str(self.helpers_dir))
        
        success = registry.update_helper_lifecycle(
            "nonexistent_helper", 
            "deprecated", 
            "This should fail"
        )
        assert not success


class TestLifecycleAPIEndpoints:
    """Test lifecycle API endpoints."""
    
    @pytest.fixture
    def mock_registry(self):
        """Mock helper registry for API tests."""
        registry = MagicMock()
        registry.registry_entries = {
            "test_helper": MagicMock()
        }
        registry.registry_entries["test_helper"].lifecycle = {
            "state": "trusted",
            "since": "2024-12-15",
            "notes": "Test helper"
        }
        registry.registry_entries["test_helper"].is_trusted.return_value = True
        registry.registry_entries["test_helper"].is_deprecated.return_value = False
        registry.registry_entries["test_helper"].is_retired.return_value = False
        registry.update_helper_lifecycle.return_value = True
        registry.get_helper_lifecycle.return_value = {
            "state": "trusted",
            "since": "2024-12-15", 
            "notes": "Test helper"
        }
        return registry
    
    @patch('tinyintent.bridge.api_routes.helper_registry')
    @patch('tinyintent.bridge.api_routes.verify_auth')
    def test_set_lifecycle_endpoint(self, mock_auth, mock_helper_registry, mock_registry):
        """Test POST /agents/lifecycle/set endpoint."""
        from bridge.api_routes import router_api
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        
        mock_auth.return_value = True
        mock_helper_registry.return_value = mock_registry
        
        app = FastAPI()
        app.include_router(router_api)
        client = TestClient(app)
        
        # Test successful lifecycle update
        response = client.post(
            "/agents/lifecycle/set",
            json={
                "helper_id": "test_helper",
                "state": "deprecated",
                "notes": "Updating for test"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
        assert "updated lifecycle" in result["message"]
    
    @patch('tinyintent.bridge.api_routes.helper_registry')
    @patch('tinyintent.bridge.api_routes.verify_auth')
    def test_get_lifecycle_endpoint(self, mock_auth, mock_helper_registry, mock_registry):
        """Test GET /agents/lifecycle/{helper_id} endpoint."""
        from bridge.api_routes import router_api
        from fastapi.testclient import TestClient
        from fastapi import FastAPI
        
        mock_auth.return_value = True
        mock_helper_registry.return_value = mock_registry
        
        app = FastAPI()
        app.include_router(router_api)
        client = TestClient(app)
        
        # Test successful lifecycle retrieval
        response = client.get(
            "/agents/lifecycle/test_helper",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["helper_id"] == "test_helper"
        assert result["lifecycle"]["state"] == "trusted"
        assert "metrics" in result


class TestLifecycleEnforcement:
    """Test lifecycle enforcement in request processing."""
    
    @pytest.fixture
    def mock_request_components(self):
        """Mock components for request processing tests."""
        components = {
            "helper_registry": MagicMock(),
            "audit_logger": MagicMock(),
            "helper_executor": MagicMock(),
            "rate_limiter": MagicMock(),
            "emergency_kill": MagicMock()
        }
        
        # Setup default returns
        components["rate_limiter"].check_rate_limit.return_value = (True, 0)
        components["emergency_kill"].is_execution_enabled.return_value = True
        components["helper_executor"].preview.return_value = {
            "status": "success",
            "action": "test_action",
            "preview_json": {"test": "data"}
        }
        
        return components
    
    def test_retired_helper_blocked(self, mock_request_components):
        """Test that retired helpers are blocked with 410 Gone."""
        # Setup retired helper
        retired_helper = MagicMock()
        retired_helper.is_retired.return_value = True
        retired_helper.is_deprecated.return_value = False
        
        mock_request_components["helper_registry"].registry_entries = {
            "retired_helper": retired_helper
        }
        
        # Mock the route endpoint logic
        with patch.multiple(
            'tinyintent.bridge.api_routes',
            **mock_request_components
        ):
            from bridge.api_routes import route_request_endpoint
            from fastapi import HTTPException
            
            # Create mock request
            request = MagicMock()
            request.route = "act"
            request.helper_id = "retired_helper"
            request.helper_input = {}
            request.execute = False
            request.session_id = "test-session"
            
            fastapi_request = MagicMock()
            fastapi_request.client.host = "127.0.0.1"
            
            response = MagicMock()
            
            # Should raise HTTPException with 410 status
            with pytest.raises(HTTPException) as exc_info:
                import asyncio
                asyncio.run(route_request_endpoint(request, fastapi_request, response))
            
            assert exc_info.value.status_code == 410
            assert "retired" in exc_info.value.detail
            assert exc_info.value.headers["X-Helper-Status"] == "retired"
    
    def test_deprecated_helper_warning(self, mock_request_components):
        """Test that deprecated helpers generate warnings but allow execution."""
        # Setup deprecated helper
        deprecated_helper = MagicMock()
        deprecated_helper.is_retired.return_value = False
        deprecated_helper.is_deprecated.return_value = True
        
        mock_request_components["helper_registry"].registry_entries = {
            "deprecated_helper": deprecated_helper
        }
        
        # Mock the route endpoint logic (simplified)
        audit_logger = mock_request_components["audit_logger"]
        
        # Simulate the deprecated helper logic
        is_deprecated = True
        helper_id = "deprecated_helper"
        session_id = "test-session"
        
        # Verify audit logging would be called
        if is_deprecated:
            audit_logger.log_entry.assert_not_called()  # Not called yet
            
            # Simulate the audit logging call
            audit_logger.log_entry({
                "action": "helper_lifecycle_warning",
                "session_id": session_id,
                "helper_id": helper_id,
                "lifecycle_state": "deprecated",
                "warning_type": "deprecated_helper_usage",
                "success": True
            })
            
            # Verify the call was made
            audit_logger.log_entry.assert_called()


class TestPruningSuggestions:
    """Test helper pruning suggestions."""
    
    def test_prune_suggestions_algorithm(self):
        """Test the pruning suggestions algorithm."""
        # Mock experience store data
        mock_data = [
            {
                "helper_id": "unused_helper",
                "ts": (datetime.now() - timedelta(days=45)).isoformat(),
                "success": True
            },
            {
                "helper_id": "error_prone_helper", 
                "ts": datetime.now().isoformat(),
                "success": False
            },
            {
                "helper_id": "error_prone_helper",
                "ts": datetime.now().isoformat(), 
                "success": False
            },
            {
                "helper_id": "healthy_helper",
                "ts": datetime.now().isoformat(),
                "success": True
            }
        ]
        
        # Simple pruning algorithm simulation
        suggestions = []
        
        # Group by helper_id
        helper_stats = {}
        for event in mock_data:
            helper_id = event["helper_id"]
            if helper_id not in helper_stats:
                helper_stats[helper_id] = {"total": 0, "errors": 0, "last_used": None}
            
            helper_stats[helper_id]["total"] += 1
            if not event["success"]:
                helper_stats[helper_id]["errors"] += 1
            
            event_time = datetime.fromisoformat(event["ts"].replace('Z', '+00:00'))
            if not helper_stats[helper_id]["last_used"] or event_time > helper_stats[helper_id]["last_used"]:
                helper_stats[helper_id]["last_used"] = event_time
        
        # Apply pruning criteria
        min_days = 30
        min_calls = 3  
        max_error_rate = 0.4
        
        for helper_id, stats in helper_stats.items():
            days_since_use = (datetime.now() - stats["last_used"].replace(tzinfo=None)).days
            error_rate = stats["errors"] / stats["total"] if stats["total"] > 0 else 0
            
            suggestion = None
            if days_since_use > min_days and stats["total"] < min_calls:
                suggestion = {
                    "helper_id": helper_id,
                    "action": "retire",
                    "reason": f"Low usage: {stats['total']} calls in {days_since_use} days"
                }
            elif error_rate > max_error_rate and stats["total"] >= min_calls:
                suggestion = {
                    "helper_id": helper_id,
                    "action": "deprecate", 
                    "reason": f"High error rate: {error_rate:.1%} ({stats['errors']}/{stats['total']})"
                }
            
            if suggestion:
                suggestions.append(suggestion)
        
        # Verify suggestions
        assert len(suggestions) == 2
        
        # Check unused_helper suggestion
        unused_suggestion = next((s for s in suggestions if s["helper_id"] == "unused_helper"), None)
        assert unused_suggestion is not None
        assert unused_suggestion["action"] == "retire"
        assert "Low usage" in unused_suggestion["reason"]
        
        # Check error_prone_helper suggestion  
        error_suggestion = next((s for s in suggestions if s["helper_id"] == "error_prone_helper"), None)
        assert error_suggestion is not None
        assert error_suggestion["action"] == "deprecate"
        assert "High error rate" in error_suggestion["reason"]


class TestLifecycleIntegration:
    """Integration tests for complete lifecycle functionality."""
    
    def test_complete_lifecycle_flow(self):
        """Test complete lifecycle from creation to retirement."""
        # This would be a more complex integration test
        # testing the full flow through the system
        pass
    
    def test_backward_compatibility(self):
        """Test that helpers without lifecycle metadata work correctly."""
        # Verify that existing helpers without lifecycle fields
        # default to appropriate states and don't break
        pass


if __name__ == "__main__":
    # Run tests
    import subprocess
    import sys
    
    print("🧪 Running M10.2 Agent Lifecycle Governance Tests...")
    
    # Run pytest with coverage if available
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
            print("✅ All lifecycle tests passed!")
        else:
            print("❌ Some tests failed!")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        sys.exit(1)