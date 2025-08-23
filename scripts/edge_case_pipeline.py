#!/usr/bin/env python3
"""
TinyIntent Edge Case Improvement Pipeline

Automated pipeline for systematic router improvement using edge case analysis.
Integrates edge case collection, analysis, training data augmentation, and retraining.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bridge.edge_case_logger import edge_case_logger
from scripts.analyze_edge_cases import EdgeCaseAnalyzer


class EdgeCasePipeline:
    """Automated pipeline for edge case driven router improvement."""
    
    def __init__(self, project_root: Path):
        """Initialize pipeline with project paths."""
        self.project_root = project_root
        self.router_dir = project_root / "router"
        self.data_dir = self.router_dir / "data"
        self.scripts_dir = project_root / "scripts"
        
        # Initialize analyzer
        self.analyzer = EdgeCaseAnalyzer()
        
        # Pipeline configuration
        self.config = {
            "min_edge_cases": 20,  # Minimum edge cases to trigger retraining
            "analysis_window_hours": 168,  # 7 days
            "min_pattern_samples": 3,
            "max_training_candidates": 100,
            "preserve_balance": True,  # Maintain 50/50 gen/act balance
            "backup_original": True
        }
    
    def run_pipeline(self, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        Run the complete edge case improvement pipeline.
        
        Args:
            force: Force retraining even if threshold not met
            dry_run: Analyze only, don't modify training data or retrain
            
        Returns:
            Pipeline execution results
        """
        print("🚀 TinyIntent Edge Case Improvement Pipeline")
        print("=" * 60)
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "pipeline_version": "1.0",
            "dry_run": dry_run,
            "steps": {}
        }
        
        try:
            # Step 1: Analyze edge cases
            print("📊 Step 1: Analyzing edge cases...")
            analysis_results = self._analyze_edge_cases()
            results["steps"]["analysis"] = analysis_results
            
            if not analysis_results["success"]:
                print("❌ Edge case analysis failed")
                return results
            
            # Step 2: Check if retraining is needed
            print("🔍 Step 2: Checking retraining criteria...")
            retrain_decision = self._should_retrain(analysis_results, force)
            results["steps"]["retrain_decision"] = retrain_decision
            
            if not retrain_decision["should_retrain"]:
                print(f"ℹ️  Retraining not needed: {retrain_decision['reason']}")
                return results
            
            print(f"✅ Retraining criteria met: {retrain_decision['reason']}")
            
            if dry_run:
                print("🔍 Dry run mode: stopping before data modification")
                return results
            
            # Step 3: Generate training data candidates
            print("📝 Step 3: Generating training data...")
            training_data_results = self._generate_training_data(analysis_results)
            results["steps"]["training_data"] = training_data_results
            
            if not training_data_results["success"]:
                print("❌ Training data generation failed")
                return results
            
            # Step 4: Update training dataset
            print("💾 Step 4: Updating training dataset...")
            dataset_update_results = self._update_training_dataset(training_data_results)
            results["steps"]["dataset_update"] = dataset_update_results
            
            if not dataset_update_results["success"]:
                print("❌ Dataset update failed")
                return results
            
            # Step 5: Retrain router
            print("🏋️  Step 5: Retraining router...")
            retrain_results = self._retrain_router()
            results["steps"]["retrain"] = retrain_results
            
            if not retrain_results["success"]:
                print("❌ Router retraining failed")
                return results
            
            # Step 6: Validate improvement
            print("🧪 Step 6: Validating improvement...")
            validation_results = self._validate_improvement()
            results["steps"]["validation"] = validation_results
            
            results["success"] = True
            results["summary"] = self._generate_summary(results)
            
            print("✅ Pipeline completed successfully!")
            
        except Exception as e:
            print(f"💥 Pipeline failed with error: {e}")
            results["success"] = False
            results["error"] = str(e)
        
        return results
    
    def _analyze_edge_cases(self) -> Dict[str, Any]:
        """Analyze edge cases to identify improvement opportunities."""
        try:
            # Get edge case statistics
            stats = edge_case_logger.get_edge_case_stats(self.config["analysis_window_hours"])
            
            if stats.get("error"):
                return {"success": False, "error": stats["error"]}
            
            # Run pattern analysis
            analysis = self.analyzer.analyze_patterns(
                hours=self.config["analysis_window_hours"],
                min_samples=self.config["min_pattern_samples"]
            )
            
            if "error" in analysis:
                return {"success": False, "error": analysis["error"]}
            
            return {
                "success": True,
                "stats": stats,
                "analysis": analysis,
                "edge_case_count": stats["edge_case_count"],
                "patterns_found": len(analysis["patterns"]),
                "training_candidates": len(analysis["training_candidates"])
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _should_retrain(self, analysis_results: Dict[str, Any], force: bool = False) -> Dict[str, Any]:
        """Determine if retraining should be triggered."""
        if force:
            return {"should_retrain": True, "reason": "forced by user"}
        
        edge_case_count = analysis_results.get("edge_case_count", 0)
        training_candidates = analysis_results.get("training_candidates", 0)
        
        # Check edge case threshold
        if edge_case_count >= self.config["min_edge_cases"]:
            return {
                "should_retrain": True,
                "reason": f"{edge_case_count} edge cases >= threshold {self.config['min_edge_cases']}"
            }
        
        # Check training candidates availability
        if training_candidates >= 10:
            return {
                "should_retrain": True,
                "reason": f"{training_candidates} training candidates available"
            }
        
        # Check edge case rate
        stats = analysis_results.get("stats", {})
        edge_case_rate = stats.get("edge_case_rate", 0)
        if edge_case_rate > 0.15:  # >15% edge case rate
            return {
                "should_retrain": True,
                "reason": f"high edge case rate {edge_case_rate:.2%}"
            }
        
        return {
            "should_retrain": False,
            "reason": f"insufficient edge cases ({edge_case_count} < {self.config['min_edge_cases']})"
        }
    
    def _generate_training_data(self, analysis_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate training data from edge case analysis."""
        try:
            analysis = analysis_results["analysis"]
            candidates = analysis["training_candidates"]
            
            if not candidates:
                return {"success": False, "error": "no training candidates available"}
            
            # Limit candidates to avoid overwhelming the training set
            if len(candidates) > self.config["max_training_candidates"]:
                # Sort by pattern severity and take top candidates
                candidates = sorted(
                    candidates, 
                    key=lambda x: x.get("pattern_severity", 0), 
                    reverse=True
                )[:self.config["max_training_candidates"]]
            
            # Export to temporary TSV file
            temp_candidates_path = self.data_dir / "edge_case_candidates.tsv"
            self.analyzer.export_training_candidates(temp_candidates_path, candidates)
            
            return {
                "success": True,
                "candidates_file": str(temp_candidates_path),
                "candidate_count": len(candidates),
                "top_patterns": [
                    pattern["representative_text"][:50] + "..."
                    for pattern in analysis["patterns"][:5]
                ]
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _update_training_dataset(self, training_data_results: Dict[str, Any]) -> Dict[str, Any]:
        """Update the training dataset with new edge case examples."""
        try:
            # Backup original dataset
            original_dataset = self.data_dir / "intents.tsv"
            if not original_dataset.exists():
                return {"success": False, "error": "original training dataset not found"}
            
            backup_path = self.data_dir / f"intents_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.tsv"
            if self.config["backup_original"]:
                shutil.copy2(original_dataset, backup_path)
                print(f"   Backed up original dataset to {backup_path.name}")
            
            # Load existing dataset
            import pandas as pd
            
            existing_df = pd.read_csv(original_dataset, sep='\\t')
            original_count = len(existing_df)
            
            # Load edge case candidates
            candidates_file = Path(training_data_results["candidates_file"])
            candidates_df = pd.read_csv(candidates_file, sep='\\t')
            
            # Add new examples to dataset
            new_examples = []
            for _, row in candidates_df.iterrows():
                new_examples.append({
                    'text': row['text'],
                    'label': row['label']  # Use suggested correct label
                })
            
            # Convert to DataFrame
            new_df = pd.DataFrame(new_examples)
            
            # Combine datasets
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            
            # Remove duplicates based on text
            combined_df = combined_df.drop_duplicates(subset=['text'], keep='first')
            
            # Balance dataset if requested
            if self.config["preserve_balance"]:
                gen_count = len(combined_df[combined_df['label'] == 'gen'])
                act_count = len(combined_df[combined_df['label'] == 'act'])
                
                print(f"   Dataset balance: gen={gen_count}, act={act_count}")
                
                # If severely imbalanced, warn but don't auto-correct
                if abs(gen_count - act_count) > max(gen_count, act_count) * 0.2:
                    print(f"   ⚠️  Dataset imbalance detected: {abs(gen_count - act_count)} difference")
            
            # Save updated dataset
            combined_df.to_csv(original_dataset, sep='\\t', index=False)
            
            # Clean up temporary file
            candidates_file.unlink()
            
            return {
                "success": True,
                "backup_file": str(backup_path) if self.config["backup_original"] else None,
                "original_count": original_count,
                "new_examples": len(new_examples),
                "final_count": len(combined_df),
                "duplicates_removed": original_count + len(new_examples) - len(combined_df)
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _retrain_router(self) -> Dict[str, Any]:
        """Retrain the router with updated dataset."""
        try:
            print("   🔄 Starting router retraining...")
            
            # Use the existing training script
            train_script = self.router_dir / "train_router.swift"
            
            if train_script.exists():
                # Run Swift training
                result = subprocess.run(
                    ["swift", str(train_script)],
                    capture_output=True,
                    text=True,
                    cwd=self.router_dir,
                    timeout=1800  # 30 minute timeout
                )
                
                if result.returncode == 0:
                    return {
                        "success": True,
                        "method": "swift_training",
                        "output": result.stdout[-500:] if result.stdout else "",  # Last 500 chars
                        "duration_info": "completed successfully"
                    }
                else:
                    return {
                        "success": False,
                        "method": "swift_training",
                        "error": result.stderr or "Swift training failed"
                    }
            else:
                # Try Python training as fallback
                python_train_script = self.router_dir / "train" / "train.py"
                
                if python_train_script.exists():
                    result = subprocess.run(
                        [sys.executable, str(python_train_script)],
                        capture_output=True,
                        text=True,
                        cwd=self.router_dir / "train",
                        timeout=3600  # 1 hour timeout
                    )
                    
                    if result.returncode == 0:
                        return {
                            "success": True,
                            "method": "python_training",
                            "output": result.stdout[-500:] if result.stdout else "",
                            "duration_info": "completed successfully"
                        }
                    else:
                        return {
                            "success": False,
                            "method": "python_training", 
                            "error": result.stderr or "Python training failed"
                        }
                else:
                    return {
                        "success": False,
                        "error": "no training script found (train_router.swift or train/train.py)"
                    }
                    
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "training timeout exceeded"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _validate_improvement(self) -> Dict[str, Any]:
        """Validate that retraining improved router performance."""
        try:
            print("   🧪 Running validation...")
            
            # Run router evaluation
            eval_script = self.router_dir / "eval_router.py"
            
            if eval_script.exists():
                result = subprocess.run(
                    [sys.executable, str(eval_script)],
                    capture_output=True,
                    text=True,
                    cwd=self.router_dir,
                    timeout=600  # 10 minute timeout
                )
                
                if result.returncode == 0:
                    # Try to load evaluation results
                    eval_results_path = self.data_dir / "eval_results.json"
                    
                    if eval_results_path.exists():
                        with open(eval_results_path, 'r') as f:
                            eval_data = json.load(f)
                        
                        performance_data = eval_data.get("performance", {})
                        edge_case_data = eval_data.get("edge_case_evaluation", {})
                        
                        return {
                            "success": True,
                            "overall_accuracy": performance_data.get("accuracy", 0.0),
                            "edge_case_accuracy": edge_case_data.get("overall_accuracy", 0.0),
                            "promotion_eligible": eval_data.get("promotion", {}).get("promotion_eligible", False),
                            "eval_output": result.stdout[-300:] if result.stdout else ""
                        }
                    else:
                        return {
                            "success": True,
                            "note": "evaluation completed but results file not found",
                            "eval_output": result.stdout[-300:] if result.stdout else ""
                        }
                else:
                    return {
                        "success": False,
                        "error": f"evaluation failed: {result.stderr or 'unknown error'}"
                    }
            else:
                return {
                    "success": False,
                    "error": "evaluation script not found"
                }
                
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "evaluation timeout exceeded"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _generate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a summary of pipeline execution."""
        steps = results.get("steps", {})
        
        summary = {
            "pipeline_success": results.get("success", False),
            "steps_completed": len([s for s in steps.values() if s.get("success", False)]),
            "total_steps": len(steps)
        }
        
        # Analysis summary
        if "analysis" in steps:
            analysis = steps["analysis"]
            summary["edge_cases_analyzed"] = analysis.get("edge_case_count", 0)
            summary["patterns_identified"] = analysis.get("patterns_found", 0)
            summary["training_candidates_generated"] = analysis.get("training_candidates", 0)
        
        # Training data summary
        if "dataset_update" in steps:
            dataset = steps["dataset_update"]
            summary["new_training_examples"] = dataset.get("new_examples", 0)
            summary["dataset_final_size"] = dataset.get("final_count", 0)
        
        # Validation summary
        if "validation" in steps:
            validation = steps["validation"]
            summary["final_accuracy"] = validation.get("overall_accuracy", 0.0)
            summary["edge_case_accuracy"] = validation.get("edge_case_accuracy", 0.0)
            summary["promotion_eligible"] = validation.get("promotion_eligible", False)
        
        return summary


def main():
    """Main pipeline function."""
    parser = argparse.ArgumentParser(description="TinyIntent Edge Case Improvement Pipeline")
    parser.add_argument("--force", action="store_true", help="Force retraining even if criteria not met")
    parser.add_argument("--dry-run", action="store_true", help="Analyze only, don't modify data or retrain")
    parser.add_argument("--output", type=str, help="Save results to JSON file")
    parser.add_argument("--min-edge-cases", type=int, default=20, help="Minimum edge cases to trigger retraining")
    
    args = parser.parse_args()
    
    # Initialize pipeline
    pipeline = EdgeCasePipeline(project_root)
    
    # Update configuration
    if args.min_edge_cases:
        pipeline.config["min_edge_cases"] = args.min_edge_cases
    
    # Run pipeline
    results = pipeline.run_pipeline(force=args.force, dry_run=args.dry_run)
    
    # Save results if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"📄 Pipeline results saved to {output_path}")
    
    # Print summary
    if results.get("success"):
        summary = results.get("summary", {})
        print("\\n📋 Pipeline Summary:")
        print(f"   ✅ Steps completed: {summary.get('steps_completed', 0)}/{summary.get('total_steps', 0)}")
        
        if summary.get("edge_cases_analyzed"):
            print(f"   📊 Edge cases analyzed: {summary['edge_cases_analyzed']}")
        
        if summary.get("new_training_examples"):
            print(f"   📝 New training examples: {summary['new_training_examples']}")
            print(f"   💾 Final dataset size: {summary.get('dataset_final_size', 0)}")
        
        if summary.get("final_accuracy"):
            print(f"   🎯 Final accuracy: {summary['final_accuracy']:.4f}")
            
        if summary.get("edge_case_accuracy"):
            print(f"   🔍 Edge case accuracy: {summary['edge_case_accuracy']:.4f}")
        
        print("\\n🎉 Pipeline completed successfully!")
        return 0
    else:
        error = results.get("error", "unknown error")
        print(f"\\n❌ Pipeline failed: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())