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
from typing import Dict, List, Tuple, Set
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
    
    def export_training_data(self, append: bool = True, min_confidence: float = 0.0) -> Dict[str, int]:
        """
        Export episodes to training TSV format.
        
        Args:
            append: If True, append to existing file; if False, overwrite
            min_confidence: Minimum confidence threshold for inclusion
            
        Returns:
            Dict with export statistics
        """
        if not self.db_file.exists():
            print(f"Error: Episode database not found at {self.db_file}")
            return {"exported": 0, "skipped": 0, "duplicates": 0}
        
        # Get existing training data to avoid duplicates
        existing_pairs = self._load_existing_training_data() if append else set()
        
        # Extract episodes from database
        episodes = self._extract_preview_episodes()
        
        # Convert to training pairs
        training_pairs = self._episodes_to_training_pairs(episodes, min_confidence)
        
        # Filter out duplicates
        new_pairs = []
        duplicate_count = 0
        
        for text, label in training_pairs:
            pair_hash = self._hash_training_pair(text, label)
            if pair_hash not in existing_pairs:
                new_pairs.append((text, label))
                existing_pairs.add(pair_hash)
            else:
                duplicate_count += 1
        
        # Write training data
        exported_count = self._write_training_data(new_pairs, append)
        
        stats = {
            "exported": exported_count,
            "skipped": len(training_pairs) - exported_count - duplicate_count,
            "duplicates": duplicate_count,
            "total_episodes": len(episodes),
            "output_file": str(self.output_file)
        }
        
        self._log_export_stats(stats)
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
    
    def _episodes_to_training_pairs(self, episodes: List[Dict], 
                                   min_confidence: float) -> List[Tuple[str, str]]:
        """Convert episodes to (text, route_label) training pairs."""
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
            
            training_pairs.append((text, label))
        
        return training_pairs
    
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
        """Write training pairs to TSV file."""
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
    
    def _log_export_stats(self, stats: Dict[str, int]):
        """Log export statistics."""
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
        min_confidence=args.min_confidence
    )
    
    # Return exit code based on success
    return 0 if stats['exported'] >= 0 else 1


if __name__ == '__main__':
    sys.exit(main())