"""
TinyIntent Bridge Routes Package

Modular route organization for better maintainability.
"""

from .health import router as health_router
from .helpers import router as helpers_router  
from .agents import router as agents_router
from .shortcut import router as shortcut_router
from .system import router as system_router
from .router import router as router_router

__all__ = [
    'health_router',
    'helpers_router', 
    'agents_router',
    'shortcut_router',
    'system_router',
    'router_router'
]