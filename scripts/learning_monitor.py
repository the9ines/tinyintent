#!/usr/bin/env python3
"""
TinyIntent Learning System Monitor - M5.5: Monitoring & Verification

Provides monitoring and verification of the continuous learning system.
Shows learning activity, model performance trends, and system health.
"""

import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
import sys


class LearningMonitor:
    """Monitors TinyIntent learning system activity and health"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.data_dir = project_root / "data" / "episodes"
        self.router_dir = project_root / "router"
        self.bridge_logs_dir = project_root / "bridge" / "logs"
        
        # Database files
        self.router_db = self.data_dir / "router_decisions.db"
        
        # Log files
        self.audit_log = self.bridge_logs_dir / "audit.log"
        self.autopilot_out_log = self.bridge_logs_dir / "autopilot.out.log"
        self.autopilot_err_log = self.bridge_logs_dir / "autopilot.err.log"
    
    def get_episode_stats(self) -> Dict[str, Any]:
        """Get statistics from episode collection"""
        stats = {
            "total_episodes": 0,
            "recent_episodes": 0,
            "route_distribution": {},
            "last_episode": None
        }
        
        if not self.router_db.exists():
            return stats
        
        try:
            with sqlite3.connect(self.router_db) as conn:
                conn.row_factory = sqlite3.Row
                
                # Total episodes
                cursor = conn.execute("SELECT COUNT(*) as total FROM edge_cases")
                stats["total_episodes"] = cursor.fetchone()["total"]
                
                # Recent episodes (last 7 days)
                week_ago = (datetime.now() - timedelta(days=7)).isoformat()
                cursor = conn.execute(
                    "SELECT COUNT(*) as recent FROM edge_cases WHERE timestamp > ?",
                    (week_ago,)
                )
                stats["recent_episodes"] = cursor.fetchone()["recent"]
                
                # Route distribution
                cursor = conn.execute(
                    "SELECT predicted_route, COUNT(*) as count FROM edge_cases GROUP BY predicted_route"
                )
                for row in cursor.fetchall():
                    stats["route_distribution"][row["predicted_route"]] = row["count"]
                
                # Last episode
                cursor = conn.execute(
                    "SELECT timestamp, text, predicted_route FROM edge_cases ORDER BY timestamp DESC LIMIT 1"
                )
                last_row = cursor.fetchone()
                if last_row:
                    stats["last_episode"] = {
                        "timestamp": last_row["timestamp"],
                        "text": last_row["text"],
                        "route": last_row["predicted_route"]
                    }
                    
        except Exception as e:
            print(f"Error reading episode stats: {e}")
        
        return stats
    
    def get_model_performance_history(self) -> List[Dict[str, Any]]:
        """Get historical model performance from training summaries"""
        history = []
        
        # Look for training summary files
        train_summary = self.router_dir / "train_summary.json"
        if train_summary.exists():
            try:
                with open(train_summary, 'r') as f:
                    data = json.load(f)
                    
                history.append({
                    "timestamp": data.get("timestamp"),
                    "training_id": data.get("training_id"),
                    "accuracy": data.get("performance", {}).get("validation_accuracy"),
                    "epochs": data.get("training", {}).get("epochs_completed"),
                    "dataset_size": data.get("dataset", {}).get("total_samples")
                })
                
            except Exception as e:
                print(f"Error reading training summary: {e}")
        
        # Look for evaluation results
        eval_results = self.router_dir / "data" / "eval_results.json"
        if eval_results.exists():
            try:
                with open(eval_results, 'r') as f:
                    data = json.load(f)
                    
                # Find matching training summary entry and update it
                if history and data.get("timestamp"):
                    # Assuming eval was run shortly after training
                    latest = history[-1]
                    latest.update({
                        "eval_accuracy": data.get("performance", {}).get("accuracy"),
                        "eval_latency": data.get("performance", {}).get("latency", {}).get("mean_ms"),
                        "promotion_eligible": data.get("promotion", {}).get("promotion_eligible"),
                        "edge_case_accuracy": data.get("edge_case_evaluation", {}).get("overall_accuracy")
                    })
                    
            except Exception as e:
                print(f"Error reading eval results: {e}")
        
        return history
    
    def get_autopilot_activity(self) -> Dict[str, Any]:
        """Get recent autopilot activity from logs"""
        activity = {
            "last_run": None,
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "recent_runs": []
        }
        
        if not self.audit_log.exists():
            return activity
        
        try:
            with open(self.audit_log, 'r') as f:
                lines = f.readlines()
                
            # Parse audit log entries for autopilot events
            for line in reversed(lines[-100:]):  # Check last 100 lines
                try:
                    entry = json.loads(line.strip())
                    if entry.get("action") == "autopilot_step" and entry.get("step") == "cycle_complete":
                        activity["total_runs"] += 1
                        
                        run_info = {
                            "timestamp": entry.get("timestamp"),
                            "success": entry.get("success"),
                            "duration": entry.get("duration_seconds"),
                            "steps_completed": entry.get("details", {}).get("completed_steps", 0),
                            "total_steps": entry.get("details", {}).get("total_steps", 4)
                        }
                        
                        if entry.get("success"):
                            activity["successful_runs"] += 1
                        else:
                            activity["failed_runs"] += 1
                        
                        if len(activity["recent_runs"]) < 5:
                            activity["recent_runs"].append(run_info)
                        
                        if not activity["last_run"]:
                            activity["last_run"] = run_info
                            
                except (json.JSONDecodeError, KeyError):
                    continue
                    
        except Exception as e:
            print(f"Error reading autopilot activity: {e}")
        
        return activity
    
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall learning system health status"""
        health = {
            "status": "healthy",
            "issues": [],
            "recommendations": []
        }
        
        # Check database exists and has data
        episode_stats = self.get_episode_stats()
        if episode_stats["total_episodes"] == 0:
            health["issues"].append("No episode data collected")
            health["recommendations"].append("Enable episode collection in bridge API")
        elif episode_stats["recent_episodes"] == 0:
            health["issues"].append("No recent episode data (last 7 days)")
            health["recommendations"].append("Check if TinyIntent is being actively used")
        
        # Check model files exist
        small_model = self.router_dir / "SmallIntent.mlmodel"
        if not small_model.exists():
            health["issues"].append("SmallIntent.mlmodel not found")
            health["recommendations"].append("Run 'make router-train' to create model")
        
        # Check training data exists
        training_data = self.router_dir / "data" / "intents.tsv"
        if not training_data.exists():
            health["issues"].append("Training data not found")
            health["recommendations"].append("Run 'make export-episodes' to create training data")
        else:
            # Check training data size
            try:
                with open(training_data, 'r') as f:
                    lines = len(f.readlines())
                if lines < 100:
                    health["issues"].append(f"Limited training data ({lines} examples)")
                    health["recommendations"].append("Collect more usage data before training")
            except Exception:
                pass
        
        # Check autopilot activity
        autopilot_activity = self.get_autopilot_activity()
        if autopilot_activity["total_runs"] == 0:
            health["recommendations"].append("Consider enabling autopilot: 'make autopilot-enable'")
        elif autopilot_activity["failed_runs"] > autopilot_activity["successful_runs"]:
            health["issues"].append("More autopilot failures than successes")
            health["recommendations"].append("Check autopilot error logs")
        
        # Overall status
        if len(health["issues"]) > 0:
            health["status"] = "degraded" if len(health["issues"]) < 3 else "unhealthy"
        
        return health
    
    def print_dashboard(self):
        """Print comprehensive learning system dashboard"""
        print("🎯 TinyIntent Learning System Dashboard")
        print("=" * 50)
        print()
        
        # Episode Collection Status
        print("📊 Episode Collection")
        print("-" * 20)
        episode_stats = self.get_episode_stats()
        print(f"Total episodes: {episode_stats['total_episodes']:,}")
        print(f"Recent episodes (7d): {episode_stats['recent_episodes']:,}")
        
        if episode_stats["route_distribution"]:
            print("Route distribution:")
            for route, count in episode_stats["route_distribution"].items():
                print(f"  {route}: {count:,} episodes")
        
        if episode_stats["last_episode"]:
            last = episode_stats["last_episode"]
            print(f"Last episode: {last['timestamp'][:19]} - \"{last['text'][:50]}...\" → {last['route']}")
        
        print()
        
        # Model Performance
        print("🧠 Model Performance")
        print("-" * 20)
        performance_history = self.get_model_performance_history()
        if performance_history:
            latest = performance_history[-1]
            print(f"Training ID: {latest.get('training_id', 'Unknown')}")
            print(f"Last trained: {latest.get('timestamp', 'Unknown')[:19]}")
            print(f"Dataset size: {latest.get('dataset_size', 'Unknown'):,} examples")
            print(f"Validation accuracy: {latest.get('accuracy', 0)*100:.1f}%")
            
            if latest.get('eval_accuracy'):
                print(f"Test accuracy: {latest.get('eval_accuracy')*100:.1f}%")
                print(f"Average latency: {latest.get('eval_latency', 0):.2f}ms")
                print(f"Edge case accuracy: {latest.get('edge_case_accuracy', 0)*100:.1f}%")
                
                eligible = latest.get('promotion_eligible', False)
                print(f"Promotion eligible: {'✅ Yes' if eligible else '❌ No'}")
        else:
            print("No model training history found")
            print("Run 'make router-train' to train the initial model")
        
        print()
        
        # Autopilot Activity
        print("🤖 Autopilot Activity")
        print("-" * 20)
        autopilot_activity = self.get_autopilot_activity()
        
        if autopilot_activity["last_run"]:
            last_run = autopilot_activity["last_run"]
            status = "✅ Success" if last_run["success"] else "❌ Failed"
            print(f"Last run: {last_run['timestamp'][:19]} - {status}")
            print(f"Duration: {last_run['duration']:.1f}s")
            print(f"Steps: {last_run['steps_completed']}/{last_run['total_steps']}")
        else:
            print("No autopilot runs found")
        
        print(f"Total runs: {autopilot_activity['total_runs']:,}")
        print(f"Success rate: {autopilot_activity['successful_runs']:,}/{autopilot_activity['total_runs']:,}")
        
        print()
        
        # System Health
        print("🏥 System Health")
        print("-" * 15)
        health = self.get_system_health()
        
        status_emoji = {
            "healthy": "🟢",
            "degraded": "🟡", 
            "unhealthy": "🔴"
        }
        print(f"Status: {status_emoji.get(health['status'], '⚪')} {health['status'].title()}")
        
        if health["issues"]:
            print("\nIssues:")
            for issue in health["issues"]:
                print(f"  ❌ {issue}")
        
        if health["recommendations"]:
            print("\nRecommendations:")
            for rec in health["recommendations"]:
                print(f"  💡 {rec}")
        
        print()
        print("🔧 Commands:")
        print("  make learn              # Manual learning cycle")
        print("  make autopilot-dry      # Test autopilot run") 
        print("  make autopilot-status   # Check autopilot scheduling")
        print("  make export-episodes    # Export new training data")
    
    def print_compact_status(self):
        """Print compact one-line status for scripts/monitoring"""
        episode_stats = self.get_episode_stats()
        performance_history = self.get_model_performance_history()
        health = self.get_system_health()
        
        # Get key metrics
        total_episodes = episode_stats["total_episodes"]
        recent_episodes = episode_stats["recent_episodes"]
        
        accuracy = 0.0
        promotion_eligible = False
        if performance_history:
            latest = performance_history[-1]
            accuracy = (latest.get("eval_accuracy") or latest.get("accuracy") or 0) * 100
            promotion_eligible = latest.get("promotion_eligible", False)
        
        status_short = health["status"][0].upper()  # H, D, U
        issues_count = len(health["issues"])
        
        print(f"LEARNING_STATUS:{status_short}|episodes:{total_episodes}|recent:{recent_episodes}|accuracy:{accuracy:.1f}%|eligible:{promotion_eligible}|issues:{issues_count}")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor TinyIntent learning system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/learning_monitor.py                # Full dashboard
  python3 scripts/learning_monitor.py --compact      # One-line status
  python3 scripts/learning_monitor.py --episodes     # Episode stats only
  python3 scripts/learning_monitor.py --performance  # Model performance only
        """
    )
    
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Print compact one-line status'
    )
    
    parser.add_argument(
        '--episodes',
        action='store_true',
        help='Show episode collection stats only'
    )
    
    parser.add_argument(
        '--performance',
        action='store_true',
        help='Show model performance only'
    )
    
    args = parser.parse_args()
    
    # Find project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent
    
    monitor = LearningMonitor(project_root)
    
    if args.compact:
        monitor.print_compact_status()
    elif args.episodes:
        episode_stats = monitor.get_episode_stats()
        print("Episode Collection:")
        print(f"  Total: {episode_stats['total_episodes']:,}")
        print(f"  Recent (7d): {episode_stats['recent_episodes']:,}")
        for route, count in episode_stats["route_distribution"].items():
            print(f"  {route}: {count:,}")
    elif args.performance:
        performance_history = monitor.get_model_performance_history()
        if performance_history:
            latest = performance_history[-1]
            print("Model Performance:")
            print(f"  Validation: {(latest.get('accuracy', 0)*100):.1f}%")
            if latest.get('eval_accuracy'):
                print(f"  Test: {(latest.get('eval_accuracy')*100):.1f}%")
                print(f"  Latency: {latest.get('eval_latency', 0):.2f}ms")
                print(f"  Promotion: {'Eligible' if latest.get('promotion_eligible') else 'Not eligible'}")
    else:
        monitor.print_dashboard()


if __name__ == "__main__":
    main()