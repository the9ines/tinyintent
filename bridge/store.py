"""
Experience Store for TinyIntent - SQLite and NDJSON logging.
Implements M2: Experience Store as specified in the PRD.
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class EventRecord:
    """Event record matching PRD schema exactly."""
    ts: str                          # ISO timestamp
    session_id: str                  # Session identifier
    text: str                        # Original user text
    route_pred: Optional[str]        # Predicted route (auto routing)
    route_final: str                 # Final route used
    model_used: Optional[str]        # Model tag used
    latency_ms: Optional[int]        # Response latency
    helper_id: Optional[str] = None  # Helper used (for act route)
    helper_input: Optional[str] = None  # Helper input JSON string (for act route)
    preview_json: Optional[str] = None  # Preview result JSON string (for act route)
    executed: Optional[bool] = None  # Whether action was executed
    success: Optional[bool] = None   # Whether request succeeded
    feedback: Optional[str] = None   # User feedback
    error_code: Optional[str] = None # Error code if failed
    labels: Optional[str] = None     # Classification labels JSON array string
    hash: str = ""                   # Content hash for deduplication
    
    def __post_init__(self):
        """Generate content hash after initialization."""
        if not self.hash:
            # Create hash from text and route for deduplication
            content = f"{self.text}:{self.route_final}"
            self.hash = hashlib.sha256(content.encode()).hexdigest()[:16]


class ExperienceStore:
    """Experience Store implementing NDJSON and SQLite logging."""
    
    def __init__(self, 
                 events_file: Optional[str] = None,
                 db_path: Optional[str] = None):
        """Initialize with paths to events file and database."""
        project_root = Path(__file__).parent.parent
        
        if events_file is None:
            self.events_file = project_root / "data" / "episodes" / "events.ndjson"
        else:
            self.events_file = Path(events_file)
        
        if db_path is None:
            db_default = os.getenv("EPISODES_DB_PATH", "data/episodes/events.db")
            self.db_path = project_root / db_default
        else:
            self.db_path = Path(db_path)
        
        # Ensure directories exist
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Session tracking
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def _init_database(self) -> None:
        """Initialize SQLite database with events table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    route_pred TEXT,
                    route_final TEXT NOT NULL,
                    model_used TEXT,
                    latency_ms INTEGER,
                    helper_id TEXT,
                    helper_input TEXT,
                    preview_json TEXT,
                    executed BOOLEAN,
                    success BOOLEAN,
                    feedback TEXT,
                    error_code TEXT,
                    labels TEXT,
                    hash TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON events(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON events(ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_hash ON events(hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_route_final ON events(route_final)")
            
            conn.commit()
    
    def log_event(self, event: EventRecord) -> None:
        """Log an event to both NDJSON and SQLite."""
        try:
            # Write to NDJSON
            self._write_ndjson(event)
            
            # Write to SQLite
            self._write_sqlite(event)
            
        except Exception as e:
            print(f"Warning: Failed to log event: {e}")
    
    def _write_ndjson(self, event: EventRecord) -> None:
        """Write event to NDJSON file."""
        event_dict = asdict(event)
        json_line = json.dumps(event_dict, separators=(',', ':'))
        
        with open(self.events_file, 'a', encoding='utf-8') as f:
            f.write(json_line + '\n')
    
    def _write_sqlite(self, event: EventRecord) -> None:
        """Write event to SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO events (
                    ts, session_id, text, route_pred, route_final, model_used,
                    latency_ms, helper_id, helper_input, preview_json, executed,
                    success, feedback, error_code, labels, hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.ts, event.session_id, event.text, event.route_pred,
                event.route_final, event.model_used, event.latency_ms,
                event.helper_id, event.helper_input, event.preview_json,
                event.executed, event.success, event.feedback, event.error_code,
                event.labels, event.hash
            ))
            conn.commit()
    
    def log_request(self,
                   session_id: str,
                   text: str,
                   route_final: str,
                   model_used: Optional[str] = None,
                   latency_ms: Optional[int] = None,
                   route_pred: Optional[str] = None,
                   success: Optional[bool] = True,
                   error_code: Optional[str] = None,
                   helper_id: Optional[str] = None,
                   helper_input: Optional[Dict] = None,
                   preview_json: Optional[Dict] = None,
                   executed: Optional[bool] = None,
                   labels: Optional[List[str]] = None) -> None:
        """Log a request event with simplified interface."""
        
        # Convert complex fields to JSON strings for storage
        helper_input_str = json.dumps(helper_input) if helper_input else None
        preview_json_str = json.dumps(preview_json) if preview_json else None
        labels_str = json.dumps(labels) if labels else None
        
        event = EventRecord(
            ts=datetime.utcnow().isoformat() + 'Z',
            session_id=session_id,
            text=text,
            route_pred=route_pred,
            route_final=route_final,
            model_used=model_used,
            latency_ms=latency_ms,
            helper_id=helper_id,
            helper_input=helper_input_str,
            preview_json=preview_json_str,
            executed=executed,
            success=success,
            error_code=error_code,
            labels=labels_str
        )
        self.log_event(event)
    
    def log_feedback(self, session_id: str, feedback: str) -> None:
        """Log feedback for a session."""
        event = EventRecord(
            ts=datetime.utcnow().isoformat() + 'Z',
            session_id=session_id,
            text="",  # Empty for feedback-only entries
            route_pred=None,
            route_final="feedback",
            model_used=None,
            latency_ms=None,
            feedback=feedback,
            success=True
        )
        self.log_event(event)
    
    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session and return its ID."""
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        self._sessions[session_id] = {
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'last_activity': datetime.utcnow().isoformat() + 'Z',
            'events': []
        }
        return session_id
    
    def update_session_activity(self, session_id: str) -> None:
        """Update last activity time for a session."""
        if session_id in self._sessions:
            self._sessions[session_id]['last_activity'] = datetime.utcnow().isoformat() + 'Z'
        else:
            # Create session if it doesn't exist
            self.create_session(session_id)
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions
    
    def get_session_events(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all events for a session from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM events WHERE session_id = ? ORDER BY ts",
                (session_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent events from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM events ORDER BY ts DESC LIMIT ?",
                (limit,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def cleanup_old_events(self, retention_days: int = None) -> int:
        """Clean up old events based on retention policy."""
        if retention_days is None:
            retention_days = int(os.getenv("RETENTION_DAYS", "30"))
        
        cutoff_date = datetime.utcnow().replace(microsecond=0)
        cutoff_date = cutoff_date.replace(day=cutoff_date.day - retention_days)
        cutoff_iso = cutoff_date.isoformat() + 'Z'
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM events WHERE ts < ?",
                (cutoff_iso,)
            )
            deleted_count = cursor.rowcount
            conn.commit()
        
        return deleted_count


# Global instance
experience_store = ExperienceStore()