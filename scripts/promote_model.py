#!/usr/bin/env python3
"""
TinyIntent Model Promotion Script - M5.4: Evaluation & Promotion Workflow

Promotes trained router models to active use based on evaluation criteria.
Only models meeting safety thresholds (accuracy ≥90%, latency ≤50ms) are promoted.
"""

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ModelPromoter:
    """Handles safe promotion of evaluated router models"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.router_dir = project_root / "router"
        self.data_dir = self.router_dir / "data"
        self.scripts_dir = project_root / "scripts"
        
        # Bridge logs directory for audit trail
        self.bridge_logs_dir = project_root / "bridge" / "logs"
        self.bridge_logs_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log = self.bridge_logs_dir / "audit.log"
        
        # Model paths
        self.eval_results_path = self.data_dir / "eval_results.json"
        self.trained_model_path = self.router_dir / "SmallIntent.mlpackage"
        self.active_model_path = self.router_dir / "TinyIntent.mlpackage"
        
        # Promotion criteria (matching eval_router.swift)
        self.accuracy_threshold = 90.0
        self.latency_threshold = 50.0
    
    def load_evaluation_results(self) -> Dict[str, Any]:
        """Load latest evaluation results from JSON file"""
        if not self.eval_results_path.exists():
            raise FileNotFoundError(
                f"Evaluation results not found at {self.eval_results_path}. "
                "Run 'make router-eval' first."
            )
        
        try:
            with open(self.eval_results_path, 'r') as f:
                results = json.load(f)
            
            logger.info(f"Loaded evaluation results from {self.eval_results_path}")
            return results
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in evaluation results: {e}")
    
    def validate_evaluation_results(self, results: Dict[str, Any]) -> None:
        """Validate that evaluation results contain required fields"""
        required_fields = [
            'accuracy', 'latency_ms', 'sample_count', 'timestamp', 
            'promotion_eligible', 'accuracy_threshold', 'latency_threshold'
        ]
        
        missing_fields = [field for field in required_fields if field not in results]
        if missing_fields:
            raise ValueError(f"Missing required fields in evaluation results: {missing_fields}")
        
        # Validate data types
        if not isinstance(results['accuracy'], (int, float)):
            raise ValueError("accuracy must be a number")
        if not isinstance(results['latency_ms'], (int, float)):
            raise ValueError("latency_ms must be a number")
        if not isinstance(results['promotion_eligible'], bool):
            raise ValueError("promotion_eligible must be a boolean")
    
    def check_promotion_eligibility(self, results: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if model meets promotion criteria
        
        Returns:
            (eligible, reason): Tuple of eligibility and reason string
        """
        accuracy = results['accuracy']
        latency_ms = results['latency_ms']
        
        # Use thresholds from evaluation results for consistency
        accuracy_threshold = results.get('accuracy_threshold', self.accuracy_threshold)
        latency_threshold = results.get('latency_threshold', self.latency_threshold)
        
        reasons = []
        
        if accuracy < accuracy_threshold:
            reasons.append(f"Accuracy too low: {accuracy:.2f}% < {accuracy_threshold}%")
        
        if latency_ms > latency_threshold:
            reasons.append(f"Latency too high: {latency_ms:.2f}ms > {latency_threshold}ms")
        
        if reasons:
            return False, "; ".join(reasons)
        
        return True, f"Model meets criteria: accuracy={accuracy:.2f}%, latency={latency_ms:.2f}ms"
    
    def backup_current_model(self) -> bool:
        """Backup current active model if it exists"""
        if not self.active_model_path.exists():
            logger.info("No current active model to backup")
            return True
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.router_dir / f"TinyIntent_backup_{timestamp}.mlpackage"
        
        try:
            if self.active_model_path.is_dir():
                shutil.copytree(self.active_model_path, backup_path)
            else:
                shutil.copy2(self.active_model_path, backup_path)
            logger.info(f"Backed up current model to {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to backup current model: {e}")
            return False
    
    def promote_model(self, results: Dict[str, Any]) -> bool:
        """
        Promote the trained model to active use
        
        Args:
            results: Evaluation results dictionary
            
        Returns:
            bool: Success status
        """
        if not self.trained_model_path.exists():
            logger.error(f"Trained model not found at {self.trained_model_path}")
            return False
        
        # Backup current model
        if not self.backup_current_model():
            logger.error("Failed to backup current model, aborting promotion")
            return False
        
        try:
            # Remove existing active model if it exists
            if self.active_model_path.exists():
                if self.active_model_path.is_dir():
                    shutil.rmtree(self.active_model_path)
                else:
                    self.active_model_path.unlink()
            
            # Copy trained model to active location
            if self.trained_model_path.is_dir():
                shutil.copytree(self.trained_model_path, self.active_model_path)
            else:
                shutil.copy2(self.trained_model_path, self.active_model_path)
            
            logger.info(f"✅ Model promoted successfully!")
            logger.info(f"   Source: {self.trained_model_path}")
            logger.info(f"   Target: {self.active_model_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to promote model: {e}")
            return False
    
    def log_promotion_decision(self, results: Dict[str, Any], promoted: bool, reason: str) -> None:
        """Log promotion decision to audit trail"""
        timestamp = datetime.now().isoformat()
        
        audit_entry = {
            "timestamp": timestamp,
            "action": "model_promotion",
            "promoted": promoted,
            "reason": reason,
            "evaluation_results": {
                "accuracy": results['accuracy'],
                "latency_ms": results['latency_ms'],
                "sample_count": results['sample_count'],
                "evaluation_timestamp": results['timestamp']
            },
            "model_paths": {
                "trained_model": str(self.trained_model_path),
                "active_model": str(self.active_model_path)
            }
        }
        
        try:
            # Append to audit log
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
            
            logger.info(f"Audit entry logged to {self.audit_log}")
            
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def run_promotion(self) -> int:
        """
        Main promotion workflow
        
        Returns:
            int: Exit code (0 = success, 1 = failure)
        """
        try:
            logger.info("🎯 TinyIntent Model Promotion")
            logger.info("============================")
            
            # Load and validate evaluation results
            results = self.load_evaluation_results()
            self.validate_evaluation_results(results)
            
            # Display evaluation summary
            logger.info(f"📊 Evaluation Summary:")
            logger.info(f"   Accuracy: {results['accuracy']:.2f}% (threshold: {results.get('accuracy_threshold', self.accuracy_threshold)}%)")
            logger.info(f"   Latency: {results['latency_ms']:.2f}ms (threshold: {results.get('latency_threshold', self.latency_threshold)}ms)")
            logger.info(f"   Sample Count: {results['sample_count']}")
            logger.info(f"   Evaluation Time: {results['timestamp']}")
            
            # Check eligibility
            eligible, reason = self.check_promotion_eligibility(results)
            
            if eligible:
                logger.info(f"\n✅ Model eligible for promotion: {reason}")
                
                # Perform promotion
                if self.promote_model(results):
                    self.log_promotion_decision(results, True, reason)
                    logger.info("\n🎉 Model promotion completed successfully!")
                    return 0
                else:
                    self.log_promotion_decision(results, False, "Promotion failed during copy operation")
                    logger.error("\n❌ Model promotion failed")
                    return 1
            else:
                logger.warning(f"\n❌ Model not eligible for promotion: {reason}")
                logger.info("   Keeping current active model in place")
                
                self.log_promotion_decision(results, False, reason)
                return 1
                
        except Exception as e:
            logger.error(f"Promotion workflow failed: {e}")
            return 1

def main():
    """Main entry point"""
    # Determine project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    # Create promoter and run
    promoter = ModelPromoter(project_root)
    exit_code = promoter.run_promotion()
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()