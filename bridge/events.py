"""
Event logging service for TinyIntent Experience Store.
Simplified wrapper around store.py for backwards compatibility.
"""

from store import experience_store, EventRecord
from typing import Dict, Any, Optional, List

# Re-export for backwards compatibility
EventLog = EventRecord

class EventLogger:
    """Simplified event logger wrapper around ExperienceStore."""
    
    def __init__(self):
        """Initialize using global experience store."""
        self.store = experience_store
    
    def log_event(self, event: EventRecord) -> None:
        """Log an event."""
        self.store.log_event(event)
    
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
        """Log a request event."""
        self.store.log_request(
            session_id=session_id,
            text=text,
            route_final=route_final,
            model_used=model_used,
            latency_ms=latency_ms,
            route_pred=route_pred,
            success=success,
            error_code=error_code,
            helper_id=helper_id,
            helper_input=helper_input,
            preview_json=preview_json,
            executed=executed,
            labels=labels
        )
    
    def log_feedback(self, session_id: str, feedback: str) -> None:
        """Log feedback for a session."""
        self.store.log_feedback(session_id, feedback)


class SessionManager:
    """Session manager wrapper around ExperienceStore."""
    
    def __init__(self):
        """Initialize using global experience store."""
        self.store = experience_store
    
    def generate_session_id(self) -> str:
        """Generate a new unique session ID."""
        import uuid
        return str(uuid.uuid4())
    
    def create_session(self, session_id: Optional[str] = None) -> str:
        """Create a new session."""
        return self.store.create_session(session_id)
    
    def update_session_activity(self, session_id: str) -> None:
        """Update session activity."""
        self.store.update_session_activity(session_id)
    
    def session_exists(self, session_id: str) -> bool:
        """Check if session exists."""
        return self.store.session_exists(session_id)
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information."""
        if self.session_exists(session_id):
            return self.store._sessions.get(session_id)
        return None


# Global instances for backwards compatibility
event_logger = EventLogger()
session_manager = SessionManager()