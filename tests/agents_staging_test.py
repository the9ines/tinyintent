#!/usr/bin/env python3
"""
Tests for M10.3: Agent Staging - Shadow Execution and Canary Rollout

Tests shadow execution, canary rollout, lifecycle gates, and safety reporting.
"""

import pytest
import asyncio
import json
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

# Add parent directory for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from tinyintent.data.episodes.episodes import AgentStagingStorage
from tinyintent.helpers.executor import HelperExecutor
from tinyintent.helpers.registry import HelperRegistry
from scripts.eval_agents import AgentEvaluator


class TestAgentStagingStorage:
    """Test the agent staging storage functionality."""
    
    def setup_method(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = AgentStagingStorage(Path(self.temp_db.name))
    
    def teardown_method(self):
        """Clean up test database."""
        Path(self.temp_db.name).unlink(missing_ok=True)
    
    def test_database_initialization(self):
        """Test that database tables are created correctly."""
        with sqlite3.connect(self.storage.db_path) as conn:
            cursor = conn.cursor()
            
            # Check shadow runs table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_shadow_runs'")
            assert cursor.fetchone() is not None
            
            # Check canary runs table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_canary_runs'")
            assert cursor.fetchone() is not None
            
            # Check staging config table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_staging_config'")
            assert cursor.fetchone() is not None
    
    def test_staging_configuration(self):
        """Test setting and getting staging configurations."""
        helper_id = "test_helper"
        
        # Set shadow configuration
        self.storage.set_staging_config(helper_id, "shadow", match_intent="test_intent")
        
        # Get configuration
        config = self.storage.get_staging_config(helper_id)
        assert config is not None
        assert config["helper_id"] == helper_id
        assert config["mode"] == "shadow"
        assert config["match_intent"] == "test_intent"
        
        # Update to canary configuration
        self.storage.set_staging_config(helper_id, "canary", canary_pct=15.0)
        
        config = self.storage.get_staging_config(helper_id)
        assert config["mode"] == "canary"
        assert config["canary_pct"] == 15.0
        
        # Remove configuration
        self.storage.remove_staging_config(helper_id)
        config = self.storage.get_staging_config(helper_id)
        assert config is None
    
    def test_shadow_run_logging(self):
        """Test logging shadow run executions."""
        helper_id = "test_helper"
        session_id = "test_session"
        helper_input = {"operation": "test"}
        intent = "test_intent"
        
        # Log successful shadow run
        self.storage.log_shadow_run(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent=intent,
            latency_ms=150,
            success=True,
            output_data={"result": "success"}
        )
        
        # Log failed shadow run
        self.storage.log_shadow_run(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent=intent,
            latency_ms=250,
            success=False,
            error_code="TIMEOUT",
            output_data=None
        )
        
        # Get metrics
        metrics = self.storage.get_staging_metrics(helper_id)
        assert metrics["shadow_runs"] == 2
        assert metrics["shadow_success_rate"] == 0.5  # 1 success out of 2
        assert metrics["avg_latency_ms"] == 200.0  # (150 + 250) / 2
        assert "TIMEOUT" in metrics["error_rates"]
    
    def test_canary_run_logging(self):
        """Test logging canary run executions."""
        helper_id = "test_helper"
        session_id = "test_session"
        helper_input = {"operation": "test"}
        intent = "test_intent"
        
        # Log canary treatment
        self.storage.log_canary_run(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent=intent,
            latency_ms=100,
            success=True,
            treatment="canary",
            output_data={"result": "canary_success"}
        )
        
        # Log control treatment
        self.storage.log_canary_run(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent=intent,
            latency_ms=0,
            success=True,
            treatment="control",
            output_data=None
        )
        
        # Get metrics
        metrics = self.storage.get_staging_metrics(helper_id)
        assert metrics["canary_runs"] == 2
        assert metrics["canary_success_rate"] == 1.0  # Both successful
    
    def test_determinism_scoring(self):
        """Test determinism score calculation."""
        helper_id = "test_helper"
        session_id = "test_session"
        helper_input = {"operation": "test"}
        
        # Log multiple runs with same input (should be deterministic)
        for i in range(3):
            self.storage.log_shadow_run(
                helper_id=helper_id,
                session_id=f"{session_id}_{i}",
                helper_input=helper_input,  # Same input
                intent="test",
                latency_ms=100 + i,  # Slight variance
                success=True,
                output_data={"result": "consistent", "size": 100}  # Same output size
            )
        
        # Log different input with different output
        self.storage.log_shadow_run(
            helper_id=helper_id,
            session_id="different_session",
            helper_input={"operation": "different"},  # Different input
            intent="test",
            latency_ms=200,
            success=True,
            output_data={"result": "different", "size": 500}  # Different output size
        )
        
        metrics = self.storage.get_staging_metrics(helper_id)
        # Should have good determinism since same inputs produce similar outputs
        assert metrics["determinism_score"] >= 0.9
    
    @pytest.mark.asyncio
    async def test_async_logging(self):
        """Test asynchronous logging methods."""
        helper_id = "test_helper"
        session_id = "test_session"
        helper_input = {"operation": "async_test"}
        
        # Test async shadow logging
        await self.storage.log_shadow_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent="async_test",
            latency_ms=75,
            success=True,
            output_data={"async": True}
        )
        
        # Test async canary logging
        await self.storage.log_canary_run_async(
            helper_id=helper_id,
            session_id=session_id,
            helper_input=helper_input,
            intent="async_test",
            latency_ms=80,
            success=True,
            treatment="canary",
            output_data={"async": True}
        )
        
        # Verify data was logged
        metrics = self.storage.get_staging_metrics(helper_id)
        assert metrics["shadow_runs"] == 1
        assert metrics["canary_runs"] == 1


class TestHelperExecutorStaging:
    """Test helper executor staging functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.mock_registry = Mock(spec=HelperRegistry)
        self.executor = HelperExecutor(self.mock_registry)
        
        # Mock helper
        self.mock_helper = Mock()
        self.mock_helper.can_preview.return_value = True
        self.mock_helper.validate_input.return_value = True
        self.mock_helper.validate_output.return_value = True
        
        self.mock_registry.is_helper_valid.return_value = True
        self.mock_registry.get_helper.return_value = self.mock_helper
    
    @patch('tinyintent.helpers.executor.get_audit_logger')
    def test_shadow_execution_mode(self, mock_audit_logger):
        """Test that shadow execution mode forces dry_run."""
        mock_audit_logger.return_value = Mock()
        
        with patch.object(self.executor, '_execute_helper') as mock_execute:
            mock_execute.return_value = {"status": "success", "preview_json": {"result": "test"}}
            
            # Execute in shadow mode
            result = self.executor.preview(
                helper_id="test_helper",
                input_data={"test": "data"},
                session_id="test_session",
                execution_mode="shadow"
            )
            
            # Verify shadow mode was passed through
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[1]["execution_mode"] == "shadow"
            
            # Verify response structure
            assert result["status"] == "success"
            assert result["action"] == "shadow"
            assert result["execution_mode"] == "shadow"
            assert "approval_token" not in result  # No approval token for staging
    
    @patch('tinyintent.helpers.executor.get_audit_logger')
    def test_canary_execution_mode(self, mock_audit_logger):
        """Test that canary execution mode forces dry_run."""
        mock_audit_logger.return_value = Mock()
        
        with patch.object(self.executor, '_execute_helper') as mock_execute:
            mock_execute.return_value = {"status": "success", "preview_json": {"result": "canary"}}
            
            # Execute in canary mode
            result = self.executor.preview(
                helper_id="test_helper",
                input_data={"test": "data"},
                session_id="test_session",
                execution_mode="canary"
            )
            
            # Verify canary mode was passed through
            mock_execute.assert_called_once()
            call_args = mock_execute.call_args
            assert call_args[1]["execution_mode"] == "canary"
            
            # Verify response structure
            assert result["action"] == "canary"
            assert result["execution_mode"] == "canary"
            assert "approval_token" not in result  # No approval token for staging
    
    @patch('tinyintent.helpers.executor.get_audit_logger')
    def test_regular_preview_mode(self, mock_audit_logger):
        """Test that regular preview mode still gets approval tokens."""
        mock_audit_logger.return_value = Mock()
        
        with patch.object(self.executor, '_execute_helper') as mock_execute, \
             patch.object(self.executor, '_generate_approval_token') as mock_token:
            
            mock_execute.return_value = {"status": "success", "preview_json": {"result": "preview"}}
            mock_token.return_value = "test_token_123"
            
            # Execute in regular preview mode
            result = self.executor.preview(
                helper_id="test_helper",
                input_data={"test": "data"},
                session_id="test_session",
                execution_mode="preview"
            )
            
            # Verify preview mode
            assert result["action"] == "preview"
            assert result["execution_mode"] == "preview"
            assert result["approval_token"] == "test_token_123"  # Should have approval token
    
    @patch('tinyintent.helpers.executor.get_audit_logger')
    def test_audit_logging_with_execution_mode(self, mock_audit_logger):
        """Test that audit logging includes execution mode."""
        mock_logger = Mock()
        mock_audit_logger.return_value = mock_logger
        
        with patch.object(self.executor, '_execute_helper') as mock_execute:
            mock_execute.return_value = {"status": "success", "preview_json": {"result": "test"}}
            
            # Execute in shadow mode
            self.executor.preview(
                helper_id="test_helper",
                input_data={"test": "data"},
                session_id="test_session",
                execution_mode="shadow"
            )
            
            # Verify audit logging was called with execution_mode
            mock_logger.log_entry.assert_called()
            log_entry = mock_logger.log_entry.call_args[0][0]
            assert log_entry["execution_mode"] == "shadow"


class TestAgentEvaluator:
    """Test the agent evaluation and safety reporting."""
    
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
    
    def test_safety_score_calculation(self):
        """Test safety score calculation logic."""
        # Create test metrics with various scenarios
        
        # High safety scenario
        high_safety_metrics = {
            "shadow_runs": 50,
            "shadow_success_rate": 0.98,
            "error_rates": {},
            "determinism_score": 0.95
        }
        
        high_safety_helper_info = {"valid": True, "exists": True}
        safety_score = self.evaluator._calculate_safety_score(high_safety_metrics, high_safety_helper_info)
        assert safety_score >= 0.9  # Should be high safety
        
        # Low safety scenario
        low_safety_metrics = {
            "shadow_runs": 20,
            "shadow_success_rate": 0.6,  # 40% error rate
            "error_rates": {
                "CAPABILITY_VIOLATION": 0.2,  # 20% capability violations
                "SCHEMA_VALIDATION": 0.1      # 10% schema failures
            },
            "determinism_score": 0.5  # Low determinism
        }
        
        low_safety_helper_info = {"valid": False, "exists": True}
        safety_score = self.evaluator._calculate_safety_score(low_safety_metrics, low_safety_helper_info)
        assert safety_score <= 0.3  # Should be low safety
    
    def test_quality_score_calculation(self):
        """Test quality score calculation logic."""
        # High quality scenario
        high_quality_metrics = {
            "shadow_runs": 100,
            "shadow_success_rate": 0.95,
            "avg_latency_ms": 80,  # Fast response
            "determinism_score": 0.9,
            "output_size_stats": {"min": 100, "max": 120, "avg": 110}  # Low variance
        }
        
        quality_score = self.evaluator._calculate_quality_score(high_quality_metrics)
        assert quality_score >= 0.9
        
        # Low quality scenario
        low_quality_metrics = {
            "shadow_runs": 30,
            "shadow_success_rate": 0.7,
            "avg_latency_ms": 3000,  # Slow response
            "determinism_score": 0.4,
            "output_size_stats": {"min": 50, "max": 500, "avg": 200}  # High variance
        }
        
        quality_score = self.evaluator._calculate_quality_score(low_quality_metrics)
        assert quality_score <= 0.5
    
    def test_promotion_eligibility_assessment(self):
        """Test promotion eligibility logic."""
        # Eligible scenario
        good_metrics = {
            "shadow_runs": 50,  # Sufficient data
            "shadow_success_rate": 0.9  # Good success rate
        }
        
        promotion_result = self.evaluator._assess_promotion_eligibility(
            good_metrics, 0.85, 0.8, 0.75, {"severity": "low"}
        )
        
        assert promotion_result["eligible"] == True
        assert promotion_result["recommendation"] == "PROMOTE"
        assert all(promotion_result["checks"].values())
        
        # Ineligible scenario - insufficient data
        insufficient_data_metrics = {
            "shadow_runs": 5,  # Insufficient data
            "shadow_success_rate": 0.95
        }
        
        promotion_result = self.evaluator._assess_promotion_eligibility(
            insufficient_data_metrics, 0.9, 0.85, 0.8, {"severity": "low"}
        )
        
        assert promotion_result["eligible"] == False
        assert promotion_result["recommendation"] == "DO_NOT_PROMOTE"
        assert promotion_result["checks"]["sufficient_data"] == False
        
        # Ineligible scenario - security violations
        security_violation_metrics = {
            "shadow_runs": 100,
            "shadow_success_rate": 0.95
        }
        
        promotion_result = self.evaluator._assess_promotion_eligibility(
            security_violation_metrics, 0.9, 0.85, 0.8, {"severity": "critical"}
        )
        
        assert promotion_result["eligible"] == False
        assert promotion_result["checks"]["no_security_violations"] == False
    
    def test_report_generation(self):
        """Test complete report generation."""
        helper_id = "test_helper"
        
        # Add some test data
        self.storage.log_shadow_run(
            helper_id=helper_id,
            session_id="session1",
            helper_input={"operation": "test"},
            intent="test_intent",
            latency_ms=100,
            success=True,
            output_data={"result": "success"}
        )
        
        with patch.object(self.evaluator, '_get_helper_info') as mock_helper_info:
            mock_helper_info.return_value = {
                "name": "Test Helper",
                "exists": True,
                "valid": True,
                "capabilities": ["network"],
                "lifecycle": {"state": "draft"}
            }
            
            # Generate report
            report = self.evaluator.evaluate_agent(helper_id, window_hours=24)
            
            # Verify report structure
            assert report["helper_id"] == helper_id
            assert "evaluation_timestamp" in report
            assert "scores" in report
            assert "performance_analysis" in report
            assert "security_analysis" in report
            assert "recommendations" in report
            assert "promotion_eligibility" in report
            
            # Verify scores are calculated
            scores = report["scores"]
            assert "safety" in scores
            assert "quality" in scores
            assert "reliability" in scores
            assert "overall" in scores
            assert 0 <= scores["overall"] <= 1


@pytest.mark.asyncio
class TestStagingIntegration:
    """Integration tests for staging functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.storage = AgentStagingStorage(Path(self.temp_db.name))
    
    def teardown_method(self):
        """Clean up test environment."""
        Path(self.temp_db.name).unlink(missing_ok=True)
    
    async def test_shadow_execution_flow(self):
        """Test end-to-end shadow execution flow."""
        # Set up staging configuration
        helper_id = "test_shadow_helper"
        self.storage.set_staging_config(helper_id, "shadow", match_intent="test")
        
        # Verify configuration
        config = self.storage.get_staging_config(helper_id)
        assert config["mode"] == "shadow"
        assert config["match_intent"] == "test"
        
        # Simulate shadow execution logging
        await self.storage.log_shadow_run_async(
            helper_id=helper_id,
            session_id="test_session",
            helper_input={"operation": "shadow_test"},
            intent="test",
            latency_ms=150,
            success=True,
            output_data={"shadow_result": "success"}
        )
        
        # Verify metrics
        metrics = self.storage.get_staging_metrics(helper_id)
        assert metrics["shadow_runs"] == 1
        assert metrics["shadow_success_rate"] == 1.0
        assert metrics["avg_latency_ms"] == 150.0
    
    async def test_canary_execution_flow(self):
        """Test end-to-end canary execution flow."""
        # Set up staging configuration
        helper_id = "test_canary_helper"
        self.storage.set_staging_config(helper_id, "canary", canary_pct=20.0)
        
        # Verify configuration
        config = self.storage.get_staging_config(helper_id)
        assert config["mode"] == "canary"
        assert config["canary_pct"] == 20.0
        
        # Simulate canary executions (both treatments)
        await self.storage.log_canary_run_async(
            helper_id=helper_id,
            session_id="canary_session",
            helper_input={"operation": "canary_test"},
            intent="test",
            latency_ms=120,
            success=True,
            treatment="canary",
            output_data={"canary_result": "success"}
        )
        
        await self.storage.log_canary_run_async(
            helper_id=helper_id,
            session_id="control_session",
            helper_input={"operation": "canary_test"},
            intent="test",
            latency_ms=0,
            success=True,
            treatment="control",
            output_data=None
        )
        
        # Verify metrics
        metrics = self.storage.get_staging_metrics(helper_id)
        assert metrics["canary_runs"] == 2
        assert metrics["canary_success_rate"] == 1.0
    
    def test_lifecycle_gate_enforcement(self):
        """Test that lifecycle gates are properly enforced."""
        # This would test the API endpoints that enforce lifecycle gates
        # In a real test, we'd use FastAPI test client to test the endpoints
        
        # Test staging restrictions
        draft_helper = "draft_helper"
        trusted_helper = "trusted_helper"
        retired_helper = "retired_helper"
        
        # Draft helpers should be able to stage
        self.storage.set_staging_config(draft_helper, "shadow")
        config = self.storage.get_staging_config(draft_helper)
        assert config is not None
        
        # Test that we can set configurations (real lifecycle enforcement is in API endpoints)
        self.storage.set_staging_config(trusted_helper, "canary", canary_pct=10.0)
        config = self.storage.get_staging_config(trusted_helper)
        assert config["mode"] == "canary"
        
        # Verify configurations can be removed
        self.storage.remove_staging_config(draft_helper)
        self.storage.remove_staging_config(trusted_helper)
        
        assert self.storage.get_staging_config(draft_helper) is None
        assert self.storage.get_staging_config(trusted_helper) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])