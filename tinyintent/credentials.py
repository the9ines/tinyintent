"""
TinyIntent Credential Manager

Handles automatic generation, persistence, and management of secure credentials
for out-of-the-box experience without manual configuration.
"""

import json
import secrets
import string
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class CredentialManager:
    """Manages auto-generated secure credentials for TinyIntent."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize credential manager with config directory."""
        self.config_dir = config_dir or Path.home() / ".tinyintent"
        self.credentials_file = self.config_dir / "credentials.json"
        self.backup_dir = self.config_dir / "backup"
        
        # Ensure config directory exists
        self.config_dir.mkdir(exist_ok=True)
        self.backup_dir.mkdir(exist_ok=True)
    
    def generate_secure_credentials(self) -> Dict[str, str]:
        """Generate cryptographically secure credentials."""
        # Use URL-safe base64 encoding for clean, copy-pastable tokens
        tinyintent_secret = secrets.token_urlsafe(48)  # ~64 chars
        shortcut_token = secrets.token_urlsafe(24)     # ~32 chars
        
        credentials = {
            "tinyintent_secret": tinyintent_secret,
            "shortcut_token": shortcut_token,
            "generated_at": datetime.now().isoformat(),
            "version": "2.0.0",
            "auto_generated": True
        }
        
        logger.info("Generated new secure credentials", 
                   secret_length=len(tinyintent_secret),
                   token_length=len(shortcut_token))
        
        return credentials
    
    def save_credentials(self, credentials: Dict[str, str]) -> None:
        """Save credentials to persistent storage."""
        try:
            # Create backup of existing credentials if they exist
            if self.credentials_file.exists():
                backup_name = f"credentials-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
                backup_path = self.backup_dir / backup_name
                backup_path.write_text(self.credentials_file.read_text())
                logger.info("Backed up existing credentials", backup_path=str(backup_path))
            
            # Save new credentials with secure permissions
            with open(self.credentials_file, 'w') as f:
                json.dump(credentials, f, indent=2)
            
            # Set secure file permissions (owner read/write only)
            self.credentials_file.chmod(0o600)
            
            logger.info("Saved credentials to file", 
                       path=str(self.credentials_file),
                       permissions="0600")
                       
        except Exception as e:
            logger.error("Failed to save credentials", error=str(e))
            raise
    
    def load_credentials(self) -> Optional[Dict[str, str]]:
        """Load existing credentials from storage."""
        if not self.credentials_file.exists():
            logger.info("No existing credentials file found")
            return None
        
        try:
            with open(self.credentials_file, 'r') as f:
                credentials = json.load(f)
            
            # Validate credential structure
            required_fields = ["tinyintent_secret", "shortcut_token"]
            if not all(field in credentials for field in required_fields):
                logger.warning("Invalid credentials file structure, regenerating")
                return None
            
            # Validate credential strength
            if (len(credentials["tinyintent_secret"]) < 32 or 
                len(credentials["shortcut_token"]) < 16):
                logger.warning("Weak credentials detected, regenerating")
                return None
            
            logger.info("Loaded existing credentials", 
                       generated_at=credentials.get("generated_at", "unknown"),
                       auto_generated=credentials.get("auto_generated", False))
            
            return credentials
            
        except (json.JSONDecodeError, IOError) as e:
            logger.error("Failed to load credentials file", error=str(e))
            return None
    
    def get_or_create_credentials(self) -> Dict[str, str]:
        """Get existing credentials or create new ones if needed."""
        credentials = self.load_credentials()
        
        if credentials is None:
            logger.info("Creating new secure credentials for first-time setup")
            credentials = self.generate_secure_credentials()
            self.save_credentials(credentials)
        
        return credentials
    
    def regenerate_credentials(self) -> Dict[str, str]:
        """Force regeneration of credentials."""
        logger.info("Regenerating credentials as requested")
        credentials = self.generate_secure_credentials()
        self.save_credentials(credentials)
        return credentials
    
    def get_credential_info(self, show_secret: bool = False) -> Dict[str, str]:
        """Get credential information for display."""
        credentials = self.load_credentials()
        
        if credentials is None:
            return {"status": "No credentials found"}
        
        info = {
            "shortcut_token": credentials["shortcut_token"],
            "secret_status": "Set" if not show_secret else credentials["tinyintent_secret"],
            "generated_at": credentials.get("generated_at", "Unknown"),
            "auto_generated": credentials.get("auto_generated", False),
            "secret_length": len(credentials["tinyintent_secret"]),
            "token_length": len(credentials["shortcut_token"])
        }
        
        return info
    
    def apply_to_environment(self) -> Tuple[str, str]:
        """Apply credentials to environment and return them."""
        import os
        
        credentials = self.get_or_create_credentials()
        
        # Set environment variables
        os.environ["TINYINTENT_SECRET"] = credentials["tinyintent_secret"]
        os.environ["SHORTCUT_TOKEN"] = credentials["shortcut_token"]
        
        logger.info("Applied credentials to environment")
        
        return credentials["tinyintent_secret"], credentials["shortcut_token"]
    
    def cleanup_old_backups(self, keep_days: int = 30) -> None:
        """Clean up old credential backups."""
        if not self.backup_dir.exists():
            return
        
        cutoff_time = datetime.now().timestamp() - (keep_days * 24 * 3600)
        removed_count = 0
        
        for backup_file in self.backup_dir.glob("credentials-*.json"):
            if backup_file.stat().st_mtime < cutoff_time:
                backup_file.unlink()
                removed_count += 1
        
        if removed_count > 0:
            logger.info("Cleaned up old credential backups", 
                       removed=removed_count, keep_days=keep_days)


# Global credential manager instance
credential_manager = CredentialManager()


def get_or_create_credentials() -> Dict[str, str]:
    """Convenience function to get or create credentials."""
    return credential_manager.get_or_create_credentials()


def apply_credentials_to_environment(quiet: bool = False) -> Tuple[str, str]:
    """Convenience function to apply credentials to environment."""
    if quiet:
        # Temporarily suppress logging
        import structlog
        global logger
        old_logger = logger
        logger = structlog.get_logger("null")
        try:
            result = credential_manager.apply_to_environment()
        finally:
            logger = old_logger
        return result
    else:
        return credential_manager.apply_to_environment()


def regenerate_credentials() -> Dict[str, str]:
    """Convenience function to regenerate credentials."""
    return credential_manager.regenerate_credentials()


def get_credential_info(show_secret: bool = False) -> Dict[str, str]:
    """Convenience function to get credential information."""
    return credential_manager.get_credential_info(show_secret)