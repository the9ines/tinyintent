"""
TinyIntent Bridge MVP - FastAPI service for routing and orchestrating AI tasks.
Implements M2: Experience Store with NDJSON and SQLite logging.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, validator
import uvicorn
import httpx

# Load environment variables from .env file if it exists
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Only set if not already in environment
                    if key not in os.environ:
                        os.environ[key] = value.strip('"').strip("'")

# Load .env file on module import
load_env_file()


# Legacy sanitization functions are now imported from sanitize module


from resolve import ModelResolver, helper_resolver
from store import experience_store
from approval import approval_manager
from episodes import episode_logger
from sanitize import sanitize_dict, sanitize_text, safe_error_payload

# Import audit log integrity system (M6.2)
from logs.rotate import initialize_audit_logger, get_audit_logger

# Import helpers framework (with fallback for missing dependencies)
import sys
sys.path.append(str(Path(__file__).parent.parent / "helpers"))
try:
    from sdk import helper_registry, helper_executor, CapabilityViolationError, HelperRateLimitError
    from reflector import reflector
    HELPERS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Helpers framework not available: {e}")
    HELPERS_AVAILABLE = False
    helper_registry = None
    helper_executor = None
    reflector = None
    CapabilityViolationError = None
    HelperRateLimitError = None


# M7.2: Router Reliability Monitoring System
from collections import deque, defaultdict
from datetime import datetime
import statistics

class RouterMetrics:
    """
    Router reliability monitoring with rolling in-memory buffer.
    Tracks router decisions, confidence distributions, and performance metrics.
    """
    
    def __init__(self, buffer_size: int = 500):
        self.buffer_size = buffer_size
        self.metrics_buffer = deque(maxlen=buffer_size)
        self.error_buffer = deque(maxlen=50)  # Last 50 errors
        self.lock = threading.Lock()  # Thread-safe access
    
    def record_routing_decision(self, 
                              route: str, 
                              intent: str, 
                              confidence: float, 
                              latency_ms: float, 
                              outcome: str,
                              text_length: int = 0,
                              session_id: str = "",
                              abstain_reason: str = None):
        """Record a router decision for monitoring."""
        with self.lock:
            entry = {
                "timestamp": time.time(),
                "route": route,
                "intent": intent, 
                "confidence": confidence,
                "latency_ms": latency_ms,
                "outcome": outcome,  # "preview", "execute", "abstain"
                "text_length": text_length,
                "session_id": session_id,
                "abstain_reason": abstain_reason
            }
            self.metrics_buffer.append(entry)
    
    def record_error(self, error_type: str, error_message: str, session_id: str = ""):
        """Record a router error for monitoring."""
        with self.lock:
            error_entry = {
                "timestamp": time.time(),
                "error_type": error_type,
                "error_message": error_message,
                "session_id": session_id
            }
            self.error_buffer.append(error_entry)
    
    def record_circuit_breaker_event(self, model: str, event_type: str, state: str, 
                                   session_id: str = "", additional_info: Dict[str, Any] = None):
        """
        Record circuit breaker events for monitoring. M7.3
        
        Args:
            model: Model name (e.g., "llama3.2:3b")
            event_type: "state_change", "failure", "success", "blocked"
            state: Current circuit breaker state
            session_id: Optional session ID
            additional_info: Additional context (failure count, etc.)
        """
        with self.lock:
            cb_entry = {
                "timestamp": time.time(),
                "event_type": "circuit_breaker_" + event_type,
                "model": model,
                "state": state,
                "session_id": session_id,
                "additional_info": additional_info or {}
            }
            self.error_buffer.append(cb_entry)  # Use error buffer for circuit breaker events
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get comprehensive router metrics summary."""
        with self.lock:
            if not self.metrics_buffer:
                return self._empty_metrics_summary()
            
            # Convert buffer to list for analysis
            entries = list(self.metrics_buffer)
            total_count = len(entries)
            
            # Confidence histogram (10 bins)
            confidences = [entry["confidence"] for entry in entries]
            confidence_histogram = self._create_histogram(confidences, bins=10)
            
            # Route distribution
            route_counts = defaultdict(int)
            for entry in entries:
                route_counts[entry["route"]] += 1
            
            # Intent distribution
            intent_counts = defaultdict(int)
            for entry in entries:
                intent_counts[entry["intent"]] += 1
            
            # Outcome distribution
            outcome_counts = defaultdict(int)
            for entry in entries:
                outcome_counts[entry["outcome"]] += 1
            
            # Abstain analysis
            abstain_count = route_counts.get("abstain", 0)
            abstain_percentage = (abstain_count / total_count) * 100 if total_count > 0 else 0
            
            # Latency analysis
            latencies = [entry["latency_ms"] for entry in entries if entry["latency_ms"] is not None]
            avg_latency = statistics.mean(latencies) if latencies else 0
            latency_p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else (max(latencies) if latencies else 0)
            
            # Recent errors
            recent_errors = list(self.error_buffer)
            
            # Time window analysis
            now = time.time()
            recent_entries = [e for e in entries if (now - e["timestamp"]) < 3600]  # Last hour
            recent_abstains = len([e for e in recent_entries if e["route"] == "abstain"])
            recent_abstain_rate = (recent_abstains / len(recent_entries)) * 100 if recent_entries else 0
            
            return {
                "summary": {
                    "total_requests": total_count,
                    "buffer_size": self.buffer_size,
                    "buffer_utilization": (total_count / self.buffer_size) * 100,
                    "oldest_entry_age_minutes": (now - entries[0]["timestamp"]) / 60 if entries else 0
                },
                "confidence_histogram": confidence_histogram,
                "route_distribution": dict(route_counts),
                "intent_distribution": dict(intent_counts),
                "outcome_distribution": dict(outcome_counts),
                "abstain_metrics": {
                    "total_abstains": abstain_count,
                    "abstain_percentage": round(abstain_percentage, 2),
                    "recent_abstain_rate_1h": round(recent_abstain_rate, 2)
                },
                "latency_metrics": {
                    "average_ms": round(avg_latency, 2),
                    "p95_ms": round(latency_p95, 2),
                    "sample_count": len(latencies)
                },
                "error_metrics": {
                    "recent_error_count": len(recent_errors),
                    "last_50_errors": recent_errors
                },
                "timestamp": now,
                "generated_at": datetime.fromtimestamp(now).isoformat()
            }
    
    def _create_histogram(self, values: List[float], bins: int = 10) -> Dict[str, Any]:
        """Create histogram from values."""
        if not values:
            return {"bins": [], "counts": [], "total": 0}
        
        min_val = min(values)
        max_val = max(values)
        
        # Handle edge case where all values are the same
        if min_val == max_val:
            return {
                "bins": [{"lower": min_val, "upper": min_val + 0.1, "count": len(values)}],
                "counts": [len(values)],
                "total": len(values),
                "min": min_val,
                "max": max_val
            }
        
        # Create bin edges
        bin_width = (max_val - min_val) / bins
        bin_edges = [min_val + i * bin_width for i in range(bins + 1)]
        bin_counts = [0] * bins
        bin_info = []
        
        # Count values in each bin
        for value in values:
            bin_idx = min(int((value - min_val) / bin_width), bins - 1)
            bin_counts[bin_idx] += 1
        
        # Create bin information
        for i in range(bins):
            bin_info.append({
                "lower": round(bin_edges[i], 3),
                "upper": round(bin_edges[i + 1], 3),
                "count": bin_counts[i]
            })
        
        return {
            "bins": bin_info,
            "counts": bin_counts,
            "total": len(values),
            "min": round(min_val, 3),
            "max": round(max_val, 3)
        }
    
    def _empty_metrics_summary(self) -> Dict[str, Any]:
        """Return empty metrics summary when no data available."""
        return {
            "summary": {
                "total_requests": 0,
                "buffer_size": self.buffer_size,
                "buffer_utilization": 0,
                "oldest_entry_age_minutes": 0
            },
            "confidence_histogram": {"bins": [], "counts": [], "total": 0},
            "route_distribution": {},
            "intent_distribution": {},
            "outcome_distribution": {},
            "abstain_metrics": {
                "total_abstains": 0,
                "abstain_percentage": 0,
                "recent_abstain_rate_1h": 0
            },
            "latency_metrics": {
                "average_ms": 0,
                "p95_ms": 0,
                "sample_count": 0
            },
            "error_metrics": {
                "recent_error_count": 0,
                "last_50_errors": []
            },
            "timestamp": time.time(),
            "generated_at": datetime.now().isoformat()
        }
    
    def get_recent_entries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent router entries for debugging."""
        with self.lock:
            recent = list(self.metrics_buffer)[-limit:]
            # Add human-readable timestamps
            for entry in recent:
                entry["timestamp_iso"] = datetime.fromtimestamp(entry["timestamp"]).isoformat()
            return recent
    
    def flush_to_database(self) -> Dict[str, Any]:
        """
        Flush current metrics buffer to database via episode logger. M7.2
        
        Returns flush status and statistics.
        """
        with self.lock:
            if not self.metrics_buffer:
                return {"status": "success", "flushed_count": 0, "message": "No metrics to flush"}
            
            # Get copy of buffer and clear it
            buffer_copy = list(self.metrics_buffer)
            self.metrics_buffer.clear()
        
        # Import here to avoid circular imports
        try:
            from episodes import episode_logger
            return episode_logger.flush_router_metrics(buffer_copy)
        except ImportError:
            # Fallback: just return success without flushing
            return {
                "status": "warning",
                "flushed_count": 0,
                "failed_count": len(buffer_copy),
                "message": "Episode logger not available, metrics not persisted"
            }

# Initialize router metrics collector
router_metrics = RouterMetrics(buffer_size=int(os.getenv("ROUTER_METRICS_BUFFER_SIZE", "500")))


# M7.3: Generation Resilience - Circuit Breaker System
from enum import Enum
import uuid

class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, blocking requests  
    HALF_OPEN = "half_open"  # Testing if service recovered

class GenerationCircuitBreaker:
    """
    Circuit breaker for generation calls with per-model tracking.
    Prevents repeated slow/failing Ollama calls from hammering the system.
    """
    
    def __init__(self):
        # Configuration from environment
        self.fail_window = int(os.getenv("GEN_CB_FAIL_WINDOW", "120"))  # seconds
        self.threshold = int(os.getenv("GEN_CB_THRESHOLD", "5"))       # failures
        self.cooldown = int(os.getenv("GEN_CB_COOLDOWN", "30"))        # seconds
        
        # Per-model circuit breaker state
        self.breakers = {}  # model -> breaker state
        self.lock = threading.Lock()
        
        print(f"Circuit breaker config: window={self.fail_window}s, threshold={self.threshold}, cooldown={self.cooldown}s")
    
    def _get_breaker_state(self, model: str) -> Dict[str, Any]:
        """Get or create breaker state for model."""
        if model not in self.breakers:
            self.breakers[model] = {
                "state": CircuitBreakerState.CLOSED,
                "failures": deque(),  # timestamps of failures
                "last_failure_time": 0,
                "last_success_time": time.time(),
                "total_requests": 0,
                "total_failures": 0,
                "state_changed_at": time.time()
            }
        return self.breakers[model]
    
    def can_execute(self, model: str) -> tuple[bool, str, Dict[str, Any]]:
        """
        Check if request can execute through circuit breaker.
        
        Returns:
            (can_execute: bool, reason: str, breaker_info: dict)
        """
        with self.lock:
            breaker = self._get_breaker_state(model)
            current_time = time.time()
            
            # Clean old failures outside the window
            cutoff_time = current_time - self.fail_window
            breaker["failures"] = deque(
                timestamp for timestamp in breaker["failures"] 
                if timestamp > cutoff_time
            )
            
            state = breaker["state"]
            failure_count = len(breaker["failures"])
            
            if state == CircuitBreakerState.CLOSED:
                # Normal operation - allow request
                if failure_count >= self.threshold:
                    # Too many failures, open the breaker
                    breaker["state"] = CircuitBreakerState.OPEN
                    breaker["state_changed_at"] = current_time
                    self._log_circuit_event(model, "open", failure_count)
                    return False, "gen_circuit_open", self._get_breaker_info(model, breaker)
                
                return True, "closed", self._get_breaker_info(model, breaker)
            
            elif state == CircuitBreakerState.OPEN:
                # Breaker is open - check if cooldown period is over
                if current_time - breaker["state_changed_at"] >= self.cooldown:
                    # Move to half-open for trial request
                    breaker["state"] = CircuitBreakerState.HALF_OPEN
                    breaker["state_changed_at"] = current_time
                    self._log_circuit_event(model, "half_open", failure_count)
                    return True, "half_open", self._get_breaker_info(model, breaker)
                
                # Still in cooldown
                return False, "gen_circuit_open", self._get_breaker_info(model, breaker)
            
            elif state == CircuitBreakerState.HALF_OPEN:
                # Only allow one request in half-open state
                return True, "half_open", self._get_breaker_info(model, breaker)
    
    def record_success(self, model: str, session_id: str = ""):
        """Record successful generation call."""
        with self.lock:
            breaker = self._get_breaker_state(model)
            breaker["total_requests"] += 1
            breaker["last_success_time"] = time.time()
            
            # M7.3: Record success event in router metrics
            try:
                router_metrics.record_circuit_breaker_event(
                    model=model,
                    event_type="success", 
                    state=breaker["state"].value,
                    session_id=session_id,
                    additional_info={
                        "total_requests": breaker["total_requests"],
                        "total_failures": breaker["total_failures"]
                    }
                )
            except:
                pass  # Don't break on metrics errors
            
            if breaker["state"] == CircuitBreakerState.HALF_OPEN:
                # Half-open success - close the breaker
                old_state = breaker["state"]
                breaker["state"] = CircuitBreakerState.CLOSED
                breaker["state_changed_at"] = time.time()
                breaker["failures"].clear()  # Reset failure history
                self._log_circuit_event(model, "closed", 0, session_id, old_state)
    
    def record_failure(self, model: str, error_type: str = "unknown", session_id: str = ""):
        """Record failed generation call."""
        with self.lock:
            breaker = self._get_breaker_state(model)
            current_time = time.time()
            
            breaker["total_requests"] += 1
            breaker["total_failures"] += 1
            breaker["last_failure_time"] = current_time
            breaker["failures"].append(current_time)
            
            # M7.3: Record failure event in router metrics
            try:
                router_metrics.record_circuit_breaker_event(
                    model=model,
                    event_type="failure", 
                    state=breaker["state"].value,
                    session_id=session_id,
                    additional_info={
                        "error_type": error_type,
                        "failure_count": len(breaker["failures"]),
                        "total_requests": breaker["total_requests"],
                        "total_failures": breaker["total_failures"]
                    }
                )
            except:
                pass  # Don't break on metrics errors
            
            if breaker["state"] == CircuitBreakerState.HALF_OPEN:
                # Half-open failure - reopen the breaker
                old_state = breaker["state"]
                breaker["state"] = CircuitBreakerState.OPEN
                breaker["state_changed_at"] = current_time
                self._log_circuit_event(model, "open", len(breaker["failures"]), session_id, old_state)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self.lock:
            stats = {
                "config": {
                    "fail_window_s": self.fail_window,
                    "threshold": self.threshold,
                    "cooldown_s": self.cooldown
                },
                "models": {}
            }
            
            for model, breaker in self.breakers.items():
                stats["models"][model] = self._get_breaker_info(model, breaker)
            
            return stats
    
    def _get_breaker_info(self, model: str, breaker: Dict[str, Any]) -> Dict[str, Any]:
        """Get breaker information for model."""
        current_time = time.time()
        return {
            "state": breaker["state"].value,
            "failure_count": len(breaker["failures"]),
            "total_requests": breaker["total_requests"],
            "total_failures": breaker["total_failures"],
            "failure_rate": (breaker["total_failures"] / max(breaker["total_requests"], 1)) * 100,
            "last_success_time": breaker["last_success_time"],
            "last_failure_time": breaker["last_failure_time"],
            "state_changed_at": breaker["state_changed_at"],
            "time_since_state_change": current_time - breaker["state_changed_at"],
            "cooldown_remaining": max(0, self.cooldown - (current_time - breaker["state_changed_at"])) if breaker["state"] == CircuitBreakerState.OPEN else 0
        }
    
    def _log_circuit_event(self, model: str, new_state: str, failure_count: int, 
                          session_id: str = "", old_state: CircuitBreakerState = None):
        """Log circuit breaker state change."""
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "gen_circuit",
            "model": model,
            "state": new_state,
            "old_state": old_state.value if old_state else "",
            "failure_count": failure_count,
            "threshold": self.threshold,
            "session_id": session_id,
            "success": True
        })
        
        # M7.3: Also record in router metrics for monitoring
        try:
            router_metrics.record_circuit_breaker_event(
                model=model,
                event_type="state_change",
                state=new_state,
                session_id=session_id,
                additional_info={
                    "old_state": old_state.value if old_state else "",
                    "failure_count": failure_count,
                    "threshold": self.threshold
                }
            )
        except:
            pass  # Don't break on metrics errors

class GenerationTaskManager:
    """
    Manages in-flight generation tasks for cancellation support.
    Tracks asyncio tasks by request_id for clean cancellation.
    """
    
    def __init__(self):
        self.active_tasks = {}  # request_id -> (task, model, start_time, session_id)
        self.lock = threading.Lock()
    
    def register_task(self, request_id: str, task: asyncio.Task, model: str, session_id: str = ""):
        """Register an active generation task."""
        with self.lock:
            self.active_tasks[request_id] = {
                "task": task,
                "model": model,
                "start_time": time.time(),
                "session_id": session_id
            }
    
    def unregister_task(self, request_id: str):
        """Unregister a completed/cancelled task."""
        with self.lock:
            return self.active_tasks.pop(request_id, None)
    
    def cancel_task(self, request_id: str) -> Dict[str, Any]:
        """Cancel a generation task by request_id."""
        with self.lock:
            task_info = self.active_tasks.get(request_id)
            if not task_info:
                return {
                    "status": "not_found",
                    "message": f"No active generation task found for request_id: {request_id}"
                }
            
            task = task_info["task"]
            model = task_info["model"]
            duration = time.time() - task_info["start_time"]
            
            # Cancel the asyncio task
            cancelled = task.cancel()
            
            if cancelled:
                # Log cancellation
                audit_logger.log_entry({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "action": "gen_cancel",
                    "request_id": request_id,
                    "model": model,
                    "session_id": task_info["session_id"],
                    "duration_s": round(duration, 2),
                    "success": True
                })
                
                # Remove from active tasks
                del self.active_tasks[request_id]
                
                return {
                    "status": "cancelled",
                    "request_id": request_id,
                    "model": model,
                    "duration_s": round(duration, 2),
                    "message": "Generation task cancelled successfully"
                }
            else:
                return {
                    "status": "cancel_failed", 
                    "message": f"Failed to cancel task for request_id: {request_id}"
                }
    
    def get_active_tasks(self) -> Dict[str, Any]:
        """Get information about active generation tasks."""
        with self.lock:
            current_time = time.time()
            tasks_info = {}
            
            for request_id, info in self.active_tasks.items():
                tasks_info[request_id] = {
                    "model": info["model"],
                    "session_id": info["session_id"],
                    "duration_s": round(current_time - info["start_time"], 2),
                    "start_time": info["start_time"]
                }
            
            return {
                "active_count": len(self.active_tasks),
                "tasks": tasks_info
            }

# Initialize circuit breaker and task manager
generation_circuit_breaker = GenerationCircuitBreaker()
generation_task_manager = GenerationTaskManager()


# Initialize FastAPI app
app = FastAPI(title="TinyIntent Bridge", version="1.0.0")

# Initialize model resolver
model_resolver = ModelResolver()

# Initialize audit log integrity system (M6.2)
audit_log_path = Path(__file__).parent / "logs" / "audit.log"
audit_logger = initialize_audit_logger(audit_log_path, max_size_mb=50)

# Emergency Kill Switch System (M6.3)
EMERGENCY_FLAG_PATH = os.environ.get("EMERGENCY_FLAG_PATH", str(Path(__file__).parent / "logs" / "emergency.flag"))
emergency_flag_path = Path(EMERGENCY_FLAG_PATH)
execution_lock = threading.Lock()  # Thread-safe access to execution state

class EmergencyKillSwitch:
    """Manages emergency kill switch state for execution control."""
    
    def __init__(self, flag_file_path: Path):
        self.flag_file_path = flag_file_path
        self.flag_file_path.parent.mkdir(parents=True, exist_ok=True)
        self._execution_enabled = True
        self._load_state_from_file()
    
    def _load_state_from_file(self):
        """Load emergency state from flag file on startup."""
        if self.flag_file_path.exists():
            self._execution_enabled = False
            print("⚠️  EXECUTION DISABLED: Emergency flag file detected")
            # Log startup warning
            audit_logger.log_entry({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                "action": "emergency_startup_disabled",
                "success": True,
                "message": "Execution disabled on startup due to emergency flag",
                "flag_file": str(self.flag_file_path)
            })
        else:
            self._execution_enabled = os.getenv("EXECUTION_ENABLED", "0") == "1"
            if self._execution_enabled:
                print("✓ Execution enabled (EXECUTION_ENABLED=1)")
            else:
                print("ℹ️  Execution disabled (EXECUTION_ENABLED=0)")
    
    def is_execution_enabled(self) -> bool:
        """Check if execution is currently enabled."""
        with execution_lock:
            return self._execution_enabled
    
    def trigger_emergency_kill(self, reason: str = "Manual trigger", triggered_by: str = "unknown") -> bool:
        """
        Trigger emergency kill switch - disables all execution immediately.
        
        Returns:
            bool: True if kill was triggered successfully
        """
        with execution_lock:
            if not self._execution_enabled:
                return False  # Already disabled
            
            try:
                # Create emergency flag file using atomic write
                emergency_data = {
                    "triggered_at": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "reason": reason,
                    "triggered_by": triggered_by
                }
                
                # Atomic write: write to temp file then replace
                temp_file = self.flag_file_path.with_suffix('.tmp')
                with open(temp_file, 'w') as f:
                    import json
                    json.dump(emergency_data, f, indent=2)
                
                # Atomic replace
                import os
                os.replace(str(temp_file), str(self.flag_file_path))
                
                # Disable execution in memory
                self._execution_enabled = False
                
                # Log emergency kill event
                audit_logger.log_entry({
                    "ts": emergency_data["triggered_at"],
                    "action": "emergency_kill",
                    "success": True,
                    "reason": reason,
                    "triggered_by": triggered_by,
                    "flag_file": str(self.flag_file_path),
                    "severity": "CRITICAL"
                })
                
                print(f"🚨 EMERGENCY KILL TRIGGERED: {reason}")
                return True
                
            except Exception as e:
                # Clean up temp file if it exists
                temp_file = self.flag_file_path.with_suffix('.tmp')
                try:
                    temp_file.unlink()
                except FileNotFoundError:
                    pass
                
                # Log error but don't fail
                audit_logger.log_entry({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "action": "emergency_kill_error",
                    "success": False,
                    "error": str(e),
                    "reason": reason,
                    "triggered_by": triggered_by
                })
                print(f"❌ Emergency kill failed: {e}")
                return False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current emergency status."""
        with execution_lock:
            status = {
                "execution_enabled": self._execution_enabled,
                "flag_file_exists": self.flag_file_path.exists(),
                "flag_file_path": str(self.flag_file_path)
            }
            
            if self.flag_file_path.exists():
                try:
                    import json
                    with open(self.flag_file_path, 'r') as f:
                        flag_data = json.load(f)
                    status["emergency_data"] = flag_data
                except Exception:
                    status["emergency_data"] = {"error": "Could not read flag file"}
            
            return status

# Initialize emergency kill switch
emergency_kill = EmergencyKillSwitch(emergency_flag_path)

# Rate Limiting System (M6.6)
class RateLimiter:
    """Manages rate limiting for sessions and global requests."""
    
    def __init__(self, 
                 session_limit: int = 60,  # requests per minute per session
                 global_limit: int = 500,  # requests per minute globally
                 window_seconds: int = 60):  # rolling window size
        self.session_limit = session_limit
        self.global_limit = global_limit
        self.window_seconds = window_seconds
        
        # Thread-safe access to counters
        self.lock = threading.Lock()
        
        # Session-based request tracking: {session_id: [(timestamp, request_count), ...]}
        self.session_requests: Dict[str, List[tuple]] = {}
        
        # Global request tracking: [(timestamp, request_count), ...]
        self.global_requests: List[tuple] = []
        
        # Cleanup thread for expired entries
        self.cleanup_thread = threading.Thread(target=self._cleanup_expired, daemon=True)
        self.cleanup_thread.start()
    
    def _cleanup_expired(self):
        """Background thread to clean up expired rate limit entries."""
        while True:
            try:
                current_time = time.time()
                cutoff_time = current_time - self.window_seconds
                
                with self.lock:
                    # Clean up session requests
                    for session_id in list(self.session_requests.keys()):
                        self.session_requests[session_id] = [
                            entry for entry in self.session_requests[session_id]
                            if entry[0] > cutoff_time
                        ]
                        # Remove empty sessions
                        if not self.session_requests[session_id]:
                            del self.session_requests[session_id]
                    
                    # Clean up global requests
                    self.global_requests = [
                        entry for entry in self.global_requests
                        if entry[0] > cutoff_time
                    ]
                
                # Sleep for cleanup interval (10 seconds)
                time.sleep(10)
                
            except Exception as e:
                print(f"Warning: Rate limiter cleanup error: {e}")
                time.sleep(10)
    
    def check_rate_limit(self, session_id: str) -> tuple[bool, Optional[int]]:
        """
        Check if request should be rate limited.
        
        Returns:
            (allowed: bool, retry_after_seconds: Optional[int])
        """
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            # Count session requests in current window
            if session_id not in self.session_requests:
                self.session_requests[session_id] = []
            
            session_count = sum(
                count for timestamp, count in self.session_requests[session_id]
                if timestamp > cutoff_time
            )
            
            # Count global requests in current window
            global_count = sum(
                count for timestamp, count in self.global_requests
                if timestamp > cutoff_time
            )
            
            # Check session limit
            if session_count >= self.session_limit:
                return False, self.window_seconds
            
            # Check global limit
            if global_count >= self.global_limit:
                return False, self.window_seconds
            
            # Add this request to counters
            self.session_requests[session_id].append((current_time, 1))
            self.global_requests.append((current_time, 1))
            
            return True, None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiting statistics."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        with self.lock:
            # Count current session requests
            session_stats = {}
            for session_id, requests in self.session_requests.items():
                count = sum(
                    count for timestamp, count in requests
                    if timestamp > cutoff_time
                )
                if count > 0:
                    session_stats[session_id] = count
            
            # Count current global requests
            global_count = sum(
                count for timestamp, count in self.global_requests
                if timestamp > cutoff_time
            )
            
            return {
                "session_limit": self.session_limit,
                "global_limit": self.global_limit,
                "window_seconds": self.window_seconds,
                "current_global_count": global_count,
                "active_sessions": len(session_stats),
                "session_counts": session_stats
            }

# Initialize rate limiter
rate_limiter = RateLimiter(
    session_limit=int(os.getenv("RATE_LIMIT_SESSION", "60")),
    global_limit=int(os.getenv("RATE_LIMIT_GLOBAL", "500")),
    window_seconds=int(os.getenv("RATE_LIMIT_WINDOW", "60"))
)

# Router & Async Generation System (M7.0)
class SmallIntentRouter:
    """Interface to SmallIntent.mlmodel for routing decisions with confidence thresholds."""
    
    def __init__(self, router_path: Optional[Path] = None):
        if router_path is None:
            self.router_path = Path(__file__).parent.parent / "router" / "runner" / "run_router.swift"
        else:
            self.router_path = router_path
            
        # Fallback for when router is not available
        self.router_available = self.router_path.exists()
        if not self.router_available:
            print(f"Warning: Router not found at {self.router_path}, using fallback routing")
        
        # M7.1: Confidence thresholds for decision making
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
        if not self.router_available:
            return self._fallback_routing(text)
        
        try:
            # Call Swift router
            result = subprocess.run(
                ["swift", str(self.router_path), text],
                capture_output=True,
                text=True,
                timeout=5  # 5 second timeout for router
            )
            
            if result.returncode != 0:
                print(f"Router execution failed: {result.stderr}")
                return self._fallback_routing(text)
            
            # Parse JSON response
            try:
                routing_result = json.loads(result.stdout.strip())
                
                # M7.1: Apply confidence thresholds
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
        
        Args:
            routing_result: Raw result from router {"route": "gen|act", "confidence": 0.85, "intent": "..."}
            text: Original text for fallback routing
        
        Returns:
            Enhanced result with potential abstain decisions
        """
        route = routing_result.get("route", "gen")
        confidence = routing_result.get("confidence", 0.5)
        intent = routing_result.get("intent", "unknown")
        
        # Check confidence thresholds
        if confidence < self.fallback_threshold:
            # Very low confidence, use fallback routing
            print(f"Router confidence {confidence:.3f} below fallback threshold {self.fallback_threshold}, using fallback")
            return self._fallback_routing(text)
        
        elif route == "gen" and confidence < self.min_conf_gen:
            # Generation route but confidence too low
            return {
                "route": "abstain",
                "intent": intent,
                "confidence": confidence,
                "abstain_reason": "low_confidence",  # M7.4: Standardized abstain reason
                "abstain_reason_detail": f"Generation confidence {confidence:.3f} below threshold {self.min_conf_gen}",
                "suggested_route": "gen",
                "fallback_available": True
            }
        
        elif route == "act" and confidence < self.min_conf_act:
            # Action route but confidence too low
            return {
                "route": "abstain", 
                "intent": intent,
                "confidence": confidence,
                "abstain_reason": "low_confidence",  # M7.4: Standardized abstain reason
                "abstain_reason_detail": f"Action confidence {confidence:.3f} below threshold {self.min_conf_act}",
                "suggested_route": "act",
                "fallback_available": True
            }
        
        else:
            # Confidence meets threshold, return original decision
            return routing_result
    
    def _fallback_routing(self, text: str) -> Dict[str, Any]:
        """Fallback routing logic when router is not available."""
        text_lower = text.lower()
        
        # Check for action-oriented keywords
        if any(term in text_lower for term in ['bot', 'position', 'trade', 'close', 'stop', 'emergency', 'execute', 'run', 'do']):
            return {
                "route": "act",
                "intent": "bot_management",
                "confidence": 0.7,
                "abstain_reason": "router_fallback",  # M7.4: Mark as fallback routing
                "abstain_reason_detail": "Using fallback routing due to router unavailability"
            }
        
        # Default to generation
        return {
            "route": "gen", 
            "intent": "general_query",
            "confidence": 0.6,
            "abstain_reason": "router_fallback",  # M7.4: Mark as fallback routing  
            "abstain_reason_detail": "Using fallback routing due to router unavailability"
        }


class AsyncOllamaClient:
    """Async client for Ollama generation with timeouts, retries, and concurrency control."""
    
    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.gen_timeout = int(os.getenv("GEN_TIMEOUT_S", "20"))
        self.max_retries = int(os.getenv("GEN_MAX_RETRIES", "2"))
        self.backoff_ms = int(os.getenv("GEN_BACKOFF_MS", "200"))
        
        # Concurrency control - limit concurrent generation requests
        # Initialize semaphore lazily to handle event loop issues
        self.concurrency_limit = int(os.getenv("GEN_CONCURRENCY", "4"))
        self._semaphore = None
        
        # HTTP client with timeouts
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.gen_timeout),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
    
    async def generate_async(self, model: str, prompt: str, request_id: str = None, session_id: str = "") -> tuple[str, int]:
        """
        Generate text asynchronously with retries, backpressure control, and circuit breaker.
        
        Args:
            model: Ollama model name
            prompt: Text to generate from
            request_id: Optional request ID for cancellation tracking
            session_id: Session ID for logging
        
        Returns:
            (generated_text, latency_ms)
        """
        # M7.3: Check circuit breaker first
        can_execute, reason, breaker_info = generation_circuit_breaker.can_execute(model)
        if not can_execute:
            # M7.3: Record blocked event in router metrics
            try:
                router_metrics.record_circuit_breaker_event(
                    model=model,
                    event_type="blocked",
                    state=breaker_info.get("state", "unknown"),
                    session_id=session_id,
                    additional_info={
                        "reason": reason,
                        "cooldown_remaining": breaker_info.get("cooldown_remaining", 0)
                    }
                )
            except:
                pass  # Don't break on metrics errors
            
            # Circuit breaker is open - return 503 immediately
            raise HTTPException(
                status_code=503,
                detail=f"Generation circuit breaker open for model {model}: {reason}",
                headers={"error_code": "gen_circuit_open", "retry_after": str(int(breaker_info.get("cooldown_remaining", 30)))}
            )
        
        # Generate request_id if not provided
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        # M7.3: Register task for cancellation tracking
        current_task = asyncio.current_task()
        generation_task_manager.register_task(request_id, current_task, model, session_id)
        
        # Get or create semaphore lazily
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        try:
            async with self._semaphore:  # Limit concurrent requests
                start_time = time.time()
                last_exception = None
                
                for attempt in range(self.max_retries + 1):
                    try:
                        # Check for cancellation before each attempt
                        if current_task.cancelled():
                            raise asyncio.CancelledError("Generation request was cancelled")
                        
                        # Add backoff delay for retries
                        if attempt > 0:
                            delay = (self.backoff_ms / 1000.0) * (2 ** (attempt - 1))
                            await asyncio.sleep(delay)
                            
                            # Log retry attempt
                            audit_logger.log_entry({
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                                "action": "ollama_retry",
                                "attempt": attempt + 1,
                                "model": model,
                                "request_id": request_id,
                                "delay_ms": int(delay * 1000),
                                "success": False
                            })
                        
                        # Make API request to Ollama
                        response = await self.client.post(
                            f"{self.ollama_host}/api/generate",
                            json={
                                "model": model,
                                "prompt": prompt,
                                "stream": False
                            }
                        )
                        
                        if response.status_code == 200:
                            result = response.json()
                            generated_text = result.get("response", "")
                            
                            end_time = time.time()
                            latency_ms = int((end_time - start_time) * 1000)
                            
                            # M7.3: Record success in circuit breaker
                            generation_circuit_breaker.record_success(model, session_id)
                            
                            # Log successful generation
                            audit_logger.log_entry({
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                                "action": "ollama_generation_success",
                                "model": model,
                                "request_id": request_id,
                                "latency_ms": latency_ms,
                                "attempts": attempt + 1,
                                "success": True
                            })
                            
                            return generated_text, latency_ms
                        else:
                            raise httpx.HTTPStatusError(
                                f"Ollama API error: {response.status_code}",
                                request=response.request,
                                response=response
                            )
                            
                    except asyncio.CancelledError:
                        # Handle task cancellation gracefully
                        end_time = time.time()
                        latency_ms = int((end_time - start_time) * 1000)
                        
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "ollama_generation_cancelled",
                            "model": model,
                            "request_id": request_id,
                            "latency_ms": latency_ms,
                            "success": False
                        })
                        
                        # Don't record as circuit breaker failure for cancellation
                        raise HTTPException(
                            status_code=499,
                            detail="Generation request was cancelled",
                            headers={"error_code": "GENERATION_CANCELLED"}
                        )
                        
                    except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                        last_exception = e
                        if attempt < self.max_retries:
                            continue
                        else:
                            # All retries exhausted - record failure in circuit breaker
                            end_time = time.time()
                            latency_ms = int((end_time - start_time) * 1000)
                            
                            # M7.3: Record failure in circuit breaker
                            error_type = "timeout" if isinstance(e, httpx.TimeoutException) else "connection" if isinstance(e, httpx.ConnectError) else "http_error"
                            generation_circuit_breaker.record_failure(model, error_type, session_id)
                            
                            # Log final failure
                            audit_logger.log_entry({
                                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                                "action": "ollama_generation_failed",
                                "model": model,
                                "request_id": request_id,
                                "attempts": self.max_retries + 1,
                                "latency_ms": latency_ms,
                                "error": str(e),
                                "success": False
                            })
                            
                            raise HTTPException(
                                status_code=504,
                                detail="Generation request timed out or failed after retries",
                                headers={"error_code": "GENERATION_TIMEOUT"}
                            )
        finally:
            # M7.3: Always clean up task registration
            generation_task_manager.unregister_task(request_id)
    
    @property
    def semaphore(self):
        """Get the semaphore, creating it if necessary."""
        if self._semaphore is None:
            try:
                self._semaphore = asyncio.Semaphore(self.concurrency_limit)
            except RuntimeError:
                # No event loop available, create a mock semaphore for testing
                return type('MockSemaphore', (), {'_value': self.concurrency_limit})()
        return self._semaphore
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


# Initialize router and async client
router = SmallIntentRouter()
async_ollama_client = AsyncOllamaClient()

# Track startup time for health endpoint
startup_time = time.time()

# Perform startup audit integrity check
print("Performing audit log integrity check...")
is_valid, integrity_errors = audit_logger.verify_integrity()
if not is_valid:
    print(f"WARNING: Audit log integrity check failed with {len(integrity_errors)} errors:")
    for error in integrity_errors[:5]:  # Show first 5 errors
        print(f"  - {error}")
    if len(integrity_errors) > 5:
        print(f"  ... and {len(integrity_errors) - 5} more errors")
    
    # Log integrity failure to new entry
    from datetime import datetime
    audit_logger.log_entry({
        "ts": datetime.utcnow().isoformat() + 'Z',
        "action": "startup_integrity_check",
        "success": False,
        "error_count": len(integrity_errors),
        "errors": integrity_errors[:10],  # Log first 10 errors
        "warning": "Audit log integrity compromised"
    })
else:
    print("✓ Audit log integrity check passed")
    # Log successful integrity check
    from datetime import datetime
    audit_logger.log_entry({
        "ts": datetime.utcnow().isoformat() + 'Z',
        "action": "startup_integrity_check", 
        "success": True,
        "error_count": 0,
        "message": "Audit log integrity verified"
    })

# Security
security = HTTPBearer(auto_error=False)


class RouteRequest(BaseModel):
    """Request model for POST /route endpoint."""
    text: str
    route: Optional[str] = "auto"  # auto|gen|act
    llm_pref: Optional[str] = None  # small|medium|large
    llm_model: Optional[str] = None  # specific ollama tag
    session_id: Optional[str] = None  # Session ID for episode tracking
    helper_id: Optional[str] = None  # Specific helper for act route
    helper_input: Optional[Dict[str, Any]] = None  # Direct helper input
    # Guarded execution fields
    execute: Optional[bool] = False  # True to execute, False for preview (default)
    approval_token: Optional[str] = None  # Required for execute=True
    # Idempotency field
    idempotency_key: Optional[str] = None  # Optional idempotency key
    # M7.4: Router self-correction & active learning
    override_route: Optional[str] = None  # gen|act - operator override when router abstains
    
    @validator('text')
    def text_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('text field cannot be empty')
        return v
    
    @validator('override_route')
    def override_route_must_be_valid(cls, v):
        if v is not None and v not in ['gen', 'act']:
            raise ValueError('override_route must be "gen" or "act"')
        return v


class RouteResponse(BaseModel):
    """Response model for POST /route endpoint."""
    status: str
    route_used: str
    text_response: Optional[str] = None
    model_used: Optional[str] = None
    latency_ms: Optional[int] = None
    session_id: str
    _router_fallback: Optional[bool] = None
    # Helper-specific fields for act route
    action: Optional[str] = None  # preview|execute
    helper_id: Optional[str] = None
    preview_json: Optional[Dict[str, Any]] = None
    approval_token: Optional[str] = None
    # Reflection layer fields
    reflection: Optional[Dict[str, Any]] = None
    veto_reason: Optional[str] = None
    reflection_error: Optional[str] = None
    # Idempotency field
    idempotent: Optional[bool] = None


class FeedbackRequest(BaseModel):
    """Request model for POST /feedback endpoint."""
    session_id: str
    feedback: str
    
    @validator('feedback')
    def feedback_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('feedback field cannot be empty')
        return v


class FeedbackResponse(BaseModel):
    """Response model for POST /feedback endpoint."""
    status: str
    message: str


def get_tinyintent_secret() -> str:
    """Get the required TINYINTENT_SECRET from environment."""
    secret = os.getenv("TINYINTENT_SECRET")
    if not secret:
        raise HTTPException(
            status_code=500,
            detail="TINYINTENT_SECRET environment variable is required"
        )
    return secret


def verify_auth(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> bool:
    """Verify X-TinyIntent-Secret header authentication."""
    # Check if dev bypass is enabled for localhost
    allow_dev_local = os.getenv("ALLOW_DEV_LOCAL", "0") == "1"
    if allow_dev_local:
        # Check if request is from localhost without X-Forwarded-For
        x_forwarded_for = request.headers.get("X-Forwarded-For")
        if not x_forwarded_for and request.client and request.client.host in ["127.0.0.1", "localhost"]:
            return True
    
    # Check for X-TinyIntent-Secret header
    secret_header = request.headers.get("X-TinyIntent-Secret")
    if not secret_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-TinyIntent-Secret header is required"
        )
    
    expected_secret = get_tinyintent_secret()
    if secret_header != expected_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid X-TinyIntent-Secret"
        )
    
    return True


def call_ollama_generate(model_tag: str, prompt: str) -> tuple[str, int]:
    """Call ollama to generate text and return the response with latency."""
    start_time = time.time()
    
    try:
        # Call ollama run command
        result = subprocess.run(
            ["ollama", "run", model_tag, prompt],
            capture_output=True,
            text=True,
            timeout=60  # 60 second timeout
        )
        
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)
        
        if result.returncode != 0:
            error_msg = result.stderr.strip() if result.stderr else "Unknown ollama error"
            raise HTTPException(
                status_code=500,
                detail=f"Ollama execution failed: {error_msg}"
            )
        
        response_text = result.stdout.strip()
        return response_text, latency_ms
        
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=500,
            detail="Ollama request timed out"
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=500,
            detail="Ollama binary not found. Please ensure ollama is installed and in PATH."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error calling ollama: {str(e)}"
        )


def check_ollama_present() -> bool:
    """Check if ollama binary is available."""
    return shutil.which("ollama") is not None


def check_env_valid() -> bool:
    """Check if required environment variables are set."""
    return os.getenv("TINYINTENT_SECRET") is not None


def check_router_binary() -> bool:
    """Check if router binary is available (placeholder for M3)."""
    # TODO: Implement router binary check in M3
    return False


def check_helpers_present() -> bool:
    """Check if helpers are available and loaded."""
    if not HELPERS_AVAILABLE or not helper_registry:
        return False
    return len(helper_registry.list_helpers()) > 0


def get_missing_helpers() -> List[str]:
    """Get list of helpers that failed to load."""
    if not HELPERS_AVAILABLE:
        return ["helpers framework not available"]
    # TODO: Implement missing helpers detection
    return []


def route_to_helper(text: str, model_tag: str) -> str:
    """Use LLM to determine which helper to use for action routing."""
    # Simple heuristic for M4 - in M5 this would use the trained router
    text_lower = text.lower()
    
    if any(term in text_lower for term in ['bot', 'position', 'trade', 'close', 'stop', 'emergency']):
        return 'bot_guard'
    
    # Default fallback
    return 'bot_guard'


def extract_helper_input(text: str, helper_id: str, model_tag: str) -> Dict[str, Any]:
    """Use LLM to extract structured input for helper from natural language."""
    # Simple extraction logic for M4 - in M5 this would use LLM
    text_lower = text.lower()
    
    if helper_id == 'bot_guard':
        # Extract trading operations from text
        if 'close all' in text_lower or 'emergency' in text_lower:
            return {
                "operation": "close_all_positions",
                "dry_run": True
            }
        elif 'close' in text_lower:
            # Try to extract symbol
            symbols = ['btc', 'eth', 'sol', 'ada', 'dot']
            symbol = None
            for s in symbols:
                if s in text_lower:
                    symbol = f"{s.upper()}/USDT"
                    break
            
            return {
                "operation": "close_position",
                "symbol": symbol or "BTC/USDT",
                "dry_run": True
            }
        elif 'position' in text_lower:
            return {
                "operation": "get_positions",
                "dry_run": True
            }
        elif 'balance' in text_lower:
            return {
                "operation": "get_balance",
                "dry_run": True
            }
    
    # Default fallback
    return {
        "operation": "get_positions",
        "dry_run": True
    }


@app.get("/healthz")
async def health_check() -> Dict[str, str]:
    """Health check endpoint - no authentication required."""
    return {"status": "ok"}


@app.get("/readyz")
async def readiness_check() -> Dict[str, Any]:
    """Readiness check endpoint - no authentication required."""
    models = model_resolver.get_all_models()
    missing_models = model_resolver.get_missing_models()
    
    checks = {
        "env_valid": check_env_valid(),
        "ollama_present": check_ollama_present(),
        "router_binary": check_router_binary(),
        "models_present": len(missing_models) == 0,
        "missing_models": missing_models,
        "helpers_present": check_helpers_present(),
        "missing_helpers": get_missing_helpers()
    }
    
    # Return 503 if any critical checks fail
    all_ready = checks["env_valid"] and checks["ollama_present"]
    status_code = 200 if all_ready else 503
    
    return {
        "ready": all_ready,
        "checks": checks,
        "models": models
    }


@app.post("/route")
async def route_request(
    request: RouteRequest, 
    fastapi_request: Request,
    auth: bool = Depends(verify_auth)
) -> RouteResponse:
    """
    Route a request to generation or action with full event logging.
    
    Example usage:
    
    # Preview request
    curl -X POST "http://localhost:8787/route" \
      -H "Content-Type: application/json" \
      -H "X-TinyIntent-Secret: your_secret" \
      -d '{"text": "Show my positions", "route": "act", "helper_id": "bot_guard"}'
    
    # Execute with approval token and idempotency
    curl -X POST "http://localhost:8787/route" \
      -H "Content-Type: application/json" \
      -H "X-TinyIntent-Secret: your_secret" \
      -H "X-Idempotency-Key: unique-key-123" \
      -d '{"text": "Show my positions", "route": "act", "helper_id": "bot_guard", 
           "execute": true, "approval_token": "abc123..."}'
    """
    
    # Get idempotency key from header or request body (prefer body)
    idempotency_key_header = fastapi_request.headers.get("X-Idempotency-Key")
    idempotency_key = request.idempotency_key or idempotency_key_header
    
    # Get or create session ID
    session_id = request.session_id
    if not session_id:
        session_id = experience_store.create_session()
    elif not experience_store.session_exists(session_id):
        experience_store.create_session(session_id)
    
    # Update session activity
    experience_store.update_session_activity(session_id)
    
    # Rate limiting check (M6.6)
    allowed, retry_after = rate_limiter.check_rate_limit(session_id)
    if not allowed:
        # Log rate limit violation
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "rate_limit",
            "session_id": session_id,
            "success": False,
            "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown",
            "user_agent": fastapi_request.headers.get("User-Agent", "unknown"),
            "route": request.route,
            "text_length": len(request.text) if request.text else 0,
            "retry_after": retry_after
        })
        
        # Log failed episode for rate limiting
        episode_logger.log_episode(
            session_id=session_id,
            action="rate_limited",
            helper_id="N/A",
            input_data={"route": request.route, "text_length": len(request.text) if request.text else 0},
            status_code=429,
            success=False,
            error_code="RATE_LIMIT_EXCEEDED"
        )
        
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(retry_after),
                "X-RateLimit-Limit-Session": str(rate_limiter.session_limit),
                "X-RateLimit-Limit-Global": str(rate_limiter.global_limit),
                "X-RateLimit-Window": str(rate_limiter.window_seconds)
            }
        )
    
    # Determine which model to use
    model_to_use = None
    if request.llm_model:
        model_to_use = request.llm_model
    elif request.llm_pref:
        model_to_use = model_resolver.get_model(request.llm_pref)
        if not model_to_use:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final=request.route,
                success=False,
                error_code="INVALID_MODEL_PREF"
            )
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model preference: {request.llm_pref}"
            )
    else:
        # Default to small model
        model_to_use = model_resolver.get_model("small")
    
    if not model_to_use:
        # Log error event
        experience_store.log_request(
            session_id=session_id,
            text=request.text,
            route_final=request.route,
            success=False,
            error_code="NO_MODEL_CONFIGURED"
        )
        raise HTTPException(
            status_code=500,
            detail="No suitable model configured"
        )
    
    # M7.0: Use SmallIntent router for automatic routing when route is "auto"
    if request.route == "auto":
        try:
            routing_result = router.route_request(request.text)
            determined_route = routing_result["route"]
            intent = routing_result["intent"]
            confidence = routing_result["confidence"]
            
            # M7.2: Record router decision metrics
            start_metrics_time = time.time()
            try:
                router_metrics.record_routing_decision(
                    route=determined_route,
                    intent=intent,
                    confidence=confidence,
                    latency_ms=0,  # Will be updated later with actual latency
                    outcome="preview" if not request.execute else "execute",
                    text_length=len(request.text) if request.text else 0,
                    session_id=session_id,
                    abstain_reason=routing_result.get("abstain_reason")
                )
            except Exception as metrics_error:
                # Don't let metrics collection break the main flow
                print(f"Router metrics recording error: {metrics_error}")
            
            # M7.1: Handle abstain decisions
            if determined_route == "abstain":
                # Router decided to abstain due to low confidence
                abstain_reason = routing_result.get("abstain_reason", "low_confidence")
                abstain_reason_detail = routing_result.get("abstain_reason_detail", "Low confidence routing decision")
                suggested_route = routing_result.get("suggested_route", "gen")
                
                # M7.4: Log abstain decision with enhanced categorization
                audit_logger.log_entry({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "action": "router_abstain",
                    "session_id": session_id,
                    "text_length": len(request.text) if request.text else 0,
                    "suggested_route": suggested_route,
                    "intent": intent,
                    "confidence": confidence,
                    "abstain_reason": abstain_reason,  # Standardized reason
                    "abstain_reason_detail": abstain_reason_detail,  # Human readable detail
                    "success": True
                })
                
                # M7.4: Log abstain episode for training
                episode_logger.log_router_episode(
                    session_id=session_id,
                    text=request.text,
                    original_route="abstain",
                    confidence=confidence,
                    intent=intent,
                    is_abstain=True,
                    abstain_reason=abstain_reason,
                    is_override=False,
                    label_source="router"
                )
                
                # M7.4: Check for operator override
                if request.override_route:
                    # Log the override event
                    audit_logger.log_entry({
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                        "action": "router_override",
                        "session_id": session_id,
                        "text_length": len(request.text) if request.text else 0,
                        "original_route": determined_route,
                        "override_route": request.override_route,
                        "abstain_reason": abstain_reason,
                        "confidence": confidence,
                        "intent": intent,
                        "client_ip": fastapi_request.client.host if fastapi_request.client else "unknown",
                        "user_agent": fastapi_request.headers.get("User-Agent", "unknown"),
                        "success": True
                    })
                    
                    # Log override episode for training
                    episode_logger.log_router_episode(
                        session_id=session_id,
                        text=request.text,
                        original_route=determined_route,
                        confidence=confidence,
                        intent=intent,
                        is_abstain=False,
                        abstain_reason=abstain_reason,
                        is_override=True,
                        override_route=request.override_route,
                        override_confidence=0.9,  # High confidence for operator override
                        label_source="override"
                    )
                    
                    # Execute override path - set determined_route to override
                    determined_route = request.override_route
                    confidence = 0.9  # High confidence for operator override
                    intent = f"{intent}_override"
                    
                    # Log successful override
                    audit_logger.log_entry({
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                        "action": "router_override_executed",
                        "session_id": session_id,
                        "override_route": request.override_route,
                        "success": True
                    })
                    
                    # Continue with override route (fall through to normal route processing)
                
                else:
                    # No override - return abstain response
                    return RouteResponse(
                        status="abstain",
                        route_used="abstain",
                        text_response=f"Router abstained: {abstain_reason_detail}. Consider being more specific or try manual routing with route=\"{suggested_route}\".",
                        session_id=session_id,
                        _router_fallback=False,
                        reflection={
                            "abstain_reason": abstain_reason,
                            "abstain_reason_detail": abstain_reason_detail,
                            "suggested_route": suggested_route,
                            "confidence": confidence,
                            "intent": intent
                        }
                    )
            
            # Log routing decision
            audit_logger.log_entry({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                "action": "router_decision",
                "session_id": session_id,
                "text_length": len(request.text) if request.text else 0,
                "determined_route": determined_route,
                "intent": intent,
                "confidence": confidence,
                "success": True
            })
            
            # Override route with router decision
            actual_route = determined_route
            router_fallback = True
            
        except Exception as e:
            # Router failed, fall back to generation
            audit_logger.log_entry({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                "action": "router_error",
                "session_id": session_id,
                "error": str(e),
                "success": False
            })
            
            # M7.2: Record router error metrics
            try:
                router_metrics.record_error(
                    error_type="router_execution_error",
                    error_message=str(e),
                    session_id=session_id
                )
            except Exception as metrics_error:
                print(f"Router error metrics recording failed: {metrics_error}")
            
            actual_route = "gen"
            router_fallback = True
            intent = "general_query"
            confidence = 0.5
    else:
        # Route explicitly specified by user
        actual_route = request.route
        router_fallback = False
        intent = None
        confidence = None
    
    # Handle different route types
    if actual_route == "gen":
        # Generation route - call async ollama
        try:
            response_text, latency_ms = await async_ollama_client.generate_async(
                model_to_use, 
                request.text,
                session_id=session_id
            )
            
            # Log successful event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="gen",
                model_used=model_to_use,
                latency_ms=latency_ms,
                success=True
            )
            
            return RouteResponse(
                status="success",
                route_used="gen",
                text_response=response_text,
                model_used=model_to_use,
                latency_ms=latency_ms,
                session_id=session_id,
                _router_fallback=router_fallback if request.route == "auto" else None
            )
            
        except HTTPException as e:
            # M7.4: Check if this is a circuit breaker error
            if e.status_code == 503 and e.headers and e.headers.get("error_code") == "gen_circuit_open":
                # Circuit breaker is open - convert to abstain with override support
                
                # Log circuit breaker abstain event
                audit_logger.log_entry({
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                    "action": "circuit_breaker_abstain",
                    "session_id": session_id,
                    "model": model_to_use,
                    "abstain_reason": "circuit_open",
                    "success": True
                })
                
                # M7.4: Log abstain episode for training
                episode_logger.log_router_episode(
                    session_id=session_id,
                    text=request.text,
                    original_route="gen",
                    confidence=0.0,  # Zero confidence when circuit breaker blocks
                    intent="generation_blocked",
                    is_abstain=True,
                    abstain_reason="circuit_open",
                    is_override=False,
                    label_source="circuit_breaker"
                )
                
                # M7.4: Check for operator override
                if request.override_route == "gen":
                    # Log the override attempt (but still block for safety)
                    audit_logger.log_entry({
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                        "action": "circuit_breaker_override_blocked",
                        "session_id": session_id,
                        "model": model_to_use,
                        "override_route": request.override_route,
                        "reason": "Circuit breaker overrides not allowed for safety",
                        "success": False
                    })
                    
                    return RouteResponse(
                        status="error", 
                        route_used="abstain",
                        text_response="Circuit breaker is open for generation. Override not allowed for safety reasons. Please try again later.",
                        session_id=session_id,
                        reflection={
                            "abstain_reason": "circuit_open",
                            "abstain_reason_detail": str(e.detail),
                            "override_blocked": True,
                            "retry_after": e.headers.get("retry_after", "30")
                        }
                    )
                else:
                    # Normal circuit breaker abstain response
                    return RouteResponse(
                        status="abstain",
                        route_used="abstain", 
                        text_response=f"Generation temporarily unavailable due to circuit breaker. {str(e.detail)}",
                        session_id=session_id,
                        reflection={
                            "abstain_reason": "circuit_open",
                            "abstain_reason_detail": str(e.detail),
                            "suggested_route": "gen",
                            "retry_after": e.headers.get("retry_after", "30")
                        }
                    )
            
            # Other HTTP exceptions - continue with original handling
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="gen",
                model_used=model_to_use,
                success=False,
                error_code="OLLAMA_ERROR"
            )
            raise  # Re-raise HTTP exceptions from call_ollama_generate
            
        except Exception as e:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="gen",
                model_used=model_to_use,
                success=False,
                error_code="UNEXPECTED_ERROR"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Unexpected error during generation: {str(e)}"
            )
    
    elif actual_route == "act":
        # Action route - delegate to Helpers Orchestrator
        try:
            start_time = time.time()
            
            # Check if helpers are available and enabled
            if not HELPERS_AVAILABLE:
                raise HTTPException(
                    status_code=503,
                    detail="Helpers framework not available (missing dependencies)"
                )
                
            helpers_enabled = os.getenv("HELPERS_ENABLED", "1") == "1"
            if not helpers_enabled:
                raise HTTPException(
                    status_code=503,
                    detail="Helpers framework is disabled"
                )
            
            # Check execution gate for execute mode (M6.3: Emergency Kill Switch)
            if request.execute:
                if not emergency_kill.is_execution_enabled():
                    # Check if it's due to emergency flag or normal configuration
                    if emergency_flag_path.exists():
                        error_detail = "Execution disabled (emergency kill)"
                        error_code = "EMERGENCY_KILL_ACTIVE"
                    else:
                        error_detail = "Execution disabled"
                        error_code = "EXECUTION_DISABLED"
                    
                    raise HTTPException(
                        status_code=503,
                        detail=error_detail,
                        headers={"error_code": error_code}
                    )
            
            # Determine helper to use - M7.0: Use router intent or explicit helper_id
            if request.helper_id:
                helper_id = request.helper_id
            elif intent and intent != "general_query":
                # Use router intent to determine helper
                if intent == "bot_management":
                    helper_id = "bot_guard"
                elif intent == "system_monitoring":
                    helper_id = "log_tailer"
                elif intent == "infrastructure":
                    helper_id = "ssh_ops"
                else:
                    # Fallback to bot_guard for other action intents
                    helper_id = "bot_guard"
            else:
                # Use fallback routing logic
                helper_id = route_to_helper(request.text, model_to_use)
            
            # Prepare helper input
            if request.helper_input:
                helper_input = request.helper_input
            else:
                # Use LLM to extract structured input from natural language
                helper_input = extract_helper_input(request.text, helper_id, model_to_use)
            
            # Check for idempotency in execute mode
            if request.execute and idempotency_key:
                cached_result = approval_manager.get_idempotency_result(
                    idempotency_key, helper_id, helper_input
                )
                if cached_result:
                    # Return cached result with idempotent flag
                    cached_result["idempotent"] = True
                    return RouteResponse(**cached_result)
            
            # Determine execution mode
            execution_mode = "execute" if request.execute else "preview"
            
            # Handle guarded execution flow
            if request.execute:
                # Get helper manifest for risk level
                helper_manifest = helper_registry.get_helper(helper_id)
                if not helper_manifest:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Helper not found: {helper_id}"
                    )
                
                # Check if helper can execute
                if not helper_manifest.can_execute():
                    raise HTTPException(
                        status_code=501,
                        detail=f"Helper {helper_id} does not support execution"
                    )
                
                # Get risk level from registry or manifest
                registry_entry = helper_registry.registry_data.get("helpers", {}).get(helper_id, {})
                risk_level = registry_entry.get("risk_level", "medium")
                
                # Validate approval token for execution
                is_valid, error_msg, token_id = approval_manager.validate_approval_token(
                    request.approval_token, helper_id, helper_input, request.text, risk_level
                )
                
                if not is_valid:
                    # Log failed approval attempt
                    experience_store.log_request(
                        session_id=session_id,
                        text=request.text,
                        route_final="act",
                        helper_id=helper_id,
                        success=False,
                        error_code="APPROVAL_FAILED"
                    )
                    
                    # Determine reason code for better error reporting
                    reason_code = "TOKEN_INVALID"
                    if "already used" in error_msg:
                        reason_code = "TOKEN_USED"
                    elif "expired" in error_msg:
                        reason_code = "TOKEN_EXPIRED"
                    elif "too old" in error_msg:
                        reason_code = "TOKEN_TOO_OLD"
                    elif "does not match" in error_msg:
                        reason_code = "TOKEN_MISMATCH"
                    
                    raise HTTPException(
                        status_code=403,
                        detail=error_msg,
                        headers={"reason_code": reason_code}
                    )
                
                # Execute helper
                try:
                    helper_result = helper_executor.execute(
                        helper_id=helper_id,
                        input_data=helper_input,
                        session_id=session_id,
                        token_id=token_id,
                        idempotency_key=idempotency_key
                    )
                except ValueError as e:
                    if hasattr(e, 'missing_vars'):
                        # Missing environment variables - return 409
                        raise HTTPException(
                            status_code=409,
                            detail=f"Required environment variables missing for {helper_id}",
                            headers={"missing_vars": json.dumps(e.missing_vars)}
                        )
                    elif "Output schema validation failed" in str(e):
                        # Schema validation failed - return 500
                        raise HTTPException(
                            status_code=500,
                            detail="Helper output schema validation failed",
                            headers={"error_code": "SCHEMA_VALIDATION_FAILED"}
                        )
                    else:
                        raise
                
                except Exception as execution_error:
                    # Check for capability violations (M6.5)
                    if (CapabilityViolationError and 
                        isinstance(execution_error, CapabilityViolationError)):
                        
                        # Log capability violation for audit
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "capability_violation",
                            "helper_id": helper_id,
                            "capability": execution_error.capability,
                            "operation": execution_error.operation,
                            "session_id": session_id,
                            "success": False,
                            "error_code": execution_error.error_code,
                            "details": execution_error.details
                        })
                        
                        # Log episode with capability violation
                        episode_logger.log_episode(
                            session_id=session_id,
                            action="execute",
                            helper_id=helper_id,
                            input_data=helper_input,
                            status_code=403,
                            success=False,
                            error_code="CAPABILITY_VIOLATION"
                        )
                        
                        # Return HTTP 403 with capability violation details
                        raise HTTPException(
                            status_code=403,
                            detail=f"Helper capability violation: {str(execution_error)}",
                            headers={
                                "reason": "CAPABILITY_VIOLATION",
                                "capability": execution_error.capability,
                                "operation": execution_error.operation
                            }
                        )
                    
                    # Check for helper rate limit violations (M6.6)
                    elif (HelperRateLimitError and 
                          isinstance(execution_error, HelperRateLimitError)):
                        
                        # Log helper rate limit violation for audit
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "helper_rate_limit",
                            "helper_id": helper_id,
                            "session_id": session_id,
                            "success": False,
                            "error_code": execution_error.error_code,
                            "current_count": execution_error.current_count,
                            "limit": execution_error.limit,
                            "window_seconds": execution_error.window_seconds
                        })
                        
                        # Log episode with rate limit violation
                        episode_logger.log_episode(
                            session_id=session_id,
                            action="execute",
                            helper_id=helper_id,
                            input_data=helper_input,
                            status_code=429,
                            success=False,
                            error_code="HELPER_RATE_LIMIT"
                        )
                        
                        # Return HTTP 429 with rate limit details
                        raise HTTPException(
                            status_code=429,
                            detail=f"Helper rate limit exceeded: {str(execution_error)}",
                            headers={
                                "reason": "HELPER_RATE_LIMIT",
                                "Retry-After": str(execution_error.window_seconds),
                                "X-RateLimit-Helper": helper_id,
                                "X-RateLimit-Limit": str(execution_error.limit),
                                "X-RateLimit-Current": str(execution_error.current_count),
                                "X-RateLimit-Window": str(execution_error.window_seconds)
                            }
                        )
                    
                    else:
                        # Re-raise other exceptions
                        raise execution_error
                
                except RuntimeError as e:
                    # Check for sandbox violations
                    if "Sandbox violation:" in str(e):
                        # Extract error code from sandbox violation
                        error_msg = str(e)
                        if "SANDBOX_TIMEOUT" in error_msg:
                            error_code = "SANDBOX_TIMEOUT"
                        elif "SANDBOX_CPU_LIMIT" in error_msg:
                            error_code = "SANDBOX_CPU_LIMIT"
                        elif "SANDBOX_MEMORY_LIMIT" in error_msg:
                            error_code = "SANDBOX_MEMORY_LIMIT"
                        elif "SANDBOX_OUTPUT_SIZE" in error_msg:
                            error_code = "SANDBOX_OUTPUT_SIZE"
                        else:
                            error_code = "SANDBOX_VIOLATION"
                        
                        raise HTTPException(
                            status_code=500,
                            detail="Helper execution failed due to sandbox limits",
                            headers={"error_code": error_code}
                        )
                    else:
                        # Regular runtime error
                        raise HTTPException(
                            status_code=500,
                            detail=f"Helper execution failed: {str(e)}",
                            headers={"error_code": "EXECUTION_FAILED"}
                        )
                
                # Cache result for idempotency if key provided
                if idempotency_key:
                    cache_result = {
                        "status": helper_result.get("status", "success"),
                        "route_used": "act",
                        "session_id": session_id,
                        "action": "execute",
                        "helper_id": helper_id,
                        "result": helper_result.get("result")
                    }
                    approval_manager.set_idempotency_result(
                        idempotency_key, helper_id, helper_input, cache_result
                    )
                
            else:
                # Execute helper in preview mode
                try:
                    helper_result = helper_executor.preview(
                        helper_id=helper_id,
                        input_data=helper_input,
                        session_id=session_id
                    )
                except Exception as preview_error:
                    # Check for capability violations in preview mode (M6.5)
                    if (CapabilityViolationError and 
                        isinstance(preview_error, CapabilityViolationError)):
                        
                        # Log capability violation for audit
                        audit_logger.log_entry({
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                            "action": "capability_violation",
                            "helper_id": helper_id,
                            "capability": preview_error.capability,
                            "operation": preview_error.operation,
                            "session_id": session_id,
                            "success": False,
                            "error_code": preview_error.error_code,
                            "details": preview_error.details
                        })
                        
                        # Log episode with capability violation
                        episode_logger.log_episode(
                            session_id=session_id,
                            action="preview",
                            helper_id=helper_id,
                            input_data=helper_input,
                            status_code=403,
                            success=False,
                            error_code="CAPABILITY_VIOLATION"
                        )
                        
                        # Return HTTP 403 with capability violation details
                        raise HTTPException(
                            status_code=403,
                            detail=f"Helper capability violation: {str(preview_error)}",
                            headers={
                                "reason": "CAPABILITY_VIOLATION",
                                "capability": preview_error.capability,
                                "operation": preview_error.operation
                            }
                        )
                    
                    # Note: Preview mode doesn't check helper rate limits as it's non-destructive
                
                except RuntimeError as e:
                    # Check for sandbox violations in preview mode
                    if "Sandbox violation:" in str(e):
                        # Extract error code from sandbox violation
                        error_msg = str(e)
                        if "SANDBOX_TIMEOUT" in error_msg:
                            error_code = "SANDBOX_TIMEOUT"
                        elif "SANDBOX_CPU_LIMIT" in error_msg:
                            error_code = "SANDBOX_CPU_LIMIT"
                        elif "SANDBOX_MEMORY_LIMIT" in error_msg:
                            error_code = "SANDBOX_MEMORY_LIMIT"
                        elif "SANDBOX_OUTPUT_SIZE" in error_msg:
                            error_code = "SANDBOX_OUTPUT_SIZE"
                        else:
                            error_code = "SANDBOX_VIOLATION"
                        
                        raise HTTPException(
                            status_code=500,
                            detail="Helper preview failed due to sandbox limits",
                            headers={"error_code": error_code}
                        )
                    else:
                        # Regular runtime error
                        sanitized_error = sanitize_text(str(e))
                        raise HTTPException(
                            status_code=500,
                            detail=f"Helper preview failed: {sanitized_error}",
                            headers={"error_code": "PREVIEW_FAILED"}
                        )
            
            # Apply reflection layer validation
            reflection_enabled = os.getenv("REFLECTION_ENABLED", "1") == "1"
            reflection_result = None
            
            if reflection_enabled and reflector and helper_result.get("status") == "success":
                try:
                    reflection_result = reflector.reflect(
                        helper_id=helper_id,
                        user_text=request.text,
                        helper_input=helper_input,
                        helper_output=helper_result.get("preview_json", {}),
                        session_id=session_id
                    )
                    
                    # Add reflection data to helper result
                    helper_result["reflection"] = reflection_result
                    
                    # Override approval if reflection vetoes
                    if not reflection_result.get("approved", False):
                        helper_result["status"] = "vetoed"
                        helper_result["veto_reason"] = reflection_result.get("veto_reason")
                        
                except Exception as e:
                    # Don't fail the request if reflection fails, but log it
                    helper_result["reflection_error"] = str(e)
            
            # Generate approval token for preview mode if helper supports execution
            approval_token = None
            if not request.execute and helper_result.get("status") == "success":
                # Check if helper requires approval for execution
                helper_manifest = helper_registry.get_helper(helper_id)
                if helper_manifest and helper_manifest.can_execute():
                    approval_token = approval_manager.generate_approval_token(
                        helper_id=helper_id,
                        helper_input=helper_input,
                        session_id=session_id,
                        user_text=request.text
                    )
                    helper_result["approval_token"] = approval_token
            
            end_time = time.time()
            latency_ms = int((end_time - start_time) * 1000)
            
            # Log successful event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="act",
                helper_id=helper_id,
                helper_input=helper_input,
                preview_json=helper_result.get("preview_json"),
                latency_ms=latency_ms,
                success=True
            )
            
            # Log episode for router retraining
            final_status = helper_result.get("status", "success")
            episode_success = final_status == "success"
            episode_error_code = None
            
            if not episode_success:
                if helper_result.get("veto_reason"):
                    episode_error_code = "REFLECTION_VETO"
                elif helper_result.get("reflection_error"):
                    episode_error_code = "REFLECTION_ERROR"
            
            episode_logger.log_episode(
                session_id=session_id,
                action=execution_mode,
                helper_id=helper_id,
                input_data=helper_input,
                status_code=200,  # HTTP status for successful response
                success=episode_success,
                approval_token_id=token_id if request.execute else None,
                idempotency_key=idempotency_key,
                error_code=episode_error_code
            )
            
            # Build response based on execution mode
            if request.execute:
                return RouteResponse(
                    status=helper_result.get("status", "success"),
                    route_used="act",
                    session_id=session_id,
                    latency_ms=latency_ms,
                    action="execute",
                    helper_id=helper_id,
                    preview_json=helper_result.get("result"),
                    reflection=helper_result.get("reflection"),
                    veto_reason=helper_result.get("veto_reason"),
                    reflection_error=helper_result.get("reflection_error")
                )
            else:
                return RouteResponse(
                    status=helper_result.get("status", "success"),
                    route_used="act",
                    session_id=session_id,
                    latency_ms=latency_ms,
                    action="preview",
                    helper_id=helper_result.get("helper_id", helper_id),
                    preview_json=helper_result.get("preview_json"),
                    approval_token=helper_result.get("approval_token"),
                    reflection=helper_result.get("reflection"),
                    veto_reason=helper_result.get("veto_reason"),
                    reflection_error=helper_result.get("reflection_error")
                )
            
        except HTTPException as e:
            # Log failed episode for HTTP exceptions
            error_code = None
            if e.status_code == 403:
                # Check if it's a capability violation or approval failure
                reason_header = e.headers.get("reason") if hasattr(e, 'headers') else None
                if reason_header == "CAPABILITY_VIOLATION":
                    error_code = "CAPABILITY_VIOLATION"
                else:
                    error_code = "APPROVAL_FAILED"
            elif e.status_code == 409:
                error_code = "MISSING_ENVIRONMENT"
            elif e.status_code == 429:
                # Check if it's helper rate limit or general rate limit
                reason_header = e.headers.get("reason") if hasattr(e, 'headers') else None
                if reason_header == "HELPER_RATE_LIMIT":
                    error_code = "HELPER_RATE_LIMIT"
                else:
                    error_code = "RATE_LIMIT_EXCEEDED"
            elif e.status_code == 500:
                error_code = "SCHEMA_VALIDATION_FAILED"
            elif e.status_code == 503:
                error_code = "EXECUTION_DISABLED"
            
            episode_logger.log_episode(
                session_id=session_id,
                action=execution_mode,
                helper_id=helper_id if 'helper_id' in locals() else "unknown",
                input_data=helper_input if 'helper_input' in locals() else {},
                status_code=e.status_code,
                success=False,
                approval_token_id=token_id if 'token_id' in locals() else None,
                idempotency_key=idempotency_key,
                error_code=error_code
            )
            
            raise  # Re-raise HTTP exceptions
            
        except Exception as e:
            # Log error event
            experience_store.log_request(
                session_id=session_id,
                text=request.text,
                route_final="act",
                success=False,
                error_code="HELPER_ERROR"
            )
            
            # Log failed episode for unexpected errors
            episode_logger.log_episode(
                session_id=session_id,
                action=execution_mode if 'execution_mode' in locals() else "unknown",
                helper_id=helper_id if 'helper_id' in locals() else "unknown",
                input_data=helper_input if 'helper_input' in locals() else {},
                status_code=500,
                success=False,
                approval_token_id=None,
                idempotency_key=idempotency_key,
                error_code="HELPER_ERROR"
            )
            
            # Sanitize error message before returning to client
            sanitized_error = sanitize_text(str(e))
            
            raise HTTPException(
                status_code=500,
                detail=f"Helper execution failed: {sanitized_error}"
            )
    
    else:
        # Log error event
        experience_store.log_request(
            session_id=session_id,
            text=request.text,
            route_final=actual_route,
            success=False,
            error_code="UNKNOWN_ROUTE"
        )
        raise HTTPException(
            status_code=400,
            detail=f"Unknown route: {actual_route}"
        )


@app.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    auth: bool = Depends(verify_auth)
) -> FeedbackResponse:
    """Submit feedback for a session/episode. Implements M2 requirement."""
    
    # Validate session exists
    if not experience_store.session_exists(request.session_id):
        raise HTTPException(
            status_code=404,
            detail=f"Session {request.session_id} not found"
        )
    
    # Log feedback event
    try:
        experience_store.log_feedback(request.session_id, request.feedback)
        
        # Update session activity
        experience_store.update_session_activity(request.session_id)
        
        return FeedbackResponse(
            status="success",
            message="Feedback logged successfully"
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to log feedback: {str(e)}"
        )


@app.post("/admin/reload-models")
async def reload_models(auth: bool = Depends(verify_auth)) -> Dict[str, str]:
    """Reload models.yaml configuration."""
    try:
        model_resolver.reload()
        return {"status": "success", "message": "Models reloaded"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload models: {str(e)}"
        )


@app.post("/admin/reload-helpers")
async def reload_helpers(auth: bool = Depends(verify_auth)) -> Dict[str, str]:
    """Reload helper manifests. M4: Helpers Framework v1"""
    if not HELPERS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Helpers framework not available (missing dependencies)"
        )
        
    try:
        helper_registry.reload()
        helpers_count = len(helper_registry.list_helpers())
        return {
            "status": "success", 
            "message": f"Helpers reloaded - {helpers_count} helpers available",
            "helpers": helper_registry.list_helpers()
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload helpers: {str(e)}"
        )


@app.post("/helpers/reload")
async def reload_helpers_dynamic(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """
    M8.2: Dynamic helper discovery and hot reload.
    Triggers re-scan of helpers/ directories with manifest validation.
    """
    try:
        # Use the global helper resolver for thread-safe reload
        reload_result = helper_resolver.load_helpers()
        
        # Log the reload event
        audit_logger.log_entry({
            "action": "helpers_dynamic_reload",
            "enabled_count": len(reload_result["enabled"]),
            "disabled_count": len(reload_result["disabled"]),
            "total_count": reload_result["total"],
            "success": True
        })
        
        return {
            "status": "success",
            "message": f"Helper reload completed - {len(reload_result['enabled'])}/{reload_result['total']} helpers enabled",
            "enabled": reload_result["enabled"],
            "disabled": reload_result["disabled"], 
            "errors": reload_result["errors"],
            "total": reload_result["total"],
            "enabled_metadata": reload_result.get("enabled_metadata", {})  # M8.3: Include version metadata
        }
        
    except Exception as e:
        # Log the failure
        audit_logger.log_entry({
            "action": "helpers_dynamic_reload",
            "success": False,
            "error": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reload helpers: {str(e)}"
        )


@app.get("/helpers")
async def get_helpers(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """
    M8.3: Get all loaded helpers with metadata.
    Returns helpers with id, description, version, updated date, and capabilities.
    """
    try:
        if not helper_resolver.available:
            raise HTTPException(
                status_code=503,
                detail="Helpers framework not available"
            )
        
        # Get helper validation summary which includes all metadata
        validation_summary = helper_resolver.get_validation_summary()
        
        if not validation_summary.get("available", False):
            raise HTTPException(
                status_code=503,
                detail="Helper registry not available"
            )
        
        # Transform the data to focus on enabled helpers with their metadata
        helpers = []
        helpers_data = validation_summary.get("helpers", {})
        
        for helper_id, helper_info in helpers_data.items():
            if helper_info.get("is_valid", False):
                helper_data = {
                    "id": helper_id,
                    "name": helper_info.get("name", helper_id),
                    "description": helper_info.get("description", ""),
                    "capabilities": helper_info.get("capabilities", []),
                    "category": helper_info.get("category", "unknown"),
                    "risk_level": helper_info.get("risk_level", "medium"),
                    "can_execute": helper_info.get("can_execute", False)
                }
                
                # M8.3: Include version metadata if present
                if helper_info.get("version"):
                    helper_data["version"] = helper_info["version"]
                if helper_info.get("added"):
                    helper_data["added"] = helper_info["added"]
                if helper_info.get("updated"):
                    helper_data["updated"] = helper_info["updated"]
                if helper_info.get("maintainer"):
                    helper_data["maintainer"] = helper_info["maintainer"]
                
                helpers.append(helper_data)
        
        return {
            "status": "success",
            "helpers": helpers,
            "total": len(helpers),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
        
    except Exception as e:
        audit_logger.log_entry({
            "action": "get_helpers",
            "success": False,
            "error": str(e)
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get helpers: {str(e)}"
        )


@app.get("/admin/audit-log-stats")
async def get_audit_log_stats(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """Get audit log statistics and integrity status. M6.2"""
    try:
        stats = audit_logger.get_stats()
        
        # Add integrity check
        is_valid, errors = audit_logger.verify_integrity()
        stats["integrity_valid"] = is_valid
        stats["integrity_error_count"] = len(errors)
        
        if not is_valid:
            stats["integrity_errors"] = errors[:5]  # First 5 errors
        
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get audit log stats: {str(e)}"
        )


@app.post("/admin/rotate-audit-log")
async def rotate_audit_log(auth: bool = Depends(verify_auth)) -> Dict[str, str]:
    """Force audit log rotation. M6.2"""
    try:
        rotated = audit_logger.rotate_now()
        if rotated:
            return {"status": "success", "message": "Audit log rotated successfully"}
        else:
            return {"status": "success", "message": "No rotation needed (log file empty or missing)"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to rotate audit log: {str(e)}"
        )


@app.get("/admin/verify-audit-integrity")
async def verify_audit_integrity(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """Verify audit log integrity for current and archived logs. M6.2"""
    try:
        is_valid, errors = audit_logger.verify_all_integrity()
        
        result = {
            "integrity_valid": is_valid,
            "error_count": len(errors),
            "message": "All audit logs verified" if is_valid else "Integrity violations found"
        }
        
        if not is_valid:
            result["errors"] = errors[:10]  # First 10 errors
            if len(errors) > 10:
                result["additional_errors"] = len(errors) - 10
        
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to verify audit integrity: {str(e)}"
        )


@app.get("/admin/rate-limit-stats")
async def get_rate_limit_stats(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """Get current rate limiting statistics. M6.6"""
    try:
        stats = rate_limiter.get_stats()
        return {
            "status": "success",
            "rate_limits": stats,
            "message": f"Rate limiting active with {stats['active_sessions']} sessions tracked"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get rate limit stats: {str(e)}"
        )


@app.get("/router/metrics")
async def get_router_metrics(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """
    Get router reliability monitoring metrics. M7.2
    
    Returns confidence histograms, abstain rates, latency stats,
    and error tracking for router health monitoring.
    """
    try:
        metrics = router_metrics.get_metrics_summary()
        return {
            "status": "success",
            "router_metrics": metrics,
            "message": f"Router metrics with {metrics['summary']['total_requests']} requests tracked"
        }
    except Exception as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "router_metrics_error",
            "error": str(e),
            "success": False
        })
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get router metrics: {str(e)}"
        )


@app.get("/router/metrics/debug")
async def get_router_metrics_debug(
    limit: int = 50,
    auth: bool = Depends(verify_auth)
) -> Dict[str, Any]:
    """
    Get recent router entries for debugging. M7.2
    
    Returns recent router decisions with full details for troubleshooting.
    """
    try:
        if limit > 200:  # Prevent excessive data return
            limit = 200
        
        recent_entries = router_metrics.get_recent_entries(limit)
        return {
            "status": "success",
            "recent_entries": recent_entries,
            "count": len(recent_entries),
            "message": f"Retrieved {len(recent_entries)} recent router entries"
        }
    except Exception as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "router_metrics_debug_error",
            "error": str(e),
            "success": False
        })
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get router debug metrics: {str(e)}"
        )


@app.post("/router/metrics/flush")
async def flush_router_metrics(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """
    Manually flush router metrics buffer to database. M7.2
    
    Useful for forcing persistence of current metrics or testing the flush mechanism.
    """
    try:
        flush_result = router_metrics.flush_to_database()
        
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "router_metrics_flush",
            "flushed_count": flush_result.get("flushed_count", 0),
            "success": flush_result.get("status") == "success"
        })
        
        return {
            "status": "success",
            "flush_result": flush_result,
            "message": f"Flush completed: {flush_result.get('message', 'Unknown result')}"
        }
    except Exception as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "router_metrics_flush_error",
            "error": str(e),
            "success": False
        })
        raise HTTPException(
            status_code=500,
            detail=f"Failed to flush router metrics: {str(e)}"
        )


@app.get("/router/metrics/database")
async def get_router_metrics_database_stats(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """
    Get router metrics statistics from database. M7.2
    
    Returns historical router performance data persisted to database.
    """
    try:
        from episodes import episode_logger
        db_stats = episode_logger.get_router_metrics_stats()
        
        return {
            "status": "success",
            "database_stats": db_stats,
            "message": f"Database contains {db_stats.get('total_requests', 0)} router metrics entries"
        }
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Episode logger not available for database access"
        )
    except Exception as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "router_metrics_database_error",
            "error": str(e),
            "success": False
        })
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get router database stats: {str(e)}"
        )


@app.get("/router/train_summary")
async def get_router_train_summary(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """
    Get router training summary for operator visibility. M7.5
    
    Returns comprehensive training results from the last retraining run,
    including model performance, dataset statistics, and sample predictions.
    """
    try:
        from pathlib import Path
        import json
        
        # Look for training summary file
        project_root = Path(__file__).parent.parent
        train_summary_path = project_root / "router" / "train_summary.json"
        
        if not train_summary_path.exists():
            # Try alternative locations
            alt_paths = [
                project_root / "router" / "train" / "output" / "train_summary.json",
                project_root / "router" / "train_output" / "train_summary.json"
            ]
            
            for alt_path in alt_paths:
                if alt_path.exists():
                    train_summary_path = alt_path
                    break
            else:
                return {
                    "status": "not_available",
                    "message": "No training summary available. Run 'make learn' to generate training results.",
                    "expected_path": str(train_summary_path),
                    "alternative_paths_checked": [str(p) for p in alt_paths]
                }
        
        # Load training summary
        with open(train_summary_path, 'r') as f:
            train_summary = json.load(f)
        
        # Add metadata
        file_stats = train_summary_path.stat()
        train_summary['file_info'] = {
            'path': str(train_summary_path),
            'size_bytes': file_stats.st_size,
            'modified_timestamp': file_stats.st_mtime,
            'modified_iso': pd.Timestamp.fromtimestamp(file_stats.st_mtime).isoformat()
        }
        
        # Assess training quality
        performance = train_summary.get('performance', {})
        val_accuracy = performance.get('validation_accuracy', 0.0)
        calibration = performance.get('calibration', {})
        post_ece = calibration.get('post_calibration_ece', 1.0)
        
        # Determine quality assessment
        quality_assessment = "unknown"
        quality_details = []
        
        if val_accuracy >= 0.95:
            quality_assessment = "excellent"
            quality_details.append("Validation accuracy >= 95%")
        elif val_accuracy >= 0.90:
            quality_assessment = "good"
            quality_details.append("Validation accuracy >= 90%")
        elif val_accuracy >= 0.80:
            quality_assessment = "acceptable"
            quality_details.append("Validation accuracy >= 80%")
        else:
            quality_assessment = "poor"
            quality_details.append(f"Validation accuracy only {val_accuracy:.1%}")
        
        if post_ece <= 0.05:
            quality_details.append("Well-calibrated confidence (ECE <= 5%)")
        elif post_ece <= 0.10:
            quality_details.append("Moderately calibrated confidence (ECE <= 10%)")
        else:
            quality_details.append(f"Poorly calibrated confidence (ECE {post_ece:.1%})")
        
        train_summary['quality_assessment'] = {
            'overall_grade': quality_assessment,
            'details': quality_details,
            'ready_for_production': quality_assessment in ["excellent", "good", "acceptable"] and post_ece <= 0.10
        }
        
        # Add operational recommendations
        recommendations = []
        if val_accuracy < 0.85:
            recommendations.append("Consider collecting more training data or reviewing data quality")
        if post_ece > 0.10:
            recommendations.append("Model confidence may be miscalibrated - review confidence thresholds")
        
        dataset = train_summary.get('dataset', {})
        total_samples = dataset.get('total_samples', 0)
        if total_samples < 100:
            recommendations.append("Small dataset detected - consider generating more episodes")
        
        label_dist = dataset.get('label_distribution', {})
        if label_dist and min(label_dist.values()) / max(label_dist.values()) < 0.3:
            recommendations.append("Label imbalance detected - ensure balanced training data")
        
        train_summary['recommendations'] = recommendations
        
        return {
            "status": "success",
            "training_summary": train_summary,
            "message": f"Training summary loaded from {train_summary_path.name}"
        }
        
    except json.JSONDecodeError as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "train_summary_json_error",
            "error": str(e),
            "success": False
        })
        raise HTTPException(
            status_code=500,
            detail=f"Training summary file corrupted: {str(e)}"
        )
    except Exception as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "train_summary_error",
            "error": str(e),
            "success": False
        })
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get training summary: {str(e)}"
        )


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Comprehensive health check endpoint for TinyIntent components.
    M7.3: Generation Resilience
    
    Checks health of:
    - Bridge API server (always healthy if responding)
    - Ollama generation service
    - Swift router runner (if available)
    - Circuit breaker states
    - Generation task manager
    
    Returns HTTP 200 for healthy, 503 for unhealthy with details.
    
    Example usage:
    curl http://localhost:8787/health
    """
    
    health_status = {
        "service": "tinyintent-bridge",
        "version": "2.0",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
        "status": "healthy",
        "components": {}
    }
    
    overall_healthy = True
    
    # 1. Bridge API health (always healthy if we can respond)
    health_status["components"]["bridge"] = {
        "status": "healthy",
        "message": "Bridge API responding normally",
        "uptime_seconds": int(time.time() - startup_time),
        "emergency_kill_active": not emergency_kill.is_execution_enabled()
    }
    
    # 2. Ollama health check
    try:
        start_time = time.time()
        response = await async_ollama_client.client.get(
            f"{async_ollama_client.ollama_host}/api/tags",
            timeout=5.0
        )
        ollama_latency = int((time.time() - start_time) * 1000)
        
        if response.status_code == 200:
            models_data = response.json()
            available_models = [model["name"] for model in models_data.get("models", [])]
            
            health_status["components"]["ollama"] = {
                "status": "healthy",
                "message": f"Ollama responding with {len(available_models)} models",
                "latency_ms": ollama_latency,
                "host": async_ollama_client.ollama_host,
                "available_models": available_models[:5],  # Limit to first 5
                "total_models": len(available_models)
            }
        else:
            raise Exception(f"Ollama returned status {response.status_code}")
            
    except Exception as e:
        overall_healthy = False
        health_status["components"]["ollama"] = {
            "status": "unhealthy",
            "message": f"Ollama health check failed: {str(e)[:200]}",
            "host": async_ollama_client.ollama_host,
            "error": str(e)
        }
    
    # 3. Swift router runner health check
    try:
        if router.router_available:
            start_time = time.time()
            # Test router with simple input
            test_result = router.route_request("test health check", skip_metrics=True)
            router_latency = int((time.time() - start_time) * 1000)
            
            health_status["components"]["router"] = {
                "status": "healthy",
                "message": "Swift router responding normally",
                "latency_ms": router_latency,
                "path": str(router.router_path),
                "test_confidence": test_result.get("confidence", 0.0)
            }
        else:
            health_status["components"]["router"] = {
                "status": "degraded",
                "message": "Swift router not available, using fallback routing",
                "path": str(router.router_path) if router.router_path else "not_configured",
                "fallback_active": True
            }
    except Exception as e:
        health_status["components"]["router"] = {
            "status": "unhealthy", 
            "message": f"Router health check failed: {str(e)[:200]}",
            "path": str(router.router_path) if router.router_path else "not_configured",
            "error": str(e)
        }
    
    # 4. Circuit breaker health
    circuit_breaker_stats = generation_circuit_breaker.get_stats()
    open_models = [model for model, state in circuit_breaker_stats["model_states"].items() 
                   if state["state"] == "open"]
    
    health_status["components"]["circuit_breaker"] = {
        "status": "degraded" if open_models else "healthy",
        "message": f"{len(open_models)} model(s) with open circuit breakers" if open_models else "All circuits healthy",
        "total_models": len(circuit_breaker_stats["model_states"]),
        "open_circuits": open_models,
        "config": {
            "failure_threshold": circuit_breaker_stats["failure_threshold"],
            "fail_window_seconds": circuit_breaker_stats["fail_window_seconds"],
            "cooldown_seconds": circuit_breaker_stats["cooldown_seconds"]
        }
    }
    
    if open_models:
        overall_healthy = False
    
    # 5. Generation task manager health
    task_stats = generation_task_manager.get_stats()
    health_status["components"]["task_manager"] = {
        "status": "healthy",
        "message": f"{task_stats['active_tasks']} active generation tasks",
        "active_tasks": task_stats["active_tasks"],
        "total_registered": task_stats["total_registered"],
        "total_cancelled": task_stats["total_cancelled"]
    }
    
    # Set overall status
    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    
    # Return appropriate HTTP status code
    if overall_healthy:
        return health_status
    else:
        raise HTTPException(
            status_code=503,
            detail=health_status
        )


class GenerationCancelRequest(BaseModel):
    """Request model for generation cancellation endpoint."""
    request_id: str
    reason: Optional[str] = "Manual cancellation requested"
    
    @validator('request_id')
    def request_id_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('request_id field cannot be empty')
        return v.strip()


@app.post("/gen/cancel")
async def cancel_generation(
    request: GenerationCancelRequest,
    auth: bool = Depends(verify_auth)
) -> Dict[str, Any]:
    """
    Cancel an in-flight generation request.
    M7.3: Generation Resilience
    
    Cancels the generation task associated with the provided request_id.
    The cancelled task will receive an asyncio.CancelledError and return
    HTTP 499 to the original caller.
    
    Example usage:
    curl -X POST "http://localhost:8787/gen/cancel" \\
      -H "Content-Type: application/json" \\
      -H "X-TinyIntent-Secret: your_secret" \\
      -d '{"request_id": "abc123-def456", "reason": "User cancelled request"}'
    """
    
    try:
        # Attempt to cancel the task
        cancel_result = generation_task_manager.cancel_task(request.request_id, request.reason)
        
        if cancel_result["success"]:
            return {
                "status": "cancelled",
                "message": f"Successfully cancelled generation task {request.request_id}",
                "request_id": request.request_id,
                "reason": request.reason,
                "task_info": {
                    "model": cancel_result.get("model"),
                    "session_id": cancel_result.get("session_id"),
                    "registered_at": cancel_result.get("registered_at"),
                    "cancelled_at": cancel_result.get("cancelled_at")
                }
            }
        else:
            # Task not found or already completed
            return {
                "status": "not_found",
                "message": f"Generation task {request.request_id} not found or already completed",
                "request_id": request.request_id,
                "reason": cancel_result.get("reason", "Task not active")
            }
            
    except Exception as e:
        audit_logger.log_entry({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
            "action": "generation_cancel_error",
            "request_id": request.request_id,
            "error": str(e),
            "success": False
        })
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel generation: {str(e)}"
        )


class EmergencyKillRequest(BaseModel):
    """Request model for emergency kill endpoint."""
    reason: Optional[str] = "Manual emergency kill triggered"
    
    @validator('reason')
    def reason_must_not_be_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('reason field cannot be empty')
        return v.strip()


@app.post("/emergency/kill")
async def emergency_kill_switch(
    request: EmergencyKillRequest,
    fastapi_request: Request,
    auth: bool = Depends(verify_auth)
) -> Dict[str, Any]:
    """
    Emergency kill switch - immediately disables all execute actions.
    M6.3: Emergency Kill Switch Flow
    
    This is a fail-safe mechanism that:
    - Immediately disables all helper execution
    - Persists the disabled state to a flag file
    - Requires manual file removal to re-enable execution
    - Logs the emergency event for audit purposes
    
    Example usage:
    curl -X POST "http://localhost:8787/emergency/kill" \\
      -H "Content-Type: application/json" \\
      -H "X-TinyIntent-Secret: your_secret" \\
      -d '{"reason": "Runaway helper detected"}'
    """
    
    # Get client info for audit trail
    client_ip = fastapi_request.client.host if fastapi_request.client else "unknown"
    user_agent = fastapi_request.headers.get("User-Agent", "unknown")
    triggered_by = f"{client_ip} ({user_agent})"
    
    try:
        # Trigger emergency kill
        success = emergency_kill.trigger_emergency_kill(
            reason=request.reason,
            triggered_by=triggered_by
        )
        
        if success:
            return {
                "status": "emergency_kill_activated",
                "message": "Emergency kill switch activated - all execution disabled",
                "reason": request.reason,
                "triggered_by": triggered_by,
                "flag_file": str(emergency_flag_path),
                "recovery_instructions": f"To re-enable execution, manually remove: {emergency_flag_path}"
            }
        else:
            return {
                "status": "already_disabled",
                "message": "Execution already disabled",
                "current_status": emergency_kill.get_status()
            }
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger emergency kill: {str(e)}"
        )


@app.get("/emergency/status")
async def emergency_status(auth: bool = Depends(verify_auth)) -> Dict[str, Any]:
    """Get current emergency kill switch status. M6.3"""
    try:
        status = emergency_kill.get_status()
        status["recovery_instructions"] = (
            f"To re-enable execution, manually remove: {emergency_flag_path}"
            if not status["execution_enabled"] and status["flag_file_exists"]
            else "Execution control via EXECUTION_ENABLED environment variable"
        )
        return status
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get emergency status: {str(e)}"
        )


# Async client cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    """Clean up async resources on shutdown."""
    await async_ollama_client.close()


if __name__ == "__main__":
    # Get configuration from environment
    bind_addr = os.getenv("TINYINTENT_BIND", "0.0.0.0")
    port = int(os.getenv("TINYINTENT_PORT", "8787"))
    
    # Ensure TINYINTENT_SECRET is set
    if not os.getenv("TINYINTENT_SECRET"):
        print("ERROR: TINYINTENT_SECRET environment variable is required")
        exit(1)
    
    # Start the server
    uvicorn.run(
        "tinyrpc:app",
        host=bind_addr,
        port=port,
        reload=False,
        log_level="info"
    )