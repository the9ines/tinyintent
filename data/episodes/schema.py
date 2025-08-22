"""
TinyIntent Episodes Database Schema

Defines the table creation statements for the episodes and router metrics database.
"""

EPISODES_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    action TEXT NOT NULL,
    helper_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    approval_token_id TEXT,
    idempotency_key TEXT,
    status_code INTEGER NOT NULL,
    success BOOLEAN NOT NULL,
    error_code TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

ROUTER_METRICS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS router_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    session_id TEXT NOT NULL,
    route TEXT NOT NULL,
    intent TEXT NOT NULL,
    confidence REAL NOT NULL,
    latency_ms REAL,
    outcome TEXT NOT NULL,
    text_length INTEGER,
    abstain_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

ROUTER_EPISODES_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS router_episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    text TEXT NOT NULL,
    original_route TEXT,
    confidence REAL,
    intent TEXT,
    is_abstain BOOLEAN DEFAULT FALSE,
    abstain_reason TEXT,
    is_override BOOLEAN DEFAULT FALSE,
    override_route TEXT,
    override_confidence REAL,
    label_source TEXT DEFAULT 'router',
    text_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

INDEX_SCHEMAS = [
    "CREATE INDEX IF NOT EXISTS idx_session_id ON episodes(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_helper_id ON episodes(helper_id)",
    "CREATE INDEX IF NOT EXISTS idx_action ON episodes(action)",
    "CREATE INDEX IF NOT EXISTS idx_timestamp ON episodes(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_router_timestamp ON router_metrics(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_router_route ON router_metrics(route)",
    "CREATE INDEX IF NOT EXISTS idx_router_confidence ON router_metrics(confidence)",
    "CREATE INDEX IF NOT EXISTS idx_router_session ON router_metrics(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_router_episodes_timestamp ON router_episodes(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_router_episodes_session ON router_episodes(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_router_episodes_abstain ON router_episodes(is_abstain)",
    "CREATE INDEX IF NOT EXISTS idx_router_episodes_override ON router_episodes(is_override)",
    "CREATE INDEX IF NOT EXISTS idx_router_episodes_hash ON router_episodes(text_hash)",
    "CREATE INDEX IF NOT EXISTS idx_router_episodes_label_source ON router_episodes(label_source)"
]
