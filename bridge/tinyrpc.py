"""
TinyIntent Bridge Service

Main entrypoint for the FastAPI application. Initializes all subsystems and
includes the API routes.
"""

import os
import uvicorn
from fastapi import FastAPI
from pathlib import Path

from tinyintent.bridge.api_routes import router_api
from tinyintent.bridge.gen_client import async_ollama_client
from tinyintent.bridge.logs.audit import initialize_audit_logger

def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    if key not in os.environ:
                        os.environ[key] = value.strip('"').strip("'")

# Load .env file on module import
load_env_file()

# Initialize FastAPI app
app = FastAPI(title="TinyIntent Bridge", version="2.0.0")

# Initialize audit log
audit_log_path = Path(__file__).parent / "logs" / "audit.log"
audit_logger = initialize_audit_logger(audit_log_path, max_size_mb=50)

# Include API routes
app.include_router(router_api)

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up async resources on shutdown."""
    await async_ollama_client.close()

if __name__ == "__main__":
    bind_addr = os.getenv("TINYINTENT_BIND", "0.0.0.0")
    port = int(os.getenv("TINYINTENT_PORT", "8787"))
    
    if not os.getenv("TINYINTENT_SECRET"):
        print("ERROR: TINYINTENT_SECRET environment variable is required")
        exit(1)
    
    uvicorn.run(
        "tinyrpc:app",
        host=bind_addr,
        port=port,
        reload=False,
        log_level="info"
    )
