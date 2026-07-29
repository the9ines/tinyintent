
"""
TinyIntent Audit Log System

Provides a tamper-evident, rotating audit log with integrity checking.
Ensures all significant events are logged securely.
"""

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

from .sanitize import sanitize_dict

logger = structlog.get_logger()


class AuditLogError(Exception):
    """Base exception for audit logging errors."""
    pass


class IntegrityError(AuditLogError):
    """Audit log integrity check failed."""
    pass


class AuditLogger:
    """Manages tamper-evident audit logging with rotation and integrity checks."""
    
    def __init__(self, log_path: Path, max_size_mb: int = 10):
        self.log_path = log_path
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = structlog.get_logger("audit")
        self._ensure_log_file()
    
    def _ensure_log_file(self):
        """Ensure log file exists."""
        if not self.log_path.exists():
            self.log_path.touch()
    
    def log_entry(self, entry: Dict[str, Any]) -> Optional[str]:
        """Log a new entry with integrity hash."""
        try:
            # Ensure timestamp is present and in ISO format
            if 'ts' not in entry:
                entry['ts'] = datetime.now(timezone.utc).isoformat()
            
            # Sanitize entry before logging
            sanitized_entry = sanitize_dict(entry)
            
            # Get previous hash
            last_hash = self._get_last_hash()
            sanitized_entry['prev_hash'] = last_hash
            
            # Create entry hash
            entry_json = json.dumps(sanitized_entry, sort_keys=True)
            entry_hash = hashlib.sha256(entry_json.encode()).hexdigest()
            
            # Final log record
            log_record = {
                "entry": sanitized_entry,
                "hash": entry_hash
            }
            
            # Atomic write operation
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_record, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())  # Force write to disk
            
            # Check for rotation
            self._rotate_if_needed()
            
            return entry_hash
            
        except Exception as e:
            self.logger.error("Failed to log audit entry", error=str(e), entry_action=entry.get('action'))
            raise AuditLogError(f"Failed to log audit entry: {e}") from e
    
    def _get_last_hash(self) -> str:
        """Get the hash of the last log entry."""
        try:
            with open(self.log_path, 'rb') as f:
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    return hashlib.sha256(b'').hexdigest()  # Genesis hash
                
                f.seek(-2, os.SEEK_END)
                while f.read(1) != b'\n':
                    f.seek(-2, os.SEEK_CUR)
                
                last_line = f.readline().decode()
                last_record = json.loads(last_line)
                return last_record['hash']
        except (IOError, json.JSONDecodeError):
            return hashlib.sha256(b'').hexdigest()  # Genesis hash on error
    
    def _rotate_if_needed(self) -> None:
        """Rotate log file if it exceeds max size."""
        if self.log_path.stat().st_size > self.max_size_bytes:
            self.rotate_now()
    
    def rotate_now(self) -> bool:
        """Force log rotation."""
        if not self.log_path.exists() or self.log_path.stat().st_size == 0:
            return False
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        archive_path = self.log_path.with_suffix(f'.{timestamp}.log')
        os.rename(self.log_path, archive_path)
        self._ensure_log_file()
        return True
    
    def verify_integrity(self, log_file: Optional[Path] = None) -> Tuple[bool, List[str]]:
        """Verify the integrity of a log file."""
        target_log = log_file or self.log_path
        if not target_log.exists():
            return True, []
        
        errors = []
        prev_hash = hashlib.sha256(b'').hexdigest()
        
        with open(target_log, 'r') as f:
            for i, line in enumerate(f):
                try:
                    record = json.loads(line)
                    entry = record['entry']
                    
                    # Check previous hash
                    if entry['prev_hash'] != prev_hash:
                        errors.append(f"Line {i+1}: Hash chain broken")
                    
                    # Verify entry hash
                    entry_json = json.dumps(entry, sort_keys=True)
                    expected_hash = hashlib.sha256(entry_json.encode()).hexdigest()
                    if record['hash'] != expected_hash:
                        errors.append(f"Line {i+1}: Entry hash mismatch")
                    
                    prev_hash = record['hash']
                except (json.JSONDecodeError, KeyError):
                    errors.append(f"Line {i+1}: Invalid log format")
        
        return len(errors) == 0, errors

# Global audit logger instance
_audit_logger_instance = None

def initialize_audit_logger(log_path: Path, max_size_mb: int = 50) -> AuditLogger:
    """Initialize the global audit logger."""
    global _audit_logger_instance
    _audit_logger_instance = AuditLogger(log_path, max_size_mb)
    return _audit_logger_instance

def get_audit_logger() -> Optional[AuditLogger]:
    """Get the global audit logger instance."""
    return _audit_logger_instance

