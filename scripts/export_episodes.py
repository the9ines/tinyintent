#!/usr/bin/env python3
"""
TinyIntent Episode Export - M5.3: Learning Loop Automation

Converts logged episodes into training data for router retraining.
Extracts (text, route_label) pairs from successful preview episodes.
"""

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set, Any
import hashlib


class EpisodeExporter:
    """Exports episodes to router training format."""
    
    def __init__(self, data_dir: Path = None, router_dir: Path = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "data" / "episodes"
        self.router_dir = router_dir or Path(__file__).parent.parent / "router" / "data"
        
        self.db_file = self.data_dir / "events.db"
        self.output_file = self.router_dir / "intents.tsv"
        
        # Create router data directory if it doesn't exist
        self.router_dir.mkdir(parents=True, exist_ok=True)
    
    def export_training_data(self, append: bool = True, min_confidence: float = 0.0, 
                            include_router_episodes: bool = True, dry_run: bool = False) -> Dict[str, int]:
        """
        Export episodes to training TSV format.
        
        Args:
            append: If True, append to existing file; if False, overwrite
            min_confidence: Minimum confidence threshold for inclusion
            include_router_episodes: If True, include M7.4 router episodes with overrides
            dry_run: If True, only print statistics without writing to file (M7.5)
            
        Returns:
            Dict with export statistics
        """
        if not self.db_file.exists():
            print(f"Error: Episode database not found at {self.db_file}")
            return {"exported": 0, "skipped": 0, "duplicates": 0, "overrides": 0}
        
        # Get existing training data to avoid duplicates
        existing_pairs = self._load_existing_training_data() if append else set()
        
        # Extract episodes from database
        episodes = self._extract_preview_episodes()
        
        # M7.4: Extract router episodes with overrides (prioritized for training)
        router_episodes = []
        if include_router_episodes:
            router_episodes = self._extract_router_episodes()
        
        # Convert to training pairs
        training_pairs = self._episodes_to_training_pairs(episodes, min_confidence)
        
        # M7.4: Convert router episodes to training pairs (with special labeling)
        router_training_pairs = self._router_episodes_to_training_pairs(router_episodes, min_confidence)
        
        # Combine training pairs - prioritize router episodes with overrides
        all_training_pairs = router_training_pairs + training_pairs
        
        # Filter out duplicates
        new_pairs = []
        duplicate_count = 0
        override_count = 0
        
        for text, label, label_source in all_training_pairs:
            pair_hash = self._hash_training_pair(text, label)
            if pair_hash not in existing_pairs:
                new_pairs.append((text, label, label_source))
                existing_pairs.add(pair_hash)
                if label_source == "override":
                    override_count += 1
            else:
                duplicate_count += 1
        
        # Write training data or perform dry run
        if dry_run:
            # M7.5: Dry run - perform analysis without writing
            exported_count = len(new_pairs)
            dry_run_stats = self._perform_dry_run_analysis(new_pairs, all_training_pairs)
            
            stats = {
                "exported": exported_count,
                "skipped": len(all_training_pairs) - exported_count - duplicate_count,
                "duplicates": duplicate_count,
                "overrides": override_count,
                "total_episodes": len(episodes),
                "router_episodes": len(router_episodes),
                "output_file": str(self.output_file),
                "dry_run": True,
                **dry_run_stats
            }
            
            self._log_dry_run_stats(stats)
        else:
            # Normal export - write to file
            exported_count = self._write_enhanced_training_data(new_pairs, append)
            
            stats = {
                "exported": exported_count,
                "skipped": len(all_training_pairs) - exported_count - duplicate_count,
                "duplicates": duplicate_count,
                "overrides": override_count,
                "total_episodes": len(episodes),
                "router_episodes": len(router_episodes),
                "output_file": str(self.output_file),
                "dry_run": False
            }
            
            self._log_enhanced_export_stats(stats)
        
        return stats
    
    def _extract_preview_episodes(self) -> List[Dict]:
        """Extract successful preview episodes from database."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT 
                        e.session_id,
                        e.helper_id,
                        e.input_hash,
                        e.timestamp,
                        s.text,
                        s.route_final
                    FROM episodes e
                    JOIN (
                        SELECT DISTINCT session_id, text, route_final
                        FROM store_events 
                        WHERE route_final IN ('act', 'gen')
                    ) s ON e.session_id = s.session_id
                    WHERE e.status_code = 200 
                    AND e.action = 'preview'
                    AND e.success = 1
                    ORDER BY e.timestamp DESC
                """)
                
                episodes = [dict(row) for row in cursor.fetchall()]
                
        except sqlite3.OperationalError:
            # Fallback if store_events table doesn't exist
            print("Warning: store_events table not found, using episodes table only")
            episodes = self._extract_episodes_fallback()
        
        return episodes
    
    def _extract_episodes_fallback(self) -> List[Dict]:
        """Fallback method using only episodes table."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT 
                        session_id,
                        helper_id,
                        input_hash,
                        timestamp,
                        'act' as route_final,
                        CASE 
                            WHEN helper_id = 'bot_guard' THEN 'Show trading positions'
                            WHEN helper_id = 'log_tailer' THEN 'Show error logs'
                            WHEN helper_id = 'ssh_ops' THEN 'Check system status'
                            ELSE 'Unknown operation'
                        END as text
                    FROM episodes
                    WHERE status_code = 200 
                    AND action = 'preview'
                    AND success = 1
                    ORDER BY timestamp DESC
                """)
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            print(f"Error extracting episodes: {e}")
            return []
    
    def _extract_router_episodes(self) -> List[Dict]:
        """Extract router episodes for M7.4 self-correction training."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT 
                        timestamp,
                        session_id,
                        text,
                        original_route,
                        confidence,
                        intent,
                        is_abstain,
                        abstain_reason,
                        is_override,
                        override_route,
                        override_confidence,
                        label_source,
                        text_hash
                    FROM router_episodes
                    ORDER BY timestamp DESC
                """)
                
                return [dict(row) for row in cursor.fetchall()]
                
        except sqlite3.OperationalError:
            # Router episodes table doesn't exist yet
            print("Info: router_episodes table not found (M7.4 not yet deployed)")
            return []
        except Exception as e:
            print(f"Error extracting router episodes: {e}")
            return []
    
    def _episodes_to_training_pairs(self, episodes: List[Dict], 
                                   min_confidence: float) -> List[Tuple[str, str, str]]:
        """Convert episodes to (text, route_label, label_source) training pairs."""
        training_pairs = []
        
        for episode in episodes:
            text = episode.get('text', '').strip()
            route_final = episode.get('route_final', '').strip()
            
            if not text or not route_final:
                continue
            
            # Map route_final to training labels
            if route_final == 'act':
                label = 'act'
            elif route_final == 'gen':
                label = 'gen'
            else:
                continue  # Skip unknown routes
            
            # M10.1: Check if this episode was derived from agent suggestions
            label_source = self._determine_label_source(episode)
            
            training_pairs.append((text, label, label_source))
        
        return training_pairs
    
    def _router_episodes_to_training_pairs(self, router_episodes: List[Dict], 
                                          min_confidence: float) -> List[Tuple[str, str, str]]:
        """Convert router episodes to (text, route_label, label_source) training pairs. M7.4"""
        training_pairs = []
        
        for episode in router_episodes:
            text = episode.get('text', '').strip()
            confidence = episode.get('confidence', 0.0)
            is_abstain = episode.get('is_abstain', False)
            is_override = episode.get('is_override', False)
            label_source = episode.get('label_source', 'router')
            
            if not text:
                continue
            
            # Skip low confidence entries unless they're overrides
            if confidence < min_confidence and not is_override:
                continue
            
            # Determine the correct label
            label = None
            
            if is_override:
                # Override episodes use the override route as ground truth
                override_route = episode.get('override_route', '').strip()
                if override_route in ['gen', 'act']:
                    label = override_route
                    label_source = "override"  # Mark as high-priority override label
            elif not is_abstain:
                # Non-abstain router decisions
                original_route = episode.get('original_route', '').strip()
                if original_route in ['gen', 'act']:
                    label = original_route
            else:
                # Abstain cases - skip for now (could be used for confidence calibration later)
                continue
            
            if label:
                training_pairs.append((text, label, label_source))
        
        return training_pairs
    
    def _determine_label_source(self, episode: Dict) -> str:
        """
        M10.1: Determine the source of this training example.
        
        Checks if episode was derived from agent suggestions to enable
        tracking of suggestion impact on router performance.
        
        Args:
            episode: Episode dictionary
            
        Returns:
            String indicating label source: "suggestion_seed", "suggestion", or "episode"
        """
        # Check if episode has suggestion source marker
        # This would be set by episodes that led to successful helper creation
        if episode.get('label_source') == 'suggestion':
            return 'suggestion'
        
        # Check if this episode was from a cluster exemplar that led to suggestions
        helper_id = episode.get('helper_id', '')
        session_id = episode.get('session_id', '')
        
        # Look for suggestion-related markers in episode data
        # This could be set when episodes are identified as cluster exemplars
        if self._is_suggestion_seed_episode(episode):
            return 'suggestion_seed'
        
        # Check if episode involves a helper that was created from suggestions
        if self._is_suggestion_derived_helper(helper_id):
            return 'suggestion'
        
        # Default to regular episode
        return 'episode'
    
    def _is_suggestion_seed_episode(self, episode: Dict) -> bool:
        """Check if episode was a seed for agent suggestions."""
        # Check database for episodes that were cluster exemplars
        try:
            session_id = episode.get('session_id', '')
            if not session_id:
                return False
            
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM events 
                    WHERE session_id = ? 
                    AND (action = 'agent_suggest' OR labels LIKE '%suggestion_seed%')
                """, (session_id,))
                
                count = cursor.fetchone()[0]
                return count > 0
                
        except Exception:
            return False
    
    def _is_suggestion_derived_helper(self, helper_id: str) -> bool:
        """Check if helper was created from suggestions."""
        if not helper_id:
            return False
        
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM events 
                    WHERE action = 'agent_create_from_suggestion'
                    AND helper_id = ?
                """, (helper_id,))
                
                count = cursor.fetchone()[0]
                return count > 0
                
        except Exception:
            return False
    
    def _load_existing_training_data(self) -> Set[str]:
        """Load existing training data to avoid duplicates."""
        existing_pairs = set()
        
        if self.output_file.exists():
            try:
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and '\t' in line:
                            text, label = line.split('\t', 1)
                            pair_hash = self._hash_training_pair(text, label)
                            existing_pairs.add(pair_hash)
            except Exception as e:
                print(f"Warning: Could not load existing training data: {e}")
        
        return existing_pairs
    
    def _hash_training_pair(self, text: str, label: str) -> str:
        """Create hash of training pair for deduplication."""
        pair_str = f"{text.strip()}\t{label.strip()}"
        return hashlib.sha256(pair_str.encode('utf-8')).hexdigest()[:16]
    
    def _write_training_data(self, training_pairs: List[Tuple[str, str]], 
                            append: bool) -> int:
        """Write training pairs to TSV file (legacy format)."""
        if not training_pairs:
            print("No new training data to export")
            return 0
        
        mode = 'a' if append else 'w'
        
        try:
            with open(self.output_file, mode, encoding='utf-8') as f:
                for text, label in training_pairs:
                    f.write(f"{text}\t{label}\n")
            
            return len(training_pairs)
            
        except Exception as e:
            print(f"Error writing training data: {e}")
            return 0
    
    def _write_enhanced_training_data(self, training_pairs: List[Tuple[str, str, str]], 
                                     append: bool) -> int:
        """Write enhanced training pairs with label_source to TSV file. M7.4"""
        if not training_pairs:
            print("No new training data to export")
            return 0
        
        mode = 'a' if append else 'w'
        
        try:
            with open(self.output_file, mode, encoding='utf-8') as f:
                for text, label, label_source in training_pairs:
                    # Enhanced format: text<TAB>label<TAB>label_source
                    # This allows the training script to prioritize override samples
                    f.write(f"{text}\t{label}\t{label_source}\n")
            
            return len(training_pairs)
            
        except Exception as e:
            print(f"Error writing enhanced training data: {e}")
            return 0
    
    def _log_export_stats(self, stats: Dict[str, int]):
        """Log export statistics (legacy)."""
        print(f"Episode Export Complete:")
        print(f"  Total episodes processed: {stats['total_episodes']}")
        print(f"  Training pairs exported: {stats['exported']}")
        print(f"  Duplicates skipped: {stats['duplicates']}")
        print(f"  Invalid entries skipped: {stats['skipped']}")
        print(f"  Output file: {stats['output_file']}")
        
        if stats['exported'] > 0:
            print(f"✅ Successfully exported {stats['exported']} new training examples")
        elif stats['duplicates'] > 0:
            print("ℹ️  No new training data (all entries were duplicates)")
        else:
            print("⚠️  No valid training data found in episodes")
    
    def _log_enhanced_export_stats(self, stats: Dict[str, int]):
        """Log enhanced export statistics with M7.4 features."""
        print(f"M7.4 Enhanced Episode Export Complete:")
        print(f"  Total episodes processed: {stats['total_episodes']}")
        print(f"  Router episodes processed: {stats['router_episodes']}")
        print(f"  Training pairs exported: {stats['exported']}")
        print(f"  Override labels exported: {stats['overrides']}")
        print(f"  Duplicates skipped: {stats['duplicates']}")
        print(f"  Invalid entries skipped: {stats['skipped']}")
        print(f"  Output file: {stats['output_file']}")
        
        if stats['exported'] > 0:
            print(f"✅ Successfully exported {stats['exported']} new training examples")
            if stats['overrides'] > 0:
                print(f"🎯 Includes {stats['overrides']} high-priority override samples for active learning")
        elif stats['duplicates'] > 0:
            print("ℹ️  No new training data (all entries were duplicates)")
        else:
            print("⚠️  No valid training data found in episodes")
        
        # Additional M7.4 insights
        if stats['router_episodes'] > 0:
            print(f"📊 M7.4 Self-Correction: {stats['router_episodes']} router decisions logged for analysis")
        if stats['overrides'] > stats['exported'] * 0.1:
            print("💡 High override rate detected - consider reviewing router confidence thresholds")
    
    def _perform_dry_run_analysis(self, new_pairs: List[Tuple[str, str, str]], 
                                 all_pairs: List[Tuple[str, str, str]]) -> Dict[str, Any]:
        """Perform detailed analysis for dry-run mode. M7.5"""
        # Count samples by label_source
        label_source_counts = {}
        label_counts = {}
        intent_distribution = {}
        
        for text, label, label_source in new_pairs:
            # Count by label source
            label_source_counts[label_source] = label_source_counts.get(label_source, 0) + 1
            
            # Count by label (gen/act)
            label_counts[label] = label_counts.get(label, 0) + 1
            
            # Extract intent from router episodes (if available)
            # For now, use label as a proxy for intent distribution
            intent_key = f"{label}_intent"
            intent_distribution[intent_key] = intent_distribution.get(intent_key, 0) + 1
        
        # Calculate percentages
        total = len(new_pairs)
        label_source_percentages = {}
        label_percentages = {}
        
        for source, count in label_source_counts.items():
            label_source_percentages[source] = (count / total * 100) if total > 0 else 0
        
        for label, count in label_counts.items():
            label_percentages[label] = (count / total * 100) if total > 0 else 0
        
        return {
            "label_source_counts": label_source_counts,
            "label_source_percentages": label_source_percentages,
            "label_counts": label_counts,
            "label_percentages": label_percentages,
            "intent_distribution": intent_distribution,
            "total_new_samples": total
        }
    
    def _log_dry_run_stats(self, stats: Dict[str, Any]):
        """Log dry-run statistics with detailed analysis. M7.5"""
        print(f"\n🔍 M7.5 Dry-Run Analysis - No files written")
        print(f"{'='*60}")
        print(f"📊 Sample Distribution:")
        print(f"  Total new training samples: {stats['total_new_samples']}")
        print(f"  Total episodes processed: {stats['total_episodes']}")
        print(f"  Router episodes processed: {stats['router_episodes']}")
        print(f"  Duplicates that would be skipped: {stats['duplicates']}")
        print(f"  Invalid entries that would be skipped: {stats['skipped']}")
        
        print(f"\n🎯 Label Source Breakdown:")
        for source, count in stats['label_source_counts'].items():
            percentage = stats['label_source_percentages'][source]
            print(f"  {source:>12}: {count:>4} samples ({percentage:>5.1f}%)")
        
        print(f"\n🏷️  Label Distribution:")
        for label, count in stats['label_counts'].items():
            percentage = stats['label_percentages'][label]
            print(f"  {label:>12}: {count:>4} samples ({percentage:>5.1f}%)")
        
        print(f"\n🧠 Training Impact:")
        if stats['overrides'] > 0:
            override_rate = (stats['overrides'] / stats['total_new_samples']) * 100
            print(f"  High-priority override samples: {stats['overrides']} ({override_rate:.1f}%)")
            if override_rate > 20:
                print(f"  ⚠️  High override rate detected - router may need retraining")
        
        if stats['router_episodes'] > 0:
            print(f"  Self-correction episodes available: {stats['router_episodes']}")
        
        print(f"\n💾 Output Target:")
        print(f"  Would write to: {stats['output_file']}")
        print(f"  Append mode: {'Yes' if not stats.get('append', True) == False else 'No'}")
        
        # Training readiness assessment
        print(f"\n✅ Training Readiness Assessment:")
        total_samples = stats['total_new_samples']
        if total_samples >= 100:
            print(f"  ✅ Sample size adequate ({total_samples} samples)")
        elif total_samples >= 50:
            print(f"  ⚠️  Sample size marginal ({total_samples} samples - recommend >100)")
        else:
            print(f"  ❌ Sample size insufficient ({total_samples} samples - need >50)")
        
        # Label balance check
        gen_count = stats['label_counts'].get('gen', 0)
        act_count = stats['label_counts'].get('act', 0)
        
        if gen_count > 0 and act_count > 0:
            balance_ratio = min(gen_count, act_count) / max(gen_count, act_count)
            if balance_ratio > 0.3:
                print(f"  ✅ Label balance good (gen:{gen_count}, act:{act_count})")
            else:
                print(f"  ⚠️  Label imbalance detected (gen:{gen_count}, act:{act_count})")
        
        override_samples = stats['overrides']
        if override_samples > 0:
            print(f"  ✅ Override samples available for active learning ({override_samples})")
        
        print(f"\n🚀 Next Steps:")
        if total_samples >= 50:
            print(f"  1. Run: make learn-dry    # This dry run")
            print(f"  2. Run: make learn        # Actual retraining if satisfied")
            print(f"  3. Check: GET /router/train_summary  # Review training results")
        else:
            print(f"  1. Generate more episodes to reach minimum 50 samples")
            print(f"  2. Consider manual override samples for key intents")
        
        print(f"{'='*60}")
        print(f"🔍 Dry-run complete - no files modified")
    
    def get_export_summary(self) -> Dict[str, int]:
        """Get summary of available export data."""
        if not self.db_file.exists():
            return {"total_episodes": 0, "preview_episodes": 0, "existing_training": 0}
        
        try:
            with sqlite3.connect(self.db_file) as conn:
                # Count total episodes
                cursor = conn.execute("SELECT COUNT(*) FROM episodes")
                total_episodes = cursor.fetchone()[0]
                
                # Count preview episodes
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM episodes 
                    WHERE status_code = 200 AND action = 'preview' AND success = 1
                """)
                preview_episodes = cursor.fetchone()[0]
                
                # Count existing training data
                existing_training = 0
                if self.output_file.exists():
                    with open(self.output_file, 'r') as f:
                        existing_training = sum(1 for line in f if line.strip())
                
                return {
                    "total_episodes": total_episodes,
                    "preview_episodes": preview_episodes,
                    "existing_training": existing_training
                }
                
        except Exception as e:
            print(f"Error getting export summary: {e}")
            return {"total_episodes": 0, "preview_episodes": 0, "existing_training": 0}


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Export episodes to router training data",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        help="Directory containing episodes database"
    )
    
    parser.add_argument(
        '--router-dir', 
        type=Path,
        help="Router data directory for output"
    )
    
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help="Overwrite existing training data instead of appending"
    )
    
    parser.add_argument(
        '--min-confidence',
        type=float,
        default=0.0,
        help="Minimum confidence threshold for inclusion"
    )
    
    parser.add_argument(
        '--summary',
        action='store_true',
        help="Show export summary without exporting"
    )
    
    parser.add_argument(
        '--no-router-episodes',
        action='store_true',
        help="Exclude M7.4 router episodes with overrides (legacy mode)"
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help="M7.5: Print counts of samples by label_source, per-intent distribution, and total exported without writing TSV"
    )
    
    args = parser.parse_args()
    
    # Create exporter
    exporter = EpisodeExporter(
        data_dir=args.data_dir,
        router_dir=args.router_dir
    )
    
    if args.summary:
        # Show summary only
        summary = exporter.get_export_summary()
        print("Export Summary:")
        print(f"  Total episodes in database: {summary['total_episodes']}")
        print(f"  Successful preview episodes: {summary['preview_episodes']}")
        print(f"  Existing training examples: {summary['existing_training']}")
        return 0
    
    # Export training data
    stats = exporter.export_training_data(
        append=not args.overwrite,
        min_confidence=args.min_confidence,
        include_router_episodes=not args.no_router_episodes,
        dry_run=args.dry_run
    )
    
    # Return exit code based on success
    return 0 if stats['exported'] >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())