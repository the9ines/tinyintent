"""
Event logging service for TinyIntent Experience Store.
Logs all requests and responses to NDJSON format for analysis and learning.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import hashlib


@dataclass
class EventLog:
    """Event log entry matching the PRD schema."""
    ts: str                          # ISO timestamp
    session_id: str                  # Session identifier
    text: str                        # Original user text
    route_pred: Optional[str]        # Predicted route (auto routing)
    route_final: str                 # Final route used
    model_used: Optional[str]        # Model tag used
    latency_ms: Optional[int]        # Response latency
    helper_id: Optional[str] = None  # Helper used (for act route)
    helper_input: Optional[Dict] = None  # Helper input (for act route)
    preview_json: Optional[Dict] = None  # Preview result (for act route)
    executed: Optional[bool] = None  # Whether action was executed
    success: Optional[bool] = None   # Whether request succeeded
    feedback: Optional[str] = None   # User feedback
    error_code: Optional[str] = None # Error code if failed
    labels: Optional[list] = None    # Classification labels
    hash: str = ""                   # Content hash for deduplication
    
    def __post_init__(self):
        """Generate content hash after initialization."""
        if not self.hash:
            # Create hash from text and route for deduplication
            content = f"{self.text}:{self.route_final}"
            self.hash = hashlib.sha256(content.encode()).hexdigest()[:16]


class EventLogger:
    """Handles logging events to NDJSON format."""
    
    def __init__(self, events_file: Optional[str] = None):
        """Initialize with path to events file."""
        if events_file is None:
            # Default to events.ndjson in data/episodes
            project_root = Path(__file__).parent.parent
            self.events_file = project_root / "data" / "episodes" / "events.ndjson"
        else:
            self.events_file = Path(events_file)
        
        # Ensure directory exists
        self.events_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log_event(self, event: EventLog) -> None:
        """Log an event to the NDJSON file."""
        try:
            # Convert to dict and then to JSON
            event_dict = asdict(event)
            json_line = json.dumps(event_dict, separators=(',', ':'))
            
            # Append to file
            with open(self.events_file, 'a', encoding='utf-8') as f:
                f.write(json_line + '\n')
                
        except Exception as e:
            print(f"Warning: Failed to log event: {e}")
    
    def log_request(
        self,
        session_id: str,
        text: str,
        route_final: str,
        model_used: Optional[str] = None,
        latency_ms: Optional[int] = None,
        route_pred: Optional[str] = None,
        success: bool = True,
        error_code: Optional[str] = None,
        helper_id: Optional[str] = None,
        helper_input: Optional[Dict] = None,
        preview_json: Optional[Dict] = None,
        executed: Optional[bool] = None
    ) -> None:
        """Log a request event with simplified interface."""
        event = EventLog(
            ts=datetime.utcnow().isoformat() + 'Z',
            session_id=session_id,
            text=text,
            route_pred=route_pred,
            route_final=route_final,
            model_used=model_used,
            latency_ms=latency_ms,
            helper_id=helper_id,
            helper_input=helper_input,
            preview_json=preview_json,
            executed=executed,
            success=success,
            error_code=error_code
        )
        self.log_event(event)
    
    def log_feedback(self, session_id: str, feedback: str) -> None:
        """Log feedback for a session."""
        event = EventLog(
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


class SessionManager:
    """Manages session IDs and episode tracking."""
    
    def __init__(self):
        """Initialize session manager."""
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def generate_session_id(self) -> str:
        """Generate a new unique session ID."""
        return str(uuid.uuid4())
    
    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session and return its ID."""
        if session_id is None:
            session_id = self.generate_session_id()
        
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
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists."""
        return session_id in self._sessions
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information."""
        return self._sessions.get(session_id)


# Global instances
event_logger = EventLogger()
session_manager = SessionManager()