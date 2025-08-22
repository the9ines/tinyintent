#!/usr/bin/env python3
"""
Tests for TinyIntent Agent Evolution via Episode Mining

Tests the complete agent suggestion and evolution flow:
- Episode mining for abstain/fallback patterns
- Clustering and analysis
- Automatic agent spec generation
- Suggestion API endpoints
- Create from suggestion flow

M10.1: Agent Evolution via Episode Mining
"""

import json
import os
import sys
import tempfile
import unittest
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tinyintent.data.episodes.episodes import EpisodeMiner
from tinyintent.helpers.manifest import infer_min_capabilities


class TestEpisodeMining(unittest.TestCase):
    """Test episode mining and clustering functionality."""
    
    def setUp(self):
        """Set up test environment with temporary database."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.db_path = self.temp_dir / "test_events.db"
        self.miner = EpisodeMiner(self.db_path)
        
        # Create test database with schema
        self._create_test_database()
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def _create_test_database(self):
        """Create test database with events table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE events (
                    id INTEGER PRIMARY KEY,
                    ts TEXT,
                    session_id TEXT,
                    text TEXT,
                    route_pred TEXT,
                    route_final TEXT,
                    success INTEGER,
                    helper_id TEXT,
                    helper_input TEXT,
                    preview_json TEXT,
                    executed INTEGER,
                    error_code TEXT,
                    labels TEXT
                )
            """)
    
    def _insert_test_events(self, events):
        """Insert test events into database."""
        with sqlite3.connect(self.db_path) as conn:
            for event in events:
                conn.execute("""
                    INSERT INTO events (ts, session_id, text, route_pred, route_final, 
                                      success, helper_id, error_code, labels)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.get('ts', datetime.utcnow().isoformat() + 'Z'),
                    event.get('session_id', f"session_{event.get('id', 1)}"),
                    event.get('text', ''),
                    event.get('route_pred', 'act'),
                    event.get('route_final', 'fallback'),
                    event.get('success', 0),
                    event.get('helper_id', None),
                    event.get('error_code', 'abstain_unknown'),
                    event.get('labels', '')
                ))
    
    def test_mine_abstain_clusters_no_events(self):
        """Test mining when no abstain events exist."""
        clusters = self.miner.mine_abstain_clusters()
        self.assertEqual(clusters, [])
    
    def test_mine_abstain_clusters_insufficient_events(self):
        """Test mining when insufficient events exist."""
        # Insert only a few events (below min_count threshold)
        events = [
            {'id': 1, 'text': 'Fetch weather data', 'route_final': 'fallback'},
            {'id': 2, 'text': 'Get stock prices', 'route_final': 'fallback'},
        ]
        self._insert_test_events(events)
        
        clusters = self.miner.mine_abstain_clusters(min_count=5)
        self.assertEqual(clusters, [])
    
    def test_mine_abstain_clusters_success(self):
        """Test successful clustering of abstain events."""
        # Insert events with two distinct themes
        base_time = datetime.utcnow()
        
        # Web scraping theme (8 events)
        web_events = [
            {'id': i, 'text': f'Fetch data from {url}', 'route_final': 'fallback'}
            for i, url in enumerate([
                'https://example.com',
                'https://news.com',
                'https://weather.com',
                'https://api.github.com',
                'https://stackoverflow.com',
                'https://reddit.com',
                'https://twitter.com',
                'https://facebook.com'
            ], 1)
        ]
        
        # File processing theme (10 events)
        file_events = [
            {'id': i, 'text': f'Process {filename}', 'route_final': 'fallback'}
            for i, filename in enumerate([
                'data.csv',
                'report.pdf',
                'config.json',
                'logs.txt',
                'image.jpg',
                'document.docx',
                'spreadsheet.xlsx',
                'presentation.pptx',
                'archive.zip',
                'database.sqlite'
            ], 100)
        ]
        
        # Set timestamps within the window
        for events in [web_events, file_events]:
            for event in events:
                event['ts'] = (base_time - timedelta(hours=1)).isoformat() + 'Z'
        
        self._insert_test_events(web_events + file_events)
        
        clusters = self.miner.mine_abstain_clusters(window_hours=24, min_count=5)
        
        # Should find at least one cluster (possibly two if clustering works well)
        self.assertGreater(len(clusters), 0)
        self.assertLessEqual(len(clusters), 5)  # Max clusters limit
        
        # Check cluster structure
        for cluster in clusters:
            self.assertIn('cluster_id', cluster)
            self.assertIn('representative_text', cluster)
            self.assertIn('sample_count', cluster)
            self.assertIn('examples', cluster)
            self.assertIn('themes', cluster)
            self.assertIn('suggested_capabilities', cluster)
            
            # Should meet minimum count requirement
            self.assertGreaterEqual(cluster['sample_count'], 5)
            
            # Should have examples
            self.assertGreater(len(cluster['examples']), 0)
            self.assertLessEqual(len(cluster['examples']), 5)  # Max 5 examples
    
    def test_mine_abstain_clusters_time_window(self):
        """Test time window filtering."""
        base_time = datetime.utcnow()
        
        # Events within window
        recent_events = [
            {
                'id': i,
                'text': f'Recent request {i}',
                'route_final': 'fallback',
                'ts': (base_time - timedelta(hours=1)).isoformat() + 'Z'
            }
            for i in range(10)
        ]
        
        # Events outside window
        old_events = [
            {
                'id': i,
                'text': f'Old request {i}',
                'route_final': 'fallback',
                'ts': (base_time - timedelta(hours=25)).isoformat() + 'Z'
            }
            for i in range(100, 110)
        ]
        
        self._insert_test_events(recent_events + old_events)
        
        clusters = self.miner.mine_abstain_clusters(window_hours=24, min_count=5)
        
        # Should only find cluster from recent events
        self.assertGreater(len(clusters), 0)
        for cluster in clusters:
            # All examples should be from recent events
            for example in cluster['examples']:
                self.assertIn('Recent request', example['text'])
    
    def test_extract_themes(self):
        """Test theme extraction from clusters."""
        # Create miner instance and test theme extraction directly
        miner = EpisodeMiner(self.db_path)
        
        # Web-related events
        web_events = [
            {'text': 'fetch data from https://api.example.com'},
            {'text': 'download file from website'},
            {'text': 'get url content'}
        ]
        
        themes = miner._extract_themes(list(range(len(web_events))), web_events)
        self.assertIn('web_interaction', themes)
        self.assertIn('data_retrieval', themes)
        
        # File processing events
        file_events = [
            {'text': 'process csv file'},
            {'text': 'read document content'},
            {'text': 'save data to file'}
        ]
        
        themes = miner._extract_themes(list(range(len(file_events))), file_events)
        self.assertIn('file_processing', themes)
    
    def test_infer_capabilities_from_cluster(self):
        """Test capability inference from cluster patterns."""
        miner = EpisodeMiner(self.db_path)
        
        # Network-related events
        network_events = [
            {'text': 'fetch data from https://api.example.com'},
            {'text': 'download url content'},
            {'text': 'call web api'}
        ]
        
        capabilities = miner._infer_capabilities_from_cluster(
            list(range(len(network_events))), network_events
        )
        self.assertIn('network', capabilities)
        
        # Filesystem events
        file_events = [
            {'text': 'read file content'},
            {'text': 'save document'},
            {'text': 'process csv data'}
        ]
        
        capabilities = miner._infer_capabilities_from_cluster(
            list(range(len(file_events))), file_events
        )
        self.assertIn('filesystem', capabilities)


class TestCapabilityInference(unittest.TestCase):
    """Test capability inference from agent specifications."""
    
    def test_infer_min_capabilities_network(self):
        """Test network capability inference."""
        spec = {
            "description": "Fetch data from URLs and APIs",
            "inputs": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "format": "uri"},
                    "endpoint": {"type": "string"}
                }
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "data": {"type": "string"}
                }
            }
        }
        
        capabilities = infer_min_capabilities(spec)
        self.assertIn('network', capabilities)
    
    def test_infer_min_capabilities_filesystem(self):
        """Test filesystem capability inference."""
        spec = {
            "description": "Process files and documents",
            "inputs": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "document": {"type": "string"}
                }
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            }
        }
        
        capabilities = infer_min_capabilities(spec)
        self.assertIn('filesystem', capabilities)
    
    def test_infer_min_capabilities_database(self):
        """Test database capability inference."""
        spec = {
            "description": "Query database tables and records",
            "inputs": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "table": {"type": "string"}
                }
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "records": {"type": "array"}
                }
            }
        }
        
        capabilities = infer_min_capabilities(spec)
        self.assertIn('database', capabilities)
    
    def test_infer_min_capabilities_minimal(self):
        """Test minimal capability inference."""
        spec = {
            "description": "Simple text processing",
            "inputs": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"}
                }
            },
            "outputs": {
                "type": "object",
                "properties": {
                    "result": {"type": "string"}
                }
            }
        }
        
        capabilities = infer_min_capabilities(spec)
        # Should return empty list for simple text processing
        self.assertEqual(capabilities, [])


# Mock FastAPI test client for API endpoint testing
try:
    from fastapi.testclient import TestClient
    from tinyintent.bridge.api_routes import router_api
    
    class TestAgentSuggestionAPI(unittest.TestCase):
        """Test agent suggestion API endpoints."""
        
        def setUp(self):
            """Set up test client."""
            from fastapi import FastAPI
            app = FastAPI()
            app.include_router(router_api)
            self.client = TestClient(app)
            
            # Mock authentication
            self.auth_headers = {"Authorization": "Bearer test-secret"}
            
            # Set up temporary database
            self.temp_dir = Path(tempfile.mkdtemp())
            self.db_path = self.temp_dir / "test_events.db"
        
        def tearDown(self):
            """Clean up test environment."""
            import shutil
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        def _create_test_database_with_events(self):
            """Create test database with abstain events."""
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE events (
                        id INTEGER PRIMARY KEY,
                        ts TEXT,
                        session_id TEXT,
                        text TEXT,
                        route_pred TEXT,
                        route_final TEXT,
                        success INTEGER,
                        helper_id TEXT,
                        error_code TEXT,
                        labels TEXT
                    )
                """)
                
                # Insert test abstain events
                base_time = datetime.utcnow()
                events = []
                
                # Web scraping cluster
                for i in range(10):
                    events.append((
                        (base_time - timedelta(hours=1)).isoformat() + 'Z',
                        f'session_{i}',
                        f'Fetch data from https://example{i}.com',
                        'act',
                        'fallback',
                        0,
                        None,
                        'abstain_unknown',
                        ''
                    ))
                
                # File processing cluster
                for i in range(10, 20):
                    events.append((
                        (base_time - timedelta(hours=1)).isoformat() + 'Z',
                        f'session_{i}',
                        f'Process file{i}.csv and extract data',
                        'act',
                        'fallback',
                        0,
                        None,
                        'abstain_unknown',
                        ''
                    ))
                
                conn.executemany("""
                    INSERT INTO events (ts, session_id, text, route_pred, route_final,
                                      success, helper_id, error_code, labels)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, events)
        
        @patch('tinyintent.bridge.api_routes.episode_miner')
        @patch('tinyintent.bridge.api_routes.async_ollama_client')
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_suggest_agents_success(self, mock_rate_limiter, mock_ollama_client, mock_episode_miner):
            """Test successful agent suggestion."""
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            
            # Mock cluster data
            mock_clusters = [
                {
                    "cluster_id": 0,
                    "representative_text": "Fetch data from https://example.com",
                    "sample_count": 10,
                    "confidence_score": 0.8,
                    "examples": [
                        {
                            "text": "Fetch data from https://example.com",
                            "timestamp": datetime.utcnow().isoformat() + 'Z',
                            "route_pred": "act",
                            "route_final": "fallback",
                            "abstain_reason": "router_fallback"
                        }
                    ],
                    "themes": ["web_interaction", "data_retrieval"],
                    "suggested_capabilities": ["network"]
                }
            ]
            mock_episode_miner.mine_abstain_clusters.return_value = mock_clusters
            
            # Mock Ollama response
            mock_ollama_response = {
                "text": json.dumps({
                    "id": "web_scraper",
                    "description": "Fetch data from web URLs",
                    "language": "python",
                    "capabilities": ["network"],
                    "inputs": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "format": "uri"}
                        },
                        "required": ["url"]
                    },
                    "outputs": {
                        "type": "object",
                        "properties": {
                            "data": {"type": "string"}
                        },
                        "required": ["data"]
                    }
                })
            }
            mock_ollama_client.generate.return_value = mock_ollama_response
            
            # Make request
            request_data = {
                "window_hours": 24,
                "min_count": 5,
                "max_suggestions": 5
            }
            
            response = self.client.post("/agents/suggest", json=request_data, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 200)
            result = response.json()
            
            self.assertIn("suggestions", result)
            self.assertIn("clusters_analyzed", result)
            self.assertIn("total_abstain_events", result)
            self.assertIn("window_hours", result)
            
            # Should have at least one suggestion
            self.assertGreater(len(result["suggestions"]), 0)
            
            suggestion = result["suggestions"][0]
            self.assertIn("spec", suggestion)
            self.assertIn("valid", suggestion)
            self.assertIn("cluster_info", suggestion)
            
            # Spec should be valid
            self.assertTrue(suggestion["valid"])
            self.assertEqual(suggestion["spec"]["id"], "web_scraper")
            self.assertFalse(suggestion["spec"]["can_execute"])  # Should be forced to false
        
        @patch('tinyintent.bridge.api_routes.episode_miner')
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_suggest_agents_no_clusters(self, mock_rate_limiter, mock_episode_miner):
            """Test agent suggestion when no clusters found."""
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_episode_miner.mine_abstain_clusters.return_value = []
            
            request_data = {"window_hours": 24}
            
            response = self.client.post("/agents/suggest", json=request_data, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 200)
            result = response.json()
            
            self.assertEqual(len(result["suggestions"]), 0)
            self.assertEqual(result["clusters_analyzed"], 0)
            self.assertEqual(result["total_abstain_events"], 0)
        
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_suggest_agents_rate_limited(self, mock_rate_limiter):
            """Test agent suggestion when rate limited."""
            # Setup rate limit
            mock_rate_limiter.check_rate_limit.return_value = (False, 60)
            
            request_data = {"window_hours": 24}
            
            response = self.client.post("/agents/suggest", json=request_data, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 429)
            self.assertIn("Retry-After", response.headers)
        
        @patch('tinyintent.bridge.api_routes.agent_generator')
        @patch('tinyintent.bridge.api_routes.helper_registry')
        @patch('tinyintent.bridge.api_routes.rate_limiter')
        def test_create_agent_from_suggestion_success(self, mock_rate_limiter, mock_helper_registry, mock_agent_generator):
            """Test successful agent creation from suggestion."""
            # Setup mocks
            mock_rate_limiter.check_rate_limit.return_value = (True, 0)
            mock_agent_generator.create_agent.return_value = {
                "created": True,
                "helper_id": "web_scraper",
                "enabled": True,
                "validation": {"passed": True, "errors": []},
                "files_created": ["web_scraper/helper.yaml", "web_scraper/main.py"]
            }
            
            # Valid suggestion spec
            spec = {
                "id": "web_scraper",
                "description": "Fetch data from web URLs",
                "language": "python",
                "capabilities": ["network"],
                "can_execute": False,
                "risk_level": "high",
                "inputs": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "format": "uri"}
                    },
                    "required": ["url"]
                },
                "outputs": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string"}
                    },
                    "required": ["data"]
                }
            }
            
            request_data = {"spec": spec}
            
            response = self.client.post("/agents/create_from_suggestion", json=request_data, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 200)
            result = response.json()
            
            self.assertTrue(result["created"])
            self.assertEqual(result["helper_id"], "web_scraper")
            self.assertTrue(result["enabled"])
            
            # Check that generator was called with correct spec
            mock_agent_generator.create_agent.assert_called_once()
            called_spec = mock_agent_generator.create_agent.call_args[0][0]
            self.assertEqual(called_spec["id"], "web_scraper")
            self.assertFalse(called_spec["can_execute"])  # Should be forced to false
            
            # Check that helper registry was reloaded
            mock_helper_registry.reload.assert_called_once()
        
        def test_create_agent_from_suggestion_invalid_spec(self):
            """Test agent creation with invalid suggestion spec."""
            # Invalid spec (missing required fields)
            spec = {
                "description": "Test agent"
                # Missing id, language, inputs, outputs
            }
            
            request_data = {"spec": spec}
            
            response = self.client.post("/agents/create_from_suggestion", json=request_data, headers=self.auth_headers)
            
            # Check response
            self.assertEqual(response.status_code, 422)  # Validation error

except ImportError:
    # FastAPI not available - skip API tests
    print("FastAPI not available - skipping API tests")
    
    class TestAgentSuggestionAPI(unittest.TestCase):
        """Placeholder for when FastAPI is not available."""
        
        def test_skip_api_tests(self):
            """Skip API tests when FastAPI not available."""
            self.skipTest("FastAPI not available")


class TestSuggestionIntegration(unittest.TestCase):
    """Integration tests for the complete suggestion flow."""
    
    def test_end_to_end_suggestion_flow(self):
        """Test the complete suggestion and creation flow."""
        # This would be an integration test that:
        # 1. Seeds database with abstain events
        # 2. Calls suggestion API
        # 3. Validates suggestions
        # 4. Creates agent from suggestion
        # 5. Verifies agent is created and enabled
        
        # For now, just test that the classes can be imported and initialized
        from tinyintent.data.episodes.episodes import EpisodeMiner
        from tinyintent.helpers.manifest import validate_agent_spec, infer_min_capabilities
        
        # Create temporary database
        temp_dir = Path(tempfile.mkdtemp())
        db_path = temp_dir / "test.db"
        
        try:
            miner = EpisodeMiner(db_path)
            self.assertIsNotNone(miner)
            
            # Test capability inference
            spec = {
                "description": "Test helper",
                "inputs": {"type": "object"},
                "outputs": {"type": "object"}
            }
            capabilities = infer_min_capabilities(spec)
            self.assertIsInstance(capabilities, list)
            
            # Test spec validation
            full_spec = {
                "id": "test_helper",
                "description": "Test helper",
                "language": "python",
                "capabilities": capabilities,
                "inputs": {"type": "object"},
                "outputs": {"type": "object"}
            }
            is_valid, errors = validate_agent_spec(full_spec)
            self.assertTrue(is_valid, f"Spec validation failed: {errors}")
            
        finally:
            # Clean up
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)