"""
TinyIntent Agent Provenance, Signing & Tamper-evidence

M10.5: Ensures every generated/updated helper has verifiable provenance 
record and signature. Provides cryptographic integrity verification 
for agent files using HMAC-SHA256 signatures.

Safe-by-default: unverifiable agents are disabled for execution.
"""

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

import structlog

# Import audit logger with fallback
try:
    from tinyintent.bridge.logs.audit import get_audit_logger
    from tinyintent.bridge.logs.sanitize import sanitize_text
    AUDIT_LOGGER_AVAILABLE = True
except ImportError:
    # Fallback for standalone usage
    def get_audit_logger():
        class MockLogger:
            def log_entry(self, entry):
                pass
        return MockLogger()
    
    def sanitize_text(text):
        return text
    
    AUDIT_LOGGER_AVAILABLE = False

logger = structlog.get_logger()


class ProvenanceError(Exception):
    """Base exception for provenance-related errors."""
    pass


class ProvenanceKeyError(ProvenanceError):
    """Error related to provenance key management."""
    pass


class ProvenanceVerificationError(ProvenanceError):
    """Error during provenance verification."""
    pass


def _get_key_path() -> Path:
    """Get the path to the provenance key file."""
    bridge_dir = Path(__file__).parent
    keys_dir = bridge_dir / "keys"
    return keys_dir / "provenance.key"


def _ensure_key_exists() -> bytes:
    """
    Ensure provenance key exists, create if missing.
    
    Returns:
        bytes: The HMAC key
        
    Raises:
        ProvenanceKeyError: If key cannot be created or read
    """
    key_path = _get_key_path()
    
    try:
        # Create keys directory if it doesn't exist
        key_path.parent.mkdir(mode=0o700, exist_ok=True)
        
        if key_path.exists():
            # Read existing key
            with open(key_path, 'rb') as f:
                key = f.read()
            
            if len(key) < 32:
                raise ProvenanceKeyError(f"Provenance key too short: {len(key)} bytes")
            
            return key
        else:
            # Generate new key
            key = secrets.token_bytes(64)  # 512-bit key for HMAC-SHA256
            
            # Write key with restrictive permissions
            with open(key_path, 'wb') as f:
                f.write(key)
            
            # Set file permissions to 0400 (read-only for owner)
            key_path.chmod(0o400)
            
            logger.info("Generated new provenance key", key_path=str(key_path))
            
            # Log key generation (without the actual key)
            if AUDIT_LOGGER_AVAILABLE:
                audit_logger = get_audit_logger()
                if audit_logger:
                    audit_logger.log_entry({
                        "action": "provenance_key_generated",
                        "key_path": str(key_path),
                        "key_length": len(key),
                        "success": True
                    })
            
            return key
            
    except Exception as e:
        raise ProvenanceKeyError(f"Failed to ensure provenance key: {e}")


def compute_helper_digest(helper_dir: Path) -> Dict[str, str]:
    """
    Compute SHA256 digests for helper files.
    
    Args:
        helper_dir: Path to helper directory
        
    Returns:
        dict: File digests and overall digest
        
    Raises:
        ProvenanceError: If required files are missing or unreadable
    """
    helper_dir = Path(helper_dir)
    
    # Required files for provenance
    required_files = [
        "helper.yaml",
        "input.schema.json", 
        "output.schema.json"
    ]
    
    # Find entrypoint (main.py or main.js)
    entrypoint = None
    for candidate in ["main.py", "main.js"]:
        if (helper_dir / candidate).exists():
            entrypoint = candidate
            break
    
    if not entrypoint:
        raise ProvenanceError(f"No entrypoint found (main.py or main.js) in {helper_dir}")
    
    required_files.append(entrypoint)
    
    file_digests = {}
    
    try:
        # Compute digest for each file
        for filename in required_files:
            file_path = helper_dir / filename
            
            if not file_path.exists():
                raise ProvenanceError(f"Required file missing: {filename}")
            
            # Read file and compute SHA256
            with open(file_path, 'rb') as f:
                content = f.read()
            
            file_hash = hashlib.sha256(content).hexdigest()
            file_digests[filename] = file_hash
        
        # Compute overall digest from concatenated file hashes
        # Sort by filename for deterministic ordering
        sorted_files = sorted(file_digests.keys())
        concatenated_hashes = "".join(file_digests[f] for f in sorted_files)
        overall_digest = hashlib.sha256(concatenated_hashes.encode()).hexdigest()
        
        result = dict(file_digests)
        result["digest"] = overall_digest
        
        return result
        
    except Exception as e:
        if isinstance(e, ProvenanceError):
            raise
        raise ProvenanceError(f"Failed to compute helper digest: {e}")


def create_provenance(helper_id: str, helper_dir: Path, generator: str) -> Dict[str, Any]:
    """
    Create provenance record for a helper.
    
    Args:
        helper_id: Helper identifier
        helper_dir: Path to helper directory
        generator: Source that generated the helper (e.g., "claude_code_gen")
        
    Returns:
        dict: Provenance record
        
    Raises:
        ProvenanceError: If provenance cannot be created
    """
    try:
        # Compute file digests
        digests = compute_helper_digest(helper_dir)
        
        # Create provenance record
        provenance = {
            "version": "1.0",
            "helper_id": helper_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "generator": generator,
            "files": {k: v for k, v in digests.items() if k != "digest"},
            "digest": digests["digest"]
        }
        
        return provenance
        
    except Exception as e:
        if isinstance(e, ProvenanceError):
            raise
        raise ProvenanceError(f"Failed to create provenance: {e}")


def sign_provenance(provenance: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sign provenance record with HMAC-SHA256.
    
    Args:
        provenance: Provenance record to sign
        
    Returns:
        dict: Signed provenance record with "sig" field
        
    Raises:
        ProvenanceError: If signing fails
    """
    try:
        # Get HMAC key
        key = _ensure_key_exists()
        
        # Create canonical JSON representation for signing
        # Remove any existing signature first
        unsigned_prov = {k: v for k, v in provenance.items() if k != "sig"}
        canonical_json = json.dumps(unsigned_prov, sort_keys=True, separators=(',', ':'))
        
        # Compute HMAC-SHA256 signature
        signature = hmac.new(
            key,
            canonical_json.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Add signature to provenance
        signed_provenance = dict(provenance)
        signed_provenance["sig"] = signature
        
        return signed_provenance
        
    except Exception as e:
        if isinstance(e, (ProvenanceError, ProvenanceKeyError)):
            raise
        raise ProvenanceError(f"Failed to sign provenance: {e}")


def verify_provenance(helper_dir: Path) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Verify provenance of a helper directory.
    
    Args:
        helper_dir: Path to helper directory
        
    Returns:
        tuple: (ok, reason, details)
        - ok: True if verification passes
        - reason: Human-readable reason for success/failure
        - details: Additional verification details
        
    Note:
        This function is designed to never raise exceptions,
        returning verification results in the tuple instead.
    """
    helper_dir = Path(helper_dir)
    provenance_file = helper_dir / "provenance.json"
    
    details = {
        "helper_dir": str(helper_dir),
        "provenance_file_exists": False,
        "signature_valid": False,
        "files_valid": False,
        "missing_files": [],
        "file_mismatches": [],
        "provenance_data": None
    }
    
    try:
        # Check if provenance file exists
        if not provenance_file.exists():
            return False, "Provenance file missing", details
        
        details["provenance_file_exists"] = True
        
        # Read provenance file
        try:
            with open(provenance_file, 'r') as f:
                provenance = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            return False, f"Cannot read provenance file: {e}", details
        
        details["provenance_data"] = provenance
        
        # Check required fields
        required_fields = ["version", "helper_id", "timestamp", "generator", "files", "digest", "sig"]
        for field in required_fields:
            if field not in provenance:
                return False, f"Missing provenance field: {field}", details
        
        # Verify HMAC signature
        try:
            key = _ensure_key_exists()
            
            # Recreate canonical JSON without signature
            unsigned_prov = {k: v for k, v in provenance.items() if k != "sig"}
            canonical_json = json.dumps(unsigned_prov, sort_keys=True, separators=(',', ':'))
            
            # Compute expected signature
            expected_sig = hmac.new(
                key,
                canonical_json.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures using constant-time comparison
            if not hmac.compare_digest(provenance["sig"], expected_sig):
                return False, "Invalid HMAC signature", details
            
            details["signature_valid"] = True
            
        except Exception as e:
            return False, f"Signature verification failed: {e}", details
        
        # Verify file digests
        try:
            current_digests = compute_helper_digest(helper_dir)
            
            # Check each file digest
            for filename, expected_hash in provenance["files"].items():
                if filename not in current_digests:
                    details["missing_files"].append(filename)
                elif current_digests[filename] != expected_hash:
                    details["file_mismatches"].append({
                        "file": filename,
                        "expected": expected_hash,
                        "actual": current_digests[filename]
                    })
            
            # Check overall digest
            if current_digests["digest"] != provenance["digest"]:
                details["file_mismatches"].append({
                    "file": "overall_digest",
                    "expected": provenance["digest"],
                    "actual": current_digests["digest"]
                })
            
            if details["missing_files"] or details["file_mismatches"]:
                return False, "File integrity check failed", details
            
            details["files_valid"] = True
            
        except ProvenanceError as e:
            return False, f"File verification failed: {e}", details
        
        # All checks passed
        return True, "Provenance verification successful", details
        
    except Exception as e:
        return False, f"Verification error: {e}", details


def generate_and_save_provenance(helper_id: str, helper_dir: Path, generator: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Generate and save provenance for a helper.
    
    Args:
        helper_id: Helper identifier
        helper_dir: Path to helper directory  
        generator: Source that generated the helper
        
    Returns:
        tuple: (ok, reason, provenance_data)
    """
    try:
        # Create provenance record
        provenance = create_provenance(helper_id, helper_dir, generator)
        
        # Sign provenance
        signed_provenance = sign_provenance(provenance)
        
        # Save to file
        provenance_file = helper_dir / "provenance.json"
        with open(provenance_file, 'w') as f:
            json.dump(signed_provenance, f, indent=2)
        
        # Log provenance generation
        if AUDIT_LOGGER_AVAILABLE:
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "agent_provenance_generate",
                    "helper_id": helper_id,
                    "generator": generator,
                    "digest": signed_provenance["digest"],
                    "success": True
                })
        
        logger.info("Generated provenance", helper_id=helper_id, generator=generator)
        
        return True, "Provenance generated successfully", signed_provenance
        
    except Exception as e:
        # Log failure
        if AUDIT_LOGGER_AVAILABLE:
            audit_logger = get_audit_logger()
            if audit_logger:
                audit_logger.log_entry({
                    "action": "agent_provenance_generate",
                    "helper_id": helper_id,
                    "generator": generator,
                    "error": sanitize_text(str(e)),
                    "success": False
                })
        
        logger.error("Failed to generate provenance", helper_id=helper_id, error=str(e))
        
        return False, f"Failed to generate provenance: {e}", {}


def log_verification_result(helper_id: str, ok: bool, reason: str, details: Dict[str, Any]):
    """Log provenance verification result to audit log."""
    if AUDIT_LOGGER_AVAILABLE:
        audit_logger = get_audit_logger()
        if audit_logger:
            # Sanitize details for audit log
            sanitized_details = {
                "helper_dir": details.get("helper_dir"),
                "provenance_file_exists": details.get("provenance_file_exists"),
                "signature_valid": details.get("signature_valid"),
                "files_valid": details.get("files_valid"),
                "missing_files_count": len(details.get("missing_files", [])),
                "file_mismatches_count": len(details.get("file_mismatches", []))
            }
            
            audit_logger.log_entry({
                "action": "agent_provenance_verify",
                "helper_id": helper_id,
                "success": ok,
                "reason": sanitize_text(reason),
                "details": sanitized_details
            })