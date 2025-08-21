#!/usr/bin/env python3
"""
Tests for M10.4: Agent Promotion & Auto-Rollback

Tests agent promotion to trusted status and automatic rollback on regressions.
"""

import pytest
import asyncio
import json
import tempfile
import sqlite3
import yaml
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

# Add parent directory for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tinyintent.data.episodes.episodes import AgentStagingStorage
from scripts.eval_agents import AgentEvaluator, PROMOTION_THRESHOLDS, ROLLBACK_THRESHOLDS
from tinyintent.helpers.registry import HelperRegistry, HelperRegistryEntry


class TestPromotionEvaluation:
    """Test promotion evaluation logic."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = AgentStagingStorage(Path(self.temp_db.name))
        
        # Patch the global storage
        self.patcher = patch('scripts.eval_agents.agent_staging_storage', self.storage)
        self.patcher.start()
        
        self.evaluator = AgentEvaluator()
    
    def teardown_method(self):
        """Clean up test environment."""
        self.patcher.stop()
        Path(self.temp_db.name).unlink(missing_ok=True)
    
    def test_promotion_criteria_satisfied(self):
        """Test promotion when all criteria are satisfied."""
        helper_id = "promotion_test_helper"
        
        # Seed staging data that meets promotion criteria
        for i in range(25):  # Exceed minimum calls requirement
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100 + (i % 10),  # Low latency
                success=True,  # High success rate
                output_data={"result": "success"}
            )
        
        # Mock helper info
        with patch.object(self.evaluator, '_get_helper_info') as mock_helper_info:
            mock_helper_info.return_value = {
                "valid": True,
                "exists": True,
                "name": "Test Helper"
            }
            
            # Evaluate for promotion
            result = self.evaluator.evaluate_for_promotion(helper_id, 24)
            
            # Verify promotion decision
            assert result["promote"] == True
            assert result["decision"] == "PROMOTE"
            assert result["metrics"]["shadow_runs"] == 25
            assert result["metrics"]["success_rate"] == 1.0
            assert result["metrics"]["error_rate"] == 0.0
            assert all(result["checks"].values())
            assert "All promotion criteria satisfied" in result["reasons"]
    
    def test_promotion_criteria_insufficient_data(self):
        """Test promotion rejection due to insufficient data."""
        helper_id = "insufficient_data_helper"
        
        # Seed only a few runs (below minimum)
        for i in range(5):
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=True,
                output_data={"result": "success"}
            )
        
        # Mock helper info
        with patch.object(self.evaluator, '_get_helper_info') as mock_helper_info:
            mock_helper_info.return_value = {
                "valid": True,
                "exists": True,
                "name": "Test Helper"
            }
            
            # Evaluate for promotion
            result = self.evaluator.evaluate_for_promotion(helper_id, 24)
            
            # Verify promotion rejection
            assert result["promote"] == False
            assert result["decision"] == "DO_NOT_PROMOTE"
            assert result["checks"]["sufficient_calls"] == False
            assert any("Insufficient data" in reason for reason in result["reasons"])
    
    def test_promotion_criteria_high_error_rate(self):
        """Test promotion rejection due to high error rate."""
        helper_id = "high_error_helper"
        
        # Seed data with high error rate
        for i in range(25):
            success = i < 15  # 15/25 = 60% success rate (40% error rate)
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=success,
                output_data={"result": "success"} if success else None,
                error_code="TIMEOUT" if not success else None
            )
        
        # Mock helper info
        with patch.object(self.evaluator, '_get_helper_info') as mock_helper_info:
            mock_helper_info.return_value = {
                "valid": True,
                "exists": True,
                "name": "Test Helper"
            }
            
            # Evaluate for promotion
            result = self.evaluator.evaluate_for_promotion(helper_id, 24)
            
            # Verify promotion rejection
            assert result["promote"] == False
            assert result["decision"] == "DO_NOT_PROMOTE"
            assert result["checks"]["error_rate_acceptable"] == False
            assert result["metrics"]["error_rate"] == 0.4  # 40% error rate
            assert any("Error rate too high" in reason for reason in result["reasons"])
    
    def test_promotion_criteria_high_latency(self):
        """Test promotion rejection due to high latency."""
        helper_id = "high_latency_helper"
        
        # Seed data with high latency
        for i in range(25):
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=2000,  # High latency that will exceed P95 threshold
                success=True,
                output_data={"result": "success"}
            )
        
        # Mock helper info
        with patch.object(self.evaluator, '_get_helper_info') as mock_helper_info:
            mock_helper_info.return_value = {
                "valid": True,
                "exists": True,
                "name": "Test Helper"
            }
            
            # Evaluate for promotion
            result = self.evaluator.evaluate_for_promotion(helper_id, 24)
            
            # Verify promotion rejection due to latency
            assert result["promote"] == False
            assert result["decision"] == "DO_NOT_PROMOTE"
            assert result["checks"]["latency_acceptable"] == False
            assert result["metrics"]["p95_latency_ms"] > PROMOTION_THRESHOLDS["max_p95_latency_ms"]
            assert any("P95 latency too high" in reason for reason in result["reasons"])
    
    def test_promotion_thresholds_configuration(self):
        """Test that promotion thresholds are configurable via environment."""
        # Check default values
        assert PROMOTION_THRESHOLDS["min_calls"] == 20
        assert PROMOTION_THRESHOLDS["max_error_rate"] == 0.1
        assert PROMOTION_THRESHOLDS["max_schema_fail"] == 0.02
        assert PROMOTION_THRESHOLDS["max_p95_latency_ms"] == 1200
        
        # Test with environment overrides
        with patch.dict(os.environ, {
            "AGENT_PROMOTE_MIN_CALLS": "30",
            "AGENT_PROMOTE_MAX_ERROR_RATE": "0.05"
        }):
            # Re-import to pick up new environment values
            import importlib
            import scripts.eval_agents
            importlib.reload(scripts.eval_agents)
            
            # Verify new thresholds are applied
            assert scripts.eval_agents.PROMOTION_THRESHOLDS["min_calls"] == 30
            assert scripts.eval_agents.PROMOTION_THRESHOLDS["max_error_rate"] == 0.05


class TestPromotionAPI:
    """Test the promotion API endpoint."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = AgentStagingStorage(Path(self.temp_db.name))
        
        # Create temporary helper directory structure
        self.temp_helper_dir = tempfile.mkdtemp()
        self.helper_dir = Path(self.temp_helper_dir) / "test_helper"
        self.helper_dir.mkdir(exist_ok=True)
        
        # Create helper.yaml
        helper_yaml = self.helper_dir / "helper.yaml"
        helper_data = {
            "id": "test_helper",
            "name": "Test Helper",
            "lifecycle": {
                "state": "draft",
                "since": "2024-01-01"
            }
        }
        with open(helper_yaml, 'w') as f:
            yaml.dump(helper_data, f)
    
    def teardown_method(self):
        """Clean up test environment."""
        Path(self.temp_db.name).unlink(missing_ok=True)
        import shutil
        shutil.rmtree(self.temp_helper_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_successful_promotion(self):
        """Test successful promotion via API endpoint."""
        from tinyintent.bridge.api_routes import AgentPromoteRequest, promote_agent
        from fastapi import HTTPException
        
        helper_id = "test_helper"
        
        # Seed staging data that meets promotion criteria
        for i in range(25):
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=True,
                output_data={"result": "success"}
            )
        
        # Mock dependencies
        with patch('scripts.eval_agents.agent_staging_storage', self.storage), \
             patch('tinyintent.bridge.api_routes.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.api_routes.rate_limiter') as mock_rate_limiter, \
             patch('tinyintent.bridge.api_routes.get_audit_logger') as mock_audit_logger, \
             patch('tinyintent.bridge.api_routes.episode_logger') as mock_episode_logger:
            
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_audit_logger.return_value = Mock()
            mock_episode_logger.log_event = Mock()
            
            mock_entry = Mock()
            mock_registry.get_registry_entry.return_value = mock_entry
            mock_registry.get_helper_lifecycle.return_value = {"state": "draft"}
            mock_registry.update_helper_lifecycle.return_value = True
            mock_registry.reload.return_value = None
            
            # Create request
            request = AgentPromoteRequest(helper_id=helper_id)
            
            # Call endpoint
            response = await promote_agent(request, auth=True)
            
            # Verify successful promotion
            assert response.status == "success"
            assert response.promoted == True
            assert response.helper_id == helper_id
            assert response.previous_state == "draft"
            assert response.new_state == "trusted"
            assert "promoted to trusted status" in response.message
            
            # Verify lifecycle update was called
            mock_registry.update_helper_lifecycle.assert_called_once_with(
                helper_id, "trusted", patch.ANY
            )
    
    @pytest.mark.asyncio
    async def test_promotion_criteria_not_met(self):
        """Test promotion rejection when criteria not met."""
        from tinyintent.bridge.api_routes import AgentPromoteRequest, promote_agent
        from fastapi import HTTPException
        
        helper_id = "test_helper"
        
        # Seed insufficient data (below minimum calls)
        for i in range(5):
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=True,
                output_data={"result": "success"}
            )
        
        # Mock dependencies
        with patch('scripts.eval_agents.agent_staging_storage', self.storage), \
             patch('tinyintent.bridge.api_routes.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.api_routes.rate_limiter') as mock_rate_limiter, \
             patch('tinyintent.bridge.api_routes.get_audit_logger') as mock_audit_logger:
            
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_audit_logger.return_value = Mock()
            
            mock_entry = Mock()
            mock_registry.get_registry_entry.return_value = mock_entry
            mock_registry.get_helper_lifecycle.return_value = {"state": "draft"}
            
            # Create request
            request = AgentPromoteRequest(helper_id=helper_id)
            
            # Call endpoint and expect HTTP 412
            with pytest.raises(HTTPException) as exc_info:
                await promote_agent(request, auth=True)
            
            assert exc_info.value.status_code == 412
            assert "Promotion criteria not met" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_promotion_invalid_state(self):
        """Test promotion rejection when helper is in invalid state."""
        from tinyintent.bridge.api_routes import AgentPromoteRequest, promote_agent
        from fastapi import HTTPException
        
        helper_id = "test_helper"
        
        # Mock dependencies
        with patch('scripts.eval_agents.agent_staging_storage', self.storage), \
             patch('tinyintent.bridge.api_routes.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.api_routes.rate_limiter') as mock_rate_limiter, \
             patch('tinyintent.bridge.api_routes.get_audit_logger') as mock_audit_logger:
            
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_audit_logger.return_value = Mock()
            
            mock_entry = Mock()
            mock_registry.get_registry_entry.return_value = mock_entry
            mock_registry.get_helper_lifecycle.return_value = {"state": "trusted"}  # Already trusted
            
            # Create request
            request = AgentPromoteRequest(helper_id=helper_id)
            
            # Call endpoint and expect HTTP 400
            with pytest.raises(HTTPException) as exc_info:
                await promote_agent(request, auth=True)
            
            assert exc_info.value.status_code == 400
            assert "Cannot promote helper in state 'trusted'" in exc_info.value.detail


class TestRollbackWatcher:
    """Test the automatic rollback functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = AgentStagingStorage(Path(self.temp_db.name))
    
    def teardown_method(self):
        """Clean up test environment."""
        Path(self.temp_db.name).unlink(missing_ok=True)
    
    def test_rollback_threshold_configuration(self):
        """Test that rollback thresholds are configurable via environment."""
        # Check default values
        assert ROLLBACK_THRESHOLDS["window_hours"] == 6
        assert ROLLBACK_THRESHOLDS["error_rate"] == 0.2
        
        # Test with environment overrides
        with patch.dict(os.environ, {
            "AGENT_ROLLBACK_WINDOW_H": "12",
            "AGENT_ROLLBACK_ERROR_RATE": "0.3"
        }):
            # Re-import to pick up new environment values
            import importlib
            import scripts.eval_agents
            importlib.reload(scripts.eval_agents)
            
            # Verify new thresholds are applied
            assert scripts.eval_agents.ROLLBACK_THRESHOLDS["window_hours"] == 12
            assert scripts.eval_agents.ROLLBACK_THRESHOLDS["error_rate"] == 0.3
    
    @pytest.mark.asyncio
    async def test_rollback_detection(self):
        """Test detection of helpers that should be rolled back."""
        from tinyintent.bridge.tinyrpc import rollback_watcher
        
        helper_id = "trusted_regression_helper"
        
        # Seed data with high error rate (above rollback threshold)
        for i in range(10):
            success = i < 6  # 6/10 = 60% success rate (40% error rate, above 20% threshold)
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=success,
                output_data={"result": "success"} if success else None,
                error_code="REGRESSION" if not success else None
            )
        
        # Mock registry to have a trusted helper
        with patch('tinyintent.bridge.tinyrpc.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.tinyrpc.agent_staging_storage', self.storage), \
             patch('tinyintent.bridge.tinyrpc.get_audit_logger') as mock_audit_logger:
            
            # Setup mocks
            mock_audit_logger.return_value = Mock()
            
            mock_entry = Mock()
            mock_entry.is_trusted.return_value = True
            mock_registry.list_all_helpers.return_value = [helper_id]
            mock_registry.get_registry_entry.return_value = mock_entry
            mock_registry.update_helper_lifecycle.return_value = True
            mock_registry.reload.return_value = None
            
            # Mock sleep to exit immediately
            with patch('asyncio.sleep') as mock_sleep:
                mock_sleep.side_effect = asyncio.CancelledError()
                
                # Run rollback watcher (should detect and rollback the helper)
                try:
                    await rollback_watcher()
                except asyncio.CancelledError:
                    pass
                
                # Verify rollback was triggered
                mock_registry.update_helper_lifecycle.assert_called_once_with(
                    helper_id,
                    "deprecated",
                    patch.ANY  # Notes about the rollback
                )
    
    @pytest.mark.asyncio
    async def test_rollback_no_action_needed(self):
        """Test that rollback watcher doesn't act when error rates are acceptable."""
        from tinyintent.bridge.tinyrpc import rollback_watcher
        
        helper_id = "trusted_good_helper"
        
        # Seed data with low error rate (below rollback threshold)
        for i in range(10):
            success = i < 9  # 9/10 = 90% success rate (10% error rate, below 20% threshold)
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=success,
                output_data={"result": "success"} if success else None,
                error_code="MINOR" if not success else None
            )
        
        # Mock registry to have a trusted helper
        with patch('tinyintent.bridge.tinyrpc.helper_registry') as mock_registry, \
             patch('tinyintent.bridge.tinyrpc.agent_staging_storage', self.storage), \
             patch('tinyintent.bridge.tinyrpc.get_audit_logger') as mock_audit_logger:
            
            # Setup mocks
            mock_audit_logger.return_value = Mock()
            
            mock_entry = Mock()
            mock_entry.is_trusted.return_value = True
            mock_registry.list_all_helpers.return_value = [helper_id]
            mock_registry.get_registry_entry.return_value = mock_entry
            mock_registry.update_helper_lifecycle.return_value = True
            
            # Mock sleep to exit immediately
            with patch('asyncio.sleep') as mock_sleep:
                mock_sleep.side_effect = asyncio.CancelledError()
                
                # Run rollback watcher (should NOT rollback the helper)
                try:
                    await rollback_watcher()
                except asyncio.CancelledError:
                    pass
                
                # Verify NO rollback was triggered
                mock_registry.update_helper_lifecycle.assert_not_called()


class TestIntegrationFlow:
    """Integration tests for the complete promotion and rollback flow."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = AgentStagingStorage(Path(self.temp_db.name))
    
    def teardown_method(self):
        """Clean up test environment."""
        Path(self.temp_db.name).unlink(missing_ok=True)
    
    def test_complete_promotion_rollback_cycle(self):
        """Test complete cycle: staging -> promotion -> rollback."""
        helper_id = "lifecycle_test_helper"
        
        # Phase 1: Staging - seed good data for promotion
        for i in range(25):
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"phase1_session_{i}",
                helper_input={"operation": "test"},
                intent="test",
                latency_ms=100,
                success=True,
                output_data={"result": "success"}
            )
        
        # Evaluate for promotion
        evaluator = AgentEvaluator()
        evaluator.staging_storage = self.storage
        
        with patch.object(evaluator, '_get_helper_info') as mock_helper_info:
            mock_helper_info.return_value = {
                "valid": True,
                "exists": True,
                "name": "Test Helper"
            }
            
            promotion_result = evaluator.evaluate_for_promotion(helper_id, 24)
            assert promotion_result["promote"] == True
        
        # Phase 2: Post-promotion - seed bad data for rollback
        for i in range(10):
            success = i < 3  # 3/10 = 30% success rate (70% error rate, well above 20% threshold)
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"phase2_session_{i}",
                helper_input={"operation": "test"},
                intent="test", 
                latency_ms=100,
                success=success,
                output_data={"result": "success"} if success else None,
                error_code="REGRESSION" if not success else None
            )
        
        # Check rollback criteria (simulating rollback watcher logic)
        metrics = self.storage.get_staging_metrics(helper_id, 6)  # 6 hour window
        
        # Calculate error rate from recent data
        total_runs = metrics.get("shadow_runs", 0)
        error_rate = 1.0 - metrics.get("shadow_success_rate", 1.0)
        
        # Verify rollback should be triggered
        assert total_runs >= 5  # Minimum runs for reliable data
        assert error_rate > 0.2  # Above rollback threshold
        
        print(f"Integration test complete: {total_runs} runs, {error_rate:.1%} error rate")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])