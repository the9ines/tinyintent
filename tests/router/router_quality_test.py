#!/usr/bin/env python3
"""
TinyIntent Router Quality, Thresholds & Fallbacks Tests - M7.1

Tests confidence calibration, thresholds-based decision making, and robust
fallback behavior when the CoreML router is unavailable or returns low confidence.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess

# Add bridge to path
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

try:
    from tinyintent.bridge.router_client import SmallIntentRouter
from tinyintent.bridge.api_routes import RouteResponse
    BRIDGE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Bridge not available: {e}")
    BRIDGE_AVAILABLE = False


class TestConfidenceThresholds(unittest.TestCase):
    """Test confidence threshold-based routing decisions."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
        
        # Create router with custom thresholds for testing
        with patch.dict(os.environ, {
            'ROUTER_MIN_CONF_GEN': '0.6',
            'ROUTER_MIN_CONF_ACT': '0.75', 
            'ROUTER_FALLBACK_THRESHOLD': '0.3'
        }):
            self.router = SmallIntentRouter()
        
        # Verify thresholds are set correctly
        self.assertEqual(self.router.min_conf_gen, 0.6)
        self.assertEqual(self.router.min_conf_act, 0.75)
        self.assertEqual(self.router.fallback_threshold, 0.3)
    
    def test_high_confidence_generation_accepted(self):
        """Test high confidence generation routing is accepted."""
        mock_router_result = {
            "route": "gen",
            "intent": "general_query",
            "confidence": 0.85
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(mock_router_result)
            mock_subprocess.return_value = mock_result
            
            result = self.router.route_request("What is machine learning?")
            
            self.assertEqual(result["route"], "gen")
            self.assertEqual(result["confidence"], 0.85)
            self.assertEqual(result["intent"], "general_query")
    
    def test_high_confidence_action_accepted(self):
        """Test high confidence action routing is accepted."""
        mock_router_result = {
            "route": "act",
            "intent": "bot_management", 
            "confidence": 0.9
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(mock_router_result)
            mock_subprocess.return_value = mock_result
            
            result = self.router.route_request("Close all bot positions")
            
            self.assertEqual(result["route"], "act")
            self.assertEqual(result["confidence"], 0.9)
            self.assertEqual(result["intent"], "bot_management")
    
    def test_low_confidence_generation_abstains(self):
        """Test low confidence generation routing leads to abstain."""
        mock_router_result = {
            "route": "gen",
            "intent": "general_query",
            "confidence": 0.45  # Below 0.6 threshold
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(mock_router_result)
            mock_subprocess.return_value = mock_result
            
            result = self.router.route_request("Ambiguous query here")
            
            self.assertEqual(result["route"], "abstain")
            self.assertEqual(result["confidence"], 0.45)
            self.assertEqual(result["suggested_route"], "gen")
            self.assertIn("Generation confidence", result["abstain_reason"])
            self.assertTrue(result["fallback_available"])
    
    def test_low_confidence_action_abstains(self):
        """Test low confidence action routing leads to abstain."""
        mock_router_result = {
            "route": "act",
            "intent": "bot_management",
            "confidence": 0.65  # Below 0.75 threshold
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(mock_router_result)
            mock_subprocess.return_value = mock_result
            
            result = self.router.route_request("Maybe do something with bots")
            
            self.assertEqual(result["route"], "abstain")
            self.assertEqual(result["confidence"], 0.65)
            self.assertEqual(result["suggested_route"], "act")
            self.assertIn("Action confidence", result["abstain_reason"])
            self.assertTrue(result["fallback_available"])
    
    def test_very_low_confidence_uses_fallback(self):
        """Test very low confidence falls back to hardcoded routing."""
        mock_router_result = {
            "route": "gen",
            "intent": "general_query", 
            "confidence": 0.25  # Below 0.3 fallback threshold
        }
        
        with patch.object(Path, 'exists', return_value=True), \
             patch('subprocess.run') as mock_subprocess:
            
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = json.dumps(mock_router_result)
            mock_subprocess.return_value = mock_result
            
            result = self.router.route_request("Completely unclear text")
            
            # Should use fallback routing logic
            self.assertIn(result["route"], ["gen", "act"])
            self.assertGreaterEqual(result["confidence"], 0.5)  # Fallback has default confidence
    
    def test_confidence_threshold_edge_cases(self):
        """Test edge cases at exact threshold boundaries."""
        test_cases = [
            # Exactly at generation threshold - should pass
            {"route": "gen", "confidence": 0.6, "expected_route": "gen"},
            # Just below generation threshold - should abstain
            {"route": "gen", "confidence": 0.599, "expected_route": "abstain"},
            # Exactly at action threshold - should pass 
            {"route": "act", "confidence": 0.75, "expected_route": "act"},
            # Just below action threshold - should abstain
            {"route": "act", "confidence": 0.749, "expected_route": "abstain"},
        ]
        
        for i, case in enumerate(test_cases):
            with self.subTest(case=i):
                mock_router_result = {
                    "route": case["route"],
                    "intent": "test_intent",
                    "confidence": case["confidence"]
                }
                
                with patch.object(Path, 'exists', return_value=True), \
                     patch('subprocess.run') as mock_subprocess:
                    
                    mock_result = MagicMock()
                    mock_result.returncode = 0
                    mock_result.stdout = json.dumps(mock_router_result)
                    mock_subprocess.return_value = mock_result
                    
                    result = self.router.route_request(f"Test case {i}")
                    
                    self.assertEqual(result["route"], case["expected_route"])


class TestFallbackBehavior(unittest.TestCase):
    """Test robust fallback behavior when router is unavailable."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    def test_router_not_found_fallback(self):
        """Test fallback when router file doesn't exist."""
        # Create router with non-existent path
        nonexistent_path = Path("/nonexistent/router.swift")
        router = SmallIntentRouter(router_path=nonexistent_path)
        
        self.assertFalse(router.router_available)
        
        # Test generation fallback
        result = router.route_request("What is the weather?")
        self.assertEqual(result["route"], "gen")
        self.assertGreaterEqual(result["confidence"], 0.5)
        
        # Test action fallback
        result = router.route_request("Close my bot positions")
        self.assertEqual(result["route"], "act")
        self.assertGreaterEqual(result["confidence"], 0.5)
    
    @patch('subprocess.run')
    def test_router_execution_failure_fallback(self, mock_subprocess):
        """Test fallback when router execution fails."""
        # Mock failed execution
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Model not found"
        mock_subprocess.return_value = mock_result
        
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Test message")
        
        self.assertIn(result["route"], ["gen", "act"])
        self.assertGreaterEqual(result["confidence"], 0.5)
    
    @patch('subprocess.run')
    def test_router_timeout_fallback(self, mock_subprocess):
        """Test fallback when router times out."""
        # Mock timeout exception
        mock_subprocess.side_effect = subprocess.TimeoutExpired(
            cmd=["swift", "router.swift", "text"], timeout=5
        )
        
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Test message")
        
        self.assertIn(result["route"], ["gen", "act"])
        self.assertGreaterEqual(result["confidence"], 0.5)
    
    @patch('subprocess.run')
    def test_invalid_json_fallback(self, mock_subprocess):
        """Test fallback when router returns invalid JSON."""
        # Mock invalid JSON response
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "invalid json response"
        mock_subprocess.return_value = mock_result
        
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Test message")
        
        self.assertIn(result["route"], ["gen", "act"])
        self.assertGreaterEqual(result["confidence"], 0.5)
    
    def test_fallback_routing_logic(self):
        """Test the accuracy of fallback routing logic."""
        router = SmallIntentRouter(router_path=Path("/nonexistent"))
        
        # Test action-oriented keywords
        action_texts = [
            "Close my bot positions",
            "Stop all trading",
            "Emergency halt",
            "Execute the strategy",
            "Run the backup",
            "Do something with my bot"
        ]
        
        for text in action_texts:
            result = router.route_request(text)
            self.assertEqual(result["route"], "act", f"Should route '{text}' to act")
            self.assertEqual(result["intent"], "bot_management")
            self.assertGreaterEqual(result["confidence"], 0.5)
        
        # Test generation-oriented texts
        generation_texts = [
            "What is the weather?",
            "Explain machine learning",
            "Tell me about Python",
            "Help me understand this",
            "Random question here"
        ]
        
        for text in generation_texts:
            result = router.route_request(text)
            self.assertEqual(result["route"], "gen", f"Should route '{text}' to gen")
            self.assertEqual(result["intent"], "general_query")
            self.assertGreaterEqual(result["confidence"], 0.5)


class TestRouterQualityIntegration(unittest.TestCase):
    """Integration tests for router quality with the full bridge."""
    
    def setUp(self):
        """Set up integration test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    @patch('subprocess.run')
    def test_abstain_response_structure(self, mock_subprocess):
        """Test that abstain responses have correct structure."""
        # Mock low confidence generation
        mock_router_result = {
            "route": "gen",
            "intent": "general_query",
            "confidence": 0.4  # Below default threshold
        }
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(mock_router_result)
        mock_subprocess.return_value = mock_result
        
        with patch.object(Path, 'exists', return_value=True):
            router = SmallIntentRouter()
            result = router.route_request("Ambiguous text")
        
        # Verify abstain response structure
        self.assertEqual(result["route"], "abstain")
        self.assertIn("abstain_reason", result)
        self.assertIn("suggested_route", result)
        self.assertIn("fallback_available", result)
        self.assertEqual(result["suggested_route"], "gen")
        self.assertTrue(result["fallback_available"])
        self.assertIn("Generation confidence", result["abstain_reason"])
    
    def test_environment_configuration(self):
        """Test that environment variables configure thresholds correctly."""
        test_env = {
            'ROUTER_MIN_CONF_GEN': '0.8',
            'ROUTER_MIN_CONF_ACT': '0.9',
            'ROUTER_FALLBACK_THRESHOLD': '0.5'
        }
        
        with patch.dict(os.environ, test_env):
            router = SmallIntentRouter()
            
            self.assertEqual(router.min_conf_gen, 0.8)
            self.assertEqual(router.min_conf_act, 0.9)
            self.assertEqual(router.fallback_threshold, 0.5)
    
    def test_default_threshold_configuration(self):
        """Test default threshold values."""
        # Clear environment variables that might affect defaults
        env_vars_to_clear = ['ROUTER_MIN_CONF_GEN', 'ROUTER_MIN_CONF_ACT', 'ROUTER_FALLBACK_THRESHOLD']
        
        with patch.dict(os.environ, {var: '' for var in env_vars_to_clear}, clear=False):
            # Remove the vars entirely
            for var in env_vars_to_clear:
                if var in os.environ:
                    del os.environ[var]
            
            router = SmallIntentRouter()
            
            self.assertEqual(router.min_conf_gen, 0.55)  # Default
            self.assertEqual(router.min_conf_act, 0.65)   # Default
            self.assertEqual(router.fallback_threshold, 0.4)  # Default


class TestCalibrationMetrics(unittest.TestCase):
    """Test confidence calibration metrics and Expected Calibration Error."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    def test_ece_calculation_perfect_calibration(self):
        """Test ECE calculation with perfectly calibrated model."""
        # Mock perfectly calibrated predictions
        confidences = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        predictions = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]  # Matches confidence
        labels = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]       # Perfect predictions
        
        ece = self._calculate_ece(confidences, predictions, labels)
        self.assertAlmostEqual(ece, 0.0, places=3)  # Should be near 0 for perfect calibration
    
    def test_ece_calculation_poor_calibration(self):
        """Test ECE calculation with poorly calibrated model."""
        # Mock overconfident predictions
        confidences = [0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9]
        predictions = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]  # All predicted as class 1
        labels = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]       # Only 50% are actually class 1
        
        ece = self._calculate_ece(confidences, predictions, labels)
        self.assertGreater(ece, 0.3)  # Should be high for poor calibration
    
    def test_reliability_bins_structure(self):
        """Test that reliability bins have correct structure."""
        # Test with sample data
        confidences = [0.1, 0.3, 0.5, 0.7, 0.9]
        predictions = [0, 0, 1, 1, 1]
        labels = [0, 1, 0, 1, 1]
        
        bins = self._create_reliability_bins(confidences, predictions, labels)
        
        # Verify bin structure
        for bin_data in bins:
            self.assertIn('bin_lower', bin_data)
            self.assertIn('bin_upper', bin_data)
            self.assertIn('avg_conf', bin_data)
            self.assertIn('emp_acc', bin_data)
            self.assertIn('count', bin_data)
            
            # Verify bounds
            self.assertGreaterEqual(bin_data['bin_lower'], 0.0)
            self.assertLessEqual(bin_data['bin_upper'], 1.0)
            self.assertGreaterEqual(bin_data['avg_conf'], 0.0)
            self.assertLessEqual(bin_data['avg_conf'], 1.0)
            self.assertGreaterEqual(bin_data['emp_acc'], 0.0)
            self.assertLessEqual(bin_data['emp_acc'], 1.0)
    
    def _calculate_ece(self, confidences, predictions, labels, n_bins=10):
        """Calculate Expected Calibration Error - helper method."""
        import numpy as np
        
        confidences = np.array(confidences)
        predictions = np.array(predictions)
        labels = np.array(labels)
        
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]
        
        ece = 0.0
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            prop_in_bin = in_bin.mean()
            
            if prop_in_bin > 0:
                accuracy_in_bin = (predictions[in_bin] == labels[in_bin]).mean()
                avg_confidence_in_bin = confidences[in_bin].mean()
                ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
        
        return ece
    
    def _create_reliability_bins(self, confidences, predictions, labels, n_bins=10):
        """Create reliability bins - helper method."""
        import numpy as np
        
        confidences = np.array(confidences)
        predictions = np.array(predictions)
        labels = np.array(labels)
        
        bins = []
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bin_lowers = bin_boundaries[:-1]
        bin_uppers = bin_boundaries[1:]
        
        for bin_lower, bin_upper in zip(bin_lowers, bin_uppers):
            in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
            
            if in_bin.sum() > 0:
                avg_conf = confidences[in_bin].mean()
                emp_acc = (predictions[in_bin] == labels[in_bin]).mean()
                count = int(in_bin.sum())
            else:
                avg_conf = 0.0
                emp_acc = 0.0
                count = 0
            
            bins.append({
                'bin_lower': float(bin_lower),
                'bin_upper': float(bin_upper),
                'avg_conf': float(avg_conf),
                'emp_acc': float(emp_acc),
                'count': count
            })
        
        return bins


class TestRouterPerformanceMetrics(unittest.TestCase):
    """Test comprehensive router performance metrics."""
    
    def setUp(self):
        """Set up test environment."""
        if not BRIDGE_AVAILABLE:
            self.skipTest("Bridge not available")
    
    def test_precision_recall_calculation(self):
        """Test precision and recall calculation for binary classification."""
        # Mock binary classification results
        y_true = [0, 0, 0, 1, 1, 1, 1, 1]  # 3 gen, 5 act
        y_pred = [0, 0, 1, 1, 1, 1, 0, 1]  # 3 gen, 5 act
        
        # Calculate metrics manually for verification
        tp_gen = sum(1 for true, pred in zip(y_true, y_pred) if true == 0 and pred == 0)  # 2
        fp_gen = sum(1 for true, pred in zip(y_true, y_pred) if true == 1 and pred == 0)  # 1
        fn_gen = sum(1 for true, pred in zip(y_true, y_pred) if true == 0 and pred == 1)  # 1
        
        precision_gen = tp_gen / (tp_gen + fp_gen) if (tp_gen + fp_gen) > 0 else 0
        recall_gen = tp_gen / (tp_gen + fn_gen) if (tp_gen + fn_gen) > 0 else 0
        f1_gen = 2 * (precision_gen * recall_gen) / (precision_gen + recall_gen) if (precision_gen + recall_gen) > 0 else 0
        
        # Verify calculations
        self.assertEqual(tp_gen, 2)
        self.assertEqual(fp_gen, 1) 
        self.assertEqual(fn_gen, 1)
        self.assertAlmostEqual(precision_gen, 2/3, places=3)
        self.assertAlmostEqual(recall_gen, 2/3, places=3)
        self.assertAlmostEqual(f1_gen, 2/3, places=3)
    
    def test_confusion_matrix_calculation(self):
        """Test confusion matrix calculation."""
        y_true = ['gen', 'gen', 'act', 'act', 'gen', 'act']
        y_pred = ['gen', 'act', 'act', 'act', 'gen', 'gen']
        
        # Manual confusion matrix calculation
        labels = ['gen', 'act']
        matrix = [[0, 0], [0, 0]]  # [[gen-gen, gen-act], [act-gen, act-act]]
        
        label_to_idx = {label: i for i, label in enumerate(labels)}
        
        for true, pred in zip(y_true, y_pred):
            true_idx = label_to_idx[true]
            pred_idx = label_to_idx[pred]
            matrix[true_idx][pred_idx] += 1
        
        # Expected: [[2, 1], [1, 2]]
        # gen correctly predicted as gen: 2
        # gen incorrectly predicted as act: 1  
        # act incorrectly predicted as gen: 1
        # act correctly predicted as act: 2
        
        expected_matrix = [[2, 1], [1, 2]]
        self.assertEqual(matrix, expected_matrix)
    
    def test_auc_calculation_properties(self):
        """Test properties of AUC calculation."""
        # Perfect classifier should have AUC = 1.0
        y_true_perfect = [0, 0, 0, 1, 1, 1]
        confidences_perfect = [0.1, 0.2, 0.3, 0.8, 0.9, 0.95]
        
        auc_perfect = self._calculate_simple_auc(y_true_perfect, confidences_perfect)
        self.assertAlmostEqual(auc_perfect, 1.0, places=2)
        
        # Random classifier should have AUC ≈ 0.5
        y_true_random = [0, 1, 0, 1, 0, 1]
        confidences_random = [0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
        
        auc_random = self._calculate_simple_auc(y_true_random, confidences_random)
        self.assertAlmostEqual(auc_random, 0.5, places=1)
    
    def _calculate_simple_auc(self, y_true, confidences):
        """Simple AUC calculation for testing."""
        import numpy as np
        
        y_true = np.array(y_true)
        confidences = np.array(confidences)
        
        # Sort by confidence descending
        sorted_indices = np.argsort(-confidences)
        y_sorted = y_true[sorted_indices]
        
        # Calculate AUC using trapezoidal rule approximation
        n_pos = np.sum(y_true == 1)
        n_neg = np.sum(y_true == 0)
        
        if n_pos == 0 or n_neg == 0:
            return 0.5
        
        tp = fp = 0
        auc = 0.0
        
        for label in y_sorted:
            if label == 1:
                tp += 1
            else:
                fp += 1
                auc += tp  # Add current TP count
        
        return auc / (n_pos * n_neg)


if __name__ == "__main__":
    # Run tests with verbose output
    unittest.main(verbosity=2)