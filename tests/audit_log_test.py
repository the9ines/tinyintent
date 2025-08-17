#!/usr/bin/env python3
"""
Tests for Audit Log Integrity & Rotation - M6.2

Tests integrity chaining, tamper detection, log rotation, and continuity preservation.
"""

import hashlib
import json
import os
import signal
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add bridge to path for testing
import sys
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

from logs.rotate import (
    AuditLogIntegrity, 
    AuditLogRotator, 
    AuditLogger,
    initialize_audit_logger
)


class TestAuditLogIntegrity(unittest.TestCase):
    """Test integrity chaining and verification."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        self.integrity = AuditLogIntegrity(self.audit_log)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_genesis_hash_for_new_log(self):
        """Test that new logs start with genesis hash."""
        self.assertEqual(self.integrity.last_hash, "genesis")
    
    def test_single_entry_integrity(self):
        """Test integrity chaining for a single entry."""
        entry = {
            "ts": "2025-08-17T12:00:00.000Z",
            "action": "test_action",
            "success": True
        }
        
        hash_result = self.integrity.append_entry(entry)
        
        # Verify hash was computed and stored
        self.assertIsNotNone(hash_result)
        self.assertEqual(self.integrity.last_hash, hash_result)
        
        # Verify entry was written with integrity fields
        with open(self.audit_log, 'r') as f:
            written_entry = json.loads(f.read().strip())
        
        self.assertIn("integrity_hash", written_entry)
        self.assertIn("prev_hash", written_entry)
        self.assertEqual(written_entry["prev_hash"], "genesis")
        self.assertEqual(written_entry["integrity_hash"], hash_result)
    
    def test_multiple_entries_chain(self):
        """Test integrity chaining across multiple entries."""
        entries = [
            {"ts": "2025-08-17T12:00:00.000Z", "action": "action1", "success": True},
            {"ts": "2025-08-17T12:01:00.000Z", "action": "action2", "success": True},
            {"ts": "2025-08-17T12:02:00.000Z", "action": "action3", "success": False}
        ]
        
        hashes = []
        for entry in entries:
            hash_result = self.integrity.append_entry(entry)
            hashes.append(hash_result)
        
        # Verify chain integrity
        is_valid, errors = self.integrity.verify_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Verify each entry has correct previous hash
        with open(self.audit_log, 'r') as f:
            lines = f.readlines()
        
        written_entries = [json.loads(line.strip()) for line in lines]
        
        # First entry should reference genesis
        self.assertEqual(written_entries[0]["prev_hash"], "genesis")
        
        # Subsequent entries should reference previous hash
        for i in range(1, len(written_entries)):
            self.assertEqual(written_entries[i]["prev_hash"], written_entries[i-1]["integrity_hash"])
    
    def test_integrity_verification_valid_log(self):
        """Test verification of a valid log."""
        # Create a few entries
        for i in range(5):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"test_action_{i}",
                "success": True
            }
            self.integrity.append_entry(entry)
        
        # Verify integrity
        is_valid, errors = self.integrity.verify_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_integrity_verification_tampered_log(self):
        """Test detection of tampered log entries."""
        # Create initial entries
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"test_action_{i}",
                "success": True
            }
            self.integrity.append_entry(entry)
        
        # Tamper with the middle entry
        with open(self.audit_log, 'r') as f:
            lines = f.readlines()
        
        # Modify the second entry's data (but not its hash)
        tampered_entry = json.loads(lines[1].strip())
        tampered_entry["action"] = "TAMPERED_ACTION"
        lines[1] = json.dumps(tampered_entry) + '\n'
        
        # Write back the tampered log
        with open(self.audit_log, 'w') as f:
            f.writelines(lines)
        
        # Re-initialize integrity checker and verify
        self.integrity = AuditLogIntegrity(self.audit_log)
        is_valid, errors = self.integrity.verify_integrity()
        
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("Hash mismatch" in error for error in errors))
    
    def test_integrity_verification_broken_chain(self):
        """Test detection of broken hash chain."""
        # Create initial entries
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"test_action_{i}",
                "success": True
            }
            self.integrity.append_entry(entry)
        
        # Break the chain by modifying prev_hash of second entry
        with open(self.audit_log, 'r') as f:
            lines = f.readlines()
        
        tampered_entry = json.loads(lines[1].strip())
        tampered_entry["prev_hash"] = "invalid_hash"
        lines[1] = json.dumps(tampered_entry) + '\n'
        
        with open(self.audit_log, 'w') as f:
            f.writelines(lines)
        
        # Verify broken chain is detected
        self.integrity = AuditLogIntegrity(self.audit_log)
        is_valid, errors = self.integrity.verify_integrity()
        
        self.assertFalse(is_valid)
        self.assertTrue(any("Chain break" in error for error in errors))
    
    def test_integrity_verification_missing_fields(self):
        """Test detection of entries missing integrity fields."""
        # Create a valid entry first
        entry = {
            "ts": "2025-08-17T12:00:00.000Z",
            "action": "valid_action",
            "success": True
        }
        self.integrity.append_entry(entry)
        
        # Manually append an entry without integrity fields (like old format)
        old_format_entry = {
            "ts": "2025-08-17T12:01:00.000Z",
            "action": "old_format_action",
            "success": True
        }
        
        with open(self.audit_log, 'a') as f:
            f.write(json.dumps(old_format_entry) + '\n')
        
        # Verify missing fields are detected
        self.integrity = AuditLogIntegrity(self.audit_log)
        is_valid, errors = self.integrity.verify_integrity()
        
        self.assertFalse(is_valid)
        self.assertTrue(any("Missing integrity_hash field" in error for error in errors))
    
    def test_load_last_hash_from_existing_log(self):
        """Test loading last hash from existing log file."""
        # Create entries with one integrity checker
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"test_action_{i}",
                "success": True
            }
            self.integrity.append_entry(entry)
        
        last_hash = self.integrity.last_hash
        
        # Create new integrity checker and verify it loads the correct last hash
        new_integrity = AuditLogIntegrity(self.audit_log)
        self.assertEqual(new_integrity.last_hash, last_hash)


class TestAuditLogRotation(unittest.TestCase):
    """Test audit log rotation functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        self.rotator = AuditLogRotator(self.audit_log, max_size_mb=1)  # 1MB for testing
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_should_rotate_based_on_size(self):
        """Test rotation trigger based on file size."""
        # Initially should not need rotation
        self.assertFalse(self.rotator.should_rotate())
        
        # Create large entries to exceed size limit
        large_data = "x" * 1000  # 1KB per entry
        for i in range(1200):  # > 1MB total
            entry = {
                "ts": f"2025-08-17T12:{i:04d}:00.000Z",
                "action": "large_action",
                "data": large_data,
                "success": True
            }
            self.rotator.append_entry(entry)
        
        # Should now need rotation
        self.assertTrue(self.rotator.should_rotate())
    
    def test_rotation_preserves_integrity_chain(self):
        """Test that rotation preserves integrity chain across files."""
        # Create initial entries
        for i in range(5):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            self.rotator.append_entry(entry)
        
        # Get last hash before rotation
        last_hash_before = self.rotator.integrity.last_hash
        
        # Force rotation
        rotated = self.rotator._perform_rotation()
        self.assertTrue(rotated)
        
        # Check that archived file was created
        archive_files = self.rotator.get_archive_files()
        self.assertEqual(len(archive_files), 1)
        
        # Verify new log starts with continuation hash
        self.assertEqual(self.rotator.integrity.last_hash, last_hash_before)
        
        # Add entry to new log and verify chain
        new_entry = {
            "ts": "2025-08-17T12:10:00.000Z",
            "action": "post_rotation_action",
            "success": True
        }
        self.rotator.append_entry(new_entry)
        
        # Verify integrity of new log
        is_valid, errors = self.rotator.verify_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_rotation_creates_timestamped_archive(self):
        """Test that rotation creates properly named archive files."""
        # Create some entries
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            self.rotator.append_entry(entry)
        
        # Force rotation
        rotated = self.rotator._perform_rotation()
        self.assertTrue(rotated)
        
        # Check archive file naming
        archive_files = self.rotator.get_archive_files()
        self.assertEqual(len(archive_files), 1)
        
        archive_name = archive_files[0].name
        self.assertTrue(archive_name.startswith("audit-"))
        self.assertTrue(archive_name.endswith(".log"))
        # Should contain timestamp in format YYYYMMDD-HHMM
        self.assertTrue(len(archive_name.split("-")) >= 3)
    
    def test_rotation_handles_duplicate_filenames(self):
        """Test that rotation handles duplicate archive filenames."""
        # Create some entries
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            self.rotator.append_entry(entry)
        
        # Mock datetime to return consistent timestamp
        with patch('logs.rotate.datetime') as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20250817-1200"
            mock_datetime.utcnow.return_value.isoformat.return_value = "2025-08-17T12:00:00.000000"
            
            # First rotation
            self.rotator._perform_rotation()
            
            # Add more entries
            for i in range(3):
                entry = {
                    "ts": f"2025-08-17T12:1{i}:00.000Z",
                    "action": f"action2_{i}",
                    "success": True
                }
                self.rotator.append_entry(entry)
            
            # Second rotation with same timestamp
            self.rotator._perform_rotation()
        
        # Should have two archive files with different suffixes
        archive_files = self.rotator.get_archive_files()
        self.assertEqual(len(archive_files), 2)
        
        archive_names = [f.name for f in archive_files]
        self.assertIn("audit-20250817-1200.log", archive_names)
        self.assertIn("audit-20250817-1200-1.log", archive_names)
    
    def test_signal_rotation_handler(self):
        """Test SIGHUP signal handling for rotation."""
        # Create some entries
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            self.rotator.append_entry(entry)
        
        # Verify no archives initially
        self.assertEqual(len(self.rotator.get_archive_files()), 0)
        
        # Send SIGHUP signal to trigger rotation
        with patch.object(self.rotator, 'rotate_if_needed') as mock_rotate:
            # Simulate signal handler call
            self.rotator._signal_rotate(signal.SIGHUP, None)
            mock_rotate.assert_called_once_with(force=True)
    
    def test_non_blocking_rotation(self):
        """Test that rotation doesn't block normal operations."""
        # This test verifies the rotation happens in background
        original_append = self.rotator.integrity.append_entry
        
        append_calls = []
        def mock_append(entry):
            append_calls.append(entry)
            return original_append(entry)
        
        with patch.object(self.rotator.integrity, 'append_entry', side_effect=mock_append):
            # Create entry that would trigger rotation
            large_entry = {
                "ts": "2025-08-17T12:00:00.000Z",
                "action": "large_action",
                "data": "x" * (2 * 1024 * 1024),  # 2MB
                "success": True
            }
            
            # This should not block even though it triggers rotation
            result = self.rotator.append_entry(large_entry)
            
            # Entry should be appended immediately
            self.assertIsNotNone(result)
            self.assertEqual(len(append_calls), 1)


class TestAuditLogger(unittest.TestCase):
    """Test the main AuditLogger interface."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
        self.logger = AuditLogger(self.audit_log, max_size_mb=1)
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_log_entry_with_integrity(self):
        """Test logging entries with integrity chaining."""
        entry = {
            "ts": "2025-08-17T12:00:00.000Z",
            "action": "test_action",
            "success": True
        }
        
        hash_result = self.logger.log_entry(entry)
        self.assertIsNotNone(hash_result)
        
        # Verify integrity
        is_valid, errors = self.logger.verify_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_verify_all_integrity_with_archives(self):
        """Test verification of current log and archived logs."""
        # Create entries to force rotation
        for i in range(10):
            large_entry = {
                "ts": f"2025-08-17T12:{i:02d}:00.000Z",
                "action": f"action_{i}",
                "data": "x" * 150000,  # 150KB per entry
                "success": True
            }
            self.logger.log_entry(large_entry)
        
        # Force rotation
        self.logger.rotate_now()
        
        # Add more entries to new log
        for i in range(5):
            entry = {
                "ts": f"2025-08-17T13:{i:02d}:00.000Z",
                "action": f"new_action_{i}",
                "success": True
            }
            self.logger.log_entry(entry)
        
        # Verify all logs (current + archived)
        is_valid, errors = self.logger.verify_all_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_get_stats(self):
        """Test audit log statistics."""
        # Add some entries
        for i in range(5):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            self.logger.log_entry(entry)
        
        stats = self.logger.get_stats()
        
        self.assertIn("current_log_size", stats)
        self.assertIn("current_log_size_mb", stats)
        self.assertIn("max_size_mb", stats)
        self.assertIn("archive_count", stats)
        self.assertIn("archives", stats)
        self.assertIn("last_hash", stats)
        
        self.assertGreater(stats["current_log_size"], 0)
        self.assertEqual(stats["max_size_mb"], 1)
        self.assertEqual(stats["archive_count"], 0)


class TestIntegrationWithTinyRPC(unittest.TestCase):
    """Test integration with TinyRPC startup checks."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_initialization_with_valid_log(self):
        """Test initialization when log is valid."""
        # Create a valid log first
        logger = AuditLogger(self.audit_log)
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            logger.log_entry(entry)
        
        # Reinitialize (simulating startup)
        new_logger = initialize_audit_logger(self.audit_log)
        is_valid, errors = new_logger.verify_integrity()
        
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_initialization_with_corrupted_log(self):
        """Test initialization when log is corrupted."""
        # Create a log and then corrupt it
        logger = AuditLogger(self.audit_log)
        for i in range(3):
            entry = {
                "ts": f"2025-08-17T12:0{i}:00.000Z",
                "action": f"action_{i}",
                "success": True
            }
            logger.log_entry(entry)
        
        # Corrupt the log by truncating it
        with open(self.audit_log, 'r+') as f:
            content = f.read()
            f.seek(0)
            f.write(content[:len(content)//2])  # Truncate to half
            f.truncate()
        
        # Reinitialize and check
        new_logger = initialize_audit_logger(self.audit_log)
        is_valid, errors = new_logger.verify_integrity()
        
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
    
    def test_backward_compatibility_with_old_logs(self):
        """Test handling of logs without integrity fields."""
        # Create old-format log entries (without integrity fields)
        old_entries = [
            {"ts": "2025-08-17T12:00:00.000Z", "action": "old_action_1", "success": True},
            {"ts": "2025-08-17T12:01:00.000Z", "action": "old_action_2", "success": False},
        ]
        
        with open(self.audit_log, 'w') as f:
            for entry in old_entries:
                f.write(json.dumps(entry) + '\n')
        
        # Initialize with mixed log
        logger = initialize_audit_logger(self.audit_log)
        
        # Should detect missing integrity fields
        is_valid, errors = logger.verify_integrity()
        self.assertFalse(is_valid)
        
        # But should be able to continue adding new entries with integrity
        new_entry = {
            "ts": "2025-08-17T12:02:00.000Z",
            "action": "new_action",
            "success": True
        }
        hash_result = logger.log_entry(new_entry)
        self.assertIsNotNone(hash_result)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and error conditions."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_log = Path(self.temp_dir) / "audit.log"
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_empty_log_file(self):
        """Test handling of empty log file."""
        # Create empty file
        self.audit_log.touch()
        
        integrity = AuditLogIntegrity(self.audit_log)
        self.assertEqual(integrity.last_hash, "genesis")
        
        is_valid, errors = integrity.verify_integrity()
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_log_with_blank_lines(self):
        """Test handling of log with blank lines."""
        # Create log with blank lines
        entries = [
            {"ts": "2025-08-17T12:00:00.000Z", "action": "action_1", "success": True},
            {"ts": "2025-08-17T12:01:00.000Z", "action": "action_2", "success": True},
        ]
        
        with open(self.audit_log, 'w') as f:
            f.write(json.dumps(entries[0]) + '\n')
            f.write('\n')  # Blank line
            f.write(json.dumps(entries[1]) + '\n')
            f.write('\n\n')  # More blank lines
        
        # Should handle blank lines gracefully
        integrity = AuditLogIntegrity(self.audit_log)
        is_valid, errors = integrity.verify_integrity()
        
        # Should fail due to missing integrity fields, but not due to blank lines
        self.assertFalse(is_valid)
        self.assertTrue(all("Missing integrity_hash field" in error for error in errors))
    
    def test_rotation_with_readonly_directory(self):
        """Test rotation behavior with permission errors."""
        logger = AuditLogger(self.audit_log)
        
        # Add some entries
        entry = {
            "ts": "2025-08-17T12:00:00.000Z",
            "action": "test_action",
            "success": True
        }
        logger.log_entry(entry)
        
        # Make directory read-only (simulating permission error)
        os.chmod(self.temp_dir, 0o444)
        
        try:
            # Rotation should fail gracefully
            result = logger.rotate_now()
            self.assertFalse(result)  # Should return False on failure
            
            # Should still be able to verify current log
            is_valid, errors = logger.verify_integrity()
            self.assertTrue(is_valid)
        finally:
            # Restore permissions for cleanup
            os.chmod(self.temp_dir, 0o755)


if __name__ == "__main__":
    unittest.main()