"""
TinyIntent Security Module

Handles security-critical components like authentication, rate limiting,
and the emergency kill switch.
"""

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tinyintent.bridge.logs.audit import get_audit_logger
from tinyintent.config import settings

# Security
security = HTTPBearer(auto_error=False)
logger = structlog.get_logger()


class SecurityError(Exception):
    """Base exception for security-related errors."""
    pass


class AuthenticationError(SecurityError):
    """Authentication failed."""
    pass


class AuthorizationError(SecurityError):
    """Authorization failed."""
    pass


def get_tinyintent_secret() -> str:
    """Get the required TINYINTENT_SECRET from configuration."""
    if not settings.security.secret:
        raise HTTPException(
            status_code=500,
            detail="TINYINTENT_SECRET environment variable is required"
        )
    return settings.security.secret


def constant_time_compare(a: str, b: str) -> bool:
    """Constant time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a.encode(), b.encode())


def generate_secure_token(length: int = 32) -> str:
    """Generate a cryptographically secure token."""
    return secrets.token_urlsafe(length)


def hash_secret(secret: str, salt: Optional[bytes] = None) -> Tuple[str, bytes]:
    """Hash a secret with salt for storage."""
    if salt is None:
        salt = secrets.token_bytes(32)
    
    # Use PBKDF2 with SHA-256
    hashed = hashlib.pbkdf2_hmac('sha256', secret.encode(), salt, 100000)
    return hashed.hex(), salt


def verify_secret_hash(secret: str, hashed: str, salt: bytes) -> bool:
    """Verify a secret against its hash."""
    expected_hash, _ = hash_secret(secret, salt)
    return constant_time_compare(expected_hash, hashed)


def is_localhost_request(request: Request) -> bool:
    """Check if request is from localhost."""
    if not request.client:
        return False
    
    localhost_ips = {"127.0.0.1", "::1", "localhost"}
    client_host = request.client.host
    
    # Check for forwarded headers (reverse proxy detection)
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    x_real_ip = request.headers.get("X-Real-IP")
    
    # If there are forwarded headers, it's not a direct localhost connection
    if x_forwarded_for or x_real_ip:
        return False
    
    return client_host in localhost_ips


def verify_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """Verify authentication using multiple methods."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "unknown")
    
    try:
        # Development bypass for localhost
        if settings.security.allow_dev_local and settings.is_development():
            if is_localhost_request(request):
                logger.debug("Authentication bypassed for localhost in development")
                return True
        
        # Check for X-TinyIntent-Secret header
        secret_header = request.headers.get("X-TinyIntent-Secret")
        if not secret_header:
            logger.warning("Missing authentication header", client_ip=client_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-TinyIntent-Secret header is required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Constant time comparison to prevent timing attacks
        expected_secret = get_tinyintent_secret()
        if not constant_time_compare(secret_header, expected_secret):
            logger.warning("Invalid authentication secret", client_ip=client_ip, user_agent=user_agent)
            
            # Log failed authentication to audit
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "authentication_failed",
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "success": False,
                    "error": "invalid_secret"
                })
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid X-TinyIntent-Secret",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Log successful authentication
        logger.debug("Authentication successful", client_ip=client_ip)
        return True
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error", error=str(e), client_ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication system error"
        )

class EmergencyKillSwitch:
    """Manages emergency kill switch state for execution control."""
    
    def __init__(self, flag_file_path: Path):
        self.flag_file_path = flag_file_path
        self.flag_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._execution_enabled = True
        self._load_state_from_file()
    
    def _load_state_from_file(self):
        """Load emergency state from flag file on startup."""
        audit_logger = get_audit_logger()
        if self.flag_file_path.exists():
            self._execution_enabled = False
            print("⚠️  EXECUTION DISABLED: Emergency flag file detected")
            # Log startup warning
            if audit_logger:
                audit_logger.log_entry({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "action": "emergency_startup_disabled",
                    "success": True,
                    "message": "Execution disabled on startup due to emergency flag",
                    "flag_file": str(self.flag_file_path)
                })
        else:
            self._execution_enabled = os.getenv("EXECUTION_ENABLED", "0") == "1"
            if self._execution_enabled:
                print("✓ Execution enabled (EXECUTION_ENABLED=1)")
            else:
                print("ℹ️  Execution disabled (EXECUTION_ENABLED=0)")
    
    def is_execution_enabled(self) -> bool:
        """Check if execution is currently enabled."""
        with threading.Lock():
            return self._execution_enabled
    
    def trigger_emergency_kill(self, reason: str = "Manual trigger", triggered_by: str = "unknown") -> bool:
        """
        Trigger emergency kill switch - disables all execution immediately.
        
        Returns:
            bool: True if kill was triggered successfully
        """
        with threading.Lock():
            if not self._execution_enabled:
                return False  # Already disabled
            
            try:
                # Create emergency flag file using atomic write
                emergency_data = {
                    "triggered_at": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "reason": reason,
                    "triggered_by": triggered_by
                }
                
                # Atomic write: write to temp file then replace
                temp_file = self.flag_file_path.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(emergency_data, f, indent=2)
                
                os.replace(str(temp_file), str(self.flag_file_path))
                
                # Disable execution in memory
                self._execution_enabled = False
                
                # Log emergency kill event
                audit_logger = get_audit_logger()
                if audit_logger:
                    audit_logger.log_entry({
                        "ts": emergency_data["triggered_at"],
                        "action": "emergency_kill",
                        "success": True,
                        "reason": reason,
                        "triggered_by": triggered_by,
                        "flag_file": str(self.flag_file_path),
                        "severity": "CRITICAL"
                    })
                
                print(f"🚨 EMERGENCY KILL TRIGGERED: {reason}")
                return True
                
            except Exception as e:
                # Clean up temp file if it exists
                temp_file = self.flag_file_path.with_suffix('.tmp')
                try:
                    temp_file.unlink()
                except FileNotFoundError:
                    pass
                
                # Log error but don't fail
                audit_logger = get_audit_logger()
                if audit_logger:
                    audit_logger.log_entry({
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                        "action": "emergency_kill_error",
                        "success": False,
                        "error": str(e),
                        "reason": reason,
                        "triggered_by": triggered_by
                    })
                print(f"❌ Emergency kill failed: {e}")
                return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current emergency status."""
        with threading.Lock():
            status = {
                "execution_enabled": self._execution_enabled,
                "flag_file_exists": self.flag_file_path.exists(),
                "flag_file_path": str(self.flag_file_path)
            }
            
            if self.flag_file_path.exists():
                try:
                    with open(self.flag_file_path, 'r') as f:
                        flag_data = json.load(f)
                    status["emergency_data"] = flag_data
                except Exception:
                    status["emergency_data"] = {"error": "Could not read flag file"}
            
            return status

class RateLimiter:
    """Manages rate limiting for sessions and global requests."""
    
    def __init__(self, 
                 session_limit: Optional[int] = None,
                 global_limit: Optional[int] = None,
                 window_seconds: Optional[int] = None):
        # Use configuration values with fallbacks
        self.session_limit = session_limit or settings.security.rate_limit_session
        self.global_limit = global_limit or settings.security.rate_limit_global
        self.window_seconds = window_seconds or settings.security.rate_limit_window
        
        # Thread-safe access to counters
        self.lock = threading.Lock()
        
        # Session-based request tracking: {session_id: [(timestamp, request_count), ...]}
        self.session_requests: Dict[str, List[tuple]] = {}
        
        # Global request tracking: [(timestamp, request_count), ...]
        self.global_requests: List[tuple] = []
        
        # Cleanup thread for expired entries
        self.cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self.cleanup_thread.start()
    
    def _cleanup_expired(self):
        """Background thread to clean up expired rate limit entries."""
        while True:
            try:
                current_time = time.time()
                cutoff_time = current_time - self.window_seconds
                
                with self.lock:
                    # Clean up session requests
                    for session_id in list(self.session_requests.keys()):
                        self.session_requests[session_id] = [
                            entry for entry in self.session_requests[session_id]
                            if entry[0] > cutoff_time
                        ]
                        # Remove empty sessions
                        if not self.session_requests[session_id]:
                            del self.session_requests[session_id]
                    
                    # Clean up global requests
                    self.global_requests = [
                        entry for entry in self.global_requests
                        if entry[0] > cutoff_time
                    ]
                
                # Sleep for cleanup interval (10 seconds)
                time.sleep(10)
                
            except Exception as e:
                print(f"Warning: Rate limiter cleanup error: {e}")
                time.sleep(10)
    
    def check_rate_limit(self, session_id: str) -> tuple[bool, Optional[int]]:
        """
        Check if request should be rate limited.
        
        Returns:
            (allowed: bool, retry_after_seconds: Optional[int])
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            # Count session requests in current window
            if session_id not in self.session_requests:
                self.session_requests[session_id] = []
            
            session_count = sum(
                count for timestamp, count in self.session_requests[session_id]
                if timestamp > cutoff_time
            )
            
            # Count global requests in current window
            global_count = sum(
                count for timestamp, count in self.global_requests
                if timestamp > cutoff_time
            )
            
            # Check session limit
            if session_count >= self.session_limit:
                return False, self.window_seconds
            
            # Check global limit
            if global_count >= self.global_limit:
                return False, self.window_seconds
            
            # Add this request to counters
            self.session_requests[session_id].append((current_time, 1))
            self.global_requests.append((current_time, 1))
            
            return True, None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiting statistics."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            # Count current session requests
            session_stats = {}
            for session_id, requests in self.session_requests.items():
                count = sum(
                    count for timestamp, count in requests
                    if timestamp > cutoff_time
                )
                if count > 0:
                    session_stats[session_id] = count
            
            # Count current global requests
            global_count = sum(
                count for timestamp, count in self.global_requests
                if timestamp > cutoff_time
            )
            
            return {
                "session_limit": self.session_limit,
                "global_limit": self.global_limit,
                "window_seconds": self.window_seconds,
                "current_global_count": global_count,
                "active_sessions": len(session_stats),
                "session_counts": session_stats
            }
