"""
Tests for TinyIntent Health Check System

Validates the comprehensive health monitoring functionality.
"""

import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from tinyintent.health import HealthChecker, HealthStatus, SystemHealth


class TestHealthChecker:
    """Test health checker functionality."""
    
    @pytest.fixture
    def health_checker(self):
        """Create health checker instance."""
        return HealthChecker()
    
    def test_check_disk_space(self, health_checker, temp_dir):
        """Test disk space health check."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.project_root = temp_dir
            
            result = health_checker.check_disk_space()
            
            assert isinstance(result, HealthStatus)
            assert result.component == "disk_space"
            assert result.status in ["healthy", "warning", "unhealthy"]
            assert "space" in result.message.lower()
            assert "free_space_gb" in result.details
            assert "total_space_gb" in result.details
    
    def test_check_sqlite_database_missing(self, health_checker, temp_dir):
        """Test SQLite database check when database doesn't exist."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.database.episodes_dir = temp_dir
            
            result = health_checker.check_sqlite_database()
            
            assert result.component == "sqlite_database"
            assert result.status == "warning"
            assert "does not exist" in result.message
    
    def test_check_sqlite_database_exists(self, health_checker, test_db):
        """Test SQLite database check when database exists."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.database.episodes_dir = test_db.parent
            
            result = health_checker.check_sqlite_database()
            
            assert result.component == "sqlite_database"
            assert result.status == "healthy"
            assert "accessible" in result.message
            assert "table_count" in result.details
    
    @pytest_asyncio.fixture
    async def test_check_ollama_connection_success(self, health_checker):
        """Test successful Ollama connection."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "0.1.0"}
        mock_response.raise_for_status = MagicMock()
        
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.models.ollama_url = "http://localhost:11434"
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
                
                result = await health_checker.check_ollama_connection()
                
                assert result.component == "ollama_server"
                assert result.status == "healthy"
                assert "accessible" in result.message
                assert result.response_time_ms is not None
                assert "version" in result.details
    
    @pytest_asyncio.fixture
    async def test_check_ollama_connection_timeout(self, health_checker):
        """Test Ollama connection timeout."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.models.ollama_url = "http://localhost:11434"
            
            with patch('httpx.AsyncClient') as mock_client:
                from httpx import TimeoutException
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(side_effect=TimeoutException("Timeout"))
                
                result = await health_checker.check_ollama_connection()
                
                assert result.component == "ollama_server"
                assert result.status == "unhealthy"
                assert "timeout" in result.message.lower()
    
    def test_check_router_model_missing(self, health_checker, temp_dir):
        """Test router model check when no model exists."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.project_root = temp_dir
            
            result = health_checker.check_router_model()
            
            assert result.component == "router_model"
            assert result.status == "warning"
            assert "No router model found" in result.message
            assert "searched_paths" in result.details
    
    def test_check_router_model_exists(self, health_checker, temp_dir):
        """Test router model check when model exists."""
        # Create a mock router model
        router_dir = temp_dir / "router"
        router_dir.mkdir()
        model_file = router_dir / "SmallIntent.mlmodel"
        model_file.write_text("mock model content")
        
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.project_root = temp_dir
            
            result = health_checker.check_router_model()
            
            assert result.component == "router_model"
            assert result.status == "healthy"
            assert "Router model available" in result.message
            assert "model_path" in result.details
            assert "size_mb" in result.details
    
    def test_check_system_dependencies(self, health_checker):
        """Test system dependencies check."""
        with patch('subprocess.run') as mock_run:
            # Mock successful dependency checks
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Python 3.11.0\n"
            
            result = health_checker.check_system_dependencies()
            
            assert result.component == "system_dependencies"
            assert result.status in ["healthy", "warning", "unhealthy"]
            assert "available" in result.details
            assert "missing" in result.details
    
    def test_check_audit_log_missing(self, health_checker, temp_dir):
        """Test audit log check when log doesn't exist."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.project_root = temp_dir
            mock_settings.logging.audit_max_size_mb = 50
            
            result = health_checker.check_audit_log()
            
            assert result.component == "audit_log"
            assert result.status == "warning"
            assert "does not exist" in result.message
    
    def test_check_audit_log_exists(self, health_checker, test_audit_log):
        """Test audit log check when log exists."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.project_root = test_audit_log.parent.parent
            mock_settings.logging.audit_max_size_mb = 50
            
            # Create bridge/logs directory structure
            (test_audit_log.parent / "bridge" / "logs").mkdir(parents=True, exist_ok=True)
            audit_log = test_audit_log.parent / "bridge" / "logs" / "audit.log"
            audit_log.write_text("sample audit log content")
            
            result = health_checker.check_audit_log()
            
            assert result.component == "audit_log"
            assert result.status in ["healthy", "warning"]
            assert "operational" in result.message or "approaching" in result.message
            assert "size_mb" in result.details
    
    @pytest_asyncio.fixture
    async def test_run_all_checks(self, health_checker, temp_dir, test_db):
        """Test running all health checks."""
        with patch('tinyintent.health.settings') as mock_settings:
            mock_settings.project_root = temp_dir
            mock_settings.database.episodes_dir = test_db.parent
            mock_settings.models.ollama_url = "http://localhost:11434"
            mock_settings.logging.audit_max_size_mb = 50
            
            # Mock Ollama client response
            mock_response = MagicMock()
            mock_response.json.return_value = {"version": "0.1.0"}
            mock_response.raise_for_status = MagicMock()
            
            with patch('httpx.AsyncClient') as mock_client:
                mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
                
                result = await health_checker.run_all_checks()
                
                assert isinstance(result, SystemHealth)
                assert result.overall_status in ["healthy", "warning", "unhealthy"]
                assert len(result.components) > 0
                assert result.healthy_count >= 0
                assert result.unhealthy_count >= 0
                assert result.warning_count >= 0
                assert result.timestamp is not None
                
                # Check that all expected components are present
                component_names = {comp.component for comp in result.components}
                expected_components = {
                    "disk_space",
                    "sqlite_database", 
                    "ollama_server",
                    "router_model",
                    "system_dependencies",
                    "audit_log"
                }
                assert component_names >= expected_components


class TestHealthStatus:
    """Test HealthStatus model."""
    
    def test_health_status_creation(self):
        """Test creating a health status."""
        status = HealthStatus(
            component="test_component",
            status="healthy",
            message="All good",
            timestamp="2025-08-20T12:00:00.000000Z"
        )
        
        assert status.component == "test_component"
        assert status.status == "healthy"
        assert status.message == "All good"
        assert status.details == {}
        assert status.response_time_ms is None
    
    def test_health_status_with_details(self):
        """Test creating a health status with details."""
        details = {"key": "value", "count": 42}
        
        status = HealthStatus(
            component="detailed_component",
            status="warning",
            message="Some issues",
            details=details,
            response_time_ms=150.5,
            timestamp="2025-08-20T12:00:00.000000Z"
        )
        
        assert status.details == details
        assert status.response_time_ms == 150.5


class TestSystemHealth:
    """Test SystemHealth model."""
    
    def test_system_health_creation(self):
        """Test creating system health."""
        components = [
            HealthStatus(
                component="comp1",
                status="healthy",
                message="OK",
                timestamp="2025-08-20T12:00:00.000000Z"
            ),
            HealthStatus(
                component="comp2",
                status="warning",
                message="Warning",
                timestamp="2025-08-20T12:00:00.000000Z"
            )
        ]
        
        health = SystemHealth(
            overall_status="warning",
            components=components,
            timestamp="2025-08-20T12:00:00.000000Z",
            healthy_count=1,
            unhealthy_count=0,
            warning_count=1
        )
        
        assert health.overall_status == "warning"
        assert len(health.components) == 2
        assert health.healthy_count == 1
        assert health.unhealthy_count == 0
        assert health.warning_count == 1