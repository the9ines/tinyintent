"""
TinyIntent Test Configuration

Shared pytest fixtures and configuration for all tests.
"""

import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

# Set test environment before importing app components
os.environ.setdefault("TINYINTENT_SECRET", "test-secret-key-for-testing-only")
os.environ.setdefault("TINYINTENT_ENVIRONMENT", "development")
os.environ.setdefault("TINYINTENT_BIND", "127.0.0.1")
os.environ.setdefault("TINYINTENT_PORT", "8788")
os.environ.setdefault("ALLOW_DEV_LOCAL", "1")

from tinyintent.bridge.tinyrpc import create_app
from tinyintent.config import settings


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def test_db(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test SQLite database."""
    db_path = temp_dir / "test.db"
    
    # Create test database schema
    with sqlite3.connect(db_path) as conn:
        conn.execute('''
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
        ''')
        conn.commit()
    
    yield db_path


@pytest.fixture
def test_audit_log(temp_dir: Path) -> Generator[Path, None, None]:
    """Create a test audit log file."""
    audit_log = temp_dir / "audit.log"
    audit_log.touch()
    yield audit_log


@pytest.fixture
def mock_settings(temp_dir: Path, monkeypatch):
    """Mock settings for testing."""
    # Override specific settings for testing
    monkeypatch.setattr(settings.security, "secret", "test-secret-key")
    monkeypatch.setattr(settings.security, "allow_dev_local", True)
    monkeypatch.setattr(settings.database, "episodes_dir", temp_dir / "episodes")
    monkeypatch.setattr(settings.project_root, temp_dir)
    
    # Ensure directories exist
    (temp_dir / "episodes").mkdir(exist_ok=True)
    (temp_dir / "bridge" / "logs").mkdir(parents=True, exist_ok=True)
    
    return settings


@pytest_asyncio.fixture
async def app() -> AsyncGenerator[TestClient, None]:
    """Create a test FastAPI application."""
    test_app = create_app()
    
    async with test_app.router.lifespan_context(test_app):
        with TestClient(test_app) as client:
            yield client


@pytest.fixture
def auth_headers() -> dict:
    """Authentication headers for test requests."""
    return {"X-TinyIntent-Secret": "test-secret-key-for-testing-only"}


@pytest.fixture
def sample_helper_manifest() -> dict:
    """Sample helper manifest for testing."""
    return {
        "helper_id": "test_helper",
        "version": "1.0.0",
        "description": "Test helper for unit tests",
        "author": "TinyIntent Test Suite",
        "environment": {
            "required": [],
            "optional": ["TEST_VAR"]
        },
        "sandbox": {
            "commands": ["echo", '{"status": "success", "message": "test"}'],
            "cpu": {"max_ms": 5000},
            "mem": {"max_mb": 128},
            "timeout": {"preview": 10, "execute": 15}
        },
        "capabilities": ["network", "filesystem"],
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string"}
            },
            "required": ["message"]
        },
        "output_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "message": {"type": "string"}
            },
            "required": ["status"]
        }
    }


@pytest.fixture
def sample_route_request() -> dict:
    """Sample route request for testing."""
    return {
        "text": "Hello, world!",
        "route": "gen",
        "session_id": "test-session-123"
    }


@pytest.fixture
def sample_audit_entry() -> dict:
    """Sample audit log entry for testing."""
    return {
        "action": "test_action",
        "session_id": "test-session",
        "success": True,
        "timestamp": "2025-08-20T12:00:00.000000Z"
    }


class MockOllamaClient:
    """Mock Ollama client for testing."""
    
    def __init__(self):
        self.is_healthy = True
        self.response_text = "Mock response from Ollama"
        self.response_latency = 100
    
    async def health_check(self):
        """Mock health check."""
        if not self.is_healthy:
            raise ConnectionError("Mock Ollama server unavailable")
        return {"status": "ok"}
    
    async def generate_async(self, model: str, prompt: str, session_id: str = None):
        """Mock text generation."""
        if not self.is_healthy:
            raise ConnectionError("Mock Ollama server unavailable")
        return self.response_text, self.response_latency
    
    async def close(self):
        """Mock client cleanup."""
        pass


@pytest.fixture
def mock_ollama_client(monkeypatch):
    """Mock Ollama client for testing."""
    client = MockOllamaClient()
    
    # Patch the actual client import
    monkeypatch.setattr("tinyintent.bridge.gen_client.async_ollama_client", client)
    
    return client


# Test markers
pytest_plugins = ["pytest_asyncio"]

# Configure asyncio for testing
@pytest.fixture(autouse=True)
def configure_asyncio():
    """Configure asyncio for testing."""
    # Ensure we have a fresh event loop for each test
    asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


# Async test utilities
@pytest_asyncio.fixture
async def async_client(app: TestClient) -> AsyncGenerator[TestClient, None]:
    """Async test client."""
    yield app