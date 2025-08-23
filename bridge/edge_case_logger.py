"""
TinyIntent Edge Case Logger

Real-time logging system for router misclassifications and edge cases.
Captures low-confidence predictions, fallback scenarios, and voice command patterns
for systematic improvement of the SmallIntent router.
"""

import asyncio
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import structlog

logger = structlog.get_logger("edge_case_logger")


class EdgeCaseLogger:
    """
    Logs router edge cases and misclassifications for continuous improvement.
    
    Integrates with existing router_episodes table and adds edge case specific
    analysis capabilities.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize edge case logger with database path."""
        if db_path is None:
            # Use existing episodes database
            self.db_path = Path(__file__).parent.parent / "data" / "episodes" / "router_decisions.db"
        else:
            self.db_path = Path(db_path)
        
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Thread-safe database access
        self._lock = threading.Lock()
        self._init_database()
        
        # Configuration
        self.edge_case_confidence_threshold = 0.7
        self.low_confidence_threshold = 0.5
        self.fallback_indicators = ["fallback", "abstain", "unknown"]
        
        logger.info("EdgeCaseLogger initialized", db_path=str(self.db_path))
    
    def _init_database(self):
        """Initialize the edge case database with required tables."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Main edge cases table - extends router_episodes concept
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS edge_cases (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        text TEXT NOT NULL,
                        text_hash TEXT NOT NULL,
                        predicted_route TEXT NOT NULL,
                        predicted_confidence REAL NOT NULL,
                        predicted_intent TEXT,
                        actual_route TEXT,
                        actual_confidence REAL,
                        fallback_reason TEXT,
                        is_edge_case BOOLEAN DEFAULT TRUE,
                        edge_case_type TEXT,
                        context_source TEXT,
                        context_metadata TEXT,
                        user_correction BOOLEAN DEFAULT FALSE,
                        correction_route TEXT,
                        voice_command BOOLEAN DEFAULT FALSE,
                        shortcut_session BOOLEAN DEFAULT FALSE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Edge case patterns table for clustering analysis
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS edge_case_patterns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pattern_hash TEXT UNIQUE NOT NULL,
                        pattern_type TEXT NOT NULL,
                        representative_text TEXT NOT NULL,
                        sample_count INTEGER DEFAULT 1,
                        avg_confidence REAL,
                        most_common_route TEXT,
                        most_common_intent TEXT,
                        first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                        last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                        resolved BOOLEAN DEFAULT FALSE,
                        resolution_notes TEXT
                    )
                """)
                
                # Performance tracking
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS edge_case_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        date TEXT NOT NULL,
                        total_predictions INTEGER DEFAULT 0,
                        edge_case_count INTEGER DEFAULT 0,
                        low_confidence_count INTEGER DEFAULT 0,
                        fallback_count INTEGER DEFAULT 0,
                        user_corrections INTEGER DEFAULT 0,
                        avg_confidence REAL,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create indexes for efficient querying
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_timestamp ON edge_cases(timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_session ON edge_cases(session_id)",
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_confidence ON edge_cases(predicted_confidence)",
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_route ON edge_cases(predicted_route)",
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_type ON edge_cases(edge_case_type)",
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_source ON edge_cases(context_source)",
                    "CREATE INDEX IF NOT EXISTS idx_edge_cases_hash ON edge_cases(text_hash)",
                    "CREATE INDEX IF NOT EXISTS idx_patterns_type ON edge_case_patterns(pattern_type)",
                    "CREATE INDEX IF NOT EXISTS idx_patterns_resolved ON edge_case_patterns(resolved)",
                    "CREATE INDEX IF NOT EXISTS idx_metrics_date ON edge_case_metrics(date)"
                ]
                
                for index_sql in indexes:
                    conn.execute(index_sql)
                
                conn.commit()
    
    def log_router_decision(
        self,
        text: str,
        session_id: str,
        predicted_route: str,
        predicted_confidence: float,
        predicted_intent: Optional[str] = None,
        actual_route: Optional[str] = None,
        actual_confidence: Optional[float] = None,
        fallback_reason: Optional[str] = None,
        context_source: str = "router",
        context_metadata: Optional[Dict[str, Any]] = None,
        voice_command: bool = False,
        shortcut_session: bool = False
    ) -> bool:
        """
        Log a router decision and determine if it's an edge case.
        
        Args:
            text: Input text that was routed
            session_id: Session identifier
            predicted_route: Route predicted by router (gen/act/fallback)
            predicted_confidence: Confidence score for prediction
            predicted_intent: Intent classification
            actual_route: Actual route used (if different from predicted)
            actual_confidence: Actual confidence used
            fallback_reason: Reason for fallback if applicable
            context_source: Source context (router, shortcut, api)
            context_metadata: Additional context data
            voice_command: Whether this was a voice command
            shortcut_session: Whether this was from iPhone Shortcut
            
        Returns:
            True if logged as edge case, False otherwise
        """
        try:
            # Calculate text hash for deduplication
            text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]
            
            # Determine if this is an edge case
            is_edge_case, edge_case_type = self._classify_edge_case(
                predicted_route, predicted_confidence, actual_route, fallback_reason
            )
            
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Prepare context metadata
            metadata_json = json.dumps(context_metadata or {})
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Insert edge case record
                    conn.execute("""
                        INSERT INTO edge_cases (
                            timestamp, session_id, text, text_hash, predicted_route,
                            predicted_confidence, predicted_intent, actual_route,
                            actual_confidence, fallback_reason, is_edge_case,
                            edge_case_type, context_source, context_metadata,
                            voice_command, shortcut_session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        timestamp, session_id, text, text_hash, predicted_route,
                        predicted_confidence, predicted_intent, actual_route,
                        actual_confidence, fallback_reason, is_edge_case,
                        edge_case_type, context_source, metadata_json,
                        voice_command, shortcut_session
                    ))
                    
                    # Update pattern tracking if edge case
                    if is_edge_case:
                        self._update_pattern_tracking(conn, text, text_hash, edge_case_type, 
                                                   predicted_route, predicted_confidence, predicted_intent)
                    
                    conn.commit()
            
            if is_edge_case:
                logger.info(
                    "Edge case logged",
                    text=text[:50] + "..." if len(text) > 50 else text,
                    type=edge_case_type,
                    confidence=predicted_confidence,
                    route=predicted_route,
                    source=context_source
                )
            
            return is_edge_case
            
        except Exception as e:
            logger.error("Failed to log router decision", error=str(e), text=text[:50])
            return False
    
    async def log_router_decision_async(self, *args, **kwargs) -> bool:
        """Async wrapper for log_router_decision."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.log_router_decision, *args, **kwargs)
    
    def log_user_correction(
        self,
        text_hash: str,
        correction_route: str,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Log a user correction for a previously recorded edge case.
        
        Args:
            text_hash: Hash of the original text
            correction_route: Corrected route (gen/act)
            session_id: Session identifier for context
            
        Returns:
            True if correction was logged successfully
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Update the edge case record
                    result = conn.execute("""
                        UPDATE edge_cases 
                        SET user_correction = TRUE, correction_route = ?
                        WHERE text_hash = ? AND session_id = COALESCE(?, session_id)
                    """, (correction_route, text_hash, session_id))
                    
                    if result.rowcount > 0:
                        conn.commit()
                        logger.info("User correction logged", text_hash=text_hash, correction=correction_route)
                        return True
                    else:
                        logger.warning("No matching edge case found for correction", text_hash=text_hash)
                        return False
                        
        except Exception as e:
            logger.error("Failed to log user correction", error=str(e), text_hash=text_hash)
            return False
    
    def _classify_edge_case(
        self, 
        predicted_route: str, 
        predicted_confidence: float,
        actual_route: Optional[str] = None,
        fallback_reason: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Classify whether a router decision represents an edge case.
        
        Returns:
            (is_edge_case, edge_case_type)
        """
        # Low confidence predictions are edge cases
        if predicted_confidence < self.edge_case_confidence_threshold:
            if predicted_confidence < self.low_confidence_threshold:
                return True, "very_low_confidence"
            else:
                return True, "low_confidence"
        
        # Fallback scenarios are edge cases
        if (predicted_route in self.fallback_indicators or 
            fallback_reason or
            any(indicator in predicted_route.lower() for indicator in self.fallback_indicators)):
            return True, "fallback"
        
        # Route override scenarios (predicted != actual)
        if actual_route and actual_route != predicted_route:
            return True, "route_override"
        
        # High confidence but potentially wrong (need user feedback to confirm)
        if predicted_confidence > 0.9:
            return False, None  # Not an edge case unless we get user correction
        
        return False, None
    
    def _update_pattern_tracking(
        self,
        conn: sqlite3.Connection,
        text: str,
        text_hash: str,
        edge_case_type: str,
        route: str,
        confidence: float,
        intent: Optional[str]
    ):
        """Update pattern tracking for clustering analysis."""
        # Create pattern hash based on text characteristics
        pattern_key = self._create_pattern_key(text, edge_case_type)
        pattern_hash = hashlib.sha256(pattern_key.encode('utf-8')).hexdigest()[:16]
        
        # Update or insert pattern record
        conn.execute("""
            INSERT INTO edge_case_patterns (
                pattern_hash, pattern_type, representative_text, sample_count,
                avg_confidence, most_common_route, most_common_intent, last_seen
            ) VALUES (?, ?, ?, 1, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pattern_hash) DO UPDATE SET
                sample_count = sample_count + 1,
                avg_confidence = (avg_confidence * (sample_count - 1) + ?) / sample_count,
                last_seen = CURRENT_TIMESTAMP
        """, (pattern_hash, edge_case_type, text[:100], confidence, route, intent, confidence))
    
    def _create_pattern_key(self, text: str, edge_case_type: str) -> str:
        """Create a pattern key for clustering similar edge cases."""
        # Normalize text for pattern matching
        normalized = text.lower().strip()
        
        # Extract key features for pattern matching
        features = []
        
        # Question vs command indicators
        question_words = ["what", "how", "when", "where", "why", "who", "which", "can", "do", "does", "is", "are"]
        command_words = ["show", "get", "close", "stop", "start", "run", "execute", "check", "monitor"]
        
        starts_with_question = any(normalized.startswith(qw) for qw in question_words)
        contains_command = any(cw in normalized for cw in command_words)
        
        features.append(f"question_start:{starts_with_question}")
        features.append(f"contains_command:{contains_command}")
        features.append(f"type:{edge_case_type}")
        features.append(f"length_bucket:{len(text) // 20}")  # Group by rough length
        
        return "|".join(features)
    
    def get_edge_case_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get edge case statistics for the last N hours."""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            cutoff_str = cutoff_time.isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                # Basic stats
                stats = conn.execute("""
                    SELECT 
                        COUNT(*) as total_decisions,
                        SUM(CASE WHEN is_edge_case THEN 1 ELSE 0 END) as edge_case_count,
                        SUM(CASE WHEN predicted_confidence < ? THEN 1 ELSE 0 END) as low_confidence_count,
                        SUM(CASE WHEN user_correction THEN 1 ELSE 0 END) as correction_count,
                        AVG(predicted_confidence) as avg_confidence,
                        SUM(CASE WHEN voice_command THEN 1 ELSE 0 END) as voice_command_count,
                        SUM(CASE WHEN shortcut_session THEN 1 ELSE 0 END) as shortcut_session_count
                    FROM edge_cases
                    WHERE timestamp >= ?
                """, (self.edge_case_confidence_threshold, cutoff_str)).fetchone()
                
                # Edge case types breakdown
                types = conn.execute("""
                    SELECT edge_case_type, COUNT(*) as count
                    FROM edge_cases
                    WHERE timestamp >= ? AND is_edge_case = TRUE
                    GROUP BY edge_case_type
                    ORDER BY count DESC
                """, (cutoff_str,)).fetchall()
                
                # Top patterns
                patterns = conn.execute("""
                    SELECT pattern_type, representative_text, sample_count, avg_confidence
                    FROM edge_case_patterns
                    WHERE last_seen >= ? AND resolved = FALSE
                    ORDER BY sample_count DESC
                    LIMIT 10
                """, (cutoff_str,)).fetchall()
                
                return {
                    "window_hours": hours,
                    "total_decisions": stats["total_decisions"],
                    "edge_case_count": stats["edge_case_count"],
                    "edge_case_rate": stats["edge_case_count"] / max(stats["total_decisions"], 1),
                    "low_confidence_count": stats["low_confidence_count"],
                    "correction_count": stats["correction_count"],
                    "avg_confidence": round(stats["avg_confidence"] or 0, 3),
                    "voice_command_count": stats["voice_command_count"],
                    "shortcut_session_count": stats["shortcut_session_count"],
                    "edge_case_types": [dict(row) for row in types],
                    "top_patterns": [dict(row) for row in patterns]
                }
                
        except Exception as e:
            logger.error("Failed to get edge case stats", error=str(e))
            return {"error": str(e)}
    
    def get_recent_edge_cases(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get the most recent edge cases for manual review."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                cases = conn.execute("""
                    SELECT 
                        timestamp, session_id, text, predicted_route, predicted_confidence,
                        predicted_intent, edge_case_type, context_source, voice_command,
                        shortcut_session, user_correction, correction_route
                    FROM edge_cases
                    WHERE is_edge_case = TRUE
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                
                return [dict(case) for case in cases]
                
        except Exception as e:
            logger.error("Failed to get recent edge cases", error=str(e))
            return []


# Global instance for use across the application
edge_case_logger = EdgeCaseLogger()


# Async logging functions for non-blocking integration
async def log_router_decision_async(*args, **kwargs) -> bool:
    """Async wrapper for logging router decisions."""
    return await edge_case_logger.log_router_decision_async(*args, **kwargs)


def log_router_decision(*args, **kwargs) -> bool:
    """Synchronous wrapper for logging router decisions."""
    return edge_case_logger.log_router_decision(*args, **kwargs)


def log_user_correction(*args, **kwargs) -> bool:
    """Log user correction for an edge case."""
    return edge_case_logger.log_user_correction(*args, **kwargs)


def get_edge_case_stats(hours: int = 24) -> Dict[str, Any]:
    """Get edge case statistics."""
    return edge_case_logger.get_edge_case_stats(hours)


def get_recent_edge_cases(limit: int = 20) -> List[Dict[str, Any]]:
    """Get recent edge cases for review."""
    return edge_case_logger.get_recent_edge_cases(limit)