#!/usr/bin/env python3
"""
TinyIntent Edge Case Analysis Tool

Analyzes collected edge cases to identify patterns, cluster misclassifications,
and generate training data candidates for systematic router improvement.
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from bridge.edge_case_logger import EdgeCaseLogger, edge_case_logger


class EdgeCaseAnalyzer:
    """Analyzes edge case patterns and generates improvement recommendations."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize analyzer with edge case database."""
        if db_path:
            self.logger = EdgeCaseLogger(db_path)
        else:
            self.logger = edge_case_logger
    
    def analyze_patterns(self, hours: int = 24, min_samples: int = 3) -> Dict[str, Any]:
        """
        Analyze edge case patterns from recent data.
        
        Args:
            hours: Time window to analyze
            min_samples: Minimum samples to form a pattern
            
        Returns:
            Analysis results with patterns and recommendations
        """
        print(f"🔍 Analyzing edge case patterns from last {hours} hours...")
        
        # Get basic statistics
        stats = self.logger.get_edge_case_stats(hours)
        print(f"📊 Found {stats['edge_case_count']} edge cases out of {stats['total_decisions']} total decisions")
        print(f"   Edge case rate: {stats['edge_case_rate']:.2%}")
        print(f"   Average confidence: {stats['avg_confidence']:.3f}")
        print(f"   Voice commands: {stats['voice_command_count']}")
        print(f"   iPhone Shortcut sessions: {stats['shortcut_session_count']}")
        
        # Get recent cases for detailed analysis
        recent_cases = self.logger.get_recent_edge_cases(limit=100)
        
        if not recent_cases:
            print("⚠️  No edge cases found in the specified time window")
            return {"error": "no_edge_cases", "stats": stats}
        
        # Pattern analysis
        patterns = self._identify_patterns(recent_cases, min_samples)
        confidence_analysis = self._analyze_confidence_distribution(recent_cases)
        misclassification_analysis = self._analyze_misclassifications(recent_cases)
        training_candidates = self._generate_training_candidates(patterns, recent_cases)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "analysis_window_hours": hours,
            "stats": stats,
            "patterns": patterns,
            "confidence_analysis": confidence_analysis,
            "misclassification_analysis": misclassification_analysis,
            "training_candidates": training_candidates,
            "recommendations": self._generate_recommendations(patterns, stats)
        }
    
    def _identify_patterns(self, cases: List[Dict[str, Any]], min_samples: int) -> List[Dict[str, Any]]:
        """Identify common patterns in edge cases."""
        print("🔎 Identifying edge case patterns...")
        
        # Group by pattern characteristics
        pattern_groups = defaultdict(list)
        
        for case in cases:
            text = case.get("text", "").lower().strip()
            edge_type = case.get("edge_case_type", "unknown")
            confidence = case.get("predicted_confidence", 0.0)
            source = case.get("context_source", "unknown")
            
            # Create pattern key based on text characteristics
            pattern_key = self._create_pattern_key(text, edge_type, confidence)
            pattern_groups[pattern_key].append({
                "text": text,
                "original_case": case,
                "confidence": confidence,
                "edge_type": edge_type,
                "source": source
            })
        
        # Filter patterns with enough samples and create analysis
        patterns = []
        for pattern_key, group in pattern_groups.items():
            if len(group) >= min_samples:
                # Find representative example
                group_sorted = sorted(group, key=lambda x: x["confidence"])
                representative = group_sorted[len(group_sorted) // 2]  # Median confidence
                
                patterns.append({
                    "pattern_key": pattern_key,
                    "sample_count": len(group),
                    "representative_text": representative["text"],
                    "avg_confidence": sum(case["confidence"] for case in group) / len(group),
                    "confidence_range": {
                        "min": min(case["confidence"] for case in group),
                        "max": max(case["confidence"] for case in group)
                    },
                    "edge_types": list(Counter(case["edge_type"] for case in group).keys()),
                    "sources": list(Counter(case["source"] for case in group).keys()),
                    "examples": [case["text"] for case in group[:5]],  # Top 5 examples
                    "severity": self._calculate_pattern_severity(group)
                })
        
        # Sort by severity and sample count
        patterns.sort(key=lambda x: (x["severity"], x["sample_count"]), reverse=True)
        
        print(f"   Found {len(patterns)} significant patterns")
        for i, pattern in enumerate(patterns[:5]):
            print(f"   {i+1}. {pattern['representative_text'][:50]}... ({pattern['sample_count']} samples, severity: {pattern['severity']:.2f})")
        
        return patterns
    
    def _create_pattern_key(self, text: str, edge_type: str, confidence: float) -> str:
        """Create a pattern key for clustering similar edge cases."""
        features = []
        
        # Question vs command indicators
        question_starters = ["what", "how", "when", "where", "why", "who", "which", "can", "do", "does", "is", "are", "will", "would", "should"]
        command_indicators = ["show", "get", "close", "stop", "start", "run", "execute", "check", "monitor", "tell me", "give me"]
        
        starts_with_question = any(text.startswith(qw + " ") for qw in question_starters)
        contains_command = any(cmd in text for cmd in command_indicators)
        
        features.append(f"question_start:{starts_with_question}")
        features.append(f"contains_command:{contains_command}")
        features.append(f"edge_type:{edge_type}")
        features.append(f"confidence_bucket:{int(confidence * 10) / 10}")  # Round to nearest 0.1
        features.append(f"length_bucket:{len(text) // 10}")  # Group by rough length
        
        # Voice-specific patterns
        if any(word in text for word in ["hey", "ok", "please", "can you", "would you"]):
            features.append("polite_voice:true")
        
        if any(word in text for word in ["status", "current", "recent", "latest", "now"]):
            features.append("status_inquiry:true")
        
        return "|".join(features)
    
    def _calculate_pattern_severity(self, group: List[Dict[str, Any]]) -> float:
        """Calculate severity score for a pattern (higher = more urgent to fix)."""
        severity = 0.0
        
        # More samples = higher severity
        severity += min(len(group) / 10.0, 1.0) * 3.0
        
        # Lower confidence = higher severity
        avg_confidence = sum(case["confidence"] for case in group) / len(group)
        severity += (1.0 - avg_confidence) * 2.0
        
        # iPhone Shortcut cases are higher priority
        shortcut_count = sum(1 for case in group if "shortcut" in case.get("source", "").lower())
        severity += (shortcut_count / len(group)) * 1.5
        
        # Certain edge types are more severe
        edge_types = [case["edge_type"] for case in group]
        if "misclassified_question" in edge_types or "misclassified_command" in edge_types:
            severity += 2.0
        elif "low_confidence" in edge_types:
            severity += 1.0
        
        return min(severity, 10.0)  # Cap at 10.0
    
    def _analyze_confidence_distribution(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze confidence score distribution of edge cases."""
        confidences = [case.get("predicted_confidence", 0.0) for case in cases]
        
        if not confidences:
            return {"error": "no_confidence_data"}
        
        # Create confidence buckets
        buckets = defaultdict(int)
        for conf in confidences:
            bucket = int(conf * 10) / 10  # Round to nearest 0.1
            buckets[bucket] += 1
        
        return {
            "total_cases": len(confidences),
            "mean_confidence": sum(confidences) / len(confidences),
            "min_confidence": min(confidences),
            "max_confidence": max(confidences),
            "confidence_buckets": dict(sorted(buckets.items())),
            "very_low_confidence_count": sum(1 for c in confidences if c < 0.3),
            "low_confidence_count": sum(1 for c in confidences if 0.3 <= c < 0.6),
            "medium_confidence_count": sum(1 for c in confidences if 0.6 <= c < 0.8),
            "high_confidence_count": sum(1 for c in confidences if c >= 0.8)
        }
    
    def _analyze_misclassifications(self, cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze types of misclassifications."""
        misclassifications = defaultdict(int)
        route_confusion = defaultdict(lambda: defaultdict(int))
        
        for case in cases:
            predicted = case.get("predicted_route", "unknown")
            actual = case.get("actual_route", "unknown")
            
            if predicted != actual and predicted != "unknown" and actual != "unknown":
                confusion_key = f"{predicted} -> {actual}"
                misclassifications[confusion_key] += 1
                route_confusion[predicted][actual] += 1
        
        return {
            "total_misclassifications": sum(misclassifications.values()),
            "misclassification_types": dict(misclassifications),
            "route_confusion_matrix": {k: dict(v) for k, v in route_confusion.items()},
            "most_common_error": max(misclassifications.items(), key=lambda x: x[1]) if misclassifications else None
        }
    
    def _generate_training_candidates(self, patterns: List[Dict[str, Any]], cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate training data candidates from edge case patterns."""
        candidates = []
        
        # Process high-severity patterns first
        for pattern in sorted(patterns, key=lambda x: x["severity"], reverse=True)[:10]:
            # Find the best examples from this pattern
            pattern_cases = [case for case in cases 
                           if self._case_matches_pattern(case, pattern)]
            
            if not pattern_cases:
                continue
            
            # Select diverse examples
            selected_examples = self._select_diverse_examples(pattern_cases, max_examples=3)
            
            for example in selected_examples:
                # Determine correct label based on context analysis
                correct_label = self._infer_correct_label(example)
                
                candidates.append({
                    "text": example.get("text", ""),
                    "predicted_label": example.get("predicted_route", "unknown"),
                    "suggested_correct_label": correct_label,
                    "confidence_issue": example.get("predicted_confidence", 0.0),
                    "pattern_severity": pattern["severity"],
                    "source": example.get("context_source", "unknown"),
                    "edge_case_type": example.get("edge_case_type", "unknown"),
                    "reasoning": self._explain_label_reasoning(example, correct_label)
                })
        
        return candidates
    
    def _case_matches_pattern(self, case: Dict[str, Any], pattern: Dict[str, Any]) -> bool:
        """Check if a case matches a pattern."""
        case_text = case.get("text", "").lower()
        pattern_text = pattern["representative_text"].lower()
        
        # Simple similarity check - could be enhanced with more sophisticated matching
        common_words = set(case_text.split()) & set(pattern_text.split())
        return len(common_words) >= 2 or case.get("edge_case_type") in pattern["edge_types"]
    
    def _select_diverse_examples(self, cases: List[Dict[str, Any]], max_examples: int = 3) -> List[Dict[str, Any]]:
        """Select diverse examples from a set of cases."""
        if len(cases) <= max_examples:
            return cases
        
        # Sort by confidence to get a range
        sorted_cases = sorted(cases, key=lambda x: x.get("predicted_confidence", 0.0))
        
        # Select examples from different confidence ranges
        selected = []
        if len(sorted_cases) >= 3:
            selected.append(sorted_cases[0])  # Lowest confidence
            selected.append(sorted_cases[len(sorted_cases)//2])  # Medium confidence
            selected.append(sorted_cases[-1])  # Highest confidence
        else:
            selected = sorted_cases[:max_examples]
        
        return selected[:max_examples]
    
    def _infer_correct_label(self, case: Dict[str, Any]) -> str:
        """Infer the correct label for a misclassified case."""
        text = case.get("text", "").lower()
        predicted = case.get("predicted_route", "")
        
        # Use heuristics to infer correct label
        question_indicators = ["what", "how", "when", "where", "why", "who", "which", "explain", "tell me about"]
        action_indicators = ["show me", "check", "get", "close", "stop", "start", "run", "execute", "monitor"]
        
        question_score = sum(1 for qi in question_indicators if qi in text)
        action_score = sum(1 for ai in action_indicators if ai in text)
        
        if question_score > action_score:
            return "gen"
        elif action_score > question_score:
            return "act"
        else:
            # If unclear, opposite of predicted might be correct (assuming misclassification)
            return "act" if predicted == "gen" else "gen"
    
    def _explain_label_reasoning(self, case: Dict[str, Any], suggested_label: str) -> str:
        """Explain why a label was suggested for a case."""
        text = case.get("text", "").lower()
        predicted = case.get("predicted_route", "")
        
        if suggested_label == "gen":
            if any(qi in text for qi in ["what", "how", "why", "explain"]):
                return "Contains question words indicating information request"
            else:
                return "Appears to be seeking information rather than action"
        elif suggested_label == "act":
            if any(ai in text for ai in ["show me", "check", "get", "status"]):
                return "Contains action words indicating system operation request"
            else:
                return "Appears to be requesting system action rather than information"
        else:
            return f"Uncertain classification, opposite of predicted '{predicted}'"
    
    def _generate_recommendations(self, patterns: List[Dict[str, Any]], stats: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # High edge case rate recommendation
        if stats.get("edge_case_rate", 0) > 0.1:  # >10% edge case rate
            recommendations.append({
                "priority": "high",
                "category": "performance",
                "title": "High edge case rate detected",
                "description": f"Edge case rate of {stats['edge_case_rate']:.2%} indicates significant router accuracy issues",
                "action": "Immediate retraining with collected edge cases recommended",
                "impact": "Will reduce misclassifications and improve user experience"
            })
        
        # Low confidence recommendations
        if stats.get("avg_confidence", 1.0) < 0.6:
            recommendations.append({
                "priority": "medium",
                "category": "confidence",
                "title": "Low average confidence scores",
                "description": f"Average confidence of {stats['avg_confidence']:.3f} suggests model uncertainty",
                "action": "Consider confidence threshold adjustment or model retraining",
                "impact": "Will improve decision reliability"
            })
        
        # Pattern-specific recommendations
        for pattern in patterns[:3]:  # Top 3 patterns
            if pattern["severity"] > 5.0:
                recommendations.append({
                    "priority": "high",
                    "category": "pattern",
                    "title": f"Critical pattern: {pattern['representative_text'][:40]}...",
                    "description": f"High-severity pattern with {pattern['sample_count']} cases",
                    "action": f"Add training examples for this pattern type: {pattern['edge_types']}",
                    "impact": "Will resolve systematic misclassifications"
                })
        
        # iPhone Shortcut specific recommendations
        if stats.get("shortcut_session_count", 0) > stats.get("total_decisions", 1) * 0.3:
            recommendations.append({
                "priority": "medium",
                "category": "voice_optimization",
                "title": "High iPhone Shortcut usage detected",
                "description": "Significant voice command usage requires voice-optimized training",
                "action": "Expand training dataset with voice command patterns",
                "impact": "Will improve voice command recognition accuracy"
            })
        
        return sorted(recommendations, key=lambda x: {"high": 3, "medium": 2, "low": 1}[x["priority"]], reverse=True)
    
    def export_training_candidates(self, output_path: Path, candidates: List[Dict[str, Any]]):
        """Export training candidates to TSV format."""
        print(f"💾 Exporting {len(candidates)} training candidates to {output_path}")
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write("text\tlabel\tpredicted_label\tconfidence\tedge_case_type\tsource\treasoning\n")
            
            # Write candidates
            for candidate in candidates:
                f.write(f"{candidate['text']}\t{candidate['suggested_correct_label']}\t{candidate['predicted_label']}\t{candidate['confidence_issue']:.3f}\t{candidate['edge_case_type']}\t{candidate['source']}\t{candidate['reasoning']}\n")
        
        print(f"✅ Training candidates exported to {output_path}")


def main():
    """Main analysis function."""
    parser = argparse.ArgumentParser(description="Analyze TinyIntent edge cases for router improvement")
    parser.add_argument("--hours", type=int, default=24, help="Time window in hours (default: 24)")
    parser.add_argument("--min-samples", type=int, default=3, help="Minimum samples per pattern (default: 3)")
    parser.add_argument("--export-candidates", type=str, help="Export training candidates to TSV file")
    parser.add_argument("--output", type=str, help="Output analysis results to JSON file")
    parser.add_argument("--db-path", type=str, help="Path to edge case database")
    
    args = parser.parse_args()
    
    print("🔍 TinyIntent Edge Case Analysis")
    print("=" * 50)
    
    # Initialize analyzer
    db_path = Path(args.db_path) if args.db_path else None
    analyzer = EdgeCaseAnalyzer(db_path)
    
    # Run analysis
    results = analyzer.analyze_patterns(args.hours, args.min_samples)
    
    if "error" in results:
        print(f"❌ Analysis failed: {results['error']}")
        return 1
    
    # Display key findings
    print("\n📈 Key Findings:")
    print(f"   • {len(results['patterns'])} significant patterns identified")
    print(f"   • {len(results['training_candidates'])} training candidates generated")
    print(f"   • {len(results['recommendations'])} recommendations created")
    
    # Display top recommendations
    if results["recommendations"]:
        print("\n🎯 Top Recommendations:")
        for i, rec in enumerate(results["recommendations"][:3], 1):
            print(f"   {i}. [{rec['priority'].upper()}] {rec['title']}")
            print(f"      {rec['description']}")
            print(f"      Action: {rec['action']}")
    
    # Export training candidates if requested
    if args.export_candidates and results["training_candidates"]:
        output_path = Path(args.export_candidates)
        analyzer.export_training_candidates(output_path, results["training_candidates"])
    
    # Save full results if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2, default=str)
        print(f"📄 Full analysis results saved to {output_path}")
    
    print("\n✅ Edge case analysis completed!")
    return 0


if __name__ == "__main__":
    sys.exit(main())