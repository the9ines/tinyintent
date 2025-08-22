"""
TinyIntent Secret Management System

Provides secure secret storage and scoped access for helpers based on their
trust level and capabilities.
"""

import os
import json
import base64
import hashlib
import secrets
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from enum import Enum
import structlog

try:
    from .logs.audit import get_audit_logger
except ImportError:
    # Fallback if audit logger not available
    def get_audit_logger():
        return None

logger = structlog.get_logger()


class SecretScope(Enum):
    """Secret access scope levels."""
    PUBLIC = "public"  # Available to all helpers
    TRUSTED = "trusted"  # Only trusted helpers
    SYSTEM = "system"  # Only system/internal use
    HELPER_SPECIFIC = "helper_specific"  # Specific helper only


class SecretViolation(Exception):
    """Raised when secret access is denied."""
    def __init__(self, message: str, secret_name: str, helper_id: str, required_scope: str):
        super().__init__(message)
        self.secret_name = secret_name
        self.helper_id = helper_id
        self.required_scope = required_scope


class SecretManager:
    """Manages secrets with scoped access control."""
    
    def __init__(self, secrets_dir: Path):
        self.secrets_dir = secrets_dir
        self.secrets_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache for decrypted secrets (with expiry)
        self._secret_cache: Dict[str, Dict[str, Any]] = {}
        
        # Secret metadata file
        self.metadata_file = self.secrets_dir / "metadata.json"
        self._load_metadata()
        
        # Encryption key for secret storage
        self._encryption_key = self._get_or_create_encryption_key()
    
    def _load_metadata(self):
        """Load secret metadata from file."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load secret metadata", error=str(e))
                self.metadata = {}
        else:
            self.metadata = {}
    
    def _save_metadata(self):
        """Save secret metadata to file."""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
            self.metadata_file.chmod(0o600)  # Restrict permissions
        except OSError as e:
            logger.error("Failed to save secret metadata", error=str(e))
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for secret storage."""
        key_file = self.secrets_dir / ".encryption_key"
        
        if key_file.exists():
            try:
                with open(key_file, 'rb') as f:
                    return f.read()
            except OSError:
                logger.warning("Failed to read encryption key, creating new one")
        
        # Create new encryption key
        key = secrets.token_bytes(32)  # 256-bit key
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            key_file.chmod(0o600)  # Restrict permissions
        except OSError as e:
            logger.error("Failed to save encryption key", error=str(e))
        
        return key
    
    def store_secret(self, name: str, value: str, scope: SecretScope, 
                    helper_id: Optional[str] = None, description: str = "") -> bool:
        """
        Store a secret with specified scope.
        
        Args:
            name: Secret name
            value: Secret value
            scope: Access scope
            helper_id: Helper ID for helper-specific secrets
            description: Secret description
            
        Returns:
            bool: True if stored successfully
        """
        try:
            # Validate inputs
            if not name or not isinstance(name, str):
                raise ValueError("Secret name must be a non-empty string")
            
            if not value or not isinstance(value, str):
                raise ValueError("Secret value must be a non-empty string")
            
            if scope == SecretScope.HELPER_SPECIFIC and not helper_id:
                raise ValueError("Helper ID required for helper-specific secrets")
            
            # Encrypt secret value
            encrypted_value = self._encrypt_secret(value)
            
            # Store encrypted secret
            secret_file = self.secrets_dir / f"{name}.secret"
            with open(secret_file, 'wb') as f:
                f.write(encrypted_value)
            secret_file.chmod(0o600)
            
            # Update metadata
            self.metadata[name] = {
                "scope": scope.value,
                "helper_id": helper_id,
                "description": description,
                "created_at": secrets.token_hex(8),  # Timestamp placeholder
                "hash": hashlib.sha256(value.encode()).hexdigest()[:16]  # Partial hash for verification
            }
            self._save_metadata()
            
            # Log secret storage
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "secret_stored",
                    "secret_name": name,
                    "scope": scope.value,
                    "helper_id": helper_id,
                    "description": description,
                    "success": True
                })
            
            return True
            
        except Exception as e:
            logger.error("Failed to store secret", name=name, error=str(e))
            return False
    
    def get_secret(self, name: str, helper_id: str, helper_trust_level: str = "draft") -> Optional[str]:
        """
        Retrieve a secret for a helper if access is allowed.
        
        Args:
            name: Secret name
            helper_id: Helper requesting the secret
            helper_trust_level: Helper trust level (draft, trusted, deprecated, retired)
            
        Returns:
            Optional[str]: Secret value if access allowed, None otherwise
            
        Raises:
            SecretViolation: If access is denied
        """
        # Check if secret exists
        if name not in self.metadata:
            return None
        
        secret_meta = self.metadata[name]
        scope = SecretScope(secret_meta["scope"])
        
        # Check access permissions
        if not self._check_access_permission(scope, helper_id, helper_trust_level, secret_meta):
            raise SecretViolation(
                f"Helper {helper_id} does not have access to secret {name}",
                name, helper_id, scope.value
            )
        
        # Load and decrypt secret
        try:
            secret_file = self.secrets_dir / f"{name}.secret"
            if not secret_file.exists():
                logger.error("Secret file missing", name=name)
                return None
            
            with open(secret_file, 'rb') as f:
                encrypted_value = f.read()
            
            decrypted_value = self._decrypt_secret(encrypted_value)
            
            # Log secret access
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "secret_accessed",
                    "secret_name": name,
                    "helper_id": helper_id,
                    "helper_trust_level": helper_trust_level,
                    "scope": scope.value,
                    "success": True
                })
            
            return decrypted_value
            
        except Exception as e:
            logger.error("Failed to retrieve secret", name=name, helper_id=helper_id, error=str(e))
            
            # Log failed access
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "secret_access_failed",
                    "secret_name": name,
                    "helper_id": helper_id,
                    "error": str(e),
                    "success": False
                })
            
            return None
    
    def list_available_secrets(self, helper_id: str, helper_trust_level: str = "draft") -> List[Dict[str, Any]]:
        """
        List secrets available to a helper.
        
        Args:
            helper_id: Helper ID
            helper_trust_level: Helper trust level
            
        Returns:
            List of available secret metadata
        """
        available_secrets = []
        
        for name, meta in self.metadata.items():
            scope = SecretScope(meta["scope"])
            
            if self._check_access_permission(scope, helper_id, helper_trust_level, meta):
                available_secrets.append({
                    "name": name,
                    "scope": scope.value,
                    "description": meta.get("description", ""),
                    "helper_specific": scope == SecretScope.HELPER_SPECIFIC
                })
        
        return available_secrets
    
    def delete_secret(self, name: str) -> bool:
        """
        Delete a secret.
        
        Args:
            name: Secret name
            
        Returns:
            bool: True if deleted successfully
        """
        try:
            # Remove from metadata
            if name in self.metadata:
                del self.metadata[name]
                self._save_metadata()
            
            # Remove secret file
            secret_file = self.secrets_dir / f"{name}.secret"
            if secret_file.exists():
                secret_file.unlink()
            
            # Log secret deletion
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "secret_deleted",
                    "secret_name": name,
                    "success": True
                })
            
            return True
            
        except Exception as e:
            logger.error("Failed to delete secret", name=name, error=str(e))
            return False
    
    def _check_access_permission(self, scope: SecretScope, helper_id: str, 
                               helper_trust_level: str, secret_meta: Dict[str, Any]) -> bool:
        """Check if helper has permission to access secret."""
        if scope == SecretScope.PUBLIC:
            return True
        
        elif scope == SecretScope.TRUSTED:
            return helper_trust_level == "trusted"
        
        elif scope == SecretScope.HELPER_SPECIFIC:
            return secret_meta.get("helper_id") == helper_id
        
        elif scope == SecretScope.SYSTEM:
            # System secrets not accessible to helpers
            return False
        
        return False
    
    def _encrypt_secret(self, value: str) -> bytes:
        """Encrypt a secret value."""
        # Simple XOR encryption with key (for demonstration)
        # In production, use proper encryption like AES-GCM
        value_bytes = value.encode('utf-8')
        key_bytes = self._encryption_key
        
        encrypted = bytearray()
        for i, byte in enumerate(value_bytes):
            encrypted.append(byte ^ key_bytes[i % len(key_bytes)])
        
        return bytes(encrypted)
    
    def _decrypt_secret(self, encrypted_value: bytes) -> str:
        """Decrypt a secret value."""
        # Simple XOR decryption (inverse of encrypt)
        key_bytes = self._encryption_key
        
        decrypted = bytearray()
        for i, byte in enumerate(encrypted_value):
            decrypted.append(byte ^ key_bytes[i % len(key_bytes)])
        
        return decrypted.decode('utf-8')
    
    def create_scoped_environment(self, helper_id: str, helper_trust_level: str, 
                                base_env: Dict[str, str]) -> Dict[str, str]:
        """
        Create an environment dictionary with secrets scoped for the helper.
        
        Args:
            helper_id: Helper ID
            helper_trust_level: Helper trust level
            base_env: Base environment dictionary
            
        Returns:
            Environment dictionary with allowed secrets
        """
        scoped_env = base_env.copy()
        
        # Get available secrets for this helper
        available_secrets = self.list_available_secrets(helper_id, helper_trust_level)
        
        for secret_info in available_secrets:
            secret_name = secret_info["name"]
            try:
                secret_value = self.get_secret(secret_name, helper_id, helper_trust_level)
                if secret_value:
                    # Add to environment with prefix to avoid conflicts
                    env_name = f"TINYINTENT_SECRET_{secret_name.upper()}"
                    scoped_env[env_name] = secret_value
            except SecretViolation:
                # Secret not accessible, skip
                continue
        
        return scoped_env
    
    def get_security_status(self) -> Dict[str, Any]:
        """Get security status of secret management."""
        total_secrets = len(self.metadata)
        scopes = {}
        
        for meta in self.metadata.values():
            scope = meta["scope"]
            scopes[scope] = scopes.get(scope, 0) + 1
        
        return {
            "total_secrets": total_secrets,
            "secrets_by_scope": scopes,
            "encryption_enabled": True,
            "metadata_file_exists": self.metadata_file.exists(),
            "secrets_directory": str(self.secrets_dir),
            "status": "operational"
        }


# Global secret manager instance
_secret_manager = None

def get_secret_manager() -> SecretManager:
    """Get the global secret manager instance."""
    global _secret_manager
    if _secret_manager is None:
        secrets_dir = Path.home() / ".tinyintent" / "secrets"
        _secret_manager = SecretManager(secrets_dir)
    return _secret_manager


def initialize_default_secrets():
    """Initialize default secrets for the system."""
    secret_manager = get_secret_manager()
    
    # Store system configuration secrets
    secret_manager.store_secret(
        "system_key",
        secrets.token_urlsafe(32),
        SecretScope.SYSTEM,
        description="System encryption key"
    )
    
    # Store default API keys as trusted secrets
    if os.getenv("EXCHANGE_API_KEY"):
        secret_manager.store_secret(
            "exchange_api_key",
            os.getenv("EXCHANGE_API_KEY"),
            SecretScope.TRUSTED,
            description="Crypto exchange API key"
        )
    
    if os.getenv("EXCHANGE_SECRET"):
        secret_manager.store_secret(
            "exchange_secret",
            os.getenv("EXCHANGE_SECRET"),
            SecretScope.TRUSTED,
            description="Crypto exchange secret"
        )