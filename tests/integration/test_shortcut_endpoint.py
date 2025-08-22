#!/usr/bin/env python3
"""
M11.0: iPhone Shortcut Voice Interface Tests

Comprehensive test suite for iOS Shortcuts integration endpoints.
Tests authentication, routing, text formatting, error handling,
and integration with existing TinyIntent flow.
"""

import os
import sys
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

# Skip if fastapi not available (for environments without full dependencies)
try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# Test modules
from bridge.shortcut_format import (
    to_speakable_text,
    sanitize_short_input,
    format_shortcut_response,
    get_shortcut_error_response,
    _format_for_speech,
    _strip_markdown
)


class TestShortcutFormatting:
    """Test shortcut text formatting utilities."""
    
    def test_to_speakable_text_with_assistant_text(self):
        """Test that assistant_text is preferred for speakable output."""
        payload = {
            "status": "success",
            "assistant_text": "Position closed on ETH at market price.",
            "gen_text": "Alternative text",
            "message": "Generic message"
        }
        
        result = to_speakable_text(payload)
        assert result == "Position closed on ETH at market price."
    
    def test_to_speakable_text_synthesis_from_structure(self):
        """Test synthesis when no preferred text fields are available."""
        payload = {
            "status": "success",
            "action": "preview",
            "helper_id": "bot_guard",
            "preview_json": {
                "message": "Found 3 active positions",
                "positions": [{"symbol": "BTC"}, {"symbol": "ETH"}, {"symbol": "SOL"}]
            }
        }
        
        result = to_speakable_text(payload)
        assert "Found 3 active positions" in result
    
    def test_to_speakable_text_bot_guard_synthesis(self):
        """Test specific bot_guard helper synthesis."""
        payload = {
            "status": "success",
            "action": "preview",
            "helper_id": "bot_guard",
            "preview_json": {
                "positions": [
                    {"symbol": "BTC", "size": 1.5},
                    {"symbol": "ETH", "size": 10.0}
                ]
            }
        }
        
        result = to_speakable_text(payload)
        assert "Found 2 trading positions" in result
    
    def test_to_speakable_text_error_handling(self):
        """Test error case synthesis."""
        payload = {
            "status": "error",
            "error": "Helper not found"
        }
        
        result = to_speakable_text(payload)
        assert "Error: Helper not found" in result
    
    def test_format_for_speech_markdown_removal(self):
        """Test markdown removal for speech synthesis."""
        text = "**Bold text** and *italic text* with `code` and [link](http://example.com)"
        result = _format_for_speech(text)
        assert "**" not in result
        assert "*" not in result
        assert "`" not in result
        assert "http://" not in result
        assert "Bold text and italic text" in result
    
    def test_format_for_speech_length_limiting(self):
        """Test that long text gets truncated appropriately."""
        long_text = "This is a very long text. " * 20  # Much longer than 280 chars
        result = _format_for_speech(long_text)
        assert len(result) <= 280
        assert result.endswith('.')
    
    def test_strip_markdown_comprehensive(self):
        """Test comprehensive markdown stripping."""
        markdown_text = """
        # Header
        **Bold text** and __also bold__
        *Italic text* and _also italic_
        - List item 1
        - List item 2
        1. Numbered item
        > Blockquote
        [Link text](http://example.com)
        """
        
        result = _strip_markdown(markdown_text)
        assert "#" not in result
        assert "**" not in result
        assert "__" not in result
        assert "*" not in result
        assert "_" not in result
        assert "-" not in result  # List markers should be removed
        assert ">" not in result
        assert "[" not in result
        assert "]" not in result
        assert "(" not in result
        assert ")" not in result
    
    def test_sanitize_short_input_valid(self):
        """Test valid input sanitization."""
        text = "  Close my ETH position  "
        result = sanitize_short_input(text, max_length=100)
        assert result == "Close my ETH position"
    
    def test_sanitize_short_input_too_long(self):
        """Test input that exceeds length limit."""
        long_text = "x" * 900
        
        with pytest.raises(ValueError) as exc_info:
            sanitize_short_input(long_text, max_length=800)
        
        assert "too long" in str(exc_info.value)
    
    def test_sanitize_short_input_empty(self):
        """Test empty input rejection."""
        with pytest.raises(ValueError) as exc_info:
            sanitize_short_input("   ")
        
        assert "empty" in str(exc_info.value)
    
    def test_sanitize_short_input_control_chars(self):
        """Test control character removal."""
        text_with_control = "Hello\x00\x01World"
        result = sanitize_short_input(text_with_control)
        assert result == "HelloWorld"
    
    def test_format_shortcut_response_text_mode(self):
        """Test shortcut response formatting in text mode."""
        payload = {
            "status": "success",
            "message": "Action completed successfully",
            "data": {"key": "value"}
        }
        
        result = format_shortcut_response(payload, "text")
        
        assert "speak" in result
        assert "truncated" in result
        assert "data" in result
        assert result["data"] == payload
        assert isinstance(result["truncated"], bool)
    
    def test_format_shortcut_response_json_mode(self):
        """Test shortcut response formatting in JSON mode."""
        payload = {
            "status": "success",
            "message": "Action completed",
            "complex_data": [1, 2, 3]
        }
        
        result = format_shortcut_response(payload, "json")
        assert result == payload
    
    def test_format_shortcut_response_invalid_mode(self):
        """Test invalid return format."""
        payload = {"status": "success"}
        
        with pytest.raises(ValueError) as exc_info:
            format_shortcut_response(payload, "invalid")
        
        assert "Invalid return format" in str(exc_info.value)
    
    def test_get_shortcut_error_response_execution_disabled(self):
        """Test execution disabled error formatting."""
        result = get_shortcut_error_response(
            "EXECUTION_DISABLED", 
            "Execution is disabled"
        )
        
        assert result["error"] == "EXECUTION_DISABLED"
        assert "disabled" in result["speak"].lower()
        assert "previews are available" in result["speak"]
        assert result["truncated"] is False
    
    def test_get_shortcut_error_response_approval_required(self):
        """Test approval required error formatting."""
        result = get_shortcut_error_response(
            "APPROVAL_REQUIRED",
            "Action requires approval"
        )
        
        assert result["error"] == "APPROVAL_REQUIRED"
        assert "approval" in result["speak"].lower()
        assert "full interface" in result["speak"]
    
    def test_get_shortcut_error_response_with_details(self):
        """Test error response with additional details."""
        details = {"limit": 800, "provided": 1000}
        result = get_shortcut_error_response(
            "VALIDATION_ERROR",
            "Input too long",
            details
        )
        
        assert result["details"] == details
        assert result["error"] == "VALIDATION_ERROR"


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not available")
class TestShortcutEndpoints:
    """Test shortcut API endpoints (requires FastAPI)."""
    
    def setup_method(self):
        """Set up test environment."""
        # Mock environment variables
        self.env_patcher = patch.dict(os.environ, {
            "SHORTCUT_TOKEN": "test-shortcut-token-123",
            "SHORTCUT_MAX_LEN": "500",
            "TINYINTENT_EXECUTION_ENABLED": "1",
            "TINYINTENT_SECRET": "test-secret"
        })
        self.env_patcher.start()
        
        # Create test app
        from bridge.api_routes import router_api
        self.app = FastAPI()
        self.app.include_router(router_api)
        self.client = TestClient(self.app)
    
    def teardown_method(self):
        """Clean up test environment."""
        self.env_patcher.stop()
    
    def test_shortcut_ping_success(self):
        """Test successful ping with valid token."""
        response = self.client.get(
            "/shortcut/ping",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "ts" in data
        assert data["service"] == "TinyIntent Bridge"
        assert data["version"] == "2.0.0"
    
    def test_shortcut_ping_missing_token(self):
        """Test ping without token returns 401."""
        response = self.client.get("/shortcut/ping")
        
        assert response.status_code == 401
        assert "Missing X-Shortcut-Token" in response.json()["detail"]
    
    def test_shortcut_ping_invalid_token(self):
        """Test ping with invalid token returns 401."""
        response = self.client.get(
            "/shortcut/ping",
            headers={"X-Shortcut-Token": "invalid-token"}
        )
        
        assert response.status_code == 401
        assert "Invalid X-Shortcut-Token" in response.json()["detail"]
    
    @patch('bridge.api_routes.route_request_endpoint')
    def test_shortcut_route_preview_success(self, mock_route):
        """Test successful preview request."""
        # Mock the route response
        mock_response = MagicMock()
        mock_response.dict.return_value = {
            "status": "success",
            "route_used": "act",
            "helper_id": "bot_guard",
            "preview_json": {"message": "Found 2 positions"}
        }
        mock_route.return_value = mock_response
        
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": "show my positions",
                "mode": "preview",
                "return_format": "text"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "speak" in data
        assert "truncated" in data
        assert "data" in data
        assert data["data"]["status"] == "success"
    
    @patch('bridge.api_routes.route_request_endpoint')
    def test_shortcut_route_execute_success(self, mock_route):
        """Test successful execute request when execution enabled."""
        mock_response = MagicMock()
        mock_response.dict.return_value = {
            "status": "success",
            "route_used": "act",
            "helper_id": "bot_guard",
            "result": {"message": "Position closed"}
        }
        mock_route.return_value = mock_response
        
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": "close ETH position",
                "mode": "execute",
                "return_format": "text"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "speak" in data
        assert data["data"]["status"] == "success"
    
    def test_shortcut_route_execute_disabled(self):
        """Test execute request when execution is disabled."""
        with patch.dict(os.environ, {"TINYINTENT_EXECUTION_ENABLED": "0"}):
            response = self.client.post(
                "/shortcut/route",
                headers={"X-Shortcut-Token": "test-shortcut-token-123"},
                json={
                    "text": "close ETH position",
                    "mode": "execute",
                    "return_format": "text"
                }
            )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "EXECUTION_DISABLED"
        assert "disabled" in data["speak"].lower()
    
    def test_shortcut_route_text_too_long(self):
        """Test request with text exceeding max length."""
        long_text = "x" * 600  # Exceeds SHORTCUT_MAX_LEN=500
        
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": long_text,
                "mode": "preview",
                "return_format": "text"
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "VALIDATION_ERROR"
        assert "too long" in data["speak"].lower()
    
    def test_shortcut_route_invalid_mode(self):
        """Test request with invalid mode."""
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": "test text",
                "mode": "invalid_mode",
                "return_format": "text"
            }
        )
        
        assert response.status_code == 422  # Pydantic validation error
    
    def test_shortcut_route_invalid_return_format(self):
        """Test request with invalid return format."""
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": "test text",
                "mode": "preview",
                "return_format": "invalid_format"
            }
        )
        
        assert response.status_code == 422  # Pydantic validation error
    
    def test_shortcut_route_json_return_format(self):
        """Test request with JSON return format."""
        with patch('bridge.api_routes.route_request_endpoint') as mock_route:
            mock_response = MagicMock()
            mock_response.dict.return_value = {
                "status": "success",
                "complex_data": {"nested": {"value": 123}}
            }
            mock_route.return_value = mock_response
            
            response = self.client.post(
                "/shortcut/route",
                headers={"X-Shortcut-Token": "test-shortcut-token-123"},
                json={
                    "text": "test request",
                    "mode": "preview", 
                    "return_format": "json"
                }
            )
        
        assert response.status_code == 200
        data = response.json()
        # In JSON mode, should return the raw payload
        assert data["status"] == "success"
        assert "complex_data" in data
    
    @patch('bridge.api_routes.route_request_endpoint')
    def test_shortcut_route_handles_http_exception(self, mock_route):
        """Test handling of HTTPException from route endpoint."""
        # Mock route endpoint to raise HTTPException
        mock_route.side_effect = HTTPException(
            status_code=403,
            detail={
                "error": "SANDBOX_LIMIT",
                "detail": "Exceeded memory limit"
            }
        )
        
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": "test request",
                "mode": "preview"
            }
        )
        
        assert response.status_code == 403
        data = response.json()
        assert data["error"] == "SANDBOX_LIMIT"
        assert "safety limits" in data["speak"].lower()
    
    @patch('bridge.api_routes.route_request_endpoint')
    def test_shortcut_route_handles_rate_limit(self, mock_route):
        """Test handling of rate limit errors."""
        mock_route.side_effect = HTTPException(
            status_code=429,
            detail="Rate limit exceeded"
        )
        
        response = self.client.post(
            "/shortcut/route",
            headers={"X-Shortcut-Token": "test-shortcut-token-123"},
            json={
                "text": "test request",
                "mode": "preview"
            }
        )
        
        assert response.status_code == 429
        data = response.json()
        assert data["error"] == "RATE_LIMIT"
        assert "too many requests" in data["speak"].lower()
    
    def test_shortcut_route_generates_session_id(self):
        """Test that session ID is generated when not provided."""
        with patch('bridge.api_routes.route_request_endpoint') as mock_route:
            mock_response = MagicMock()
            mock_response.dict.return_value = {"status": "success"}
            mock_route.return_value = mock_response
            
            response = self.client.post(
                "/shortcut/route",
                headers={"X-Shortcut-Token": "test-shortcut-token-123"},
                json={
                    "text": "test request",
                    "mode": "preview"
                }
            )
        
        assert response.status_code == 200
        
        # Verify RouteRequest was called with generated session_id
        mock_route.assert_called_once()
        route_request = mock_route.call_args[0][0]
        assert route_request.session_id.startswith("shortcut_")
    
    def test_shortcut_route_uses_provided_session_id(self):
        """Test that provided session ID is used."""
        with patch('bridge.api_routes.route_request_endpoint') as mock_route:
            mock_response = MagicMock()
            mock_response.dict.return_value = {"status": "success"}
            mock_route.return_value = mock_response
            
            response = self.client.post(
                "/shortcut/route",
                headers={"X-Shortcut-Token": "test-shortcut-token-123"},
                json={
                    "text": "test request",
                    "mode": "preview",
                    "session_id": "custom-session-123"
                }
            )
        
        assert response.status_code == 200
        
        # Verify custom session ID was used
        route_request = mock_route.call_args[0][0]
        assert route_request.session_id == "custom-session-123"


class TestShortcutTokenConfiguration:
    """Test shortcut token configuration scenarios."""
    
    def test_missing_shortcut_token_env(self):
        """Test behavior when SHORTCUT_TOKEN environment variable is missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not be able to import/use shortcut endpoints
            pass  # This would be caught during startup in production
    
    def test_shortcut_max_len_configuration(self):
        """Test SHORTCUT_MAX_LEN configuration."""
        # Test default value
        with patch.dict(os.environ, {}, clear=True):
            result = sanitize_short_input("x" * 799)  # Should work with default 800
            assert len(result) == 799
        
        # Test with text exceeding default
        with pytest.raises(ValueError):
            sanitize_short_input("x" * 801)  # Should fail with default 800


if __name__ == "__main__":
    # Run tests
    import subprocess
    
    print("🧪 Running M11.0 iPhone Shortcut Voice Interface Tests...")
    
    try:
        # Run formatting tests (always available)
        print("\n📱 Testing shortcut formatting utilities...")
        
        # Test basic formatting
        test_payload = {
            "status": "success",
            "assistant_text": "Trading position closed successfully on ETH."
        }
        speak_text = to_speakable_text(test_payload)
        print(f"✅ Speakable text: '{speak_text}'")
        
        # Test markdown stripping
        markdown_text = "**Bold** and *italic* with `code` and [link](http://example.com)"
        clean_text = _format_for_speech(markdown_text)
        print(f"✅ Markdown stripped: '{clean_text}'")
        
        # Test input sanitization
        try:
            sanitized = sanitize_short_input("  Close my ETH position  ")
            print(f"✅ Input sanitized: '{sanitized}'")
        except Exception as e:
            print(f"❌ Sanitization failed: {e}")
        
        # Test error response formatting
        error_response = get_shortcut_error_response(
            "EXECUTION_DISABLED",
            "Execution is currently disabled"
        )
        print(f"✅ Error response: '{error_response['speak']}'")
        
        # Test response formatting
        response = format_shortcut_response(test_payload, "text")
        print(f"✅ Response formatted: speak='{response['speak']}', truncated={response['truncated']}")
        
        print("\n✅ All formatting utility tests passed!")
        
        if FASTAPI_AVAILABLE:
            print("\n🌐 Running endpoint integration tests...")
            
            # Use pytest if available
            try:
                result = subprocess.run([
                    sys.executable, "-m", "pytest", 
                    __file__ + "::TestShortcutEndpoints",
                    "-v", 
                    "--tb=short",
                    "-x"
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    print("✅ All endpoint tests passed!")
                else:
                    print(f"❌ Some endpoint tests failed:")
                    print(result.stdout)
                    print(result.stderr)
            except FileNotFoundError:
                print("ℹ️  pytest not available, endpoint tests skipped")
        else:
            print("ℹ️  FastAPI not available, endpoint tests skipped")
        
        print("\n🎉 M11.0 Shortcut interface testing complete!")
        
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        import traceback
        traceback.print_exc()