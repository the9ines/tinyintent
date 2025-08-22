
"""
TinyIntent Episode Logger

Handles the logging of helper and router episodes to both NDJSON and SQLite.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from queue import Queue
import hashlib

from tinyintent.data.episodes.schema import (
    EPISODES_TABLE_SCHEMA,
    ROUTER_METRICS_TABLE_SCHEMA,
    ROUTER_EPISODES_TABLE_SCHEMA,
    INDEX_SCHEMAS
)
from tinyintent.bridge.logs.sanitize import sanitize_dict

class EpisodeLogger:
    """Logs helper episodes for router retraining."""
    
    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path(__file__).parent.parent.parent / "data" / "episodes"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.ndjson_file = self.data_dir / "events.ndjson"
        self.db_file = self.data_dir / "events.db"
        
        self.max_file_size = 100 * 1024 * 1024
        
        self.episode_queue = Queue()
        self.shutdown_event = threading.Event()
        self.worker_thread = threading.Thread(target=self._process_episodes, daemon=True)
        self.worker_thread.start()
        
        self._init_database()
    
    def _init_database(self):
        """Initialize SQLite database schema."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.execute(EPISODES_TABLE_SCHEMA)
                conn.execute(ROUTER_METRICS_TABLE_SCHEMA)
                conn.execute(ROUTER_EPISODES_TABLE_SCHEMA)
                for index_schema in INDEX_SCHEMAS:
                    conn.execute(index_schema)
                conn.commit()
        except Exception as e:
            print(f"Warning: Failed to initialize episode database: {e}")
    
    def log_episode(self, session_id: str, action: str, helper_id: str, 
                   input_data: Dict[str, Any], status_code: int, success: bool,
                   approval_token_id: str = None, idempotency_key: str = None,
                   error_code: str = None):
        """Log an episode event (non-blocking)."""
        try:
            episode = {
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "session_id": session_id,
                "action": action,
                "helper_id": helper_id,
                "input_hash": self._hash_input(input_data),
                "approval_token_id": approval_token_id,
                "idempotency_key": idempotency_key,
                "status_code": status_code,
                "success": success,
                "error_code": error_code
            }
            self.episode_queue.put(episode)
        except Exception as e:
            print(f"Warning: Failed to queue episode: {e}")
    
    def log_helper_violation(self, session_id: str, helper_id: str, 
                           violation_type: str, error_code: str, 
                           details: Dict[str, Any] = None):
        """M10.7: Log helper sandbox/capability violation (non-blocking)."""
        try:
            violation = {
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "session_id": session_id,
                "action": f"{violation_type}_violation",
                "helper_id": helper_id,
                "violation_type": violation_type,
                "error_code": error_code,
                "details": details or {},
                "status_code": 403,  # All violations are 403 Forbidden
                "success": False
            }
            self.episode_queue.put(violation)
        except Exception as e:
            print(f"Warning: Failed to queue violation: {e}")
    
    def _hash_input(self, input_data: Dict[str, Any]) -> str:
        """Create consistent hash of input data."""
        input_str = json.dumps(input_data, sort_keys=True)
        return hashlib.sha256(input_str.encode()).hexdigest()[:16]
    
    def _process_episodes(self):
        """Background thread to process episode queue."""
        while not self.shutdown_event.is_set():
            try:
                try:
                    episode = self.episode_queue.get(timeout=1.0)
                except:
                    continue
                
                self._write_ndjson(episode)
                self._write_sqlite(episode)
                
                self.episode_queue.task_done()
            except Exception as e:
                print(f"Warning: Failed to process episode: {e}")
    
    def _write_ndjson(self, episode: Dict[str, Any]):
        """Write episode to NDJSON file with rotation."""
        try:
            if self.ndjson_file.exists() and self.ndjson_file.stat().st_size > self.max_file_size:
                self._rotate_ndjson()
            
            sanitized_episode = sanitize_dict(episode)
            
            with open(self.ndjson_file, 'a') as f:
                f.write(json.dumps(sanitized_episode) + '\n')
                
        except Exception as e:
            print(f"Warning: Failed to write NDJSON episode: {e}")
    
    def _write_sqlite(self, episode: Dict[str, Any]):
        """Write episode to SQLite database."""
        try:
            sanitized_episode = sanitize_dict(episode)
            
            with sqlite3.connect(self.db_file, timeout=5.0) as conn:
                conn.execute("""
                    INSERT INTO episodes (
                        timestamp, session_id, action, helper_id, input_hash,
                        approval_token_id, idempotency_key, status_code, 
                        success, error_code
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sanitized_episode["timestamp"],
                    sanitized_episode["session_id"], 
                    sanitized_episode["action"],
                    sanitized_episode["helper_id"],
                    sanitized_episode["input_hash"],
                    sanitized_episode["approval_token_id"],
                    sanitized_episode["idempotency_key"],
                    sanitized_episode["status_code"],
                    sanitized_episode["success"],
                    sanitized_episode["error_code"]
                ))
                conn.commit()
                
        except Exception as e:
            print(f"Warning: Failed to write SQLite episode: {e}")
    
    def _rotate_ndjson(self):
        """Rotate NDJSON file when it gets too large."""
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            rotated_file = self.data_dir / f"events_{timestamp}.ndjson"
            self.ndjson_file.rename(rotated_file)
            print(f"Rotated NDJSON file to {rotated_file}")
        except Exception as e:
            print(f"Warning: Failed to rotate NDJSON file: {e}")
    
    def get_recent_episodes(self, limit: int = 100) -> list:
        """Get recent episodes for analysis."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("SELECT * FROM episodes ORDER BY created_at DESC LIMIT ?", (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Warning: Failed to retrieve episodes: {e}")
            return []
    
    def get_episode_stats(self) -> Dict[str, Any]:
        """Get episode statistics."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.execute("SELECT COUNT(*), COUNT(CASE WHEN success = 1 THEN 1 END) FROM episodes")
                row = cursor.fetchone()
                if row:
                    return {"total_episodes": row[0], "success_count": row[1]}
                else:
                    return {"total_episodes": 0}
        except Exception as e:
            print(f"Warning: Failed to get episode stats: {e}")
            return {"total_episodes": 0, "error": str(e)}
    
    def shutdown(self):
        """Gracefully shutdown episode logger."""
        self.shutdown_event.set()
        self.worker_thread.join(timeout=5.0)

# Global episode logger instance
episode_logger = EpisodeLogger()
