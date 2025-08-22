"""
TinyIntent Utility Functions

Common utility functions used across the platform.
"""

import asyncio
import functools
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar, Union

import structlog

logger = structlog.get_logger()

T = TypeVar('T')


def hash_data(data: Union[str, Dict[str, Any]], algorithm: str = 'sha256') -> str:
    """Create a consistent hash of data."""
    if isinstance(data, dict):
        data_str = json.dumps(data, sort_keys=True)
    else:
        data_str = str(data)
    
    hasher = hashlib.new(algorithm)
    hasher.update(data_str.encode('utf-8'))
    return hasher.hexdigest()


def ensure_path(path: Union[str, Path], create_parents: bool = True) -> Path:
    """Ensure a path exists and return as Path object."""
    path_obj = Path(path)
    if create_parents:
        path_obj.parent.mkdir(parents=True, exist_ok=True)
    return path_obj


def safe_json_loads(data: str, default: Any = None) -> Any:
    """Safely load JSON data with fallback."""
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("Failed to parse JSON", error=str(e), data_preview=data[:100])
        return default


def safe_json_dumps(data: Any, default: str = "{}") -> str:
    """Safely dump JSON data with fallback."""
    try:
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    except (TypeError, ValueError) as e:
        logger.warning("Failed to serialize JSON", error=str(e), data_type=type(data).__name__)
        return default


def retry_with_backoff(
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """Decorator for retrying functions with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Function failed, retrying",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        wait_time=wait_time,
                        error=str(e)
                    )
                    time.sleep(wait_time)
            
            # This should never be reached, but satisfies type checker
            raise RuntimeError("Retry logic failed unexpectedly")
        
        return wrapper
    return decorator


async def async_retry_with_backoff(
    max_attempts: int = 3,
    backoff_factor: float = 1.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """Async decorator for retrying functions with exponential backoff."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    
                    wait_time = backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Async function failed, retrying",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                        wait_time=wait_time,
                        error=str(e)
                    )
                    await asyncio.sleep(wait_time)
            
            # This should never be reached, but satisfies type checker
            raise RuntimeError("Async retry logic failed unexpectedly")
        
        return wrapper
    return decorator


def measure_time(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to measure function execution time."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> T:
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(
                "Function executed",
                function=func.__name__,
                execution_time_ms=round(execution_time * 1000, 2)
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "Function failed",
                function=func.__name__,
                execution_time_ms=round(execution_time * 1000, 2),
                error=str(e)
            )
            raise
    
    return wrapper


async def async_measure_time(func: Callable[..., T]) -> Callable[..., T]:
    """Async decorator to measure function execution time."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(
                "Async function executed",
                function=func.__name__,
                execution_time_ms=round(execution_time * 1000, 2)
            )
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                "Async function failed",
                function=func.__name__,
                execution_time_ms=round(execution_time * 1000, 2),
                error=str(e)
            )
            raise
    
    return wrapper


def validate_file_size(file_path: Path, max_size_mb: float) -> bool:
    """Check if file size is within limits."""
    if not file_path.exists():
        return True
    
    file_size_mb = file_path.stat().st_size / (1024 * 1024)
    return file_size_mb <= max_size_mb


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string to maximum length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def format_bytes(bytes_count: int) -> str:
    """Format bytes in human-readable format."""
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(bytes_count)
    
    for unit in units:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    
    return f"{size:.1f} PB"


def get_file_hash(file_path: Path, algorithm: str = 'sha256') -> Optional[str]:
    """Calculate hash of a file."""
    if not file_path.exists():
        return None
    
    try:
        hasher = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logger.error("Failed to calculate file hash", file=str(file_path), error=str(e))
        return None