#!/usr/bin/env python3
"""
TinyIntent Router Performance Monitor

Monitors router performance in production, tracks edge case accumulation,
and triggers improvement pipelines when thresholds are exceeded.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bridge.edge_case_logger import edge_case_logger
from scripts.analyze_edge_cases import EdgeCaseAnalyzer
from scripts.edge_case_pipeline import EdgeCasePipeline


class RouterPerformanceMonitor:
    """Monitors router performance and triggers improvement actions."""
    
    def __init__(self, project_root: Path):
        """Initialize monitor with project paths."""
        self.project_root = project_root
        self.analyzer = EdgeCaseAnalyzer()
        self.pipeline = EdgeCasePipeline(project_root)
        
        # Monitoring configuration
        self.config = {
            "check_interval_minutes": 60,  # Check every hour
            "alert_edge_case_rate": 0.15,  # Alert if >15% edge case rate
            "alert_edge_case_count": 50,   # Alert if >50 edge cases per day
            "auto_retrain_threshold": 100, # Auto-retrain if >100 edge cases
            "confidence_degradation_threshold": 0.05,  # Alert if confidence drops 5%
            "monitoring_window_hours": 24,
            "baseline_window_hours": 168  # 7 days for baseline
        }
        
        self.baseline_metrics = None
        self.last_metrics = None
    
    def monitor_once(self) -> Dict[str, Any]:
        """Run a single monitoring check."""
        print(f"🔍 Router Performance Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        
        try:
            # Get current metrics
            current_metrics = self._get_current_metrics()
            
            # Compare with baseline if available
            performance_analysis = self._analyze_performance_trends(current_metrics)
            
            # Check alert conditions
            alerts = self._check_alert_conditions(current_metrics, performance_analysis)
            
            # Generate recommendations
            recommendations = self._generate_recommendations(current_metrics, alerts)
            
            # Update stored metrics
            self.last_metrics = current_metrics
            
            monitoring_result = {
                "timestamp": datetime.now().isoformat(),
                "metrics": current_metrics,
                "performance_analysis": performance_analysis,
                "alerts": alerts,
                "recommendations": recommendations,
                "monitoring_config": self.config
            }
            
            # Print summary
            self._print_monitoring_summary(monitoring_result)
            
            # Take automated actions if configured
            actions_taken = self._take_automated_actions(alerts, recommendations)
            if actions_taken:
                monitoring_result["actions_taken"] = actions_taken
            
            return monitoring_result
            
        except Exception as e:
            error_result = {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "success": False
            }
            print(f"❌ Monitoring failed: {e}")
            return error_result
    
    def monitor_continuous(self, duration_hours: Optional[int] = None):
        """Run continuous monitoring for specified duration."""
        print(f"🚀 Starting continuous router monitoring...")
        print(f"Check interval: {self.config['check_interval_minutes']} minutes")
        if duration_hours:
            print(f"Duration: {duration_hours} hours")
        print("=" * 60)
        
        start_time = datetime.now()
        check_count = 0
        
        try:
            while True:
                check_count += 1
                print(f"\\n📊 Check #{check_count}")
                
                # Run monitoring check
                result = self.monitor_once()
                
                # Save results
                self._save_monitoring_result(result)
                
                # Check if we should stop
                if duration_hours:
                    elapsed_hours = (datetime.now() - start_time).total_seconds() / 3600
                    if elapsed_hours >= duration_hours:
                        print(f"\\n✅ Completed {duration_hours} hour monitoring session")
                        break
                
                # Wait until next check
                print(f"💤 Waiting {self.config['check_interval_minutes']} minutes until next check...")
                time.sleep(self.config["check_interval_minutes"] * 60)
                
        except KeyboardInterrupt:
            print(f"\\n🛑 Monitoring stopped by user after {check_count} checks")
        except Exception as e:
            print(f"\\n💥 Continuous monitoring failed: {e}")
    
    def _get_current_metrics(self) -> Dict[str, Any]:
        """Get current router performance metrics."""
        # Get edge case statistics
        edge_stats = edge_case_logger.get_edge_case_stats(self.config["monitoring_window_hours"])
        
        # Get recent edge cases for pattern analysis
        recent_cases = edge_case_logger.get_recent_edge_cases(limit=50)
        
        # Calculate additional metrics
        metrics = {
            "basic_stats": edge_stats,
            "recent_cases_sample": len(recent_cases),
            "patterns_detected": len(set(case.get("edge_case_type", "unknown") for case in recent_cases)),
            "voice_command_ratio": edge_stats["voice_command_count"] / max(edge_stats["total_decisions"], 1),
            "shortcut_session_ratio": edge_stats["shortcut_session_count"] / max(edge_stats["total_decisions"], 1)
        }
        
        # Add confidence distribution analysis
        if recent_cases:
            confidences = [case.get("predicted_confidence", 0.0) for case in recent_cases]
            metrics["confidence_distribution"] = {
                "mean": sum(confidences) / len(confidences),
                "min": min(confidences),
                "max": max(confidences),
                "below_50": sum(1 for c in confidences if c < 0.5),
                "below_70": sum(1 for c in confidences if c < 0.7)
            }
        
        return metrics
    
    def _analyze_performance_trends(self, current_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance trends compared to baseline."""
        if not self.baseline_metrics:
            # Try to establish baseline from historical data
            try:
                baseline_stats = edge_case_logger.get_edge_case_stats(self.config["baseline_window_hours"])
                self.baseline_metrics = {"basic_stats": baseline_stats}
            except:
                return {"status": "no_baseline", "message": "Insufficient historical data for baseline"}
        
        current_stats = current_metrics["basic_stats"]
        baseline_stats = self.baseline_metrics["basic_stats"]
        
        trends = {
            "edge_case_rate_change": current_stats["edge_case_rate"] - baseline_stats.get("edge_case_rate", 0),
            "confidence_change": current_stats["avg_confidence"] - baseline_stats.get("avg_confidence", 0),
            "total_decisions_change": current_stats["total_decisions"] - baseline_stats.get("total_decisions", 0),
            "voice_usage_change": current_metrics["voice_command_ratio"] - self.baseline_metrics.get("voice_command_ratio", 0)
        }
        
        return {
            "status": "analyzed",
            "trends": trends,
            "baseline_period": f"{self.config['baseline_window_hours']} hours",
            "current_period": f"{self.config['monitoring_window_hours']} hours"
        }
    
    def _check_alert_conditions(self, metrics: Dict[str, Any], trends: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Check for alert conditions based on metrics and trends."""
        alerts = []
        current_stats = metrics["basic_stats"]
        
        # High edge case rate alert
        if current_stats["edge_case_rate"] > self.config["alert_edge_case_rate"]:
            alerts.append({
                "severity": "high",
                "type": "edge_case_rate",
                "message": f"Edge case rate {current_stats['edge_case_rate']:.2%} exceeds threshold {self.config['alert_edge_case_rate']:.2%}",
                "value": current_stats["edge_case_rate"],
                "threshold": self.config["alert_edge_case_rate"]
            })
        
        # High edge case count alert
        if current_stats["edge_case_count"] > self.config["alert_edge_case_count"]:
            alerts.append({
                "severity": "medium",
                "type": "edge_case_count",
                "message": f"Edge case count {current_stats['edge_case_count']} exceeds threshold {self.config['alert_edge_case_count']}",
                "value": current_stats["edge_case_count"],
                "threshold": self.config["alert_edge_case_count"]
            })
        
        # Confidence degradation alert
        if trends.get("status") == "analyzed":
            confidence_change = trends["trends"]["confidence_change"]
            if confidence_change < -self.config["confidence_degradation_threshold"]:
                alerts.append({
                    "severity": "high",
                    "type": "confidence_degradation",
                    "message": f"Router confidence decreased by {abs(confidence_change):.3f}",
                    "value": confidence_change,
                    "threshold": -self.config["confidence_degradation_threshold"]
                })
        
        # Auto-retrain threshold
        if current_stats["edge_case_count"] > self.config["auto_retrain_threshold"]:
            alerts.append({
                "severity": "critical",
                "type": "auto_retrain_trigger",
                "message": f"Edge case count {current_stats['edge_case_count']} exceeds auto-retrain threshold {self.config['auto_retrain_threshold']}",
                "value": current_stats["edge_case_count"],
                "threshold": self.config["auto_retrain_threshold"],
                "action_required": True
            })
        
        return alerts
    
    def _generate_recommendations(self, metrics: Dict[str, Any], alerts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        current_stats = metrics["basic_stats"]
        
        # Recommendations based on alerts
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        high_alerts = [a for a in alerts if a["severity"] == "high"]
        
        if critical_alerts:
            recommendations.append({
                "priority": "immediate",
                "action": "trigger_retraining",
                "title": "Immediate retraining required",
                "description": "Critical thresholds exceeded, automated retraining recommended",
                "command": "make learn-edges-force"
            })
        
        elif high_alerts:
            recommendations.append({
                "priority": "high",
                "action": "analyze_patterns",
                "title": "Analyze edge case patterns",
                "description": "High-severity issues detected, run pattern analysis",
                "command": "make analyze-edges"
            })
        
        # Data-driven recommendations
        if metrics.get("patterns_detected", 0) > 5:
            recommendations.append({
                "priority": "medium",
                "action": "pattern_review",
                "title": "Review edge case patterns",
                "description": f"Multiple patterns detected ({metrics['patterns_detected']}), manual review recommended"
            })
        
        # Voice command specific recommendations
        if metrics.get("voice_command_ratio", 0) > 0.5:
            recommendations.append({
                "priority": "medium",
                "action": "voice_optimization",
                "title": "Voice command optimization",
                "description": "High voice usage detected, consider voice-specific training data expansion"
            })
        
        return recommendations
    
    def _take_automated_actions(self, alerts: List[Dict[str, Any]], recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Take automated actions based on alerts and recommendations."""
        actions_taken = []
        
        # Check for auto-retrain triggers
        auto_retrain_alerts = [a for a in alerts if a.get("action_required") and a["type"] == "auto_retrain_trigger"]
        
        if auto_retrain_alerts:
            print(f"🚨 CRITICAL: Auto-retrain threshold exceeded!")
            print(f"   Triggering automated edge case pipeline...")
            
            try:
                # Run edge case pipeline
                pipeline_result = self.pipeline.run_pipeline(force=True)
                
                actions_taken.append({
                    "action": "automated_retraining",
                    "timestamp": datetime.now().isoformat(),
                    "trigger": "auto_retrain_threshold",
                    "result": pipeline_result,
                    "success": pipeline_result.get("success", False)
                })
                
                if pipeline_result.get("success"):
                    print("✅ Automated retraining completed successfully!")
                else:
                    print(f"❌ Automated retraining failed: {pipeline_result.get('error', 'unknown error')}")
                    
            except Exception as e:
                actions_taken.append({
                    "action": "automated_retraining",
                    "timestamp": datetime.now().isoformat(),
                    "trigger": "auto_retrain_threshold",
                    "success": False,
                    "error": str(e)
                })
                print(f"❌ Automated retraining failed with exception: {e}")
        
        return actions_taken
    
    def _print_monitoring_summary(self, result: Dict[str, Any]):
        """Print a summary of monitoring results."""
        metrics = result["metrics"]["basic_stats"]
        alerts = result["alerts"]
        recommendations = result["recommendations"]
        
        print(f"📊 Current Metrics:")
        print(f"   Total decisions: {metrics['total_decisions']}")
        print(f"   Edge case rate: {metrics['edge_case_rate']:.2%}")
        print(f"   Average confidence: {metrics['avg_confidence']:.3f}")
        print(f"   Voice commands: {metrics['voice_command_count']} ({result['metrics']['voice_command_ratio']:.2%})")
        
        if alerts:
            print(f"\\n🚨 Alerts ({len(alerts)}):")
            for alert in alerts:
                severity_icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(alert["severity"], "ℹ️")
                print(f"   {severity_icon} {alert['message']}")
        else:
            print(f"\\n✅ No alerts - system operating normally")
        
        if recommendations:
            print(f"\\n💡 Recommendations ({len(recommendations)}):")
            for rec in recommendations[:3]:  # Show top 3
                priority_icon = {"immediate": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(rec["priority"], "ℹ️")
                print(f"   {priority_icon} {rec['title']}")
                if rec.get("command"):
                    print(f"      Command: {rec['command']}")
    
    def _save_monitoring_result(self, result: Dict[str, Any]):
        """Save monitoring result to file."""
        try:
            logs_dir = self.project_root / "bridge" / "logs"
            logs_dir.mkdir(exist_ok=True)
            
            log_file = logs_dir / "router_performance.jsonl"
            
            with open(log_file, 'a') as f:
                f.write(json.dumps(result, default=str) + '\\n')
                
        except Exception as e:
            print(f"⚠️  Failed to save monitoring result: {e}")


def main():
    """Main monitoring function."""
    parser = argparse.ArgumentParser(description="Monitor TinyIntent router performance")
    parser.add_argument("--once", action="store_true", help="Run single monitoring check")
    parser.add_argument("--continuous", action="store_true", help="Run continuous monitoring")
    parser.add_argument("--duration", type=int, help="Duration in hours for continuous monitoring")
    parser.add_argument("--output", type=str, help="Save results to JSON file")
    parser.add_argument("--auto-retrain-threshold", type=int, default=100, help="Auto-retrain threshold")
    
    args = parser.parse_args()
    
    # Initialize monitor
    monitor = RouterPerformanceMonitor(project_root)
    
    # Update configuration
    if args.auto_retrain_threshold:
        monitor.config["auto_retrain_threshold"] = args.auto_retrain_threshold
    
    # Run monitoring
    if args.continuous:
        monitor.monitor_continuous(args.duration)
        return 0
    else:
        # Single check
        result = monitor.monitor_once()
        
        # Save results if requested
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(result, f, indent=2, default=str)
            print(f"📄 Results saved to {output_path}")
        
        return 0 if result.get("success", True) else 1


if __name__ == "__main__":
    sys.exit(main())