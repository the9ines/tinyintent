#!/usr/bin/env python3
"""
TinyIntent Router Self-Correction & Override Tests - M7.4

Tests abstain reason categorization, operator override functionality,
enhanced episode logging, and training data export with override labels.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import sqlite3

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent / "bridge"))
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

try:
    from tinyintent.bridge.api_routes import RouteRequest, RouteResponse, route_request
from tinyintent.bridge.router_client import SmallIntentRouter
from tinyintent.data.episodes.logger import EpisodeLogger
from tinyintent.scripts.export_episodes import EpisodeExporter
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Bridge not available: {e}")
    BRIDGE_AVAILABLE = False


class TestAbstainReasonCategorization(unittest.TestCase):
    """Test M7.4 abstain reason categorization."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create router with test configuration
        with patch.dict(os.environ, {
            'ROUTER_MIN_CONF_GEN': '0.6',
            'ROUTER_MIN_CONF_ACT': '0.75',
            'ROUTER_FALLBACK_THRESHOLD': '0.4'
        }):
            self.router = SmallIntentRouter()
    
    def test_low_confidence_abstain_reason(self):
        """Test low confidence abstain reasons are properly categorized."""
        # Mock low confidence generation
        mock_routing_result = {
            "route": "gen",
            "intent": "general_query", 
            "confidence": 0.5  # Below 0.6 threshold
        }
        
        result = self.router._apply_confidence_thresholds(mock_routing_result, "test text")
        
        self.assertEqual(result["route"], "abstain")
        self.assertEqual(result["abstain_reason"], "low_confidence")
        self.assertIn("Generation confidence", result["abstain_reason_detail"])
        self.assertEqual(result["suggested_route"], "gen")
        self.assertTrue(result["fallback_available"])
    
    def test_low_confidence_action_abstain_reason(self):
        """Test low confidence action abstain reasons are properly categorized."""
        # Mock low confidence action
        mock_routing_result = {
            "route": "act",
            "intent": "bot_management",
            "confidence": 0.7  # Below 0.75 threshold
        }
        
        result = self.router._apply_confidence_thresholds(mock_routing_result, "test text")
        
        self.assertEqual(result["route"], "abstain")
        self.assertEqual(result["abstain_reason"], "low_confidence")
        self.assertIn("Action confidence", result["abstain_reason_detail"])
        self.assertEqual(result["suggested_route"], "act")
        self.assertTrue(result["fallback_available"])
    
    def test_router_fallback_abstain_reason(self):
        """Test router fallback abstain reasons are properly categorized."""
        # Test fallback routing
        result = self.router._fallback_routing("test text")
        
        self.assertEqual(result["abstain_reason"], "router_fallback")
        self.assertIn("fallback routing", result["abstain_reason_detail"])
        self.assertIn(result["route"], ["gen", "act"])  # Should still route, but with fallback flag


class TestOperatorOverride(unittest.IsolatedAsyncioTestCase):
    """Test M7.4 operator override functionality."""
    
    def setUp(self):
        """Set up async test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    @patch('tinyrpc.router')
    @patch('tinyrpc.episode_logger')
    @patch('tinyrpc.audit_logger')
    async def test_abstain_with_override(self, mock_audit, mock_episode_logger, mock_router):
        """Test abstain decision with operator override."""
        # Mock router abstain decision
        mock_router.route_request.return_value = {
            "route": "abstain",
            "intent": "unclear_intent",
            "confidence": 0.45,
            "abstain_reason": "low_confidence",
            "abstain_reason_detail": "Generation confidence 0.45 below threshold 0.6",
            "suggested_route": "gen",
            "fallback_available": True
        }
        
        # Create request with override
        request = RouteRequest(
            text="Show me my trading positions",
            route="auto",
            override_route="act"
        )
        
        # Mock FastAPI request
        mock_fastapi_request = MagicMock()
        mock_fastapi_request.client.host = "127.0.0.1"
        mock_fastapi_request.headers = {"User-Agent": "test-client"}
        
        # Mock other dependencies
        with patch('tinyrpc.experience_store') as mock_store, \
             patch('tinyrpc.rate_limiter') as mock_rate_limiter, \
             patch('tinyrpc.async_ollama_client') as mock_ollama, \
             patch('tinyrpc.router_metrics'):
            
            mock_store.create_session.return_value = "test-session-123"
            mock_store.session_exists.return_value = False
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_ollama.generate_async.return_value = ("Test response", 150)
            
            # Call route_request
            response = await route_request(request, mock_fastapi_request, auth=True)
            
            # Verify override was processed
            self.assertEqual(response.status, "success")
            self.assertIn(response.route_used, ["act", "gen"])  # Should continue with override route
            
            # Verify both abstain and override events were logged
            mock_episode_logger.log_router_episode.assert_any_call(
                session_id="test-session-123",
                text=request.text,
                original_route="abstain",
                confidence=0.45,
                intent="unclear_intent",
                is_abstain=True,
                abstain_reason="low_confidence",
                is_override=False,
                label_source="router"
            )
            
            mock_episode_logger.log_router_episode.assert_any_call(
                session_id="test-session-123",
                text=request.text,
                original_route="abstain",
                confidence=0.45,
                intent="unclear_intent",
                is_abstain=False,
                abstain_reason="low_confidence",
                is_override=True,
                override_route="act",
                override_confidence=0.9,
                label_source="override"
            )
            
            # Verify audit logs
            audit_calls = mock_audit.log_entry.call_args_list
            abstain_calls = [call for call in audit_calls if call[0][0].get("action") == "router_abstain"]
            override_calls = [call for call in audit_calls if call[0][0].get("action") == "router_override"]
            
            self.assertGreater(len(abstain_calls), 0)
            self.assertGreater(len(override_calls), 0)
    
    @patch('tinyrpc.router')
    @patch('tinyrpc.episode_logger')
    @patch('tinyrpc.audit_logger')
    async def test_abstain_without_override(self, mock_audit, mock_episode_logger, mock_router):
        """Test abstain decision without operator override."""
        # Mock router abstain decision
        mock_router.route_request.return_value = {
            "route": "abstain",
            "intent": "unclear_intent",
            "confidence": 0.45,
            "abstain_reason": "low_confidence",
            "abstain_reason_detail": "Generation confidence 0.45 below threshold 0.6",
            "suggested_route": "gen",
            "fallback_available": True
        }
        
        # Create request without override
        request = RouteRequest(
            text="Show me my trading positions",
            route="auto"
        )
        
        # Mock FastAPI request
        mock_fastapi_request = MagicMock()
        mock_fastapi_request.client.host = "127.0.0.1"
        mock_fastapi_request.headers = {"User-Agent": "test-client"}
        
        # Mock other dependencies
        with patch('tinyrpc.experience_store') as mock_store, \
             patch('tinyrpc.rate_limiter') as mock_rate_limiter:
            
            mock_store.create_session.return_value = "test-session-123"
            mock_store.session_exists.return_value = False
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            
            # Call route_request
            response = await route_request(request, mock_fastapi_request, auth=True)
            
            # Verify abstain response
            self.assertEqual(response.status, "abstain")
            self.assertEqual(response.route_used, "abstain")
            self.assertIn("abstain_reason", response.reflection)
            self.assertEqual(response.reflection["abstain_reason"], "low_confidence")
            
            # Verify only abstain event was logged (no override)
            mock_episode_logger.log_router_episode.assert_called_once_with(
                session_id="test-session-123",
                text=request.text,
                original_route="abstain",
                confidence=0.45,
                intent="unclear_intent",
                is_abstain=True,
                abstain_reason="low_confidence",
                is_override=False,
                label_source="router"
            )
    
    def test_override_route_validation(self):
        """Test override_route field validation."""
        # Valid override routes
        valid_request = RouteRequest(
            text="Test text",
            override_route="gen"
        )
        self.assertEqual(valid_request.override_route, "gen")
        
        valid_request2 = RouteRequest(
            text="Test text",
            override_route="act"
        )
        self.assertEqual(valid_request2.override_route, "act")
        
        # Invalid override routes should raise validation error
        with self.assertRaises(ValueError):
            RouteRequest(
                text="Test text",
                override_route="invalid"
            )
    
    @patch('tinyrpc.async_ollama_client')
    @patch('tinyrpc.episode_logger')
    async def test_circuit_breaker_abstain_no_override(self, mock_episode_logger, mock_ollama):
        """Test circuit breaker abstain does not allow override for safety."""
        # Mock circuit breaker error
        from fastapi import HTTPException
        circuit_error = HTTPException(
            status_code=503,
            detail="Generation circuit breaker open",
            headers={"error_code": "gen_circuit_open", "retry_after": "30"}
        )
        mock_ollama.generate_async.side_effect = circuit_error
        
        request = RouteRequest(
            text="Generate text",
            route="gen",
            override_route="gen"  # Try to override circuit breaker
        )
        
        mock_fastapi_request = MagicMock()
        mock_fastapi_request.client.host = "127.0.0.1"
        
        with patch('tinyrpc.experience_store') as mock_store, \
             patch('tinyrpc.rate_limiter') as mock_rate_limiter, \
             patch('tinyrpc.audit_logger'):
            
            mock_store.create_session.return_value = "test-session-123"
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            
            # Call route_request
            response = await route_request(request, mock_fastapi_request, auth=True)
            
            # Verify override was blocked
            self.assertEqual(response.status, "error")
            self.assertEqual(response.route_used, "abstain")
            self.assertIn("Override not allowed", response.text_response)
            self.assertTrue(response.reflection.get("override_blocked", False))
            
            # Verify circuit breaker abstain was logged
            mock_episode_logger.log_router_episode.assert_called_with(
                session_id="test-session-123",
                text=request.text,
                original_route="gen",
                confidence=0.0,
                intent="generation_blocked",
                is_abstain=True,
                abstain_reason="circuit_open",
                is_override=False,
                label_source="circuit_breaker"
            )


class TestEnhancedEpisodeLogging(unittest.TestCase):
    """Test M7.4 enhanced episode logging for router learning."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create temporary directory for test database
        self.temp_dir = tempfile.mkdtemp()
        self.test_db = Path(self.temp_dir) / "test_episodes.db"
        self.episode_logger = EpisodeLogger(data_dir=Path(self.temp_dir))
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_router_episode_logging_abstain(self):
        """Test router episode logging for abstain cases."""
        # Log abstain episode
        self.episode_logger.log_router_episode(
            session_id="test-session",
            text="Show me my trading positions",
            original_route="abstain",
            confidence=0.45,
            intent="unclear_intent",
            is_abstain=True,
            abstain_reason="low_confidence",
            is_override=False,
            label_source="router"
        )
        
        # Verify database entry
        with sqlite3.connect(self.test_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM router_episodes ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            
            self.assertIsNotNone(row)
            self.assertEqual(row["session_id"], "test-session")
            self.assertEqual(row["text"], "Show me my trading positions")
            self.assertEqual(row["original_route"], "abstain")
            self.assertEqual(row["confidence"], 0.45)
            self.assertEqual(row["intent"], "unclear_intent")
            self.assertEqual(row["is_abstain"], 1)  # SQLite boolean
            self.assertEqual(row["abstain_reason"], "low_confidence")
            self.assertEqual(row["is_override"], 0)  # SQLite boolean
            self.assertEqual(row["label_source"], "router")
            self.assertIsNotNone(row["text_hash"])
    
    def test_router_episode_logging_override(self):
        """Test router episode logging for override cases."""
        # Log override episode
        self.episode_logger.log_router_episode(
            session_id="test-session",
            text="Show me my trading positions",
            original_route="abstain",
            confidence=0.45,
            intent="unclear_intent",
            is_abstain=False,
            abstain_reason="low_confidence",
            is_override=True,
            override_route="act",
            override_confidence=0.9,
            label_source="override"
        )
        
        # Verify database entry
        with sqlite3.connect(self.test_db) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM router_episodes ORDER BY timestamp DESC LIMIT 1")
            row = cursor.fetchone()
            
            self.assertIsNotNone(row)
            self.assertEqual(row["session_id"], "test-session")
            self.assertEqual(row["text"], "Show me my trading positions")
            self.assertEqual(row["original_route"], "abstain")
            self.assertEqual(row["confidence"], 0.45)
            self.assertEqual(row["intent"], "unclear_intent")
            self.assertEqual(row["is_abstain"], 0)  # SQLite boolean
            self.assertEqual(row["abstain_reason"], "low_confidence")
            self.assertEqual(row["is_override"], 1)  # SQLite boolean
            self.assertEqual(row["override_route"], "act")
            self.assertEqual(row["override_confidence"], 0.9)
            self.assertEqual(row["label_source"], "override")
    
    def test_router_episode_stats(self):
        """Test router episode statistics calculation."""
        # Add multiple test episodes
        episodes = [
            # Abstain episode
            {
                "session_id": "s1", "text": "unclear text 1", "original_route": "abstain",
                "confidence": 0.4, "intent": "unclear", "is_abstain": True,
                "abstain_reason": "low_confidence", "is_override": False, "label_source": "router"
            },
            # Override episode  
            {
                "session_id": "s2", "text": "show positions", "original_route": "abstain",
                "confidence": 0.45, "intent": "unclear", "is_abstain": False,
                "abstain_reason": "low_confidence", "is_override": True, 
                "override_route": "act", "override_confidence": 0.9, "label_source": "override"
            },
            # Circuit breaker abstain
            {
                "session_id": "s3", "text": "generate text", "original_route": "gen",
                "confidence": 0.0, "intent": "generation_blocked", "is_abstain": True,
                "abstain_reason": "circuit_open", "is_override": False, "label_source": "circuit_breaker"
            }
        ]
        
        for episode in episodes:
            self.episode_logger.log_router_episode(**episode)
        
        # Get stats
        stats = self.episode_logger.get_router_episodes_stats()
        
        self.assertEqual(stats["total_episodes"], 3)
        self.assertEqual(stats["abstain_count"], 2)
        self.assertEqual(stats["override_count"], 1)
        self.assertEqual(stats["abstain_rate_percent"], 66.67)
        self.assertEqual(stats["override_rate_percent"], 33.33)
        
        # Check abstain reason breakdown
        self.assertEqual(stats["abstain_reasons"]["low_confidence"], 2)
        self.assertEqual(stats["abstain_reasons"]["circuit_open"], 1)
        self.assertEqual(stats["abstain_reasons"]["router_fallback"], 0)
        
        self.assertEqual(stats["override_labels"], 1)
        self.assertEqual(stats["unique_texts"], 3)


class TestExportScriptIntegration(unittest.TestCase):
    """Test M7.4 export script with override labels."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create temporary directories
        self.temp_dir = tempfile.mkdtemp()
        self.data_dir = Path(self.temp_dir) / "episodes"
        self.router_dir = Path(self.temp_dir) / "router"
        
        self.data_dir.mkdir(parents=True)
        self.router_dir.mkdir(parents=True)
        
        # Create test database with router episodes
        self.test_db = self.data_dir / "events.db"
        self._create_test_database()
        
        # Create exporter
        self.exporter = EpisodeExporter(
            data_dir=self.data_dir,
            router_dir=self.router_dir
        )
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_database(self):
        """Create test database with router episodes."""
        with sqlite3.connect(self.test_db) as conn:
            # Create router_episodes table
            conn.execute("""
                CREATE TABLE router_episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    original_route TEXT,
                    confidence REAL,
                    intent TEXT,
                    is_abstain BOOLEAN DEFAULT FALSE,
                    abstain_reason TEXT,
                    is_override BOOLEAN DEFAULT FALSE,
                    override_route TEXT,
                    override_confidence REAL,
                    label_source TEXT DEFAULT 'router',
                    text_hash TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Insert test data
            test_episodes = [
                # Normal router decision
                ("2024-01-01T10:00:00Z", "s1", "What is machine learning?", "gen", 0.85, "explanation", 0, None, 0, None, None, "router", "hash1"),
                # Low confidence abstain  
                ("2024-01-01T10:01:00Z", "s2", "unclear request", "abstain", 0.4, "unclear", 1, "low_confidence", 0, None, None, "router", "hash2"),
                # Override episode (high priority for training)
                ("2024-01-01T10:02:00Z", "s3", "show my positions", "abstain", 0.45, "unclear", 0, "low_confidence", 1, "act", 0.9, "override", "hash3"),
                # Circuit breaker abstain
                ("2024-01-01T10:03:00Z", "s4", "generate text", "gen", 0.0, "generation_blocked", 1, "circuit_open", 0, None, None, "circuit_breaker", "hash4"),
            ]
            
            for episode in test_episodes:
                conn.execute("""
                    INSERT INTO router_episodes 
                    (timestamp, session_id, text, original_route, confidence, intent, 
                     is_abstain, abstain_reason, is_override, override_route, 
                     override_confidence, label_source, text_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, episode)
            
            conn.commit()
    
    def test_export_with_override_labels(self):
        """Test export includes override labels for training."""
        stats = self.exporter.export_training_data(
            append=False, 
            min_confidence=0.0,
            include_router_episodes=True
        )
        
        # Verify export stats
        self.assertGreater(stats["exported"], 0)
        self.assertEqual(stats["overrides"], 1)  # One override episode
        self.assertEqual(stats["router_episodes"], 4)  # Four router episodes total
        
        # Check output file content
        output_file = self.router_dir / "intents.tsv"
        self.assertTrue(output_file.exists())
        
        with open(output_file, 'r') as f:
            lines = f.readlines()
        
        # Verify enhanced format with label_source
        override_lines = [line for line in lines if line.strip().endswith('\toverride')]
        self.assertEqual(len(override_lines), 1)
        
        # Verify override line content
        override_line = override_lines[0].strip()
        parts = override_line.split('\t')
        self.assertEqual(len(parts), 3)  # text, label, label_source
        self.assertEqual(parts[0], "show my positions")
        self.assertEqual(parts[1], "act") 
        self.assertEqual(parts[2], "override")
        
        # Verify other training samples are included
        router_lines = [line for line in lines if line.strip().endswith('\trouter')]
        self.assertGreater(len(router_lines), 0)
    
    def test_export_legacy_mode(self):
        """Test export in legacy mode (no router episodes)."""
        stats = self.exporter.export_training_data(
            append=False,
            min_confidence=0.0,
            include_router_episodes=False
        )
        
        # Should have no overrides in legacy mode
        self.assertEqual(stats["overrides"], 0)
        self.assertEqual(stats["router_episodes"], 0)
    
    def test_override_priority_in_export(self):
        """Test that override samples are prioritized in export."""
        # Export with overrides
        stats = self.exporter.export_training_data(
            append=False,
            min_confidence=0.6,  # High confidence threshold
            include_router_episodes=True
        )
        
        # Override samples should still be included despite low router confidence
        self.assertEqual(stats["overrides"], 1)
        
        # Check that the override sample is in the output despite low original confidence
        output_file = self.router_dir / "intents.tsv"
        with open(output_file, 'r') as f:
            content = f.read()
        
        self.assertIn("show my positions\tact\toverride", content)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)