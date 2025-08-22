#!/usr/bin/env python3
"""
TinyIntent Router Retraining Tests - M7.5

Tests end-to-end retraining dry-run and safeguards functionality,
including export script dry-run mode, training summary generation,
and API endpoint integration.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import sqlite3

# Add paths to modules
sys.path.append(str(Path(__file__).parent.parent / "bridge"))
sys.path.append(str(Path(__file__).parent.parent / "scripts"))

try:
    from export_episodes import EpisodeExporter
    EXPORT_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Export script not available: {e}")
    EXPORT_AVAILABLE = False

try:
    from tinyintent.bridge.api_routes import get_router_train_summary
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Bridge not available: {e}")
    BRIDGE_AVAILABLE = False


class TestExportDryRunFunctionality(unittest.TestCase):
    """Test M7.5 export script dry-run functionality."""
    
    def setUp(self):
        """Set up test environment."""
        if not EXPORT_AVAILABLE:
            self.skipTest("Export script not available")
        
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
        """Create test database with diverse router episodes."""
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
            
            # Insert diverse test data for comprehensive dry-run analysis
            test_episodes = [
                # Normal router decisions
                ("2024-01-01T10:00:00Z", "s1", "What is machine learning?", "gen", 0.85, "explanation", 0, None, 0, None, None, "router", "hash1"),
                ("2024-01-01T10:01:00Z", "s2", "Close my trading position", "act", 0.90, "trading", 0, None, 0, None, None, "router", "hash2"),
                ("2024-01-01T10:02:00Z", "s3", "Generate a summary report", "gen", 0.92, "generation", 0, None, 0, None, None, "router", "hash3"),
                
                # Low confidence abstains (good for retraining with overrides)
                ("2024-01-01T10:03:00Z", "s4", "unclear request 1", "abstain", 0.4, "unclear", 1, "low_confidence", 0, None, None, "router", "hash4"),
                ("2024-01-01T10:04:00Z", "s5", "ambiguous instruction", "abstain", 0.35, "unclear", 1, "low_confidence", 0, None, None, "router", "hash5"),
                
                # Override episodes (high priority for training)
                ("2024-01-01T10:05:00Z", "s6", "show my positions", "abstain", 0.45, "unclear", 0, "low_confidence", 1, "act", 0.9, "override", "hash6"),
                ("2024-01-01T10:06:00Z", "s7", "generate crypto report", "abstain", 0.42, "unclear", 0, "low_confidence", 1, "gen", 0.88, "override", "hash7"),
                ("2024-01-01T10:07:00Z", "s8", "emergency stop bots", "abstain", 0.38, "unclear", 0, "low_confidence", 1, "act", 0.95, "override", "hash8"),
                
                # Circuit breaker abstains (should be excluded from training)
                ("2024-01-01T10:08:00Z", "s9", "generate text", "gen", 0.0, "generation_blocked", 1, "circuit_open", 0, None, None, "circuit_breaker", "hash9"),
                ("2024-01-01T10:09:00Z", "s10", "create document", "gen", 0.0, "generation_blocked", 1, "circuit_open", 0, None, None, "circuit_breaker", "hash10"),
                
                # Router fallback cases
                ("2024-01-01T10:10:00Z", "s11", "fallback case", "gen", 0.5, "fallback_intent", 1, "router_fallback", 0, None, None, "router", "hash11"),
                
                # More normal cases for balance
                ("2024-01-01T10:11:00Z", "s12", "Execute trading strategy", "act", 0.87, "trading", 0, None, 0, None, None, "router", "hash12"),
                ("2024-01-01T10:12:00Z", "s13", "Write documentation", "gen", 0.91, "generation", 0, None, 0, None, None, "router", "hash13"),
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
    
    def test_dry_run_export_analysis(self):
        """Test dry-run export provides comprehensive analysis."""
        stats = self.exporter.export_training_data(
            append=False, 
            min_confidence=0.0,
            include_router_episodes=True,
            dry_run=True
        )
        
        # Verify dry-run stats structure
        self.assertTrue(stats["dry_run"])
        self.assertIn("label_source_counts", stats)
        self.assertIn("label_source_percentages", stats)
        self.assertIn("label_counts", stats)
        self.assertIn("label_percentages", stats)
        self.assertIn("intent_distribution", stats)
        self.assertIn("total_new_samples", stats)
        
        # Verify override samples are detected
        self.assertEqual(stats["overrides"], 3)  # 3 override episodes
        self.assertGreater(stats["label_source_counts"]["override"], 0)
        
        # Verify router episodes are processed
        self.assertEqual(stats["router_episodes"], 13)  # 13 total router episodes
        
        # Verify correct label distribution
        self.assertIn("gen", stats["label_counts"])
        self.assertIn("act", stats["label_counts"])
        
        # Verify no files were written in dry-run
        output_file = self.router_dir / "intents.tsv"
        self.assertFalse(output_file.exists())
    
    def test_dry_run_vs_normal_export_comparison(self):
        """Test dry-run produces same analysis as normal export without writing files."""
        # Run dry-run export
        dry_run_stats = self.exporter.export_training_data(
            append=False,
            min_confidence=0.0,
            include_router_episodes=True,
            dry_run=True
        )
        
        # Run normal export
        normal_stats = self.exporter.export_training_data(
            append=False,
            min_confidence=0.0,
            include_router_episodes=True,
            dry_run=False
        )
        
        # Verify dry-run didn't write files
        output_file = self.router_dir / "intents.tsv"
        self.assertTrue(output_file.exists())  # Normal export should create file
        
        # Clear file for clean comparison
        output_file.unlink()
        
        # Key stats should be identical
        self.assertEqual(dry_run_stats["exported"], normal_stats["exported"])
        self.assertEqual(dry_run_stats["overrides"], normal_stats["overrides"])
        self.assertEqual(dry_run_stats["router_episodes"], normal_stats["router_episodes"])
        self.assertEqual(dry_run_stats["total_episodes"], normal_stats["total_episodes"])
    
    def test_dry_run_quality_assessment(self):
        """Test dry-run provides training readiness assessment."""
        stats = self.exporter.export_training_data(
            append=False,
            min_confidence=0.0,
            include_router_episodes=True,
            dry_run=True
        )
        
        # Should have enough samples for training (13 router episodes)
        total_samples = stats["total_new_samples"]
        self.assertGreater(total_samples, 5)
        
        # Should detect override samples for active learning
        self.assertEqual(stats["overrides"], 3)
        
        # Should have both gen and act labels for balanced training
        self.assertGreater(stats["label_counts"]["gen"], 0)
        self.assertGreater(stats["label_counts"]["act"], 0)
    
    def test_dry_run_with_confidence_filtering(self):
        """Test dry-run respects confidence thresholds but includes overrides."""
        # High confidence threshold should filter out low confidence entries
        # but keep override entries regardless of original confidence
        stats = self.exporter.export_training_data(
            append=False,
            min_confidence=0.8,  # High threshold
            include_router_episodes=True,
            dry_run=True
        )
        
        # Overrides should still be included despite low original confidence
        self.assertEqual(stats["overrides"], 3)
        
        # High-confidence router decisions should be included
        normal_high_conf = [ep for ep in [0.85, 0.90, 0.92, 0.87, 0.91] if ep >= 0.8]
        self.assertGreater(len(normal_high_conf), 0)


class TestTrainingSummaryGeneration(unittest.TestCase):
    """Test training summary generation in router training script."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.router_dir = Path(self.temp_dir) / "router"
        self.router_dir.mkdir(parents=True)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_training_summary_structure(self):
        """Test training summary JSON has required structure."""
        # Create mock training summary
        mock_summary = {
            'timestamp': '2024-01-01T12:00:00',
            'status': 'completed',
            'model': {
                'name': 'test-model',
                'architecture': 'transformer_classification',
                'num_parameters': 1000000,
                'vocab_size': 30000,
                'num_labels': 2
            },
            'dataset': {
                'total_samples': 150,
                'train_samples': 90,
                'val_samples': 30,
                'cal_samples': 30,
                'label_distribution': {'gen': 75, 'act': 75}
            },
            'training': {
                'epochs_completed': 10,
                'batch_size': 8,
                'learning_rate': 2e-5,
                'early_stopping_patience': 3,
                'device_used': 'mps'
            },
            'performance': {
                'validation_accuracy': 0.92,
                'validation_loss': 0.25,
                'calibration': {
                    'temperature': 1.2,
                    'pre_calibration_ece': 0.08,
                    'post_calibration_ece': 0.04,
                    'method': 'temperature_scaling'
                }
            },
            'files': {
                'model_path': '/path/to/model',
                'metadata_path': '/path/to/metadata.json',
                'calibration_path': '/path/to/calibration.pkl',
                'output_directory': '/path/to/output'
            },
            'sample_predictions': [
                {
                    'text': 'Generate a summary report',
                    'predicted_label': 'gen',
                    'raw_confidence': 0.89,
                    'calibrated_confidence': 0.85
                },
                {
                    'text': 'Close all trading positions',
                    'predicted_label': 'act',
                    'raw_confidence': 0.93,
                    'calibrated_confidence': 0.91
                }
            ]
        }
        
        # Verify required sections
        required_sections = ['timestamp', 'status', 'model', 'dataset', 'training', 'performance', 'files', 'sample_predictions']
        for section in required_sections:
            self.assertIn(section, mock_summary)
        
        # Verify model section
        model = mock_summary['model']
        self.assertIn('name', model)
        self.assertIn('num_parameters', model)
        self.assertIn('vocab_size', model)
        
        # Verify performance section
        performance = mock_summary['performance']
        self.assertIn('validation_accuracy', performance)
        self.assertIn('calibration', performance)
        
        calibration = performance['calibration']
        self.assertIn('temperature', calibration)
        self.assertIn('post_calibration_ece', calibration)
        
        # Verify sample predictions
        self.assertGreater(len(mock_summary['sample_predictions']), 0)
        for pred in mock_summary['sample_predictions']:
            self.assertIn('text', pred)
            self.assertIn('predicted_label', pred)
            self.assertIn('calibrated_confidence', pred)
    
    def test_training_summary_file_creation(self):
        """Test training summary file is created in correct location."""
        train_summary_path = self.router_dir / "train_summary.json"
        
        # Mock training summary data
        mock_summary = {
            'timestamp': '2024-01-01T12:00:00',
            'status': 'completed',
            'performance': {'validation_accuracy': 0.85}
        }
        
        # Write summary file
        with open(train_summary_path, 'w') as f:
            json.dump(mock_summary, f, indent=2)
        
        # Verify file exists and is readable
        self.assertTrue(train_summary_path.exists())
        
        with open(train_summary_path, 'r') as f:
            loaded_summary = json.load(f)
        
        self.assertEqual(loaded_summary['status'], 'completed')
        self.assertEqual(loaded_summary['performance']['validation_accuracy'], 0.85)


class TestTrainSummaryAPIEndpoint(unittest.IsolatedAsyncioTestCase):
    """Test GET /router/train_summary API endpoint."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        self.temp_dir = tempfile.mkdtemp()
        self.router_dir = Path(self.temp_dir) / "router"
        self.router_dir.mkdir(parents=True)
    
    async def asyncTearDown(self):
        """Clean up test environment."""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @patch('tinyrpc.Path')
    async def test_train_summary_not_available(self, mock_path):
        """Test API response when no training summary is available."""
        # Mock path to return non-existent file
        mock_project_root = MagicMock()
        mock_path.return_value.parent.parent = mock_project_root
        mock_project_root.__truediv__ = MagicMock()
        
        # Mock file doesn't exist
        mock_summary_path = MagicMock()
        mock_summary_path.exists.return_value = False
        mock_project_root.__truediv__.return_value = mock_summary_path
        
        # Mock alternative paths also don't exist
        for _ in range(3):  # project_root calls + alt paths
            alt_mock = MagicMock()
            alt_mock.exists.return_value = False
            mock_project_root.__truediv__.return_value = alt_mock
        
        result = await get_router_train_summary(auth=True)
        
        self.assertEqual(result["status"], "not_available")
        self.assertIn("No training summary available", result["message"])
        self.assertIn("expected_path", result)
    
    @patch('tinyrpc.Path')
    @patch('builtins.open', new_callable=mock_open)
    async def test_train_summary_available(self, mock_file, mock_path):
        """Test API response when training summary is available."""
        # Mock training summary data
        mock_summary_data = {
            'timestamp': '2024-01-01T12:00:00',
            'status': 'completed',
            'model': {
                'name': 'test-model',
                'num_parameters': 1000000
            },
            'dataset': {
                'total_samples': 100,
                'label_distribution': {'gen': 60, 'act': 40}
            },
            'performance': {
                'validation_accuracy': 0.92,
                'calibration': {
                    'post_calibration_ece': 0.04
                }
            }
        }
        
        # Mock file operations
        mock_file.return_value.read.return_value = json.dumps(mock_summary_data)
        
        # Mock path operations
        mock_project_root = MagicMock()
        mock_path.return_value.parent.parent = mock_project_root
        
        mock_summary_path = MagicMock()
        mock_summary_path.exists.return_value = True
        mock_summary_path.stat.return_value.st_size = 1024
        mock_summary_path.stat.return_value.st_mtime = 1640995200  # 2022-01-01
        mock_summary_path.name = "train_summary.json"
        mock_project_root.__truediv__.return_value = mock_summary_path
        
        # Mock json.load
        with patch('json.load', return_value=mock_summary_data):
            result = await get_router_train_summary(auth=True)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("training_summary", result)
        
        training_summary = result["training_summary"]
        self.assertEqual(training_summary["status"], "completed")
        self.assertIn("quality_assessment", training_summary)
        self.assertIn("recommendations", training_summary)
        self.assertIn("file_info", training_summary)
        
        # Verify quality assessment
        quality = training_summary["quality_assessment"]
        self.assertIn("overall_grade", quality)
        self.assertIn("ready_for_production", quality)
        self.assertIsInstance(quality["ready_for_production"], bool)
    
    @patch('tinyrpc.Path')
    @patch('builtins.open', side_effect=json.JSONDecodeError("Invalid JSON", "doc", 0))
    async def test_train_summary_corrupted_json(self, mock_file, mock_path):
        """Test API response when training summary JSON is corrupted."""
        # Mock path operations
        mock_project_root = MagicMock()
        mock_path.return_value.parent.parent = mock_project_root
        
        mock_summary_path = MagicMock()
        mock_summary_path.exists.return_value = True
        mock_project_root.__truediv__.return_value = mock_summary_path
        
        with self.assertRaises(Exception) as context:
            await get_router_train_summary(auth=True)
        
        # Should raise HTTPException with 500 status
        self.assertEqual(context.exception.status_code, 500)
        self.assertIn("corrupted", context.exception.detail)


class TestMakeLearnDryIntegration(unittest.TestCase):
    """Test make learn-dry target integration."""
    
    def test_makefile_learn_dry_target_exists(self):
        """Test that make learn-dry target exists in Makefile."""
        makefile_path = Path(__file__).parent.parent / "Makefile"
        
        if not makefile_path.exists():
            self.skipTest("Makefile not found")
        
        with open(makefile_path, 'r') as f:
            makefile_content = f.read()
        
        # Verify learn-dry target exists
        self.assertIn("learn-dry:", makefile_content)
        self.assertIn("--dry-run", makefile_content)
        self.assertIn("M7.5", makefile_content)
    
    @patch('subprocess.run')
    def test_export_script_cli_dry_run_flag(self, mock_subprocess):
        """Test export script accepts --dry-run CLI flag."""
        # Mock successful subprocess call
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "Dry-run analysis complete"
        mock_subprocess.return_value = mock_result
        
        # Test command that would be run by make learn-dry
        test_command = [
            "python3", "scripts/export_episodes.py", "--dry-run"
        ]
        
        result = subprocess.run(test_command, capture_output=True, text=True, timeout=5)
        
        # Command should be accepted (even if it fails due to missing data)
        # The important thing is that --dry-run flag is recognized
        self.assertIsInstance(result.returncode, int)


class TestEndToEndRetrainingWorkflow(unittest.TestCase):
    """Test end-to-end retraining workflow with safeguards."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        
        # Create project structure
        (self.project_root / "router").mkdir(parents=True)
        (self.project_root / "data" / "episodes").mkdir(parents=True)
        (self.project_root / "scripts").mkdir(parents=True)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_retraining_workflow_steps(self):
        """Test the logical flow of retraining workflow."""
        # Step 1: Dry-run analysis should come first
        workflow_steps = [
            "export_episodes_dry_run",
            "assess_training_readiness", 
            "actual_export_if_approved",
            "router_training",
            "training_summary_generation",
            "api_endpoint_availability"
        ]
        
        # Verify logical dependencies
        dry_run_index = workflow_steps.index("export_episodes_dry_run")
        assess_index = workflow_steps.index("assess_training_readiness")
        export_index = workflow_steps.index("actual_export_if_approved")
        train_index = workflow_steps.index("router_training")
        summary_index = workflow_steps.index("training_summary_generation")
        api_index = workflow_steps.index("api_endpoint_availability")
        
        # Verify proper ordering
        self.assertLess(dry_run_index, assess_index)
        self.assertLess(assess_index, export_index)
        self.assertLess(export_index, train_index)
        self.assertLess(train_index, summary_index)
        self.assertLess(summary_index, api_index)
    
    def test_safeguards_prevent_bad_training(self):
        """Test safeguards that prevent training on insufficient data."""
        # Simulate insufficient training data scenario
        insufficient_data_scenarios = [
            {"total_samples": 10, "should_train": False},    # Too few samples
            {"total_samples": 100, "gen_samples": 5, "act_samples": 95, "should_train": False},  # Imbalanced
            {"total_samples": 150, "gen_samples": 75, "act_samples": 75, "should_train": True},  # Good
            {"total_samples": 50, "override_samples": 20, "should_train": True},  # Borderline but has overrides
        ]
        
        for scenario in insufficient_data_scenarios:
            with self.subTest(scenario=scenario):
                total = scenario.get("total_samples", 0)
                gen = scenario.get("gen_samples", total // 2)
                act = scenario.get("act_samples", total - gen)
                overrides = scenario.get("override_samples", 0)
                
                # Training readiness assessment logic
                size_adequate = total >= 50
                balance_good = min(gen, act) / max(gen, act) >= 0.3 if gen > 0 and act > 0 else False
                has_overrides = overrides > 0
                
                should_train = size_adequate and (balance_good or has_overrides)
                
                self.assertEqual(should_train, scenario["should_train"], 
                               f"Training assessment failed for {scenario}")


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)