#!/usr/bin/env python3
"""
TinyIntent Autopilot - M5.5: Continuous Learning Orchestration

Automates the full retrain → eval → promote cycle for continuous improvement.
Executes: export episodes → retrain → eval → promote with comprehensive logging.
"""

import argparse
import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AutopilotOrchestrator:
    """Orchestrates the continuous learning pipeline"""
    
    def __init__(self, project_root: Path, dry_run: bool = False):
        self.project_root = project_root
        self.dry_run = dry_run
        
        # Bridge logs directory for audit trail
        self.bridge_logs_dir = project_root / "bridge" / "logs"
        self.bridge_logs_dir.mkdir(parents=True, exist_ok=True)
        self.audit_log = self.bridge_logs_dir / "audit.log"
        
        # Key paths
        self.scripts_dir = project_root / "scripts"
        self.router_dir = project_root / "router"
        self.data_dir = self.router_dir / "data"
        
        # Step configuration
        self.steps = [
            ("export_episodes", "Export episodes to training data"),
            ("retrain_router", "Retrain router model"),
            ("evaluate_model", "Evaluate trained model"),
            ("promote_model", "Promote model if criteria met")
        ]
    
    def log_autopilot_event(self, step: str, success: bool, details: Dict[str, Any], 
                           duration_seconds: float = 0.0, error: Optional[str] = None) -> None:
        """Log autopilot step to audit trail"""
        timestamp = datetime.now().isoformat()
        
        audit_entry = {
            "timestamp": timestamp,
            "action": "autopilot_step",
            "step": step,
            "success": success,
            "dry_run": self.dry_run,
            "duration_seconds": round(duration_seconds, 2),
            "details": details,
            "error": error
        }
        
        try:
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(audit_entry) + '\n')
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")
    
    def run_make_target(self, target: str) -> Tuple[bool, str, float]:
        """
        Run a make target and return success status, output, and duration
        
        Returns:
            (success, output, duration_seconds)
        """
        start_time = time.time()
        
        try:
            result = subprocess.run(
                ['make', target],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            duration = time.time() - start_time
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            
            return success, output, duration
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return False, f"Command timed out after {duration:.1f} seconds", duration
        except Exception as e:
            duration = time.time() - start_time
            return False, f"Command failed: {e}", duration
    
    def run_python_script(self, script_name: str, args: list = None) -> Tuple[bool, str, float]:
        """
        Run a Python script and return success status, output, and duration
        
        Returns:
            (success, output, duration_seconds)
        """
        start_time = time.time()
        script_path = self.scripts_dir / script_name
        
        if not script_path.exists():
            duration = time.time() - start_time
            return False, f"Script not found: {script_path}", duration
        
        cmd = ['python3', str(script_path)]
        if args:
            cmd.extend(args)
        
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            duration = time.time() - start_time
            success = result.returncode == 0
            output = result.stdout if success else result.stderr
            
            return success, output, duration
            
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return False, f"Script timed out after {duration:.1f} seconds", duration
        except Exception as e:
            duration = time.time() - start_time
            return False, f"Script failed: {e}", duration
    
    def step_export_episodes(self) -> Tuple[bool, Dict[str, Any]]:
        """Step 1: Export episodes to training data"""
        logger.info("🔄 Step 1: Exporting episodes to training data...")
        
        success, output, duration = self.run_make_target("export-episodes")
        
        details = {
            "make_target": "export-episodes",
            "output_lines": len(output.split('\n')) if output else 0,
            "output_preview": output[:200] + "..." if len(output) > 200 else output
        }
        
        if success:
            logger.info(f"✅ Episodes exported successfully ({duration:.1f}s)")
        else:
            logger.error(f"❌ Episode export failed ({duration:.1f}s): {output}")
        
        return success, details
    
    def step_retrain_router(self) -> Tuple[bool, Dict[str, Any]]:
        """Step 2: Retrain the router model"""
        logger.info("🧠 Step 2: Retraining router model...")
        
        success, output, duration = self.run_make_target("router-train")
        
        details = {
            "make_target": "router-train",
            "output_lines": len(output.split('\n')) if output else 0,
            "training_completed": "training complete" in output.lower() if output else False
        }
        
        if success:
            logger.info(f"✅ Router retrained successfully ({duration:.1f}s)")
        else:
            logger.error(f"❌ Router retraining failed ({duration:.1f}s): {output}")
        
        return success, details
    
    def step_evaluate_model(self) -> Tuple[bool, Dict[str, Any]]:
        """Step 3: Evaluate the trained model"""
        logger.info("📊 Step 3: Evaluating trained model...")
        
        success, output, duration = self.run_make_target("router-eval")
        
        details = {
            "make_target": "router-eval",
            "output_lines": len(output.split('\n')) if output else 0,
            "evaluation_completed": "evaluation completed" in output.lower() if output else False
        }
        
        # Try to extract evaluation results
        eval_results_path = self.data_dir / "eval_results.json"
        if eval_results_path.exists():
            try:
                with open(eval_results_path, 'r') as f:
                    eval_data = json.load(f)
                details["evaluation_results"] = {
                    "accuracy": eval_data.get("accuracy"),
                    "latency_ms": eval_data.get("latency_ms"),
                    "promotion_eligible": eval_data.get("promotion_eligible")
                }
            except Exception as e:
                details["evaluation_results_error"] = str(e)
        
        if success:
            logger.info(f"✅ Model evaluated successfully ({duration:.1f}s)")
        else:
            logger.error(f"❌ Model evaluation failed ({duration:.1f}s): {output}")
        
        return success, details
    
    def step_promote_model(self) -> Tuple[bool, Dict[str, Any]]:
        """Step 4: Promote model if criteria are met"""
        if self.dry_run:
            logger.info("🔍 Step 4: Promoting model (DRY RUN - skipped)")
            return True, {"dry_run": True, "action": "skipped"}
        
        logger.info("🚀 Step 4: Promoting model if criteria met...")
        
        success, output, duration = self.run_make_target("promote")
        
        details = {
            "make_target": "promote",
            "output_lines": len(output.split('\n')) if output else 0,
            "promotion_attempted": True
        }
        
        # Check if promotion was successful or rejected
        if output:
            if "promotion completed successfully" in output.lower():
                details["promotion_result"] = "promoted"
            elif "not eligible for promotion" in output.lower():
                details["promotion_result"] = "rejected_criteria"
                # This is actually success for the step - rejection is expected behavior
                success = True
            else:
                details["promotion_result"] = "failed"
        
        if success:
            result = details.get("promotion_result", "unknown")
            logger.info(f"✅ Promotion step completed ({duration:.1f}s): {result}")
        else:
            logger.error(f"❌ Promotion step failed ({duration:.1f}s): {output}")
        
        return success, details
    
    def run_autopilot_cycle(self) -> bool:
        """
        Run a complete autopilot cycle
        
        Returns:
            bool: True if all steps succeeded, False otherwise
        """
        cycle_start_time = time.time()
        
        logger.info("🎯 TinyIntent Autopilot - Continuous Learning Cycle")
        logger.info("=" * 55)
        
        if self.dry_run:
            logger.info("🔍 DRY RUN MODE: Promotion will be skipped")
            logger.info("")
        
        # Log cycle start
        self.log_autopilot_event(
            "cycle_start", 
            True, 
            {"dry_run": self.dry_run, "steps_planned": len(self.steps)}
        )
        
        all_success = True
        step_results = []
        
        # Execute each step
        step_methods = {
            "export_episodes": self.step_export_episodes,
            "retrain_router": self.step_retrain_router,
            "evaluate_model": self.step_evaluate_model,
            "promote_model": self.step_promote_model
        }
        
        for step_name, step_description in self.steps:
            step_start_time = time.time()
            
            try:
                step_method = step_methods[step_name]
                step_success, step_details = step_method()
                step_duration = time.time() - step_start_time
                
                step_results.append({
                    "step": step_name,
                    "success": step_success,
                    "duration": step_duration,
                    "details": step_details
                })
                
                # Log step completion
                self.log_autopilot_event(
                    step_name,
                    step_success,
                    step_details,
                    step_duration,
                    error=None if step_success else "Step failed"
                )
                
                if not step_success:
                    all_success = False
                    logger.error(f"❌ Step failed: {step_description}")
                    break  # Stop on first failure
                    
            except Exception as e:
                step_duration = time.time() - step_start_time
                error_msg = str(e)
                
                logger.error(f"❌ Step error: {step_description} - {error_msg}")
                
                self.log_autopilot_event(
                    step_name,
                    False,
                    {"error_type": type(e).__name__},
                    step_duration,
                    error=error_msg
                )
                
                all_success = False
                break
        
        # Calculate total duration
        total_duration = time.time() - cycle_start_time
        
        # Log cycle completion
        cycle_details = {
            "total_steps": len(self.steps),
            "completed_steps": len(step_results),
            "all_steps_successful": all_success,
            "step_results": step_results
        }
        
        self.log_autopilot_event(
            "cycle_complete",
            all_success,
            cycle_details,
            total_duration
        )
        
        # Summary
        logger.info("")
        logger.info("📈 Autopilot Cycle Summary")
        logger.info("-" * 25)
        logger.info(f"Total Duration: {total_duration:.1f}s")
        logger.info(f"Steps Completed: {len(step_results)}/{len(self.steps)}")
        logger.info(f"Overall Success: {'✅ YES' if all_success else '❌ NO'}")
        
        if step_results:
            logger.info("\nStep Results:")
            for result in step_results:
                status = "✅" if result["success"] else "❌"
                logger.info(f"  {status} {result['step']}: {result['duration']:.1f}s")
        
        return all_success

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="TinyIntent Autopilot - Continuous Learning Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 autopilot.py                    # Run full autopilot cycle
  python3 autopilot.py --dry-run          # Run without promotion
  
Steps executed:
  1. Export episodes to training data
  2. Retrain router model  
  3. Evaluate trained model
  4. Promote model if criteria met (accuracy ≥90%, latency ≤50ms)
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Run without actually promoting the model (useful for testing)'
    )
    
    parser.add_argument(
        '--project-root',
        type=Path,
        help='Project root directory (auto-detected if not specified)'
    )
    
    args = parser.parse_args()
    
    # Determine project root
    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        script_path = Path(__file__).resolve()
        project_root = script_path.parent.parent
    
    if not project_root.exists():
        logger.error(f"Project root not found: {project_root}")
        sys.exit(1)
    
    # Validate project structure
    required_dirs = ["bridge", "router", "scripts"]
    missing_dirs = [d for d in required_dirs if not (project_root / d).exists()]
    if missing_dirs:
        logger.error(f"Missing required directories: {missing_dirs}")
        logger.error(f"Project root: {project_root}")
        sys.exit(1)
    
    # Create orchestrator and run
    orchestrator = AutopilotOrchestrator(project_root, dry_run=args.dry_run)
    
    try:
        success = orchestrator.run_autopilot_cycle()
        exit_code = 0 if success else 1
        
        if args.dry_run:
            logger.info("\n🔍 DRY RUN completed - no models were promoted")
        
        sys.exit(exit_code)
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Autopilot interrupted by user")
        orchestrator.log_autopilot_event(
            "cycle_interrupted",
            False,
            {"reason": "user_interrupt"},
            error="KeyboardInterrupt"
        )
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Autopilot failed with unexpected error: {e}")
        orchestrator.log_autopilot_event(
            "cycle_error",
            False,
            {"error_type": type(e).__name__},
            error=str(e)
        )
        sys.exit(1)

if __name__ == "__main__":
    main()