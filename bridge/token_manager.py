"""
Secure Token Management for TinyIntent

Handles cryptographically secure token generation, validation, and rotation
for iPhone Shortcut authentication and other security-critical operations.
"""

import os
import secrets
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
from threading import Lock

logger = logging.getLogger(__name__)

@dataclass
class TokenInfo:
    """Information about a generated token."""
    token: str
    generated_at: datetime
    length: int
    entropy_bits: float
    purpose: str

class SecureTokenManager:
    """
    Secure token management with automatic generation, validation, and rotation.
    
    Features:
    - Cryptographically secure token generation using secrets module
    - Configurable token length and entropy requirements
    - Token metadata tracking (generation time, purpose, etc.)
    - Thread-safe token operations
    - Secure token storage with proper file permissions
    """
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize secure token manager.
        
        Args:
            config_dir: Directory to store token configuration (default: bridge/tokens/)
        """
        self.config_dir = config_dir or Path(__file__).parent / "tokens"
        self.config_dir.mkdir(exist_ok=True, mode=0o700)  # Owner-only access
        
        self.token_file = self.config_dir / "shortcut_token.json"
        self.lock = Lock()
        
        # Security requirements
        self.min_token_length = 32
        self.min_entropy_bits = 160.0  # ~32 chars of base64
        
    def generate_secure_token(self, length: int = 32, purpose: str = "shortcut_auth") -> TokenInfo:
        """
        Generate a cryptographically secure token.
        
        Args:
            length: Token length in characters (minimum 32)
            purpose: Purpose description for the token
            
        Returns:
            TokenInfo with generated token and metadata
            
        Raises:
            ValueError: If length is below minimum requirements
        """
        if length < self.min_token_length:
            raise ValueError(f"Token length must be at least {self.min_token_length} characters")
        
        # Generate cryptographically secure random token
        token = secrets.token_urlsafe(length)
        
        # Calculate entropy (approximation for URL-safe base64)
        entropy_bits = length * 6.0  # Each base64 char ≈ 6 bits of entropy
        
        if entropy_bits < self.min_entropy_bits:
            logger.warning(f"Generated token entropy ({entropy_bits:.1f} bits) below recommended minimum ({self.min_entropy_bits} bits)")
        
        token_info = TokenInfo(
            token=token,
            generated_at=datetime.now(timezone.utc),
            length=len(token),
            entropy_bits=entropy_bits,
            purpose=purpose
        )
        
        logger.info(f"Generated secure token: length={len(token)}, entropy={entropy_bits:.1f} bits, purpose={purpose}")
        
        return token_info
    
    def save_token_securely(self, token_info: TokenInfo) -> bool:
        """
        Save token information to secure file with proper permissions.
        
        Args:
            token_info: Token information to save
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            with self.lock:
                # Convert to serializable format
                token_data = {
                    **asdict(token_info),
                    'generated_at': token_info.generated_at.isoformat()
                }
                
                # Write to temporary file first (atomic operation)
                temp_file = self.token_file.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    json.dump(token_data, f, indent=2)
                
                # Set restrictive permissions (owner only)
                temp_file.chmod(0o600)
                
                # Atomic rename
                temp_file.replace(self.token_file)
                
                logger.info(f"Saved secure token to {self.token_file} with restrictive permissions")
                return True
                
        except Exception as e:
            logger.error(f"Failed to save token securely: {e}")
            return False
    
    def load_token_info(self) -> Optional[TokenInfo]:
        """
        Load token information from secure storage.
        
        Returns:
            TokenInfo if loaded successfully, None otherwise
        """
        try:
            with self.lock:
                if not self.token_file.exists():
                    return None
                
                # Verify file permissions
                file_stat = self.token_file.stat()
                if file_stat.st_mode & 0o077:  # Check if group/other have any permissions
                    logger.warning(f"Token file {self.token_file} has overly permissive permissions")
                
                with open(self.token_file, 'r') as f:
                    token_data = json.load(f)
                
                # Parse datetime
                generated_at = datetime.fromisoformat(token_data['generated_at'])
                
                token_info = TokenInfo(
                    token=token_data['token'],
                    generated_at=generated_at,
                    length=token_data['length'],
                    entropy_bits=token_data['entropy_bits'],
                    purpose=token_data['purpose']
                )
                
                return token_info
                
        except Exception as e:
            logger.error(f"Failed to load token info: {e}")
            return None
    
    def get_or_generate_shortcut_token(self) -> str:
        """
        Get existing shortcut token or generate a new one.
        
        Returns:
            Secure shortcut token string
        """
        # Try to load existing token
        token_info = self.load_token_info()
        
        if token_info and token_info.purpose == "shortcut_auth":
            logger.info("Using existing secure shortcut token")
            return token_info.token
        
        # Generate new token
        logger.info("Generating new secure shortcut token")
        token_info = self.generate_secure_token(length=43, purpose="shortcut_auth")  # 43 chars = ~256 bits entropy
        
        # Save securely
        if self.save_token_securely(token_info):
            return token_info.token
        else:
            logger.error("Failed to save token securely, using in-memory token")
            return token_info.token
    
    def validate_token_strength(self, token: str) -> Dict[str, Any]:
        """
        Validate token strength and provide security assessment.
        
        Args:
            token: Token string to validate
            
        Returns:
            Dictionary with validation results
        """
        length = len(token)
        
        # Estimate entropy (simplified)
        if token.replace('-', '').replace('_', '').isalnum():
            # URL-safe base64 characters
            entropy_bits = length * 6.0
        else:
            # Conservative estimate for mixed characters
            entropy_bits = length * 4.0
        
        is_strong = (
            length >= self.min_token_length and 
            entropy_bits >= self.min_entropy_bits and
            not self._is_predictable_pattern(token)
        )
        
        return {
            "length": length,
            "entropy_bits": entropy_bits,
            "meets_minimum_length": length >= self.min_token_length,
            "meets_minimum_entropy": entropy_bits >= self.min_entropy_bits,
            "no_predictable_pattern": not self._is_predictable_pattern(token),
            "is_strong": is_strong,
            "strength_score": min(100, int((entropy_bits / 256.0) * 100))  # Score out of 100
        }
    
    def _is_predictable_pattern(self, token: str) -> bool:
        """
        Check if token contains predictable patterns.
        
        Args:
            token: Token to check
            
        Returns:
            True if predictable patterns detected
        """
        predictable_patterns = [
            "123", "abc", "password", "token", "key", "secret",
            "test", "demo", "example", "default", "admin",
            "iphone", "shortcut", "tinyintent"
        ]
        
        token_lower = token.lower()
        return any(pattern in token_lower for pattern in predictable_patterns)

    def rotate_shortcut_token(self) -> str:
        """
        Generate and save a new shortcut token, rotating the existing one.
        
        Returns:
            New secure shortcut token
        """
        logger.info("Rotating shortcut token")
        
        # Generate new token
        new_token_info = self.generate_secure_token(length=43, purpose="shortcut_auth")
        
        # Save securely  
        if self.save_token_securely(new_token_info):
            logger.info("Token rotation completed successfully")
            return new_token_info.token
        else:
            logger.error("Failed to save rotated token securely")
            return new_token_info.token

# Global token manager instance
_token_manager: Optional[SecureTokenManager] = None
_token_manager_lock = Lock()

def get_token_manager() -> SecureTokenManager:
    """Get or create the global secure token manager instance."""
    global _token_manager
    
    if _token_manager is None:
        with _token_manager_lock:
            if _token_manager is None:
                _token_manager = SecureTokenManager()
    
    return _token_manager

def get_secure_shortcut_token() -> str:
    """
    Get secure shortcut token, generating one if needed.
    
    This is the main function used by the application to get
    a cryptographically secure shortcut authentication token.
    
    Returns:
        Secure shortcut token string
    """
    return get_token_manager().get_or_generate_shortcut_token()