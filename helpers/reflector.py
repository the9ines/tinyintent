"""
TinyIntent Helpers Reflector - M4: Reflection Layer

Provides LLM-based validation of helper output before execution.
Verifies that the helper's previewed intent makes logical sense, is non-destructive,
and matches expected input/output schema.
"""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime


class HelperReflector:
    """Reflection layer for validating helper output using LLM."""
    
    def __init__(self, model_tag: str = "llama3.1:8b-instruct-q5_K_M"):
        self.model_tag = model_tag
        self.audit_log = Path(__file__).parent.parent / "bridge" / "logs" / "audit.log"
        self.audit_log.parent.mkdir(parents=True, exist_ok=True)
    
    def reflect(self, helper_id: str, user_text: str, helper_input: Dict[str, Any], 
                helper_output: Dict[str, Any], session_id: str = None) -> Dict[str, Any]:
        """
        Reflect on helper output using LLM to validate safety and correctness.
        
        Args:
            helper_id: ID of the helper being validated
            user_text: Original user request text
            helper_input: Input data sent to helper
            helper_output: Output received from helper
            session_id: Optional session ID for audit logging
            
        Returns:
            Dict with reflection result:
            {
                "approved": bool,
                "confidence": float,
                "reasoning": str,
                "warnings": List[str],
                "veto_reason": Optional[str]
            }
        """
        start_time = time.time()
        timestamp = datetime.utcnow().isoformat() + 'Z'
        
        try:
            # Build reflection prompt
            reflection_prompt = self._build_reflection_prompt(
                helper_id, user_text, helper_input, helper_output
            )
            
            # Call LLM for reflection
            reflection_response = self._call_llm(reflection_prompt)
            
            # Parse LLM response
            reflection_result = self._parse_reflection_response(reflection_response)
            
            # Log reflection
            self._log_reflection(
                helper_id=helper_id,
                user_text=user_text,
                helper_input=helper_input,
                helper_output=helper_output,
                reflection_result=reflection_result,
                session_id=session_id,
                latency_ms=int((time.time() - start_time) * 1000)
            )
            
            return reflection_result
            
        except Exception as e:
            # Log reflection error
            error_result = {
                "approved": False,
                "confidence": 0.0,
                "reasoning": f"Reflection failed: {str(e)}",
                "warnings": ["Reflection system error"],
                "veto_reason": f"Internal reflection error: {str(e)}"
            }
            
            self._log_reflection(
                helper_id=helper_id,
                user_text=user_text,
                helper_input=helper_input,
                helper_output=helper_output,
                reflection_result=error_result,
                session_id=session_id,
                error=str(e),
                latency_ms=int((time.time() - start_time) * 1000)
            )
            
            return error_result
    
    def _build_reflection_prompt(self, helper_id: str, user_text: str, 
                               helper_input: Dict[str, Any], helper_output: Dict[str, Any]) -> str:
        """Build reflection prompt for LLM validation."""
        
        prompt = f"""You are a safety validator for TinyIntent helpers. Your job is to review helper operations before execution.

HELPER CONTEXT:
Helper ID: {helper_id}
User Request: "{user_text}"

HELPER INPUT:
{json.dumps(helper_input, indent=2)}

HELPER OUTPUT:
{json.dumps(helper_output, indent=2)}

VALIDATION CRITERIA:
1. SAFETY: Is this operation non-destructive and safe to execute?
2. LOGIC: Does the helper output logically match the user's intent?
3. SCHEMA: Does the output follow expected patterns and schemas?
4. SCOPE: Is the operation within reasonable bounds?

HIGH-RISK OPERATIONS TO SCRUTINIZE:
- Financial operations (closing positions, transfers)
- System commands (restarts, shutdowns)
- Data deletion or modification
- Network operations with external systems

RESPONSE FORMAT (JSON only):
{{
    "approved": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of decision",
    "warnings": ["list", "of", "concerns"],
    "veto_reason": "reason if not approved, null if approved"
}}

Respond with JSON only, no other text."""

        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """Call Ollama LLM for reflection."""
        try:
            result = subprocess.run(
                ["ollama", "run", self.model_tag, prompt],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout for reflection
            )
            
            if result.returncode != 0:
                error_msg = result.stderr.strip() if result.stderr else "Unknown ollama error"
                raise RuntimeError(f"Ollama execution failed: {error_msg}")
            
            return result.stdout.strip()
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("Reflection LLM request timed out")
        except FileNotFoundError:
            raise RuntimeError("Ollama binary not found")
        except Exception as e:
            raise RuntimeError(f"Error calling reflection LLM: {str(e)}")
    
    def _parse_reflection_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM reflection response into structured format."""
        try:
            # Try to extract JSON from response
            response = response.strip()
            
            # Handle cases where LLM adds explanation before/after JSON
            if '{' in response and '}' in response:
                start = response.find('{')
                end = response.rfind('}') + 1
                json_part = response[start:end]
                reflection_data = json.loads(json_part)
            else:
                # Fallback: try parsing entire response as JSON
                reflection_data = json.loads(response)
            
            # Validate required fields
            required_fields = ['approved', 'confidence', 'reasoning']
            for field in required_fields:
                if field not in reflection_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Ensure proper types
            reflection_data['approved'] = bool(reflection_data['approved'])
            reflection_data['confidence'] = float(reflection_data['confidence'])
            reflection_data['reasoning'] = str(reflection_data['reasoning'])
            reflection_data['warnings'] = reflection_data.get('warnings', [])
            reflection_data['veto_reason'] = reflection_data.get('veto_reason')
            
            # Clamp confidence to 0.0-1.0
            reflection_data['confidence'] = max(0.0, min(1.0, reflection_data['confidence']))
            
            return reflection_data
            
        except json.JSONDecodeError as e:
            # Fallback for unparseable responses
            return {
                "approved": False,
                "confidence": 0.0,
                "reasoning": f"Failed to parse LLM response: {str(e)}",
                "warnings": ["LLM response parsing error"],
                "veto_reason": f"Invalid LLM response format: {response[:100]}..."
            }
        except Exception as e:
            return {
                "approved": False,
                "confidence": 0.0,
                "reasoning": f"Reflection parsing error: {str(e)}",
                "warnings": ["Reflection system error"],
                "veto_reason": f"Internal parsing error: {str(e)}"
            }
    
    def _log_reflection(self, helper_id: str, user_text: str, helper_input: Dict[str, Any],
                       helper_output: Dict[str, Any], reflection_result: Dict[str, Any],
                       session_id: str = None, error: str = None, latency_ms: int = None):
        """Log reflection activity to audit log."""
        try:
            log_entry = {
                "ts": datetime.utcnow().isoformat() + 'Z',
                "session_id": session_id or "unknown",
                "action": "reflection",
                "helper_id": helper_id,
                "user_text_hash": hash(user_text),
                "input_hash": hash(json.dumps(helper_input, sort_keys=True)),
                "output_hash": hash(json.dumps(helper_output, sort_keys=True)),
                "approved": reflection_result.get("approved", False),
                "confidence": reflection_result.get("confidence", 0.0),
                "warnings_count": len(reflection_result.get("warnings", [])),
                "latency_ms": latency_ms,
                "success": error is None,
                "error": error
            }
            
            with open(self.audit_log, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
                
        except Exception as e:
            # Don't fail the reflection if logging fails
            print(f"Warning: Failed to log reflection: {e}")


# Global reflector instance for import
reflector = HelperReflector()