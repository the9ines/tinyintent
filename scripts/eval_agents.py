#!/usr/bin/env python3
"""
TinyIntent Agent Safety & Quality Evaluation

Computes per-agent safety/quality metrics over a time window for staged helpers.
Generates comprehensive reports for operator review.

M10.3: Agent Staging - Safety Report Generation
M10.4: Agent Promotion - Automated promotion/rollback decisions
"""

import json
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tinyintent.data.episodes.episodes import agent_staging_storage
from tinyintent.helpers.registry import HelperRegistry
from tinyintent.helpers.manifest import validate_helper_manifest


# M10.4: Environment-configurable promotion thresholds
PROMOTION_THRESHOLDS = {
    "min_calls": int(os.getenv("AGENT_PROMOTE_MIN_CALLS", "20")),
    "max_error_rate": float(os.getenv("AGENT_PROMOTE_MAX_ERROR_RATE", "0.1")),
    "max_schema_fail": float(os.getenv("AGENT_PROMOTE_MAX_SCHEMA_FAIL", "0.02")),
    "max_p95_latency_ms": int(os.getenv("AGENT_PROMOTE_MAX_P95_LATENCY_MS", "1200"))
}

ROLLBACK_THRESHOLDS = {
    "window_hours": int(os.getenv("AGENT_ROLLBACK_WINDOW_H", "6")),
    "error_rate": float(os.getenv("AGENT_ROLLBACK_ERROR_RATE", "0.2"))
}


class AgentEvaluator:
    """Evaluates agent safety and quality metrics for staging."""
    
    def __init__(self):
        self.staging_storage = agent_staging_storage
        self.helper_registry = HelperRegistry()
    
    def evaluate_agent(self, helper_id: str, window_hours: int = 24) -> Dict[str, Any]:
        """
        Evaluate safety and quality metrics for a specific helper.
        
        Args:
            helper_id: ID of the helper to evaluate
            window_hours: Time window for analysis (default: 24 hours)
            
        Returns:
            dict: Comprehensive safety and quality report
        """
        # Get staging metrics from storage
        staging_metrics = self.staging_storage.get_staging_metrics(helper_id, window_hours)
        
        # Get helper manifest information
        helper_info = self._get_helper_info(helper_id)
        
        # Calculate derived metrics
        safety_score = self._calculate_safety_score(staging_metrics, helper_info)
        quality_score = self._calculate_quality_score(staging_metrics)
        reliability_score = self._calculate_reliability_score(staging_metrics)
        
        # Analyze performance patterns
        performance_analysis = self._analyze_performance_patterns(staging_metrics)
        
        # Check for security violations
        security_analysis = self._analyze_security_violations(helper_id, window_hours)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            staging_metrics, safety_score, quality_score, reliability_score, security_analysis
        )
        
        # Determine promotion eligibility
        promotion_eligibility = self._assess_promotion_eligibility(
            staging_metrics, safety_score, quality_score, reliability_score, security_analysis
        )
        
        # Compile final report
        report = {
            "helper_id": helper_id,
            "evaluation_timestamp": datetime.now().isoformat(),
            "window_hours": window_hours,
            "helper_info": helper_info,
            "staging_metrics": staging_metrics,
            "scores": {
                "safety": safety_score,
                "quality": quality_score,
                "reliability": reliability_score,
                "overall": (safety_score + quality_score + reliability_score) / 3
            },
            "performance_analysis": performance_analysis,
            "security_analysis": security_analysis,
            "recommendations": recommendations,
            "promotion_eligibility": promotion_eligibility,
            "metadata": {
                "evaluator_version": "1.0.0",
                "evaluation_criteria": self._get_evaluation_criteria()
            }
        }
        
        return report
    
    def evaluate_all_staged_agents(self, window_hours: int = 24) -> Dict[str, Dict[str, Any]]:
        """
        Evaluate all agents that have staging activity.
        
        Args:
            window_hours: Time window for analysis
            
        Returns:
            dict: Reports for all staged agents
        """
        # Get all helpers with staging configurations
        staged_helpers = self._get_staged_helpers()
        
        reports = {}
        for helper_id in staged_helpers:
            try:
                reports[helper_id] = self.evaluate_agent(helper_id, window_hours)
            except Exception as e:
                reports[helper_id] = {
                    "error": f"Evaluation failed: {str(e)}",
                    "helper_id": helper_id,
                    "evaluation_timestamp": datetime.now().isoformat()
                }
        
        return reports
    
    def _get_helper_info(self, helper_id: str) -> Dict[str, Any]:
        """Get helper manifest and registry information."""
        try:
            helper = self.helper_registry.get_helper(helper_id)
            if helper:
                return {
                    "name": helper.name,
                    "description": helper.description,
                    "version": helper.version,
                    "capabilities": helper.capabilities,
                    "lifecycle": helper.lifecycle,
                    "exists": True,
                    "valid": self.helper_registry.is_helper_valid(helper_id),
                    "validation_errors": self.helper_registry.get_helper_validation_errors(helper_id)
                }
            else:
                return {
                    "exists": False,
                    "valid": False,
                    "error": "Helper not found in registry"
                }
        except Exception as e:
            return {
                "exists": False,
                "valid": False,
                "error": f"Failed to load helper info: {str(e)}"
            }
    
    def _calculate_safety_score(self, metrics: Dict[str, Any], helper_info: Dict[str, Any]) -> float:
        """
        Calculate safety score based on error rates, capability violations, and determinism.
        Scale: 0.0 (unsafe) to 1.0 (perfectly safe)
        """
        score = 1.0
        
        # Penalty for high error rates
        if metrics["shadow_runs"] > 0:
            error_rate = 1.0 - metrics["shadow_success_rate"]
            score -= error_rate * 0.3  # Up to 30% penalty for errors
        
        # Penalty for specific error types
        error_rates = metrics.get("error_rates", {})
        
        # Security violations are heavily penalized
        if "CAPABILITY_VIOLATION" in error_rates:
            score -= error_rates["CAPABILITY_VIOLATION"] * 0.5
        
        if "SANDBOX_LIMIT" in error_rates:
            score -= error_rates["SANDBOX_LIMIT"] * 0.4
        
        # Schema validation failures
        if "SCHEMA_VALIDATION" in error_rates:
            score -= error_rates["SCHEMA_VALIDATION"] * 0.2
        
        # Determinism penalty (non-deterministic outputs are concerning)
        determinism_penalty = (1.0 - metrics["determinism_score"]) * 0.2
        score -= determinism_penalty
        
        # Helper validation status
        if not helper_info.get("valid", False):
            score -= 0.3  # Significant penalty for invalid helpers
        
        return max(0.0, score)
    
    def _calculate_quality_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate quality score based on success rates, latency, and output consistency.
        Scale: 0.0 (poor quality) to 1.0 (excellent quality)
        """
        score = 0.0
        
        # Base score from success rate
        if metrics["shadow_runs"] > 0:
            score = metrics["shadow_success_rate"]
        
        # Latency bonus/penalty
        avg_latency = metrics.get("avg_latency_ms", 0)
        if avg_latency > 0:
            if avg_latency < 100:  # Very fast
                score += 0.1
            elif avg_latency < 500:  # Acceptable
                score += 0.05
            elif avg_latency > 2000:  # Slow
                score -= 0.1
            elif avg_latency > 5000:  # Very slow
                score -= 0.2
        
        # Output consistency bonus
        determinism_bonus = metrics["determinism_score"] * 0.1
        score += determinism_bonus
        
        # Penalty for excessive output size variability
        output_stats = metrics.get("output_size_stats", {})
        if output_stats and output_stats.get("max", 0) > 0:
            size_variance = (output_stats["max"] - output_stats.get("min", 0)) / output_stats["max"]
            if size_variance > 0.5:  # High variance
                score -= 0.05
        
        return max(0.0, min(1.0, score))
    
    def _calculate_reliability_score(self, metrics: Dict[str, Any]) -> float:
        """
        Calculate reliability score based on consistency and predictability.
        Scale: 0.0 (unreliable) to 1.0 (highly reliable)
        """
        score = 0.0
        
        # Base score from determinism
        score = metrics["determinism_score"]
        
        # Consistency in success rates
        if metrics["shadow_runs"] > 5:  # Need enough data points
            success_rate = metrics["shadow_success_rate"]
            if success_rate > 0.95:  # Very consistent
                score += 0.2
            elif success_rate > 0.8:  # Reasonably consistent
                score += 0.1
            elif success_rate < 0.5:  # Inconsistent
                score -= 0.2
        
        # Latency consistency (if we have latency data)
        if metrics.get("avg_latency_ms", 0) > 0:
            # Assume good latency consistency for now
            # In a full implementation, we'd calculate latency variance
            score += 0.05
        
        return max(0.0, min(1.0, score))
    
    def _analyze_performance_patterns(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze performance patterns and trends."""
        analysis = {
            "summary": "Insufficient data for pattern analysis",
            "trends": [],
            "anomalies": [],
            "recommendations": []
        }
        
        if metrics["shadow_runs"] > 0:
            analysis["summary"] = f"Analyzed {metrics['shadow_runs']} shadow runs"
            
            # Basic trend analysis
            success_rate = metrics["shadow_success_rate"]
            if success_rate >= 0.95:
                analysis["trends"].append("Consistently high success rate")
            elif success_rate >= 0.8:
                analysis["trends"].append("Good success rate with occasional failures")
            elif success_rate >= 0.5:
                analysis["trends"].append("Moderate success rate - needs improvement")
            else:
                analysis["trends"].append("Low success rate - significant issues")
            
            # Latency analysis
            avg_latency = metrics.get("avg_latency_ms", 0)
            if avg_latency > 0:
                if avg_latency < 100:
                    analysis["trends"].append("Excellent response time")
                elif avg_latency < 500:
                    analysis["trends"].append("Good response time")
                elif avg_latency < 2000:
                    analysis["trends"].append("Acceptable response time")
                else:
                    analysis["trends"].append("Slow response time")
            
            # Error pattern analysis
            error_rates = metrics.get("error_rates", {})
            if error_rates:
                for error_type, rate in error_rates.items():
                    if rate > 0.1:  # More than 10% error rate
                        analysis["anomalies"].append(f"High {error_type} error rate: {rate:.1%}")
        
        return analysis
    
    def _analyze_security_violations(self, helper_id: str, window_hours: int) -> Dict[str, Any]:
        """Analyze security violations and capability breaches."""
        # This would typically query audit logs for security events
        # For now, we'll provide a basic analysis structure
        
        return {
            "capability_violations": 0,
            "sandbox_violations": 0,
            "network_violations": 0,
            "filesystem_violations": 0,
            "severity": "low",  # low, medium, high, critical
            "details": [],
            "recommendations": []
        }
    
    def _generate_recommendations(self, metrics: Dict[str, Any], safety_score: float, 
                                quality_score: float, reliability_score: float, 
                                security_analysis: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on evaluation."""
        recommendations = []
        
        # Safety recommendations
        if safety_score < 0.7:
            recommendations.append("Safety score is low - review error patterns and fix capability violations")
        
        if metrics.get("determinism_score", 1.0) < 0.8:
            recommendations.append("Output determinism is low - ensure consistent outputs for identical inputs")
        
        # Quality recommendations
        if quality_score < 0.7:
            recommendations.append("Quality score needs improvement - focus on reducing error rates")
        
        if metrics.get("avg_latency_ms", 0) > 2000:
            recommendations.append("Response time is slow - optimize helper performance")
        
        # Reliability recommendations
        if reliability_score < 0.7:
            recommendations.append("Reliability is concerning - improve consistency and predictability")
        
        # Security recommendations
        if security_analysis.get("severity") in ["high", "critical"]:
            recommendations.append("Address security violations before promoting to production")
        
        # Data volume recommendations
        if metrics["shadow_runs"] < 10:
            recommendations.append("Insufficient staging data - run more shadow tests before promotion")
        
        return recommendations
    
    def _assess_promotion_eligibility(self, metrics: Dict[str, Any], safety_score: float, 
                                    quality_score: float, reliability_score: float, 
                                    security_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Assess whether the agent is eligible for promotion."""
        
        # Minimum thresholds for promotion
        min_safety = 0.8
        min_quality = 0.7
        min_reliability = 0.7
        min_runs = 20
        
        checks = {
            "safety_score": safety_score >= min_safety,
            "quality_score": quality_score >= min_quality,
            "reliability_score": reliability_score >= min_reliability,
            "sufficient_data": metrics["shadow_runs"] >= min_runs,
            "no_security_violations": security_analysis.get("severity", "low") in ["low", "medium"],
            "success_rate": metrics.get("shadow_success_rate", 0) >= 0.85
        }
        
        eligible = all(checks.values())
        
        return {
            "eligible": eligible,
            "checks": checks,
            "thresholds": {
                "min_safety_score": min_safety,
                "min_quality_score": min_quality,
                "min_reliability_score": min_reliability,
                "min_shadow_runs": min_runs
            },
            "recommendation": "PROMOTE" if eligible else "DO_NOT_PROMOTE",
            "reasoning": self._get_promotion_reasoning(checks)
        }
    
    def _get_promotion_reasoning(self, checks: Dict[str, bool]) -> str:
        """Generate reasoning for promotion decision."""
        failed_checks = [check for check, passed in checks.items() if not passed]
        
        if not failed_checks:
            return "All promotion criteria met - safe for production deployment"
        
        return f"Promotion blocked by: {', '.join(failed_checks)}"
    
    def evaluate_for_promotion(self, helper_id: str, window_h: int = 24) -> Dict[str, Any]:
        """
        M10.4: Evaluate helper for promotion to trusted status.
        
        Args:
            helper_id: ID of the helper to evaluate
            window_h: Time window in hours for analysis
            
        Returns:
            dict: Promotion verdict with metrics and promote flag
        """
        # Get staging metrics
        staging_metrics = self.staging_storage.get_staging_metrics(helper_id, window_h)
        
        # Get helper information
        helper_info = self._get_helper_info(helper_id)
        
        # Calculate P95 latency (approximate from average for now)
        avg_latency = staging_metrics.get("avg_latency_ms", 0)
        p95_latency = avg_latency * 1.2  # Rough approximation
        
        # Extract relevant error rates
        error_rates = staging_metrics.get("error_rates", {})
        total_error_rate = 1.0 - staging_metrics.get("shadow_success_rate", 0.0)
        schema_fail_rate = error_rates.get("SCHEMA_VALIDATION", 0.0)
        
        # Check promotion criteria
        checks = {
            "sufficient_calls": staging_metrics.get("shadow_runs", 0) >= PROMOTION_THRESHOLDS["min_calls"],
            "error_rate_acceptable": total_error_rate <= PROMOTION_THRESHOLDS["max_error_rate"],
            "schema_failures_low": schema_fail_rate <= PROMOTION_THRESHOLDS["max_schema_fail"],
            "latency_acceptable": p95_latency <= PROMOTION_THRESHOLDS["max_p95_latency_ms"],
            "helper_valid": helper_info.get("valid", False),
            "helper_exists": helper_info.get("exists", False)
        }
        
        # Determine promotion eligibility
        promote = all(checks.values())
        
        # Generate reasons for decision
        reasons = []
        if not checks["sufficient_calls"]:
            reasons.append(f"Insufficient data: {staging_metrics.get('shadow_runs', 0)} calls < {PROMOTION_THRESHOLDS['min_calls']} required")
        if not checks["error_rate_acceptable"]:
            reasons.append(f"Error rate too high: {total_error_rate:.1%} > {PROMOTION_THRESHOLDS['max_error_rate']:.1%} threshold")
        if not checks["schema_failures_low"]:
            reasons.append(f"Schema failure rate too high: {schema_fail_rate:.1%} > {PROMOTION_THRESHOLDS['max_schema_fail']:.1%} threshold")
        if not checks["latency_acceptable"]:
            reasons.append(f"P95 latency too high: {p95_latency:.0f}ms > {PROMOTION_THRESHOLDS['max_p95_latency_ms']}ms threshold")
        if not checks["helper_valid"]:
            reasons.append("Helper manifest validation failed")
        if not checks["helper_exists"]:
            reasons.append("Helper does not exist")
        
        if promote:
            reasons.append("All promotion criteria satisfied")
        
        return {
            "helper_id": helper_id,
            "evaluation_timestamp": datetime.utcnow().isoformat() + 'Z',
            "window_hours": window_h,
            "promote": promote,
            "decision": "PROMOTE" if promote else "DO_NOT_PROMOTE",
            "reasons": reasons,
            "metrics": {
                "shadow_runs": staging_metrics.get("shadow_runs", 0),
                "success_rate": staging_metrics.get("shadow_success_rate", 0.0),
                "error_rate": total_error_rate,
                "schema_fail_rate": schema_fail_rate,
                "avg_latency_ms": avg_latency,
                "p95_latency_ms": p95_latency,
                "determinism_score": staging_metrics.get("determinism_score", 0.0)
            },
            "thresholds": PROMOTION_THRESHOLDS,
            "checks": checks,
            "helper_info": helper_info
        }
    
    def _get_evaluation_criteria(self) -> Dict[str, Any]:
        """Get the evaluation criteria used for scoring."""
        return {
            "safety_score": {
                "description": "Based on error rates, security violations, and determinism",
                "range": "0.0 (unsafe) to 1.0 (perfectly safe)",
                "weight": "33%"
            },
            "quality_score": {
                "description": "Based on success rates, latency, and output consistency",
                "range": "0.0 (poor) to 1.0 (excellent)",
                "weight": "33%"
            },
            "reliability_score": {
                "description": "Based on consistency and predictability",
                "range": "0.0 (unreliable) to 1.0 (highly reliable)",
                "weight": "33%"
            },
            "promotion_thresholds": PROMOTION_THRESHOLDS
        }
    
    def _get_staged_helpers(self) -> List[str]:
        """Get list of helpers that have staging configurations."""
        # This would query the staging storage for helpers with configurations
        # For now, return empty list as we don't have a direct query method
        return []
    
    def save_report(self, helper_id: str, report: Dict[str, Any]) -> Path:
        """Save evaluation report to helper directory."""
        # Determine helper directory
        helpers_dir = Path(__file__).parent.parent / "helpers"
        helper_dir = helpers_dir / helper_id
        
        if not helper_dir.exists():
            helper_dir.mkdir(parents=True, exist_ok=True)
        
        # Save report
        report_path = helper_dir / "report.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)
        
        return report_path


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Evaluate agent safety and quality metrics")
    parser.add_argument("--helper-id", type=str, help="Specific helper to evaluate")
    parser.add_argument("--window-hours", type=int, default=24, help="Time window in hours (default: 24)")
    parser.add_argument("--output", type=str, help="Output file path (default: stdout)")
    parser.add_argument("--save-reports", action="store_true", help="Save reports to helper directories")
    parser.add_argument("--all", action="store_true", help="Evaluate all staged agents")
    
    args = parser.parse_args()
    
    evaluator = AgentEvaluator()
    
    try:
        if args.all:
            # Evaluate all staged agents
            reports = evaluator.evaluate_all_staged_agents(args.window_hours)
            
            if args.save_reports:
                for helper_id, report in reports.items():
                    if "error" not in report:
                        report_path = evaluator.save_report(helper_id, report)
                        print(f"Report saved: {report_path}")
            
            # Output summary
            output_data = {
                "evaluation_summary": {
                    "total_agents": len(reports),
                    "successful_evaluations": len([r for r in reports.values() if "error" not in r]),
                    "failed_evaluations": len([r for r in reports.values() if "error" in r]),
                    "timestamp": datetime.now().isoformat()
                },
                "reports": reports
            }
            
        elif args.helper_id:
            # Evaluate specific helper
            report = evaluator.evaluate_agent(args.helper_id, args.window_hours)
            
            if args.save_reports:
                report_path = evaluator.save_report(args.helper_id, report)
                print(f"Report saved: {report_path}")
            
            output_data = report
            
        else:
            parser.error("Must specify either --helper-id or --all")
        
        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"Results written to: {args.output}")
        else:
            print(json.dumps(output_data, indent=2))
    
    except Exception as e:
        print(f"Evaluation failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()