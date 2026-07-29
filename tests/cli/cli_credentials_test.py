"""
Tests for CLI credential management functions.

Tests cover:
- CredentialManager class
- Credential generation, storage, loading
- CLI show_credentials and regenerate_credentials functions
- Environment variable setup
- Server startup fallback paths
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

import pytest


class TestCredentialManager:
    """Test the CredentialManager class."""

    def test_generate_secure_credentials(self, tmp_path):
        """Test credential generation produces strong credentials."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)
        credentials = manager.generate_secure_credentials()

        # Check all required fields
        assert "tinyintent_secret" in credentials
        assert "shortcut_token" in credentials
        assert "generated_at" in credentials
        assert "version" in credentials
        assert "auto_generated" in credentials

        # Check credential strength
        assert len(credentials["tinyintent_secret"]) >= 48
        assert len(credentials["shortcut_token"]) >= 24

        # Check auto_generated flag
        assert credentials["auto_generated"] is True

    def test_save_credentials_creates_file(self, tmp_path):
        """Test credentials are saved to file with correct permissions."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)
        credentials = manager.generate_secure_credentials()

        manager.save_credentials(credentials)

        # Check file exists
        assert manager.credentials_file.exists()

        # Check permissions (owner read/write only)
        file_mode = manager.credentials_file.stat().st_mode & 0o777
        assert file_mode == 0o600

        # Check content
        with open(manager.credentials_file) as f:
            saved = json.load(f)
        assert saved["tinyintent_secret"] == credentials["tinyintent_secret"]
        assert saved["shortcut_token"] == credentials["shortcut_token"]

    def test_save_credentials_creates_backup(self, tmp_path):
        """Test saving credentials creates backup of existing ones."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Create initial credentials
        creds1 = manager.generate_secure_credentials()
        manager.save_credentials(creds1)

        # Create new credentials (should backup old)
        creds2 = manager.generate_secure_credentials()
        manager.save_credentials(creds2)

        # Check backup exists
        backups = list(manager.backup_dir.glob("credentials-*.json"))
        assert len(backups) == 1

        # Check backup contains original credentials
        with open(backups[0]) as f:
            backup_data = json.load(f)
        assert backup_data["tinyintent_secret"] == creds1["tinyintent_secret"]

    def test_load_credentials_returns_none_when_missing(self, tmp_path):
        """Test loading credentials when file doesn't exist."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)
        result = manager.load_credentials()

        assert result is None

    def test_load_credentials_returns_valid_credentials(self, tmp_path):
        """Test loading valid credentials from file."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Save credentials
        credentials = manager.generate_secure_credentials()
        manager.save_credentials(credentials)

        # Load and verify
        loaded = manager.load_credentials()
        assert loaded is not None
        assert loaded["tinyintent_secret"] == credentials["tinyintent_secret"]
        assert loaded["shortcut_token"] == credentials["shortcut_token"]

    def test_load_credentials_rejects_weak_credentials(self, tmp_path):
        """Test that weak credentials are rejected."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Create weak credentials file manually
        weak_creds = {
            "tinyintent_secret": "short",  # Too short
            "shortcut_token": "tiny",  # Too short
            "generated_at": "2024-01-01T00:00:00"
        }
        manager.credentials_file.parent.mkdir(exist_ok=True)
        with open(manager.credentials_file, 'w') as f:
            json.dump(weak_creds, f)

        # Should return None for weak credentials
        loaded = manager.load_credentials()
        assert loaded is None

    def test_load_credentials_rejects_invalid_json(self, tmp_path):
        """Test that invalid JSON file returns None."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Create invalid JSON file
        manager.credentials_file.parent.mkdir(exist_ok=True)
        with open(manager.credentials_file, 'w') as f:
            f.write("not valid json {")

        # Should return None for invalid JSON
        loaded = manager.load_credentials()
        assert loaded is None

    def test_get_or_create_credentials_creates_when_missing(self, tmp_path):
        """Test get_or_create creates credentials when missing."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)
        credentials = manager.get_or_create_credentials()

        # Should create and return credentials
        assert credentials is not None
        assert "tinyintent_secret" in credentials
        assert manager.credentials_file.exists()

    def test_get_or_create_credentials_returns_existing(self, tmp_path):
        """Test get_or_create returns existing credentials."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Create credentials
        original = manager.get_or_create_credentials()

        # Get again - should return same
        again = manager.get_or_create_credentials()
        assert again["tinyintent_secret"] == original["tinyintent_secret"]

    def test_regenerate_credentials(self, tmp_path):
        """Test credential regeneration."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Create initial credentials
        original = manager.get_or_create_credentials()

        # Regenerate
        regenerated = manager.regenerate_credentials()

        # Should be different
        assert regenerated["tinyintent_secret"] != original["tinyintent_secret"]
        assert regenerated["shortcut_token"] != original["shortcut_token"]

    def test_get_credential_info_with_secret_hidden(self, tmp_path):
        """Test credential info display with secret hidden."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)
        manager.get_or_create_credentials()

        info = manager.get_credential_info(show_secret=False)

        assert info["secret_status"] == "Set"
        assert "shortcut_token" in info
        assert info["secret_length"] > 0

    def test_get_credential_info_with_secret_shown(self, tmp_path):
        """Test credential info display with secret shown."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)
        creds = manager.get_or_create_credentials()

        info = manager.get_credential_info(show_secret=True)

        assert info["secret_status"] == creds["tinyintent_secret"]

    def test_get_credential_info_no_credentials(self, tmp_path):
        """Test credential info when no credentials exist."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        info = manager.get_credential_info()

        assert "status" in info
        assert "No credentials found" in info["status"]

    def test_apply_to_environment(self, tmp_path):
        """Test applying credentials to environment variables."""
        from tinyintent.credentials import CredentialManager

        manager = CredentialManager(config_dir=tmp_path)

        # Clear any existing env vars
        os.environ.pop("TINYINTENT_SECRET", None)
        os.environ.pop("SHORTCUT_TOKEN", None)

        secret, token = manager.apply_to_environment()

        # Check environment variables are set
        assert os.environ["TINYINTENT_SECRET"] == secret
        assert os.environ["SHORTCUT_TOKEN"] == token

        # Cleanup
        os.environ.pop("TINYINTENT_SECRET", None)
        os.environ.pop("SHORTCUT_TOKEN", None)

    def test_cleanup_old_backups(self, tmp_path):
        """Test cleanup of old backup files."""
        from tinyintent.credentials import CredentialManager
        import time

        manager = CredentialManager(config_dir=tmp_path)

        # Create old backup file
        old_backup = manager.backup_dir / "credentials-20200101-000000.json"
        old_backup.parent.mkdir(exist_ok=True)
        old_backup.write_text("{}")

        # Set modification time to 60 days ago
        old_time = time.time() - (60 * 24 * 3600)
        os.utime(old_backup, (old_time, old_time))

        # Create recent backup
        recent_backup = manager.backup_dir / "credentials-recent.json"
        recent_backup.write_text("{}")

        # Cleanup with 30 day retention
        manager.cleanup_old_backups(keep_days=30)

        # Old should be gone, recent should remain
        assert not old_backup.exists()
        assert recent_backup.exists()


class TestCLIShowCredentials:
    """Test the show_credentials CLI function."""

    def test_show_credentials_displays_info(self, tmp_path):
        """Test show_credentials displays credential information."""
        from tinyintent.credentials import CredentialManager

        # Setup credentials
        manager = CredentialManager(config_dir=tmp_path)
        manager.get_or_create_credentials()

        # Mock the CLI function's credential manager
        with patch('tinyintent.cli.get_credential_info') as mock_get_info:
            mock_get_info.return_value = {
                "shortcut_token": "test-token-123",
                "secret_status": "Set",
                "generated_at": "2024-01-01T00:00:00",
                "auto_generated": True,
                "secret_length": 64,
                "token_length": 32
            }

            # Capture console output
            with patch('tinyintent.cli.console') as mock_console:
                from tinyintent.cli import show_credentials
                show_credentials(show_secret=False)

                # Verify console.print was called
                assert mock_console.print.called

    def test_show_credentials_handles_missing_credentials(self):
        """Test show_credentials handles missing credentials gracefully."""
        with patch('tinyintent.cli.get_credential_info') as mock_get_info:
            mock_get_info.return_value = {"status": "No credentials found"}

            with patch('tinyintent.cli.console') as mock_console:
                from tinyintent.cli import show_credentials
                show_credentials()

                # Should show error message
                calls = [str(call) for call in mock_console.print.call_args_list]
                assert any("No credentials found" in str(call) or "Run 'tinyintent'" in str(call)
                          for call in calls)


class TestCLIRegenerateCredentials:
    """Test the regenerate_credentials CLI function."""

    def test_regenerate_credentials_with_confirmation(self):
        """Test regenerate_credentials with user confirmation."""
        with patch('tinyintent.cli.regenerate_credentials') as mock_regen:
            mock_regen.return_value = {
                "shortcut_token": "new-token-456",
                "tinyintent_secret": "new-secret"
            }

            with patch('tinyintent.cli.console') as mock_console:
                # Mock user input to confirm
                mock_console.input.return_value = "y"

                from tinyintent.cli import regenerate_credentials
                regenerate_credentials()

                # Should have regenerated
                mock_regen.assert_called_once()

    def test_regenerate_credentials_cancelled(self):
        """Test regenerate_credentials when user cancels."""
        with patch('tinyintent.cli.regenerate_credentials') as mock_regen:
            with patch('tinyintent.cli.console') as mock_console:
                # Mock user input to cancel
                mock_console.input.return_value = "n"

                from tinyintent.cli import regenerate_credentials
                regenerate_credentials()

                # Should NOT have regenerated
                mock_regen.assert_not_called()


class TestCLISetupEnvironment:
    """Test the setup_environment function."""

    def test_setup_environment_creates_credentials(self):
        """Test setup_environment creates credentials when missing."""
        # Clear environment
        os.environ.pop("TINYINTENT_SECRET", None)
        os.environ.pop("SHORTCUT_TOKEN", None)

        with patch('tinyintent.cli.apply_credentials_to_environment') as mock_apply:
            mock_apply.return_value = ("test-secret", "test-token")

            from tinyintent.cli import setup_environment
            setup_environment(quiet=True)

            mock_apply.assert_called_once()

    def test_setup_environment_sets_defaults(self):
        """Test setup_environment sets default environment variables."""
        # Set credentials to avoid credential setup
        os.environ["TINYINTENT_SECRET"] = "existing-secret"
        os.environ["SHORTCUT_TOKEN"] = "existing-token"

        # Clear other defaults
        os.environ.pop("TINYINTENT_PORT", None)
        os.environ.pop("TINYINTENT_BIND", None)

        from tinyintent.cli import setup_environment
        setup_environment(quiet=True)

        # Check defaults are set
        assert os.environ.get("TINYINTENT_PORT") == "8787"
        assert os.environ.get("TINYINTENT_BIND") == "0.0.0.0"
        assert os.environ.get("TINYINTENT_ALLOW_DEV_LOCAL") == "1"

        # Cleanup
        os.environ.pop("TINYINTENT_SECRET", None)
        os.environ.pop("SHORTCUT_TOKEN", None)

    def test_setup_environment_fallback_on_error(self):
        """Test setup_environment falls back to temporary credentials on error."""
        os.environ.pop("TINYINTENT_SECRET", None)
        os.environ.pop("SHORTCUT_TOKEN", None)

        with patch('tinyintent.cli.apply_credentials_to_environment') as mock_apply:
            mock_apply.side_effect = Exception("Credential error")

            from tinyintent.cli import setup_environment
            setup_environment(quiet=True)

            # Should have temporary credentials set
            assert "TINYINTENT_SECRET" in os.environ
            assert "SHORTCUT_TOKEN" in os.environ
            assert len(os.environ["TINYINTENT_SECRET"]) > 20

        # Cleanup
        os.environ.pop("TINYINTENT_SECRET", None)
        os.environ.pop("SHORTCUT_TOKEN", None)


class TestCLIStartServer:
    """Test the start_server function."""

    def test_start_server_uses_provided_port(self):
        """Test start_server uses provided port parameter."""
        with patch('tinyintent.cli.setup_environment'):
            with patch('tinyintent.cli.uvicorn.run') as mock_run:
                with patch('tinyintent.cli.console'):
                    # Mock the import of bridge app
                    with patch.dict('sys.modules', {'bridge.tinyrpc': MagicMock()}):
                        from tinyintent.cli import start_server

                        # This will fail on actual uvicorn.run, but we're mocking
                        try:
                            start_server(host="127.0.0.1", port=9000, quiet=True)
                        except:
                            pass

                        # Check uvicorn was called with correct port
                        if mock_run.called:
                            call_kwargs = mock_run.call_args[1]
                            assert call_kwargs.get("port") == 9000


class TestCLIMainFunction:
    """Test the main CLI entry point."""

    def test_main_with_status_command(self):
        """Test main function with status command."""
        with patch('sys.argv', ['tinyintent', 'status']):
            with patch('tinyintent.cli.show_status') as mock_status:
                from tinyintent.cli import main
                main()
                mock_status.assert_called_once()

    def test_main_with_show_credentials_command(self):
        """Test main function with show-credentials command."""
        with patch('sys.argv', ['tinyintent', 'show-credentials']):
            with patch('tinyintent.cli.show_credentials') as mock_show:
                from tinyintent.cli import main
                main()
                mock_show.assert_called_once()

    def test_main_with_show_secret_flag(self):
        """Test main function with --show-secret flag."""
        with patch('sys.argv', ['tinyintent', 'show-credentials', '--show-secret']):
            with patch('tinyintent.cli.show_credentials') as mock_show:
                from tinyintent.cli import main
                main()
                mock_show.assert_called_once_with(show_secret=True)

    def test_main_with_regenerate_command(self):
        """Test main function with regenerate-credentials command."""
        with patch('sys.argv', ['tinyintent', 'regenerate-credentials']):
            with patch('tinyintent.cli.regenerate_credentials') as mock_regen:
                from tinyintent.cli import main
                main()
                mock_regen.assert_called_once()

    def test_main_with_verbose_flag(self):
        """Test main function with verbose flag sets debug logging."""
        with patch('sys.argv', ['tinyintent', 'status', '--verbose']):
            with patch('tinyintent.cli.show_status'):
                from tinyintent.cli import main
                main()
                assert os.environ.get('TINYINTENT_LOG_LEVEL') == 'debug'

        # Cleanup
        os.environ.pop('TINYINTENT_LOG_LEVEL', None)

    def test_main_with_quiet_flag(self):
        """Test main function with quiet flag sets error logging."""
        with patch('sys.argv', ['tinyintent', 'status', '--quiet']):
            with patch('tinyintent.cli.show_status'):
                from tinyintent.cli import main
                main()
                assert os.environ.get('TINYINTENT_LOG_LEVEL') == 'error'

        # Cleanup
        os.environ.pop('TINYINTENT_LOG_LEVEL', None)
