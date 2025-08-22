"""
TinyIntent Router Client

Provides an interface to the CoreML router model. Handles executing the Swift runner,
applying confidence thresholds, and managing fallback logic.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

class SmallIntentRouter:
    """Interface to SmallIntent.mlmodel for routing decisions with confidence thresholds."""
    
    def __init__(self, router_path: Optional[Path] = None, require_models: bool = True):
        if router_path is None:
            self.router_path = Path(__file__).parent.parent / "router" / "runner" / "run_router.swift"
        else:
            self.router_path = router_path
            
        # M10.6: Check for required model files
        self.model_dir = Path(__file__).parent.parent / "router"
        self.small_model = self.model_dir / "SmallIntent.mlmodel"
        self.tiny_model = self.model_dir / "TinyIntent.mlmodel"
        
        self.router_available = self.router_path.exists()
        self.models_available = self.small_model.exists() and self.tiny_model.exists()
        
        if require_models and not self.models_available:
            missing_models = []
            if not self.small_model.exists():
                missing_models.append("SmallIntent.mlmodel")
            if not self.tiny_model.exists():
                missing_models.append("TinyIntent.mlmodel")
            
            error_msg = f"CRITICAL: Required CoreML models missing: {', '.join(missing_models)}. Run 'make learn' to generate models before starting bridge."
            print(f"ERROR: {error_msg}")
            raise RuntimeError(error_msg)
        
        if not self.router_available:
            print(f"Warning: Router script not found at {self.router_path}, using fallback routing")
        elif not self.models_available:
            print(f"Warning: CoreML models missing, using fallback routing")
        
        self.min_conf_gen = float(os.getenv("ROUTER_MIN_CONF_GEN", "0.55"))
        self.min_conf_act = float(os.getenv("ROUTER_MIN_CONF_ACT", "0.65"))
        self.fallback_threshold = float(os.getenv("ROUTER_FALLBACK_THRESHOLD", "0.4"))
        
        print(f"Router confidence thresholds: gen={self.min_conf_gen}, act={self.min_conf_act}, fallback={self.fallback_threshold}")
    
    def route_request(self, text: str, skip_metrics: bool = False) -> Dict[str, Any]:
        """
        Route request using SmallIntent.mlmodel with confidence thresholds.
        
        Args:
            text: Input text to route
            skip_metrics: Skip recording metrics (used by health checks)
        
        Returns:
            {"route": "gen|act|abstain", "intent": "...", "confidence": 0.95, "abstain_reason": "..."}
        """
        if not self.router_available or not self.models_available:
            return self._fallback_routing(text)
        
        try:
            result = subprocess.run(
                ["swift", str(self.router_path), text],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                print(f"Router execution failed: {result.stderr}")
                return self._fallback_routing(text)
            
            try:
                routing_result = json.loads(result.stdout.strip())
                return self._apply_confidence_thresholds(routing_result, text)
                
            except json.JSONDecodeError:
                print(f"Invalid JSON from router: {result.stdout}")
                return self._fallback_routing(text)
                
        except Exception as e:
            print(f"Router error: {e}")
            return self._fallback_routing(text)
    
    def _apply_confidence_thresholds(self, routing_result: Dict[str, Any], text: str) -> Dict[str, Any]:
        """
        Apply confidence thresholds to routing decisions.
        """
        route = routing_result.get("route", "gen")
        confidence = routing_result.get("confidence", 0.5)
        intent = routing_result.get("intent", "unknown")
        
        if confidence < self.fallback_threshold:
            print(f"Router confidence {confidence:.3f} below fallback threshold {self.fallback_threshold}, using fallback")
            return self._fallback_routing(text)
        
        elif route == "gen" and confidence < self.min_conf_gen:
            return {
                "route": "abstain",
                "intent": intent,
                "confidence": confidence,
                "abstain_reason": "low_confidence",
                "abstain_reason_detail": f"Generation confidence {confidence:.3f} below threshold {self.min_conf_gen}",
                "suggested_route": "gen",
                "fallback_available": True
            }
        
        elif route == "act" and confidence < self.min_conf_act:
            return {
                "route": "abstain", 
                "intent": intent,
                "confidence": confidence,
                "abstain_reason": "low_confidence",
                "abstain_reason_detail": f"Action confidence {confidence:.3f} below threshold {self.min_conf_act}",
                "suggested_route": "act",
                "fallback_available": True
            }
        
        else:
            return routing_result
    
    def _fallback_routing(self, text: str) -> Dict[str, Any]:
        """Fallback routing logic when router is not available."""
        text_lower = text.lower()
        
        if any(term in text_lower for term in ['bot', 'position', 'trade', 'close', 'stop', 'emergency', 'execute', 'run', 'do']):
            return {
                "route": "act",
                "intent": "bot_management",
                "confidence": 0.7,
                "abstain_reason": "router_fallback",
                "abstain_reason_detail": "Using fallback routing due to router unavailability"
            }
        
        return {
            "route": "gen", 
            "intent": "general_query",
            "confidence": 0.6,
            "abstain_reason": "router_fallback",
            "abstain_reason_detail": "Using fallback routing due to router unavailability"
        }


# Global router instance
router = SmallIntentRouter()
