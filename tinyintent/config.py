"""
TinyIntent Configuration Management

Centralized configuration handling using Pydantic Settings for type safety
and validation. Supports environment variables, .env files, and defaults.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any

from pydantic import Field, validator
from pydantic_settings import BaseSettings


class SecuritySettings(BaseSettings):
    """Security-related configuration."""
    
    secret: str = Field(..., description="Main authentication secret")
    allow_dev_local: bool = Field(False, description="Allow localhost without auth in dev")
    rate_limit_session: int = Field(60, description="Requests per minute per session")
    rate_limit_global: int = Field(500, description="Global requests per minute")
    rate_limit_window: int = Field(60, description="Rate limit window in seconds")
    execution_enabled: bool = Field(False, description="Enable helper execution")
    
    @validator('secret')
    def validate_secret_strength(cls, v: str) -> str:
        if not v:
            raise ValueError('Secret is required')
        
        # Import here to avoid circular imports
        try:
            from bridge.secret_validator import enforce_secret_requirements
            return enforce_secret_requirements(v, "TinyIntent API")
        except ImportError:
            # Fallback validation if secret_validator not available
            if len(v) < 32:
                raise ValueError('Secret must be at least 32 characters for production use')
            
            # Basic weak pattern detection
            weak_patterns = ['password', 'secret', 'test', 'demo', 'default', 'change', '123']
            if any(pattern in v.lower() for pattern in weak_patterns):
                raise ValueError('Secret contains weak patterns and is not suitable for production')
            
            return v
    
    class Config:
        env_prefix = "TINYINTENT_"
        case_sensitive = False


class ServerSettings(BaseSettings):
    """Server configuration."""
    
    bind: str = Field("127.0.0.1", description="Server bind address")
    port: int = Field(8787, description="Server port")
    log_level: str = Field("info", description="Log level")
    workers: int = Field(1, description="Number of worker processes")
    reload: bool = Field(False, description="Enable auto-reload in development")
    
    @validator('port')
    def valid_port(cls, v: int) -> int:
        if not 1024 <= v <= 65535:
            raise ValueError('Port must be between 1024 and 65535')
        return v
    
    @validator('log_level')
    def valid_log_level(cls, v: str) -> str:
        valid_levels = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.lower()
    
    class Config:
        env_prefix = "TINYINTENT_"
        case_sensitive = False


class HelperSettings(BaseSettings):
    """Helper framework configuration."""
    
    rate_limit: int = Field(10, description="Helper executions per minute")
    rate_limit_window: int = Field(60, description="Rate limit window in seconds")
    default_timeout: int = Field(30, description="Default helper timeout in seconds")
    max_memory_mb: int = Field(256, description="Default max memory per helper in MB")
    max_cpu_time: int = Field(10, description="Default max CPU time per helper in seconds")
    max_output_size: int = Field(1048576, description="Default max output size in bytes")
    
    @validator('rate_limit', 'rate_limit_window', 'default_timeout', 'max_memory_mb', 'max_cpu_time')
    def positive_values(cls, v: int) -> int:
        if v <= 0:
            raise ValueError('Value must be positive')
        return v
    
    class Config:
        env_prefix = "HELPER_"
        case_sensitive = False


class DatabaseSettings(BaseSettings):
    """Database configuration."""
    
    episodes_dir: Path = Field(Path("data/episodes"), description="Episodes data directory")
    backup_dir: Path = Field(Path("backups"), description="Backup directory")
    max_episodes_file_size: int = Field(104857600, description="Max episodes file size (100MB)")
    
    class Config:
        env_prefix = "DB_"
        case_sensitive = False


class LoggingSettings(BaseSettings):
    """Logging configuration."""
    
    audit_max_size_mb: int = Field(50, description="Max audit log size in MB")
    audit_retention_days: int = Field(90, description="Audit log retention in days")
    structured_logging: bool = Field(True, description="Enable structured logging")
    
    class Config:
        env_prefix = "LOG_"
        case_sensitive = False


class ModelSettings(BaseSettings):
    """Model configuration."""
    
    ollama_url: str = Field("http://localhost:11434", description="Ollama server URL")
    default_model: str = Field("llama2", description="Default LLM model")
    router_model_path: Optional[Path] = Field(None, description="Path to router model")
    
    class Config:
        env_prefix = "MODEL_"
        case_sensitive = False


class TinyIntentSettings(BaseSettings):
    """Main TinyIntent configuration."""
    
    # Environment
    environment: str = Field("development", description="Environment (development/production)")
    debug: bool = Field(False, description="Enable debug mode")
    
    # Project paths
    project_root: Path = Field(Path.cwd(), description="Project root directory")
    
    # Sub-configurations
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    server: ServerSettings = Field(default_factory=ServerSettings)
    helpers: HelperSettings = Field(default_factory=HelperSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    
    @validator('environment')
    def valid_environment(cls, v: str) -> str:
        valid_envs = {"development", "staging", "production"}
        if v.lower() not in valid_envs:
            raise ValueError(f'Environment must be one of: {valid_envs}')
        return v.lower()
    
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == "production"
    
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.environment == "development"
    
    class Config:
        env_prefix = ""
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


def load_settings() -> TinyIntentSettings:
    """Load and validate TinyIntent settings."""
    return TinyIntentSettings()


# Global settings instance
settings = load_settings()