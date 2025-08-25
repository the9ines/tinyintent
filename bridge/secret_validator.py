"""
Production Secret Validation for TinyIntent

Enforces strong cryptographic requirements for production secrets to prevent
security vulnerabilities from weak or default secrets.
"""

import os
import re
import math
import logging
from typing import Dict, Any, List, Tuple
from collections import Counter

logger = logging.getLogger(__name__)


class SecretValidationResult:
    """Result of secret validation with detailed analysis."""
    
    def __init__(self, is_valid: bool, score: int, issues: List[str], 
                 suggestions: List[str], entropy: float, analysis: Dict[str, Any]):
        self.is_valid = is_valid
        self.score = score  # 0-100
        self.issues = issues
        self.suggestions = suggestions
        self.entropy = entropy
        self.analysis = analysis
    
    def __bool__(self) -> bool:
        return self.is_valid


class ProductionSecretValidator:
    """
    Production-grade secret validation with entropy analysis and pattern detection.
    
    Enforces strict requirements for production secrets to prevent security
    vulnerabilities from weak, predictable, or default secrets.
    """
    
    # Minimum requirements for production secrets
    MIN_LENGTH = 32
    MIN_ENTROPY_BITS = 128.0
    MIN_SCORE = 80
    
    # Common weak patterns that should be rejected
    WEAK_PATTERNS = [
        r'password\d*',
        r'secret\d*', 
        r'key\d*',
        r'token\d*',
        r'test.*',
        r'demo.*',
        r'default.*',
        r'example.*',
        r'sample.*',
        r'admin.*',
        r'tinyintent.*',
        r'change.*me.*',
        r'replace.*',
        r'placeholder.*',
        r'your.*secret.*',
        r'insert.*here.*',
        r'abc+',
        r'123+',
        r'qwe.*',
        r'aaa+',
        r'.*-secure-token-123',  # Specific to our old default
    ]
    
    # Predictable character sequences
    SEQUENCES = [
        'abcdefghijklmnopqrstuvwxyz',
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 
        '0123456789',
        'qwertyuiop',
        'asdfghjkl',
        'zxcvbnm',
    ]
    
    def __init__(self, production_mode: bool = None):
        """
        Initialize secret validator.
        
        Args:
            production_mode: If True, enforce strictest validation. 
                           If None, auto-detect based on environment.
        """
        if production_mode is None:
            # Auto-detect production mode
            production_mode = self._detect_production_mode()
        
        self.production_mode = production_mode
        
        # Adjust requirements based on mode
        if production_mode:
            self.min_length = 32
            self.min_entropy = 128.0
            self.min_score = 85
            self.fail_on_weak = True
        else:
            self.min_length = 16  # Relaxed for development
            self.min_entropy = 64.0
            self.min_score = 60
            self.fail_on_weak = False
        
        logger.info(f"Secret validator initialized: production={production_mode}, "
                   f"min_length={self.min_length}, min_entropy={self.min_entropy}")
    
    def _detect_production_mode(self) -> bool:
        """Auto-detect if we're running in production mode."""
        production_indicators = [
            os.environ.get('NODE_ENV') == 'production',
            os.environ.get('ENVIRONMENT') == 'production',
            os.environ.get('TINYINTENT_PRODUCTION') == '1',
            os.path.exists('/.dockerenv'),  # Docker container
            'prod' in os.environ.get('HOSTNAME', '').lower(),
        ]
        
        return any(production_indicators)
    
    def validate_secret(self, secret: str) -> SecretValidationResult:
        """
        Validate a secret with comprehensive security analysis.
        
        Args:
            secret: The secret string to validate
            
        Returns:
            SecretValidationResult with detailed analysis
        """
        if not secret:
            return SecretValidationResult(
                is_valid=False,
                score=0,
                issues=["Secret is empty or None"],
                suggestions=["Generate a cryptographically secure secret"],
                entropy=0.0,
                analysis={"length": 0, "charset": "empty"}
            )
        
        issues = []
        suggestions = []
        score = 0
        
        # Basic length check
        length = len(secret)
        if length < self.min_length:
            issues.append(f"Secret too short ({length} chars, minimum {self.min_length})")
            suggestions.append(f"Use at least {self.min_length} characters")
        else:
            score += min(30, (length / self.min_length) * 30)
        
        # Entropy analysis
        entropy = self._calculate_entropy(secret)
        if entropy < self.min_entropy:
            issues.append(f"Insufficient entropy ({entropy:.1f} bits, minimum {self.min_entropy:.1f})")
            suggestions.append("Use more random characters from different character sets")
        else:
            score += min(40, (entropy / self.min_entropy) * 40)
        
        # Character set diversity
        charset_score, charset_issues = self._analyze_character_sets(secret)
        score += charset_score
        issues.extend(charset_issues)
        
        # Weak pattern detection
        pattern_score, pattern_issues = self._detect_weak_patterns(secret)
        score += pattern_score
        issues.extend(pattern_issues)
        
        # Sequence detection
        sequence_score, sequence_issues = self._detect_sequences(secret)
        score += sequence_score
        issues.extend(sequence_issues)
        
        # Production-specific checks
        if self.production_mode:
            prod_issues = self._production_checks(secret)
            issues.extend(prod_issues)
            if prod_issues:
                score = min(score, 50)  # Cap score if production issues found
        
        # Final validation
        is_valid = (
            score >= self.min_score and
            length >= self.min_length and
            entropy >= self.min_entropy and
            not (self.fail_on_weak and issues)
        )
        
        # Generate suggestions if needed
        if not is_valid and not suggestions:
            suggestions.extend([
                "Generate a new secret using: python -c \"import secrets; print(secrets.token_urlsafe(32))\"",
                "Use a password manager to generate a strong secret",
                "Ensure the secret contains mixed case, numbers, and special characters"
            ])
        
        analysis = {
            "length": length,
            "entropy": entropy,
            "charset": self._analyze_charset(secret),
            "production_mode": self.production_mode,
            "pattern_matches": self._get_pattern_matches(secret)
        }
        
        return SecretValidationResult(
            is_valid=is_valid,
            score=min(100, max(0, int(score))),
            issues=issues,
            suggestions=suggestions,
            entropy=entropy,
            analysis=analysis
        )
    
    def _calculate_entropy(self, secret: str) -> float:
        """Calculate Shannon entropy of the secret."""
        if not secret:
            return 0.0
        
        # Count character frequencies
        counts = Counter(secret)
        length = len(secret)
        
        # Calculate Shannon entropy
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                probability = count / length
                entropy -= probability * math.log2(probability)
        
        # Return bits of entropy
        return entropy * length
    
    def _analyze_character_sets(self, secret: str) -> Tuple[int, List[str]]:
        """Analyze character set diversity."""
        score = 0
        issues = []
        
        has_lower = bool(re.search(r'[a-z]', secret))
        has_upper = bool(re.search(r'[A-Z]', secret))
        has_digits = bool(re.search(r'\d', secret))
        has_special = bool(re.search(r'[^a-zA-Z0-9]', secret))
        
        charset_count = sum([has_lower, has_upper, has_digits, has_special])
        
        if charset_count >= 3:
            score += 15
        elif charset_count >= 2:
            score += 8
            issues.append("Secret uses limited character sets")
        else:
            score += 0
            issues.append("Secret uses very limited character sets")
        
        if not has_lower:
            issues.append("Missing lowercase letters")
        if not has_upper:
            issues.append("Missing uppercase letters") 
        if not has_digits:
            issues.append("Missing numbers")
        if not has_special and len(secret) > 20:
            issues.append("Consider adding special characters for longer secrets")
        
        return score, issues
    
    def _detect_weak_patterns(self, secret: str) -> Tuple[int, List[str]]:
        """Detect weak or predictable patterns."""
        score = 15  # Start with full score
        issues = []
        
        secret_lower = secret.lower()
        
        for pattern in self.WEAK_PATTERNS:
            if re.search(pattern, secret_lower):
                score = 0
                issues.append(f"Contains weak pattern: {pattern}")
                break
        
        # Check for repetitive patterns
        if len(set(secret)) < len(secret) * 0.6:
            score = min(score, 5)
            issues.append("High character repetition detected")
        
        return score, issues
    
    def _detect_sequences(self, secret: str) -> Tuple[int, List[str]]:
        """Detect predictable character sequences."""
        score = 10  # Start with full score
        issues = []
        
        for sequence in self.SEQUENCES:
            # Check for sequences of 4+ characters
            for i in range(len(sequence) - 3):
                substring = sequence[i:i+4]
                reverse_substring = substring[::-1]
                
                if substring.lower() in secret.lower() or reverse_substring.lower() in secret.lower():
                    score = min(score, 2)
                    issues.append(f"Contains predictable sequence: {substring}")
        
        return score, issues
    
    def _production_checks(self, secret: str) -> List[str]:
        """Additional checks for production environments."""
        issues = []
        
        # Check for common development/test indicators
        test_indicators = ['test', 'dev', 'localhost', 'demo', 'sample', 'example']
        if any(indicator in secret.lower() for indicator in test_indicators):
            issues.append("Secret appears to be a test/development value (not suitable for production)")
        
        # Check for timestamps or dates (often used in weak secrets)
        if re.search(r'20\d{2}|19\d{2}|\d{4}-\d{2}-\d{2}', secret):
            issues.append("Secret contains date/timestamp patterns (potential weakness)")
        
        # Check for dictionary words (basic check)
        common_words = ['password', 'secret', 'key', 'token', 'admin', 'user', 'login']
        for word in common_words:
            if word in secret.lower():
                issues.append(f"Secret contains common word: {word}")
        
        return issues
    
    def _analyze_charset(self, secret: str) -> Dict[str, bool]:
        """Analyze character set usage."""
        return {
            "lowercase": bool(re.search(r'[a-z]', secret)),
            "uppercase": bool(re.search(r'[A-Z]', secret)),
            "digits": bool(re.search(r'\d', secret)),
            "special": bool(re.search(r'[^a-zA-Z0-9]', secret)),
            "unicode": any(ord(c) > 127 for c in secret)
        }
    
    def _get_pattern_matches(self, secret: str) -> List[str]:
        """Get list of weak patterns that match."""
        matches = []
        secret_lower = secret.lower()
        
        for pattern in self.WEAK_PATTERNS:
            if re.search(pattern, secret_lower):
                matches.append(pattern)
        
        return matches


def validate_production_secret(secret: str, production_mode: bool = None) -> SecretValidationResult:
    """
    Validate a secret for production use.
    
    Convenience function for validating secrets with production-grade requirements.
    
    Args:
        secret: Secret string to validate
        production_mode: Force production mode (auto-detect if None)
        
    Returns:
        SecretValidationResult with detailed analysis
    """
    validator = ProductionSecretValidator(production_mode)
    return validator.validate_secret(secret)


def enforce_secret_requirements(secret: str, context: str = "TinyIntent") -> str:
    """
    Enforce secret requirements and fail fast if validation fails.
    
    This function should be called during application startup to ensure
    only strong secrets are used in production.
    
    Args:
        secret: Secret to validate
        context: Context description for error messages
        
    Returns:
        The secret if valid
        
    Raises:
        ValueError: If secret fails validation requirements
    """
    result = validate_production_secret(secret)
    
    if not result.is_valid:
        error_msg = f"{context} secret validation failed:\n"
        for issue in result.issues:
            error_msg += f"  - {issue}\n"
        
        if result.suggestions:
            error_msg += "\nSuggestions:\n"
            for suggestion in result.suggestions:
                error_msg += f"  - {suggestion}\n"
        
        error_msg += f"\nSecret strength score: {result.score}/100"
        error_msg += f"\nEntropy: {result.entropy:.1f} bits"
        
        logger.error(f"Secret validation failed for {context}: score={result.score}/100")
        raise ValueError(error_msg)
    
    logger.info(f"Secret validation passed for {context}: score={result.score}/100, entropy={result.entropy:.1f} bits")
    return secret