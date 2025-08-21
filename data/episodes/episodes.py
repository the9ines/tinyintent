"""
TinyIntent Episode Mining for Agent Evolution

Analyzes episode data to identify patterns where the router abstains
or falls back, suggesting new helpers that could handle these cases.

M10.1: Agent Evolution via Episode Mining
M10.3: Agent Staging - Shadow Execution and Canary Rollout Storage
"""

import json
import math
import sqlite3
import hashlib
import asyncio
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timedelta
import threading
import time

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


class EpisodeMiner:
    """Mines episode data for agent evolution insights."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize episode miner with database path."""
        if db_path is None:
            # Default to events.db in same directory
            self.db_path = Path(__file__).parent / "events.db"
        else:
            self.db_path = Path(db_path)
    
    def mine_abstain_clusters(self, window_hours: int = 24, min_count: int = 8, max_clusters: int = 5) -> List[Dict[str, Any]]:
        """
        Mine abstain/fallback patterns from recent episodes.
        
        Args:
            window_hours: Time window to analyze (hours)
            min_count: Minimum occurrences to form a cluster
            max_clusters: Maximum number of clusters to return
            
        Returns:
            List of cluster dictionaries with representative text and examples
        """
        # Get abstain/fallback events from database
        abstain_events = self._get_abstain_events(window_hours)
        
        if len(abstain_events) < min_count:
            return []
        
        # Extract text for clustering
        texts = [event.get("text", "") for event in abstain_events]
        texts = [text for text in texts if text.strip()]  # Remove empty texts
        
        if len(texts) < min_count:
            return []
        
        # Perform clustering
        clusters = self._cluster_texts(texts, max_clusters)
        
        # Build cluster results with metadata
        results = []
        for i, cluster in enumerate(clusters):
            if len(cluster["indices"]) < min_count:
                continue
            
            # Get representative examples
            examples = [abstain_events[idx] for idx in cluster["indices"][:5]]  # Top 5 examples
            
            cluster_info = {
                "cluster_id": i,
                "representative_text": cluster["representative"],
                "sample_count": len(cluster["indices"]),
                "confidence_score": cluster.get("confidence", 0.0),
                "examples": [
                    {
                        "text": example.get("text", ""),
                        "timestamp": example.get("ts", ""),
                        "route_pred": example.get("route_pred", ""),
                        "route_final": example.get("route_final", ""),
                        "abstain_reason": example.get("abstain_reason", ""),
                        "fallback": example.get("fallback", False)
                    }
                    for example in examples
                ],
                "themes": self._extract_themes(cluster["indices"], abstain_events),
                "suggested_capabilities": self._infer_capabilities_from_cluster(cluster["indices"], abstain_events)
            }
            
            results.append(cluster_info)
        
        # Sort by sample count (most frequent first)
        results.sort(key=lambda x: x["sample_count"], reverse=True)
        
        return results[:max_clusters]
    
    def _get_abstain_events(self, window_hours: int) -> List[Dict[str, Any]]:
        """Get abstain/fallback events from the last N hours."""
        if not self.db_path.exists():
            return []
        
        # Calculate time window
        cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)
        cutoff_str = cutoff_time.isoformat() + 'Z'
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row  # Access columns by name
                
                cursor = conn.execute("""
                    SELECT ts, text, route_pred, route_final, success, 
                           helper_id, helper_input, preview_json, executed,
                           error_code, labels
                    FROM events 
                    WHERE ts >= ? 
                      AND (
                          (route_final = 'fallback') OR
                          (success = 0 AND error_code LIKE '%abstain%') OR
                          (labels LIKE '%abstain%') OR
                          (route_pred != route_final AND route_final = 'gen')
                      )
                    ORDER BY ts DESC
                """, (cutoff_str,))
                
                events = []
                for row in cursor.fetchall():
                    event = dict(row)
                    
                    # Parse JSON fields if present
                    if event.get("helper_input"):
                        try:
                            event["helper_input"] = json.loads(event["helper_input"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    if event.get("preview_json"):
                        try:
                            event["preview_json"] = json.loads(event["preview_json"])
                        except (json.JSONDecodeError, TypeError):
                            pass
                    
                    # Determine abstain reason
                    abstain_reason = "unknown"
                    if event.get("route_final") == "fallback":
                        abstain_reason = "router_fallback"
                    elif event.get("error_code") and "abstain" in event.get("error_code", "").lower():
                        abstain_reason = "explicit_abstain"
                    elif event.get("route_pred") != event.get("route_final"):
                        abstain_reason = "route_override"
                    
                    event["abstain_reason"] = abstain_reason
                    event["fallback"] = event.get("route_final") == "fallback"
                    
                    events.append(event)
                
                return events
                
        except Exception as e:
            print(f"Error querying abstain events: {e}")
            return []
    
    def _cluster_texts(self, texts: List[str], max_clusters: int) -> List[Dict[str, Any]]:
        """Cluster texts using TF-IDF and similarity."""
        if HAS_NUMPY:
            return self._cluster_texts_with_numpy(texts, max_clusters)
        else:
            return self._cluster_texts_simple(texts, max_clusters)
    
    def _cluster_texts_with_numpy(self, texts: List[str], max_clusters: int) -> List[Dict[str, Any]]:
        """Cluster texts using numpy-based TF-IDF and k-means."""
        # Simple TF-IDF implementation
        vectorizer = SimpleTFIDFVectorizer()
        vectors = vectorizer.fit_transform(texts)
        
        # Simple k-means clustering
        num_clusters = min(max_clusters, len(texts) // 2, 10)
        clusters = simple_kmeans(vectors, num_clusters)
        
        # Build cluster results
        results = []
        for cluster_id in range(num_clusters):
            indices = [i for i, c in enumerate(clusters) if c == cluster_id]
            if not indices:
                continue
            
            # Find representative text (closest to centroid)
            cluster_vectors = vectors[indices]
            centroid = np.mean(cluster_vectors, axis=0)
            
            # Find closest text to centroid
            best_idx = indices[0]
            best_distance = float('inf')
            for idx in indices:
                distance = np.linalg.norm(vectors[idx] - centroid)
                if distance < best_distance:
                    best_distance = distance
                    best_idx = idx
            
            # Calculate cluster confidence (inverse of intra-cluster variance)
            if len(indices) > 1:
                distances = [np.linalg.norm(vectors[idx] - centroid) for idx in indices]
                confidence = 1.0 / (1.0 + np.std(distances))
            else:
                confidence = 1.0
            
            results.append({
                "representative": texts[best_idx],
                "indices": indices,
                "confidence": confidence
            })
        
        return results
    
    def _cluster_texts_simple(self, texts: List[str], max_clusters: int) -> List[Dict[str, Any]]:
        """Simple clustering without numpy using keyword frequency."""
        # Extract keywords from all texts
        all_keywords = set()
        text_keywords = []
        
        for text in texts:
            keywords = self._extract_keywords(text)
            text_keywords.append(keywords)
            all_keywords.update(keywords)
        
        # Group texts by shared keywords
        keyword_groups = defaultdict(list)
        for i, keywords in enumerate(text_keywords):
            # Create a signature from top keywords
            signature = tuple(sorted(keywords)[:3])  # Top 3 keywords
            keyword_groups[signature].append(i)
        
        # Convert to clusters
        clusters = []
        for signature, indices in keyword_groups.items():
            if len(indices) >= 2:  # Only clusters with multiple items
                # Find representative text (longest or most keyword-rich)
                best_idx = max(indices, key=lambda i: len(text_keywords[i]))
                
                clusters.append({
                    "representative": texts[best_idx],
                    "indices": indices,
                    "confidence": min(1.0, len(indices) / 5.0)  # Higher confidence for larger clusters
                })
        
        # Sort by cluster size
        clusters.sort(key=lambda x: len(x["indices"]), reverse=True)
        
        return clusters[:max_clusters]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract keywords from text using simple rules."""
        import re
        
        # Convert to lowercase and extract words
        words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
        
        # Filter out common stop words
        stop_words = {
            'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did', 'man', 'oil', 'sit', 'too', 'use', 'way', 'she', 'what', 'with', 'this', 'that', 'they', 'from', 'have', 'been', 'said', 'each', 'find', 'make', 'most', 'part', 'time', 'very', 'were', 'will', 'work', 'call', 'came', 'come', 'down', 'into', 'like', 'look', 'more', 'over', 'people', 'side', 'their', 'want', 'water', 'would', 'write', 'could', 'first', 'other', 'than', 'then', 'there', 'these', 'think', 'where', 'which', 'your'
        }
        
        keywords = [word for word in words if word not in stop_words and len(word) > 3]
        
        # Return most frequent keywords
        counter = Counter(keywords)
        return [word for word, count in counter.most_common(10)]
    
    def _extract_themes(self, indices: List[int], events: List[Dict[str, Any]]) -> List[str]:
        """Extract common themes from a cluster of events."""
        cluster_events = [events[i] for i in indices]
        
        themes = set()
        
        # Look for common patterns
        for event in cluster_events:
            text = event.get("text", "").lower()
            
            # Common action themes
            if any(word in text for word in ["fetch", "get", "retrieve", "download"]):
                themes.add("data_retrieval")
            if any(word in text for word in ["summarize", "summary", "explain"]):
                themes.add("content_analysis")
            if any(word in text for word in ["url", "http", "website", "web"]):
                themes.add("web_interaction")
            if any(word in text for word in ["file", "document", "pdf", "csv"]):
                themes.add("file_processing")
            if any(word in text for word in ["email", "send", "message"]):
                themes.add("communication")
            if any(word in text for word in ["calculate", "compute", "math"]):
                themes.add("computation")
            if any(word in text for word in ["schedule", "calendar", "time", "date"]):
                themes.add("scheduling")
            if any(word in text for word in ["search", "find", "lookup"]):
                themes.add("search")
        
        return list(themes)
    
    def _infer_capabilities_from_cluster(self, indices: List[int], events: List[Dict[str, Any]]) -> List[str]:
        """Infer required capabilities from cluster patterns."""
        cluster_events = [events[i] for i in indices]
        capabilities = set()
        
        for event in cluster_events:
            text = event.get("text", "").lower()
            
            # Network capabilities
            if any(word in text for word in ["url", "http", "website", "web", "api", "fetch", "download"]):
                capabilities.add("network")
            
            # Filesystem capabilities
            if any(word in text for word in ["file", "document", "read", "write", "save", "load", "csv", "pdf"]):
                capabilities.add("filesystem")
            
            # Database capabilities
            if any(word in text for word in ["database", "sql", "query", "table", "record"]):
                capabilities.add("database")
        
        # Always start with minimal capabilities for safety
        return list(capabilities) if capabilities else []


class SimpleTFIDFVectorizer:
    """Simple TF-IDF vectorizer without sklearn dependency."""
    
    def __init__(self):
        self.vocabulary = {}
        self.idf_values = {}
    
    def fit_transform(self, texts: List[str]) -> 'np.ndarray':
        """Fit and transform texts to TF-IDF vectors."""
        # Build vocabulary
        all_words = set()
        documents = []
        
        for text in texts:
            words = self._tokenize(text)
            documents.append(words)
            all_words.update(words)
        
        self.vocabulary = {word: i for i, word in enumerate(sorted(all_words))}
        
        # Calculate IDF values
        n_docs = len(documents)
        for word in self.vocabulary:
            doc_count = sum(1 for doc in documents if word in doc)
            self.idf_values[word] = math.log(n_docs / (doc_count + 1))
        
        # Create TF-IDF matrix
        matrix = np.zeros((len(texts), len(self.vocabulary)))
        
        for doc_idx, words in enumerate(documents):
            word_counts = Counter(words)
            doc_length = len(words)
            
            for word, count in word_counts.items():
                if word in self.vocabulary:
                    tf = count / doc_length
                    idf = self.idf_values[word]
                    word_idx = self.vocabulary[word]
                    matrix[doc_idx, word_idx] = tf * idf
        
        return matrix
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        import re
        words = re.findall(r'\b[a-zA-Z]{2,}\b', text.lower())
        # Filter common stop words
        stop_words = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'who', 'with', 'this', 'that', 'they', 'from', 'have', 'been', 'said', 'what', 'will', 'make', 'time', 'very', 'were', 'more', 'than', 'then', 'there', 'these', 'think', 'where', 'which', 'your'}
        return [word for word in words if word not in stop_words]


def simple_kmeans(X: 'np.ndarray', k: int, max_iters: int = 100) -> List[int]:
    """Simple k-means clustering implementation."""
    n_samples, n_features = X.shape
    
    # Initialize centroids randomly
    centroids = X[np.random.choice(n_samples, k, replace=False)]
    
    for _ in range(max_iters):
        # Assign points to closest centroid
        distances = np.linalg.norm(X[:, np.newaxis] - centroids, axis=2)
        labels = np.argmin(distances, axis=1)
        
        # Update centroids
        new_centroids = np.zeros_like(centroids)
        for i in range(k):
            cluster_points = X[labels == i]
            if len(cluster_points) > 0:
                new_centroids[i] = np.mean(cluster_points, axis=0)
            else:
                new_centroids[i] = centroids[i]
        
        # Check for convergence
        if np.allclose(centroids, new_centroids, rtol=1e-4):
            break
        
        centroids = new_centroids
    
    return labels.tolist()


# Global instance
episode_miner = EpisodeMiner()


class AgentStagingStorage:
    """Storage for agent shadow and canary run data."""
    
    def __init__(self, db_path: Optional[Path] = None):
        """Initialize staging storage with database path."""
        if db_path is None:
            # Default to staging.db in same directory
            self.db_path = Path(__file__).parent / "staging.db"
        else:
            self.db_path = Path(db_path)
        
        self._lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database tables for staging data."""
        with sqlite3.connect(self.db_path) as conn:
            # Agent shadow runs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_shadow_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    helper_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    intent TEXT,
                    latency_ms INTEGER,
                    success BOOLEAN,
                    error_code TEXT,
                    output_bytes INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Agent canary runs table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_canary_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    helper_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    input_hash TEXT NOT NULL,
                    intent TEXT,
                    latency_ms INTEGER,
                    success BOOLEAN,
                    error_code TEXT,
                    output_bytes INTEGER,
                    treatment TEXT NOT NULL,  -- 'control' or 'canary'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Staging configuration table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_staging_config (
                    helper_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,  -- 'shadow', 'canary', 'none'
                    canary_pct REAL DEFAULT 0,
                    match_intent TEXT,
                    enabled BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indices for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_shadow_helper_ts ON agent_shadow_runs(helper_id, ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canary_helper_ts ON agent_canary_runs(helper_id, ts)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_shadow_input_hash ON agent_shadow_runs(input_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_canary_input_hash ON agent_canary_runs(input_hash)")
            
            conn.commit()
    
    def log_shadow_run(self, helper_id: str, session_id: str, helper_input: Dict[str, Any], 
                      intent: Optional[str], latency_ms: int, success: bool, 
                      error_code: Optional[str] = None, output_data: Optional[Dict[str, Any]] = None):
        """Log a shadow run execution."""
        # Calculate input hash for determinism tracking
        input_hash = self._calculate_input_hash(helper_input)
        
        # Calculate output size
        output_bytes = 0
        if output_data:
            try:
                output_bytes = len(json.dumps(output_data).encode('utf-8'))
            except:
                output_bytes = 0
        
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO agent_shadow_runs 
                    (helper_id, session_id, input_hash, intent, latency_ms, success, error_code, output_bytes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (helper_id, session_id, input_hash, intent, latency_ms, success, error_code, output_bytes))
                conn.commit()
    
    def log_canary_run(self, helper_id: str, session_id: str, helper_input: Dict[str, Any],
                      intent: Optional[str], latency_ms: int, success: bool, treatment: str,
                      error_code: Optional[str] = None, output_data: Optional[Dict[str, Any]] = None):
        """Log a canary run execution."""
        # Calculate input hash for determinism tracking
        input_hash = self._calculate_input_hash(helper_input)
        
        # Calculate output size
        output_bytes = 0
        if output_data:
            try:
                output_bytes = len(json.dumps(output_data).encode('utf-8'))
            except:
                output_bytes = 0
        
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO agent_canary_runs 
                    (helper_id, session_id, input_hash, intent, latency_ms, success, error_code, output_bytes, treatment)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (helper_id, session_id, input_hash, intent, latency_ms, success, error_code, output_bytes, treatment))
                conn.commit()
    
    def set_staging_config(self, helper_id: str, mode: str, canary_pct: float = 0.0, 
                          match_intent: Optional[str] = None):
        """Set staging configuration for a helper."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO agent_staging_config 
                    (helper_id, mode, canary_pct, match_intent, enabled, updated_at)
                    VALUES (?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP)
                """, (helper_id, mode, canary_pct, match_intent))
                conn.commit()
    
    def get_staging_config(self, helper_id: str) -> Optional[Dict[str, Any]]:
        """Get staging configuration for a helper."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM agent_staging_config WHERE helper_id = ? AND enabled = TRUE
            """, (helper_id,))
            row = cursor.fetchone()
            
            if row:
                return dict(row)
            return None
    
    def remove_staging_config(self, helper_id: str):
        """Remove staging configuration for a helper."""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM agent_staging_config WHERE helper_id = ?", (helper_id,))
                conn.commit()
    
    def get_staging_metrics(self, helper_id: str, window_hours: int = 24) -> Dict[str, Any]:
        """Get staging metrics for a helper in the given time window."""
        cutoff_time = datetime.now() - timedelta(hours=window_hours)
        cutoff_str = cutoff_time.isoformat()
        
        metrics = {
            "shadow_runs": 0,
            "canary_runs": 0,
            "shadow_success_rate": 0.0,
            "canary_success_rate": 0.0,
            "avg_latency_ms": 0.0,
            "error_rates": {},
            "determinism_score": 1.0,
            "output_size_stats": {},
            "window_hours": window_hours
        }
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            
            # Shadow run metrics
            shadow_cursor = conn.execute("""
                SELECT success, latency_ms, error_code, output_bytes, input_hash
                FROM agent_shadow_runs 
                WHERE helper_id = ? AND ts >= ?
                ORDER BY ts
            """, (helper_id, cutoff_str))
            
            shadow_runs = list(shadow_cursor.fetchall())
            metrics["shadow_runs"] = len(shadow_runs)
            
            if shadow_runs:
                successes = sum(1 for run in shadow_runs if run["success"])
                metrics["shadow_success_rate"] = successes / len(shadow_runs)
                
                latencies = [run["latency_ms"] for run in shadow_runs if run["latency_ms"]]
                if latencies:
                    metrics["avg_latency_ms"] = sum(latencies) / len(latencies)
                
                # Error rate analysis
                error_counts = Counter(run["error_code"] for run in shadow_runs if run["error_code"])
                total_errors = sum(error_counts.values())
                if total_errors > 0:
                    metrics["error_rates"] = {
                        error: count / len(shadow_runs) 
                        for error, count in error_counts.items()
                    }
                
                # Determinism analysis (variance in outputs for same inputs)
                metrics["determinism_score"] = self._calculate_determinism_score(shadow_runs)
                
                # Output size statistics
                output_sizes = [run["output_bytes"] for run in shadow_runs if run["output_bytes"]]
                if output_sizes:
                    metrics["output_size_stats"] = {
                        "min": min(output_sizes),
                        "max": max(output_sizes),
                        "avg": sum(output_sizes) / len(output_sizes)
                    }
            
            # Canary run metrics
            canary_cursor = conn.execute("""
                SELECT success, latency_ms, error_code, output_bytes, treatment
                FROM agent_canary_runs 
                WHERE helper_id = ? AND ts >= ?
                ORDER BY ts
            """, (helper_id, cutoff_str))
            
            canary_runs = list(canary_cursor.fetchall())
            metrics["canary_runs"] = len(canary_runs)
            
            if canary_runs:
                successes = sum(1 for run in canary_runs if run["success"])
                metrics["canary_success_rate"] = successes / len(canary_runs)
        
        return metrics
    
    def _calculate_input_hash(self, helper_input: Dict[str, Any]) -> str:
        """Calculate deterministic hash of helper input."""
        # Create a stable string representation
        stable_str = json.dumps(helper_input, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(stable_str.encode('utf-8')).hexdigest()[:16]
    
    def _calculate_determinism_score(self, runs: List[sqlite3.Row]) -> float:
        """Calculate determinism score based on output variance for same inputs."""
        # Group runs by input hash
        input_groups = defaultdict(list)
        for run in runs:
            input_groups[run["input_hash"]].append(run)
        
        # Calculate variance within each input group
        total_variance = 0.0
        input_count = 0
        
        for input_hash, group_runs in input_groups.items():
            if len(group_runs) > 1:
                # Calculate output size variance
                output_sizes = [run["output_bytes"] or 0 for run in group_runs]
                if len(set(output_sizes)) > 1:  # If outputs differ
                    variance = sum((size - sum(output_sizes) / len(output_sizes)) ** 2 
                                 for size in output_sizes) / len(output_sizes)
                    total_variance += variance
                    input_count += 1
        
        if input_count == 0:
            return 1.0  # Perfect determinism if no repeated inputs
        
        # Convert variance to score (1.0 = perfectly deterministic)
        avg_variance = total_variance / input_count
        return max(0.0, 1.0 - (avg_variance / 10000))  # Scale factor for size variance
    
    async def log_shadow_run_async(self, helper_id: str, session_id: str, helper_input: Dict[str, Any], 
                                   intent: Optional[str], latency_ms: int, success: bool, 
                                   error_code: Optional[str] = None, output_data: Optional[Dict[str, Any]] = None):
        """Async wrapper for shadow run logging."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, 
            self.log_shadow_run, 
            helper_id, session_id, helper_input, intent, latency_ms, success, error_code, output_data
        )
    
    async def log_canary_run_async(self, helper_id: str, session_id: str, helper_input: Dict[str, Any],
                                   intent: Optional[str], latency_ms: int, success: bool, treatment: str,
                                   error_code: Optional[str] = None, output_data: Optional[Dict[str, Any]] = None):
        """Async wrapper for canary run logging.""" 
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.log_canary_run,
            helper_id, session_id, helper_input, intent, latency_ms, success, treatment, error_code, output_data
        )


# Global staging storage instance
agent_staging_storage = AgentStagingStorage()