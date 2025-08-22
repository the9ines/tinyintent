"""
Tests for route request/response contracts including validation of
RouteRequest and RouteResponse fields, especially new idempotency features.
"""

import json
import unittest
from typing import Dict, Any, Optional

from pydantic import ValidationError

# Add project paths to system path
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent / "bridge"))

from tinyintent.bridge.api_routes import RouteRequest, RouteResponse


class TestRouteContract(unittest.TestCase):
    """Test cases for route request/response contracts."""
    
    def test_route_request_basic_fields(self):
        """Test basic RouteRequest field validation."""
        # Valid request
        request = RouteRequest(
            text="Show me my trading positions",
            route="act",
            helper_id="bot_guard"
        )
        
        self.assertEqual(request.text, "Show me my trading positions")
        self.assertEqual(request.route, "act")
        self.assertEqual(request.helper_id, "bot_guard")
        self.assertFalse(request.execute)  # Default
        self.assertIsNone(request.approval_token)  # Default
        self.assertIsNone(request.idempotency_key)  # Default
    
    def test_route_request_empty_text_validation(self):
        """Test that empty text raises validation error."""
        with self.assertRaises(ValidationError) as context:
            RouteRequest(text="", route="act")
        
        errors = context.exception.errors()
        self.assertTrue(any("text field cannot be empty" in str(error) for error in errors))
        
        with self.assertRaises(ValidationError) as context:
            RouteRequest(text="   ", route="act")  # Whitespace only
        
        errors = context.exception.errors()
        self.assertTrue(any("text field cannot be empty" in str(error) for error in errors))
    
    def test_route_request_execute_fields(self):
        """Test execute-related fields in RouteRequest."""
        request = RouteRequest(
            text="Execute trading operation",
            route="act",
            helper_id="bot_guard",
            execute=True,
            approval_token="abc123xyz789",
            idempotency_key="unique-operation-key"
        )
        
        self.assertTrue(request.execute)
        self.assertEqual(request.approval_token, "abc123xyz789")
        self.assertEqual(request.idempotency_key, "unique-operation-key")
    
    def test_route_request_optional_fields(self):
        """Test optional fields in RouteRequest."""
        request = RouteRequest(
            text="Test request",
            route="gen",
            llm_pref="small",
            llm_model="llama3.1:8b-instruct-q5_K_M",
            session_id="session-123",
            helper_input={"operation": "test"}
        )
        
        self.assertEqual(request.llm_pref, "small")
        self.assertEqual(request.llm_model, "llama3.1:8b-instruct-q5_K_M")
        self.assertEqual(request.session_id, "session-123")
        self.assertEqual(request.helper_input["operation"], "test")
    
    def test_route_response_basic_fields(self):
        """Test basic RouteResponse field validation."""
        response = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123"
        )
        
        self.assertEqual(response.status, "success")
        self.assertEqual(response.route_used, "act")
        self.assertEqual(response.session_id, "session-123")
        self.assertIsNone(response.text_response)  # Optional
        self.assertIsNone(response.latency_ms)  # Optional
    
    def test_route_response_generation_fields(self):
        """Test generation-specific fields in RouteResponse."""
        response = RouteResponse(
            status="success",
            route_used="gen",
            session_id="session-123",
            text_response="Generated response text",
            model_used="llama3.1:8b-instruct-q5_K_M",
            latency_ms=1500
        )
        
        self.assertEqual(response.text_response, "Generated response text")
        self.assertEqual(response.model_used, "llama3.1:8b-instruct-q5_K_M")
        self.assertEqual(response.latency_ms, 1500)
    
    def test_route_response_action_fields(self):
        """Test action-specific fields in RouteResponse."""
        preview_json = {
            "status": "success",
            "message": "Found 3 open positions",
            "positions": [
                {"symbol": "BTC/USDT", "size": 1.5},
                {"symbol": "ETH/USDT", "size": 10.0}
            ]
        }
        
        response = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123",
            action="preview",
            helper_id="bot_guard",
            preview_json=preview_json,
            approval_token="approval-token-123",
            latency_ms=800
        )
        
        self.assertEqual(response.action, "preview")
        self.assertEqual(response.helper_id, "bot_guard")
        self.assertEqual(response.preview_json, preview_json)
        self.assertEqual(response.approval_token, "approval-token-123")
        self.assertEqual(response.latency_ms, 800)
    
    def test_route_response_execute_fields(self):
        """Test execute-specific fields in RouteResponse."""
        result_json = {
            "status": "success",
            "operation": "get_positions",
            "positions": [
                {"symbol": "BTC/USDT", "size": 1.5, "pnl": 150.00}
            ]
        }
        
        response = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123",
            action="execute",
            helper_id="bot_guard",
            preview_json=result_json,  # Result goes in preview_json field
            latency_ms=1200
        )
        
        self.assertEqual(response.action, "execute")
        self.assertEqual(response.helper_id, "bot_guard")
        self.assertEqual(response.preview_json, result_json)
        self.assertIsNone(response.approval_token)  # Not needed for execute response
    
    def test_route_response_reflection_fields(self):
        """Test reflection layer fields in RouteResponse."""
        reflection_data = {
            "approved": True,
            "confidence": 0.95,
            "reasoning": "Operation is safe and non-destructive",
            "warnings": ["Consider position size limits"]
        }
        
        response = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123",
            action="preview",
            helper_id="bot_guard",
            reflection=reflection_data
        )
        
        self.assertEqual(response.reflection, reflection_data)
        self.assertIsNone(response.veto_reason)
        self.assertIsNone(response.reflection_error)
    
    def test_route_response_veto_fields(self):
        """Test vetoed response fields."""
        response = RouteResponse(
            status="vetoed",
            route_used="act",
            session_id="session-123",
            action="preview",
            helper_id="bot_guard",
            veto_reason="Operation involves high-risk financial transaction"
        )
        
        self.assertEqual(response.status, "vetoed")
        self.assertEqual(response.veto_reason, "Operation involves high-risk financial transaction")
    
    def test_route_response_idempotent_field(self):
        """Test idempotent field in RouteResponse."""
        # Non-idempotent response
        response1 = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123",
            action="execute",
            helper_id="bot_guard"
        )
        
        self.assertIsNone(response1.idempotent)  # Default
        
        # Idempotent response
        response2 = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123",
            action="execute",
            helper_id="bot_guard",
            idempotent=True
        )
        
        self.assertTrue(response2.idempotent)
    
    def test_route_response_error_scenarios(self):
        """Test error scenario response fields."""
        # 403 error with reason code
        response_403 = RouteResponse(
            status="error",
            route_used="act",
            session_id="session-123"
        )
        
        self.assertEqual(response_403.status, "error")
        
        # 409 error (would include missing_vars in headers, not response body)
        response_409 = RouteResponse(
            status="error",
            route_used="act", 
            session_id="session-123"
        )
        
        self.assertEqual(response_409.status, "error")
    
    def test_route_request_json_serialization(self):
        """Test JSON serialization of RouteRequest."""
        request = RouteRequest(
            text="Test request",
            route="act",
            helper_id="bot_guard",
            execute=True,
            approval_token="token123",
            idempotency_key="key456",
            helper_input={"operation": "test"}
        )
        
        # Test that it can be serialized to JSON
        json_str = request.json()
        self.assertIsInstance(json_str, str)
        
        # Test that it can be deserialized
        data = json.loads(json_str)
        self.assertEqual(data["text"], "Test request")
        self.assertEqual(data["route"], "act")
        self.assertEqual(data["helper_id"], "bot_guard")
        self.assertTrue(data["execute"])
        self.assertEqual(data["approval_token"], "token123")
        self.assertEqual(data["idempotency_key"], "key456")
        self.assertEqual(data["helper_input"]["operation"], "test")
    
    def test_route_response_json_serialization(self):
        """Test JSON serialization of RouteResponse."""
        response = RouteResponse(
            status="success",
            route_used="act",
            session_id="session-123",
            action="execute",
            helper_id="bot_guard",
            preview_json={"result": "test"},
            latency_ms=500,
            idempotent=True
        )
        
        # Test that it can be serialized to JSON
        json_str = response.json()
        self.assertIsInstance(json_str, str)
        
        # Test that it can be deserialized
        data = json.loads(json_str)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["route_used"], "act")
        self.assertEqual(data["session_id"], "session-123")
        self.assertEqual(data["action"], "execute")
        self.assertEqual(data["helper_id"], "bot_guard")
        self.assertEqual(data["preview_json"]["result"], "test")
        self.assertEqual(data["latency_ms"], 500)
        self.assertTrue(data["idempotent"])
    
    def test_route_request_defaults(self):
        """Test default values in RouteRequest."""
        request = RouteRequest(text="Test")
        
        self.assertEqual(request.route, "auto")  # Default
        self.assertFalse(request.execute)  # Default
        self.assertIsNone(request.approval_token)
        self.assertIsNone(request.idempotency_key)
        self.assertIsNone(request.helper_id)
        self.assertIsNone(request.helper_input)
        self.assertIsNone(request.session_id)
        self.assertIsNone(request.llm_pref)
        self.assertIsNone(request.llm_model)
    
    def test_route_response_required_fields(self):
        """Test that required fields are enforced in RouteResponse."""
        # Missing required fields should raise ValidationError
        with self.assertRaises(ValidationError):
            RouteResponse()  # Missing all required fields
        
        with self.assertRaises(ValidationError):
            RouteResponse(status="success")  # Missing route_used and session_id
        
        with self.assertRaises(ValidationError):
            RouteResponse(
                status="success", 
                route_used="act"
            )  # Missing session_id
        
        # All required fields present should work
        response = RouteResponse(
            status="success",
            route_used="act", 
            session_id="session-123"
        )
        self.assertEqual(response.status, "success")


if __name__ == '__main__':
    unittest.main()