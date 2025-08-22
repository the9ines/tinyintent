"""
TinyIntent Generation Client

Handles all interactions with the Ollama generation service.
Includes an async client, circuit breaker for resilience, and a task manager
for handling cancellations.
"""

import os
import time
import asyncio
import httpx
import uuid
from enum import Enum
import threading
from collections import deque
from typing import Dict, Any

from fastapi import HTTPException

from tinyintent.bridge.logs.audit import get_audit_logger

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
        self.breakers = {}
        self.lock = threading.Lock()
        
        print(f"Circuit breaker config: window={self.fail_window}s, threshold={self.threshold}, cooldown={self.cooldown}s")
    
    def _get_breaker_state(self, model: str) -> Dict[str, Any]:
        """Get or create breaker state for model."""
        if model not in self.breakers:
            self.breakers[model] = {
                "state": CircuitBreakerState.CLOSED,
                "failures": deque(),
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
            
            cutoff_time = current_time - self.fail_window
            breaker["failures"] = deque(
                timestamp for timestamp in breaker["failures"] 
                if timestamp > cutoff_time
            )
            
            state = breaker["state"]
            failure_count = len(breaker["failures"])
            
            if state == CircuitBreakerState.CLOSED:
                if failure_count >= self.threshold:
                    breaker["state"] = CircuitBreakerState.OPEN
                    breaker["state_changed_at"] = current_time
                    self._log_circuit_event(model, "open", failure_count)
                    return False, "gen_circuit_open", self._get_breaker_info(model, breaker)
                
                return True, "closed", self._get_breaker_info(model, breaker)
            
            elif state == CircuitBreakerState.OPEN:
                if current_time - breaker["state_changed_at"] >= self.cooldown:
                    breaker["state"] = CircuitBreakerState.HALF_OPEN
                    breaker["state_changed_at"] = current_time
                    self._log_circuit_event(model, "half_open", failure_count)
                    return True, "half_open", self._get_breaker_info(model, breaker)
                
                return False, "gen_circuit_open", self._get_breaker_info(model, breaker)
            
            elif state == CircuitBreakerState.HALF_OPEN:
                return True, "half_open", self._get_breaker_info(model, breaker)
    
    def record_success(self, model: str, session_id: str = ""):
        """Record successful generation call."""
        with self.lock:
            breaker = self._get_breaker_state(model)
            breaker["total_requests"] += 1
            breaker["last_success_time"] = time.time()
            
            if breaker["state"] == CircuitBreakerState.HALF_OPEN:
                old_state = breaker["state"]
                breaker["state"] = CircuitBreakerState.CLOSED
                breaker["state_changed_at"] = time.time()
                breaker["failures"].clear()
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
            
            if breaker["state"] == CircuitBreakerState.HALF_OPEN:
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
        audit_logger = get_audit_logger()
        if audit_logger:
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

class GenerationTaskManager:
    """Manages in-flight generation tasks for cancellation support."""
    
    def __init__(self):
        self.active_tasks = {}
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
            
            cancelled = task.cancel()
            
            if cancelled:
                audit_logger = get_audit_logger()
                if audit_logger:
                    audit_logger.log_entry({
                        "ts": time.strftime("%Y-%m-%dT%H:%M:%S.000000Z", time.gmtime()),
                        "action": "gen_cancel",
                        "request_id": request_id,
                        "model": model,
                        "session_id": task_info["session_id"],
                        "duration_s": round(duration, 2),
                        "success": True
                    })
                
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

class AsyncOllamaClient:
    """Async client for Ollama generation with timeouts, retries, and concurrency control."""
    
    def __init__(self, circuit_breaker: GenerationCircuitBreaker, task_manager: GenerationTaskManager):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.gen_timeout = int(os.getenv("GEN_TIMEOUT_S", "20"))
        self.max_retries = int(os.getenv("GEN_MAX_RETRIES", "2"))
        self.backoff_ms = int(os.getenv("GEN_BACKOFF_MS", "200"))
        self.concurrency_limit = int(os.getenv("GEN_CONCURRENCY", "4"))
        self._semaphore = None
        self.circuit_breaker = circuit_breaker
        self.task_manager = task_manager
        
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.gen_timeout),
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
        )
    
    async def generate_async(self, model: str, prompt: str, request_id: str = None, session_id: str = "") -> tuple[str, int]:
        """
        Generate text asynchronously with retries, backpressure control, and circuit breaker.
        """
        can_execute, reason, breaker_info = self.circuit_breaker.can_execute(model)
        if not can_execute:
            raise HTTPException(
                status_code=503,
                detail=f"Generation circuit breaker open for model {model}: {reason}",
                headers={"error_code": "gen_circuit_open", "retry_after": str(int(breaker_info.get("cooldown_remaining", 30)))}
            )
        
        if request_id is None:
            request_id = str(uuid.uuid4())
        
        current_task = asyncio.current_task()
        self.task_manager.register_task(request_id, current_task, model, session_id)
        
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.concurrency_limit)
        
        try:
            async with self._semaphore:
                start_time = time.time()
                last_exception = None
                
                for attempt in range(self.max_retries + 1):
                    try:
                        if current_task.cancelled():
                            raise asyncio.CancelledError("Generation request was cancelled")
                        
                        if attempt > 0:
                            delay = (self.backoff_ms / 1000.0) * (2 ** (attempt - 1))
                            await asyncio.sleep(delay)
                        
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
                            
                            self.circuit_breaker.record_success(model, session_id)
                            
                            return generated_text, latency_ms
                        else:
                            raise httpx.HTTPStatusError(
                                f"Ollama API error: {response.status_code}",
                                request=response.request,
                                response=response
                            )
                            
                    except asyncio.CancelledError:
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
                            self.circuit_breaker.record_failure(model, "http_error", session_id)
                            raise HTTPException(
                                status_code=504,
                                detail="Generation request timed out or failed after retries",
                                headers={"error_code": "GENERATION_TIMEOUT"}
                            )
        finally:
            self.task_manager.unregister_task(request_id)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
