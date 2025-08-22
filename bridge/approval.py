"""
TinyIntent Approval Token Manager - M5: Guarded Execution

Manages approval tokens for two-step helper execution with expiry.
"""

import hashlib
import json
import secrets
import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

# Import centralized sanitization
try:
    from sanitize import sanitize_dict, sanitize_text
    CENTRALIZED_SANITIZATION = True
except ImportError:
    CENTRALIZED_SANITIZATION = False


class ApprovalTokenManager:
    """Manages approval tokens for guarded helper execution."""
    
    def __init__(self, token_expiry_minutes: int = 2):
        self.token_expiry_minutes = token_expiry_minutes
        self.tokens: Dict[str, Dict[str, Any]] = {}
        self.idempotency_cache: Dict[str, Dict[str, Any]] = {}
        self.audit_log = Path(__file__).parent / "logs" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
    
    def generate_approval_token(self, helper_id: str, helper_input: Dict[str, Any], 
                               session_id: str, user_text: str) -> str:
        """
        Generate a new approval token for helper execution.
        
        Args:
            helper_id: ID of the helper
            helper_input: Input data for the helper
            session_id: Session ID for tracking
            user_text: Original user request text
            
        Returns:
            Generated approval token string
        """
        # Generate secure random token
        token = secrets.token_urlsafe(32)
        
        # Calculate expiry time
        expiry_time = datetime.utcnow() + timedelta(minutes=self.token_expiry_minutes)
        
        # Create input hash for validation
        input_hash = self._hash_input(helper_id, helper_input, user_text)
        
        # Store token metadata
        self.tokens[token] = {
            "helper_id": helper_id,
            "helper_input": helper_input,
            "session_id": session_id,
            "user_text": user_text,
            "input_hash": input_hash,
            "created_at": datetime.utcnow().isoformat() + 'Z',
            "expires_at": expiry_time.isoformat() + 'Z',
            "used": False
        }
        
        # Log token generation
        self._log_approval_event("token_generated", token, helper_id, session_id)
        
        # Clean up expired tokens
        self._cleanup_expired_tokens()
        
        return token
    
    def validate_approval_token(self, token: str, helper_id: str, 
                               helper_input: Dict[str, Any], user_text: str, 
                               risk_level: str = "medium") -> Tuple[bool, str, Optional[str]]:
        """
        Validate an approval token for execution.
        
        Args:
            token: Approval token to validate
            helper_id: Helper ID being executed
            helper_input: Input data for the helper
            user_text: Original user request text
            risk_level: Risk level of the helper (low/medium/high)
            
        Returns:
            Tuple of (is_valid, error_message, token_id)
        """
        if not token:
            return False, "Approval token is required for execution", None
        
        token_data = self.tokens.get(token)
        if not token_data:
            self._log_approval_event("token_invalid", token, helper_id)
            return False, "Invalid approval token", None
        
        # Check if token is already used
        if token_data.get("used", False):
            self._log_approval_event("token_already_used", token, helper_id)
            return False, "Approval token already used", None
        
        # Check if token is expired
        expiry_time = datetime.fromisoformat(token_data["expires_at"].replace('Z', '+00:00'))
        if datetime.utcnow().replace(tzinfo=expiry_time.tzinfo) > expiry_time:
            self._log_approval_event("token_expired", token, helper_id)
            return False, "Approval token expired", None
        
        # Check high-risk token age requirement (≤60s)
        if risk_level == "high":
            created_time = datetime.fromisoformat(token_data["created_at"].replace('Z', '+00:00'))
            token_age = datetime.utcnow().replace(tzinfo=created_time.tzinfo) - created_time
            if token_age.total_seconds() > 60:
                self._log_approval_event("token_too_old", token, helper_id)
                return False, "Approval token too old for high-risk helper", None
        
        # Validate token matches current request
        expected_hash = self._hash_input(helper_id, helper_input, user_text)
        if token_data["input_hash"] != expected_hash:
            self._log_approval_event("token_mismatch", token, helper_id)
            return False, "Approval token does not match current request", None
        
        # Mark token as used
        token_data["used"] = True
        token_data["used_at"] = datetime.utcnow().isoformat() + 'Z'
        
        # Generate stable token_id for logging
        token_id = hashlib.sha256(token.encode()).hexdigest()[:16]
        
        self._log_approval_event("token_validated", token, helper_id, token_data["session_id"])
        return True, "", token_id
    
    def get_token_info(self, token: str) -> Optional[Dict[str, Any]]:
        """Get information about an approval token."""
        return self.tokens.get(token)
    
    def cleanup_session_tokens(self, session_id: str) -> int:
        """Clean up all tokens for a session. Returns number of tokens removed."""
        removed_count = 0
        tokens_to_remove = []
        
        for token, data in self.tokens.items():
            if data.get("session_id") == session_id:
                tokens_to_remove.append(token)
        
        for token in tokens_to_remove:
            del self.tokens[token]
            removed_count += 1
            self._log_approval_event("token_removed", token, "cleanup", session_id)
        
        return removed_count
    
    def get_idempotency_result(self, idempotency_key: str, helper_id: str, 
                              helper_input: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached result for idempotency key if within 10 minutes."""
        if not idempotency_key:
            return None
        
        cache_key = self._build_idempotency_key(idempotency_key, helper_id, helper_input)
        cached_entry = self.idempotency_cache.get(cache_key)
        
        if not cached_entry:
            return None
        
        # Check if entry is within 10 minutes
        cached_time = datetime.fromisoformat(cached_entry["timestamp"].replace('Z', '+00:00'))
        age = datetime.utcnow().replace(tzinfo=cached_time.tzinfo) - cached_time
        
        if age.total_seconds() > 600:  # 10 minutes
            # Clean up expired entry
            del self.idempotency_cache[cache_key]
            return None
        
        return cached_entry["result"]
    
    def set_idempotency_result(self, idempotency_key: str, helper_id: str, 
                              helper_input: Dict[str, Any], result: Dict[str, Any]):
        """Cache result for idempotency key."""
        if not idempotency_key:
            return
        
        cache_key = self._build_idempotency_key(idempotency_key, helper_id, helper_input)
        
        self.idempotency_cache[cache_key] = {
            "result": result,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "helper_id": helper_id
        }
        
        # Clean up expired entries
        self._cleanup_expired_idempotency()
    
    def _build_idempotency_key(self, idempotency_key: str, helper_id: str, 
                              helper_input: Dict[str, Any]) -> str:
        """Build cache key for idempotency."""
        input_hash = self._hash_input(helper_id, helper_input, "")
        return f"{idempotency_key}:{helper_id}:{input_hash}"
    
    def _cleanup_expired_idempotency(self):
        """Remove expired idempotency cache entries."""
        current_time = datetime.utcnow()
        keys_to_remove = []
        
        for cache_key, entry in self.idempotency_cache.items():
            cached_time = datetime.fromisoformat(entry["timestamp"].replace('Z', '+00:00'))
            age = current_time.replace(tzinfo=cached_time.tzinfo) - cached_time
            
            if age.total_seconds() > 600:  # 10 minutes
                keys_to_remove.append(cache_key)
        
        for key in keys_to_remove:
            del self.idempotency_cache[key]
    
    def _hash_input(self, helper_id: str, helper_input: Dict[str, Any], user_text: str) -> str:
        """Create a hash of the input parameters for validation."""
        input_str = json.dumps({
            "helper_id": helper_id,
            "helper_input": helper_input,
            "user_text": user_text
        }, sort_keys=True)
        return hashlib.sha256(input_str.encode()).hexdigest()
    
    def _cleanup_expired_tokens(self):
        """Remove expired tokens from memory."""
        current_time = datetime.utcnow()
        tokens_to_remove = []
        
        for token, data in self.tokens.items():
            expiry_time = datetime.fromisoformat(data["expires_at"].replace('Z', '+00:00'))
            if current_time.replace(tzinfo=expiry_time.tzinfo) > expiry_time:
                tokens_to_remove.append(token)
        
        for token in tokens_to_remove:
            helper_id = self.tokens[token].get("helper_id", "unknown")
            del self.tokens[token]
            self._log_approval_event("token_expired_cleanup", token, helper_id)
    
    def _log_approval_event(self, event_type: str, token: str, helper_id: str, 
                           session_id: str = None):
        """Log approval-related events to audit log."""
        try:
            # Only log partial token for security
            token_partial = token[:8] + "..." if len(token) > 8 else token
            
            log_entry = {
                "ts": datetime.utcnow().isoformat() + 'Z',
                "session_id": session_id or "unknown",
                "action": f"approval_{event_type}",
                "helper_id": helper_id,
                "token_partial": token_partial,
                "token_count": len(self.tokens)
            }
            
            # Sanitize log entry before writing
            if CENTRALIZED_SANITIZATION:
                log_entry = sanitize_dict(log_entry)
            
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            # Don't fail operations if logging fails
            print(f"Warning: Failed to log approval event: {e}")


# Global approval manager instance
approval_manager = ApprovalTokenManager()