"""
M10.7: Agent Quotas & Cost Guardrails

Manages per-agent usage quotas and budgets to keep self-replicating agents safe and affordable.
Implements rolling counters for preview/execute requests and daily budget tracking.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, Tuple, Any
from collections import defaultdict, deque
import threading


class AgentQuotaManager:
    """
    M10.7: Manages per-agent usage quotas and budgets for cost guardrails.
    
    Implements rolling counters for preview/execute requests and daily budget tracking.
    Thread-safe implementation with automatic cleanup.
    """
    
    def __init__(self):
        self.lock = threading.RLock()
        
        # Environment defaults
        self.default_preview_per_min = int(os.environ.get("AGENT_MAX_PREVIEW_PER_MIN", 60))
        self.default_exec_per_min = int(os.environ.get("AGENT_MAX_EXEC_PER_MIN", 10))
        self.default_daily_exec_budget = int(os.environ.get("AGENT_DAILY_EXEC_BUDGET", 200))
        
        # Rolling counters (1-minute windows)
        self.preview_counters: Dict[str, deque] = defaultdict(deque)  # helper_id -> timestamps
        self.exec_counters: Dict[str, deque] = defaultdict(deque)     # helper_id -> timestamps
        
        # Daily counters (reset at midnight local time)
        self.daily_exec_counters: Dict[str, Dict[str, int]] = defaultdict(dict)  # helper_id -> {date: count}
        
        # Last cleanup time
        self.last_cleanup = time.time()
        
        # Load daily counters from persistent storage on startup
        self._load_daily_counters_from_storage()
    
    def _cleanup_old_entries(self):
        """Clean up old rolling counter entries (older than 1 minute)."""
        current_time = time.time()
        cutoff_time = current_time - 60  # 1 minute ago
        
        # Clean preview counters
        for helper_id in list(self.preview_counters.keys()):
            counter = self.preview_counters[helper_id]
            while counter and counter[0] < cutoff_time:
                counter.popleft()
            # Remove empty counters
            if not counter:
                del self.preview_counters[helper_id]
        
        # Clean execute counters
        for helper_id in list(self.exec_counters.keys()):
            counter = self.exec_counters[helper_id]
            while counter and counter[0] < cutoff_time:
                counter.popleft()
            # Remove empty counters
            if not counter:
                del self.exec_counters[helper_id]
        
        # Clean old daily counters (keep last 7 days)
        today = datetime.now().strftime("%Y-%m-%d")
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        for helper_id in list(self.daily_exec_counters.keys()):
            dates_to_remove = []
            for date in self.daily_exec_counters[helper_id]:
                if date < cutoff_date:
                    dates_to_remove.append(date)
            
            for date in dates_to_remove:
                del self.daily_exec_counters[helper_id][date]
            
            # Remove empty helper entries
            if not self.daily_exec_counters[helper_id]:
                del self.daily_exec_counters[helper_id]
        
        self.last_cleanup = current_time
    
    def _load_daily_counters_from_storage(self):
        """Load daily counters from persistent storage."""
        try:
            from tinyintent.data.episodes.episodes import agent_staging_storage
            
            # Load current day's counters for all helpers
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Get all unique helper_ids from persistent storage
            # We'll do this by querying for today's counters
            with self.lock:
                # Since we don't know all helper IDs, we'll load them as needed
                # For now, just ensure the structure is ready
                pass
                
        except Exception:
            # Fail gracefully if persistent storage is unavailable
            pass
    
    def _get_helper_limits(self, helper_id: str) -> Dict[str, int]:
        """Get quota limits for a helper, with fallbacks to environment defaults."""
        # Import here to avoid circular dependency
        from tinyintent.helpers.sdk import helper_registry
        
        limits = helper_registry.get_helper_quota_limits(helper_id)
        if limits:
            return limits
        
        # Fallback to environment defaults
        return {
            "preview_per_min": self.default_preview_per_min,
            "exec_per_min": self.default_exec_per_min,
            "daily_exec_budget": self.default_daily_exec_budget
        }
    
    def check_preview_quota(self, helper_id: str) -> Tuple[bool, int]:
        """
        Check if preview request is within quota.
        
        Returns:
            Tuple[bool, int]: (allowed, retry_after_seconds)
        """
        with self.lock:
            # Periodic cleanup
            if time.time() - self.last_cleanup > 60:  # Every minute
                self._cleanup_old_entries()
            
            limits = self._get_helper_limits(helper_id)
            limit = limits["preview_per_min"]
            
            current_count = len(self.preview_counters[helper_id])
            
            if current_count >= limit:
                return False, 60  # Retry after 1 minute
            
            return True, 0
    
    def check_execute_quota(self, helper_id: str) -> Tuple[bool, int, str]:
        """
        Check if execute request is within quota (both per-minute and daily budget).
        
        Returns:
            Tuple[bool, int, str]: (allowed, retry_after_seconds, reason)
        """
        with self.lock:
            # Periodic cleanup
            if time.time() - self.last_cleanup > 60:  # Every minute
                self._cleanup_old_entries()
            
            limits = self._get_helper_limits(helper_id)
            per_min_limit = limits["exec_per_min"]
            daily_limit = limits["daily_exec_budget"]
            
            # Check per-minute limit
            current_count = len(self.exec_counters[helper_id])
            if current_count >= per_min_limit:
                return False, 60, "exec_per_min_exceeded"
            
            # Check daily budget (with persistent storage fallback)
            today = datetime.now().strftime("%Y-%m-%d")
            daily_count = self.daily_exec_counters[helper_id].get(today, 0)
            
            # Fallback to persistent storage if in-memory counter is 0
            if daily_count == 0:
                try:
                    from tinyintent.data.episodes.episodes import agent_staging_storage
                    persistent_count = agent_staging_storage.get_daily_counter(helper_id, "execute", today)
                    daily_count = max(daily_count, persistent_count)
                    # Update in-memory counter to match persistent storage
                    self.daily_exec_counters[helper_id][today] = daily_count
                except Exception:
                    # Use in-memory value if persistent storage fails
                    pass
            
            if daily_count >= daily_limit:
                # Calculate seconds until midnight
                now = datetime.now()
                midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                retry_after = int((midnight - now).total_seconds())
                return False, retry_after, "daily_exec_budget_exceeded"
            
            return True, 0, ""
    
    def record_preview_request(self, helper_id: str):
        """Record a preview request for quota tracking."""
        with self.lock:
            current_time = time.time()
            self.preview_counters[helper_id].append(current_time)
    
    def record_execute_request(self, helper_id: str):
        """Record an execute request for quota tracking."""
        with self.lock:
            current_time = time.time()
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Record in rolling counter
            self.exec_counters[helper_id].append(current_time)
            
            # Record in daily counter (both in memory and persistent storage)
            if today not in self.daily_exec_counters[helper_id]:
                self.daily_exec_counters[helper_id][today] = 0
            self.daily_exec_counters[helper_id][today] += 1
            
            # Update persistent storage
            try:
                from tinyintent.data.episodes.episodes import agent_staging_storage
                agent_staging_storage.increment_daily_counter(helper_id, "execute", today)
            except Exception:
                # Fail gracefully if persistent storage is unavailable
                pass
    
    def get_quota_status(self, helper_id: str) -> Dict[str, Any]:
        """Get current quota status for a helper."""
        with self.lock:
            limits = self._get_helper_limits(helper_id)
            today = datetime.now().strftime("%Y-%m-%d")
            
            preview_count = len(self.preview_counters[helper_id])
            exec_count = len(self.exec_counters[helper_id])
            daily_exec_count = self.daily_exec_counters[helper_id].get(today, 0)
            
            return {
                "helper_id": helper_id,
                "limits": limits,
                "current_usage": {
                    "preview_per_min": preview_count,
                    "exec_per_min": exec_count,
                    "daily_exec_count": daily_exec_count
                },
                "quota_remaining": {
                    "preview_per_min": max(0, limits["preview_per_min"] - preview_count),
                    "exec_per_min": max(0, limits["exec_per_min"] - exec_count),
                    "daily_exec_budget": max(0, limits["daily_exec_budget"] - daily_exec_count)
                }
            }


# Global quota manager instance
agent_quota_manager = AgentQuotaManager()